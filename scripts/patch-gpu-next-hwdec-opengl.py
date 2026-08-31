#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} <mpv-source-dir>")

root = Path(sys.argv[1])


def replace_once(rel, old, new):
    path = root / rel
    data = path.read_text()
    if data.count(old) != 1:
        raise SystemExit(f"{rel}: patch anchor not found exactly once")
    path.write_text(data.replace(old, new, 1))


def write(rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# Use the frame being acquired for NV15 unpack dimensions.
replace_once(
    "video/out/gpu_next/video.c",
    """static bool hwdec_unpack_nv15(struct pl_video *p, struct frame_priv *fp,
                              struct pl_frame *frame)
{
    pl_fmt formats[2] = {pl_find_named_fmt(p->ra->gpu, \"r16\"),
""",
    """static bool hwdec_unpack_nv15(struct pl_video *p, struct frame_priv *fp,
                              struct pl_frame *frame)
{
    struct mp_image *mpi = frame->user_data;
    pl_fmt formats[2] = {pl_find_named_fmt(p->ra->gpu, \"r16\"),
""",
)
replace_once(
    "video/out/gpu_next/video.c",
    """            .w = n ? p->current_params.w / 2 : p->current_params.w,
            .h = n ? p->current_params.h / 2 : p->current_params.h,
""",
    """            .w = n ? mpi->params.w / 2 : mpi->params.w,
            .h = n ? mpi->params.h / 2 : mpi->params.h,
""",
)

# Build mpv's legacy OpenGL RA on Stremio's current GL context. Rockchip's
# DRM-PRIME importer uses that RA, while gpu-next continues rendering through
# libplacebo on the same context.
replace_once(
    "video/out/gpu_next/libmpv_gpu_next.h",
    """#include \"mpv/render.h\"      // for mpv_render_param

""",
    """#include \"mpv/render.h\"      // for mpv_render_param

struct ra;

""",
)
replace_once(
    "video/out/gpu_next/libmpv_gpu_next.h",
    """    struct ra_next *ra;
    // The underlying GPU object, needed by the Host for resource management.
""",
    """    struct ra_next *ra;
    struct ra *hwdec_ra;
    // The underlying GPU object, needed by the Host for resource management.
""",
)
replace_once(
    "video/out/gpu_next/context.c",
    """    pl_gpu gpu;
    struct ra_next *ra;

    // Store a persistent copy of the init params to avoid a dangling pointer.
""",
    """    pl_gpu gpu;
    struct ra_next *ra;
    GL *legacy_gl;
    struct ra *hwdec_ra;

    // Store a persistent copy of the init params to avoid a dangling pointer.
""",
)
replace_once(
    "video/out/gpu_next/context.c",
    """    p->ra = ra_pl_create(p->gpu, ctx->log, p->pl_log);
    if (!p->ra) {
        pl_opengl_destroy(&p->gl);
        pl_log_destroy(&p->pl_log);
        return MPV_ERROR_VO_INIT_FAILED;
    }

    ctx->ra = p->ra;
    ctx->gpu = p->gpu;
    return 0;
""",
    """    p->ra = ra_pl_create(p->gpu, ctx->log, p->pl_log);
    if (!p->ra) {
        pl_opengl_destroy(&p->gl);
        pl_log_destroy(&p->pl_log);
        return MPV_ERROR_VO_INIT_FAILED;
    }

    p->legacy_gl = talloc_zero(p, GL);
    mpgl_load_functions2(p->legacy_gl,
        gl_params->get_proc_address, gl_params->get_proc_address_ctx,
        NULL, ctx->log);
    p->hwdec_ra = ra_create_gl(p->legacy_gl, ctx->log);
    if (!p->hwdec_ra) {
        talloc_free(p->legacy_gl);
        p->legacy_gl = NULL;
        ra_pl_destroy(&p->ra);
        pl_opengl_destroy(&p->gl);
        pl_log_destroy(&p->pl_log);
        return MPV_ERROR_VO_INIT_FAILED;
    }

    ctx->ra = p->ra;
    ctx->hwdec_ra = p->hwdec_ra;
    ctx->gpu = p->gpu;
    return 0;
""",
)
replace_once(
    "video/out/gpu_next/context.c",
    """    if (p->ra) {
        ra_pl_destroy(&p->ra);
    }

    pl_opengl_destroy(&p->gl);
    pl_log_destroy(&p->pl_log);
}
""",
    """    if (p->hwdec_ra)
        ra_free(&p->hwdec_ra);
    talloc_free(p->legacy_gl);
    p->legacy_gl = NULL;
    ctx->hwdec_ra = NULL;

    if (p->ra)
        ra_pl_destroy(&p->ra);

    pl_opengl_destroy(&p->gl);
    pl_log_destroy(&p->pl_log);
    talloc_free(p);
    ctx->priv = NULL;
}
""",
)
replace_once(
    "video/out/gpu_next/libmpv_gpu_next.c",
    """    p->video_engine = pl_video_init(ctx->global, ctx->log, p->context->ra,
                                    ctx->hwdec_devs);
""",
    """    p->video_engine = pl_video_init(ctx->global, ctx->log, p->context->ra,
                                    p->context->hwdec_ra, ctx->hwdec_devs);
""",
)
replace_once(
    "video/out/gpu_next/video.h",
    """struct ra_next;
""",
    """struct ra;
struct ra_next;
""",
)
replace_once(
    "video/out/gpu_next/video.h",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra,
                               struct mp_hwdec_devices *hwdec_devs);
""",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra, struct ra *hwdec_ra,
                               struct mp_hwdec_devices *hwdec_devs);
""",
)
replace_once(
    "video/out/gpu_next/video.c",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra,
                               struct mp_hwdec_devices *hwdec_devs) {
""",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra, struct ra *hwdec_ra,
                               struct mp_hwdec_devices *hwdec_devs) {
""",
)
replace_once(
    "video/out/gpu_next/video.c",
    """    p->hwdec_bridge = orp5_hwdec_bridge_create(global, log, ra->gpu, hwdec_devs);
""",
    """    p->hwdec_bridge = orp5_hwdec_bridge_create(
        global, log, ra->gpu, hwdec_ra, hwdec_devs);
""",
)

write("video/out/gpu_next/hwdec_compat.h", r'''#pragma once

#include <stdbool.h>
#include <libplacebo/gpu.h>
#include "video/mp_image.h"

struct mp_hwdec_devices;
struct mp_log;
struct mpv_global;
struct ra;
struct orp5_hwdec_bridge;

struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct ra *hwdec_ra, struct mp_hwdec_devices *devs);
void orp5_hwdec_bridge_destroy(struct orp5_hwdec_bridge **bridge);

bool orp5_hwdec_bridge_prepare(struct orp5_hwdec_bridge *bridge,
                               const struct mp_image_params *src,
                               struct mp_image_params *dst,
                               bool *is_nv15);
int orp5_hwdec_bridge_map(struct orp5_hwdec_bridge *bridge,
                          struct mp_image *img);
void orp5_hwdec_bridge_unmap(struct orp5_hwdec_bridge *bridge);
pl_tex orp5_hwdec_bridge_tex(struct orp5_hwdec_bridge *bridge, int plane);
''')

write("video/out/gpu_next/hwdec_compat.c", r'''#include "hwdec_compat.h"

#include <string.h>
#include <libplacebo/opengl.h>

#include "common/msg.h"
#include "ta/ta_talloc.h"
#include "video/hwdec.h"
#include "video/img_format.h"
#include "video/out/gpu/context.h"
#include "video/out/gpu/hwdec.h"
#include "video/out/gpu/ra.h"
#include "video/out/opengl/ra_gl.h"

struct orp5_hwdec_bridge {
    struct mp_log *log;
    struct mp_hwdec_devices *devs;
    pl_gpu gpu;
    struct ra *ra;
    struct ra_ctx ra_ctx;
    struct ra_hwdec_ctx hwdec_ctx;
    struct ra_hwdec *active_hwdec;
    struct ra_hwdec_mapper *mapper;
    pl_tex wrapped[4];
    bool nv15;
};

static void destroy_wrapped_textures(struct orp5_hwdec_bridge *b)
{
    for (int n = 0; n < 4; n++)
        pl_tex_destroy(b->gpu, &b->wrapped[n]);
}

static void load_hwdec_api(void *ctx, struct hwdec_imgfmt_request *params)
{
    struct orp5_hwdec_bridge *b = ctx;
    ra_hwdec_ctx_load_fmt(&b->hwdec_ctx, b->devs, params);
}

struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct ra *hwdec_ra, struct mp_hwdec_devices *devs)
{
    struct orp5_hwdec_bridge *b = talloc_zero(NULL, struct orp5_hwdec_bridge);
    b->log = log;
    b->devs = devs;
    b->gpu = gpu;
    b->ra = hwdec_ra;

    if (!b->gpu || !b->ra || !ra_is_gl(b->ra) || !pl_opengl_get(b->gpu)) {
        talloc_free(b);
        return NULL;
    }

    b->ra_ctx = (struct ra_ctx) {
        .ra = b->ra,
        .global = global,
        .log = log,
    };
    b->hwdec_ctx = (struct ra_hwdec_ctx) {
        .log = log,
        .global = global,
        .ra_ctx = &b->ra_ctx,
    };

    hwdec_devices_set_loader(devs, load_hwdec_api, b);
    ra_hwdec_ctx_init(&b->hwdec_ctx, devs, "auto", false);
    MP_INFO(b, "orp5: libmpv gpu-next hwdec bridge enabled\n");
    return b;
}

void orp5_hwdec_bridge_destroy(struct orp5_hwdec_bridge **bridge)
{
    struct orp5_hwdec_bridge *b = bridge ? *bridge : NULL;
    if (!b)
        return;

    hwdec_devices_set_loader(b->devs, NULL, NULL);
    destroy_wrapped_textures(b);
    ra_hwdec_mapper_free(&b->mapper);
    ra_hwdec_ctx_uninit(&b->hwdec_ctx);
    talloc_free(b);
    *bridge = NULL;
}

bool orp5_hwdec_bridge_prepare(struct orp5_hwdec_bridge *b,
                               const struct mp_image_params *src,
                               struct mp_image_params *dst,
                               bool *is_nv15)
{
    struct ra_hwdec *hwdec = ra_hwdec_get(&b->hwdec_ctx, src->imgfmt);
    if (!hwdec)
        return false;

    if (b->mapper && b->active_hwdec == hwdec &&
        mp_image_params_static_equal(src, &b->mapper->src_params))
    {
        b->mapper->src_params.repr.dovi = src->repr.dovi;
        b->mapper->dst_params.repr.dovi = src->repr.dovi;
        b->mapper->src_params.color.hdr = src->color.hdr;
        b->mapper->dst_params.color.hdr = src->color.hdr;
    } else {
        destroy_wrapped_textures(b);
        ra_hwdec_mapper_free(&b->mapper);
        b->mapper = ra_hwdec_mapper_create(hwdec, src);
        if (!b->mapper) {
            b->active_hwdec = NULL;
            return false;
        }
        b->active_hwdec = hwdec;
    }

    *dst = b->mapper->dst_params;
    const char *subfmt = mp_imgfmt_to_name(src->hw_subfmt);
    b->nv15 = subfmt && strcmp(subfmt, "yuv420p10") == 0 &&
              b->mapper->dst_params.imgfmt == IMGFMT_P010;
    if (is_nv15)
        *is_nv15 = b->nv15;
    return true;
}

int orp5_hwdec_bridge_map(struct orp5_hwdec_bridge *b, struct mp_image *img)
{
    if (!b->mapper)
        return -1;
    if (!b->nv15)
        destroy_wrapped_textures(b);
    return ra_hwdec_mapper_map(b->mapper, img);
}

void orp5_hwdec_bridge_unmap(struct orp5_hwdec_bridge *b)
{
    if (!b->mapper)
        return;
    if (!b->nv15)
        destroy_wrapped_textures(b);
    ra_hwdec_mapper_unmap(b->mapper);
}

pl_tex orp5_hwdec_bridge_tex(struct orp5_hwdec_bridge *b, int plane)
{
    if (!b->mapper || plane < 0 || plane >= 4 || !b->mapper->tex[plane])
        return NULL;
    if (b->wrapped[plane])
        return b->wrapped[plane];

    struct ra_tex *ratex = b->mapper->tex[plane];
    struct pl_opengl_wrap_params par = {
        .width = ratex->params.w,
        .height = ratex->params.h,
    };
    ra_gl_get_format(ratex->params.format, &par.iformat,
                     &(GLenum){0}, &(GLenum){0});
    ra_gl_get_raw_tex(b->mapper->ra, ratex, &par.texture, &par.target);
    b->wrapped[plane] = pl_opengl_wrap(b->gpu, &par);
    return b->wrapped[plane];
}
''')

replace_once(
    "video/out/gpu_next/video.c",
    """    orp5_hwdec_bridge_destroy(&p->hwdec_bridge);
    for (int i = 0; i < ORP5_NV15_TEX_POOL_SIZE; i++) {
        for (int n = 0; n < 2; n++)
            pl_tex_destroy(p->ra->gpu, &p->nv15_pool[i].planes[n]);
    }
    pl_dispatch_destroy(&p->nv15_dispatch);
    ra_next_queue_destroy(&p->queue);
""",
    """    ra_next_queue_destroy(&p->queue);
    orp5_hwdec_bridge_destroy(&p->hwdec_bridge);
    for (int i = 0; i < ORP5_NV15_TEX_POOL_SIZE; i++) {
        for (int n = 0; n < 2; n++)
            pl_tex_destroy(p->ra->gpu, &p->nv15_pool[i].planes[n]);
    }
    pl_dispatch_destroy(&p->nv15_dispatch);
""",
)
