#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} <mpv-source-dir>")

root = Path(sys.argv[1])


def replace_once(rel, old, new, label):
    path = root / rel
    data = path.read_text()
    count = data.count(old)
    if count != 1:
        raise SystemExit(f"{rel}: expected one {label} anchor, found {count}")
    path.write_text(data.replace(old, new, 1))


def write(rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# The queue can retain frames across a format/resolution transition. Size the
# NV15 unpack targets from the frame being acquired rather than the engine's
# mutable current_params state.
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
    "geometry declaration",
)
replace_once(
    "video/out/gpu_next/video.c",
    """            .w = n ? p->current_params.w / 2 : p->current_params.w,
            .h = n ? p->current_params.h / 2 : p->current_params.h,
""",
    """            .w = n ? mpi->params.w / 2 : mpi->params.w,
            .h = n ? mpi->params.h / 2 : mpi->params.h,
""",
    "geometry dimensions",
)

# orp6: libplacebo's OpenGL backend does not expose PL_HANDLE_DMA_BUF import.
# Use mpv's normal EGL/OpenGL RA for hardware surfaces, exactly like modern
# vo_gpu_next: import the DRM PRIME surface with dmabuf_interop_gl, then wrap
# the resulting GL texture into the libplacebo GPU with pl_opengl_wrap().
replace_once(
    "video/out/gpu_next/libmpv_gpu_next.h",
    """#include \"mpv/render.h\"      // for mpv_render_param

""",
    """#include \"mpv/render.h\"      // for mpv_render_param

struct ra;

""",
    "legacy RA forward declaration",
)
replace_once(
    "video/out/gpu_next/libmpv_gpu_next.h",
    """    struct ra_next *ra;
    // The underlying GPU object, needed by the Host for resource management.
""",
    """    struct ra_next *ra;
    // Legacy mpv OpenGL RA sharing the client's current context. Hardware
    // decoders use this for EGL DMA-BUF import before wrapping textures into
    // the libplacebo gpu-next context.
    struct ra *hwdec_ra;
    // The underlying GPU object, needed by the Host for resource management.
""",
    "hwdec RA field",
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
    "OpenGL hwdec state",
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

    // libplacebo OpenGL deliberately has no DMA-BUF texture import path. Build
    // mpv's legacy OpenGL RA on the exact same client GL context so Rockchip's
    // proven EGL dmabuf interop can import DRM PRIME/NV15 surfaces. The mapped
    // GL textures are wrapped back into p->gpu by hwdec_compat.c.
    p->legacy_gl = talloc_zero(p, GL);
    mpgl_load_functions2(p->legacy_gl,
        gl_params->get_proc_address, gl_params->get_proc_address_ctx,
        NULL, ctx->log);
    p->hwdec_ra = ra_create_gl(p->legacy_gl, ctx->log);
    if (!p->hwdec_ra) {
        MP_ERR(ctx, \"Failed to create legacy OpenGL RA for EGL DMA-BUF hwdec.\\n\");
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
    MP_INFO(ctx, \"orp6: legacy OpenGL hwdec RA enabled for EGL DMA-BUF import\\n\");
    return 0;
""",
    "legacy OpenGL RA initialization",
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
    "legacy OpenGL RA teardown",
)

replace_once(
    "video/out/gpu_next/libmpv_gpu_next.c",
    """    p->video_engine = pl_video_init(ctx->global, ctx->log, p->context->ra,
                                    ctx->hwdec_devs);
""",
    """    p->video_engine = pl_video_init(ctx->global, ctx->log, p->context->ra,
                                    p->context->hwdec_ra, ctx->hwdec_devs);
""",
    "video engine hwdec RA wiring",
)

replace_once(
    "video/out/gpu_next/video.h",
    """struct ra_next;
""",
    """struct ra;
struct ra_next;
""",
    "video header legacy RA declaration",
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
    "video init hwdec RA signature",
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
    "video init hwdec RA signature",
)
replace_once(
    "video/out/gpu_next/video.c",
    """    p->hwdec_bridge = orp5_hwdec_bridge_create(global, log, ra->gpu, hwdec_devs);
""",
    """    p->hwdec_bridge = orp5_hwdec_bridge_create(
        global, log, ra->gpu, hwdec_ra, hwdec_devs);
""",
    "hwdec bridge legacy RA wiring",
)

# The lifetime patch generated these compatibility files. Replace them as a
# whole so there is only one source of truth for mapper lifetime + GL wrapping.
write("video/out/gpu_next/hwdec_compat.h", r'''#pragma once

#include <stdbool.h>
#include <libplacebo/gpu.h>
#include "video/mp_image.h"

struct mp_hwdec_devices;
struct mp_log;
struct mpv_global;
struct ra;
struct orp5_hwdec_bridge;
struct orp5_hwdec_frame;

struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct ra *hwdec_ra, struct mp_hwdec_devices *devs);
void orp5_hwdec_bridge_destroy(struct orp5_hwdec_bridge **bridge);

struct orp5_hwdec_frame *orp5_hwdec_frame_create(
    struct orp5_hwdec_bridge *bridge, const struct mp_image_params *src,
    struct mp_image_params *dst, bool *is_nv15);
void orp5_hwdec_frame_destroy(struct orp5_hwdec_frame **frame);
int orp5_hwdec_frame_map(struct orp5_hwdec_frame *frame,
                         struct mp_image *img);
void orp5_hwdec_frame_unmap(struct orp5_hwdec_frame *frame);
pl_tex orp5_hwdec_frame_tex(struct orp5_hwdec_frame *frame, int plane);
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
};

struct orp5_hwdec_frame {
    struct orp5_hwdec_bridge *bridge;
    struct ra_hwdec_mapper *mapper;
    pl_tex wrapped[4];
};

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
        MP_ERR(b, "orp6: OpenGL hwdec RA/libplacebo GPU mismatch\n");
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
    MP_INFO(b, "orp5: per-frame hwdec mapper lifetime enabled\n");
    MP_INFO(b, "orp6: EGL/OpenGL DMA-BUF hwdec interop enabled\n");
    return b;
}

void orp5_hwdec_bridge_destroy(struct orp5_hwdec_bridge **bridge)
{
    struct orp5_hwdec_bridge *b = bridge ? *bridge : NULL;
    if (!b)
        return;

    hwdec_devices_set_loader(b->devs, NULL, NULL);
    ra_hwdec_ctx_uninit(&b->hwdec_ctx);
    // b->ra is owned by the gpu-next OpenGL context and outlives this bridge.
    b->ra = NULL;
    talloc_free(b);
    *bridge = NULL;
}

struct orp5_hwdec_frame *orp5_hwdec_frame_create(
    struct orp5_hwdec_bridge *b, const struct mp_image_params *src,
    struct mp_image_params *dst, bool *is_nv15)
{
    struct ra_hwdec *hwdec = ra_hwdec_get(&b->hwdec_ctx, src->imgfmt);
    if (!hwdec)
        return NULL;

    struct orp5_hwdec_frame *f = talloc_zero(NULL, struct orp5_hwdec_frame);
    f->bridge = b;
    f->mapper = ra_hwdec_mapper_create(hwdec, src);
    if (!f->mapper) {
        MP_ERR(b, "orp5: initializing per-frame hwdec mapper failed\n");
        talloc_free(f);
        return NULL;
    }

    *dst = f->mapper->dst_params;
    if (is_nv15) {
        const char *subfmt = mp_imgfmt_to_name(src->hw_subfmt);
        *is_nv15 = subfmt && strcmp(subfmt, "yuv420p10") == 0 &&
                   f->mapper->dst_params.imgfmt == IMGFMT_P010;
    }
    return f;
}

static void destroy_wrapped_textures(struct orp5_hwdec_frame *f)
{
    if (!f || !f->bridge)
        return;
    for (int n = 0; n < 4; n++)
        pl_tex_destroy(f->bridge->gpu, &f->wrapped[n]);
}

void orp5_hwdec_frame_destroy(struct orp5_hwdec_frame **frame)
{
    struct orp5_hwdec_frame *f = frame ? *frame : NULL;
    if (!f)
        return;
    // pl_opengl_wrap() wrappers must disappear before the underlying EGLImage
    // / GL texture objects owned by the mapper are torn down.
    destroy_wrapped_textures(f);
    ra_hwdec_mapper_free(&f->mapper);
    talloc_free(f);
    *frame = NULL;
}

int orp5_hwdec_frame_map(struct orp5_hwdec_frame *f, struct mp_image *img)
{
    return f && f->mapper ? ra_hwdec_mapper_map(f->mapper, img) : -1;
}

void orp5_hwdec_frame_unmap(struct orp5_hwdec_frame *f)
{
    if (!f || !f->mapper)
        return;
    destroy_wrapped_textures(f);
    ra_hwdec_mapper_unmap(f->mapper);
}

pl_tex orp5_hwdec_frame_tex(struct orp5_hwdec_frame *f, int plane)
{
    if (!f || !f->mapper || plane < 0 || plane >= 4 ||
        !f->mapper->tex[plane])
        return NULL;
    if (f->wrapped[plane])
        return f->wrapped[plane];

    struct ra_tex *ratex = f->mapper->tex[plane];
    struct ra *ra = f->mapper->ra;
    if (!ra_is_gl(ra) || !pl_opengl_get(f->bridge->gpu))
        return NULL;

    // Same conversion used by modern mpv vo_gpu_next: the hwdec mapper owns
    // the EGL-imported GL texture, while libplacebo owns only this wrapper.
    struct pl_opengl_wrap_params par = {
        .width = ratex->params.w,
        .height = ratex->params.h,
    };
    ra_gl_get_format(ratex->params.format, &par.iformat,
                     &(GLenum){0}, &(GLenum){0});
    ra_gl_get_raw_tex(ra, ratex, &par.texture, &par.target);
    f->wrapped[plane] = pl_opengl_wrap(f->bridge->gpu, &par);
    if (!f->wrapped[plane])
        MP_ERR(f->bridge, "orp6: failed wrapping EGL-imported hwdec texture %d\n",
               plane);
    return f->wrapped[plane];
}
''')

print("orp6: routed gpu-next hwdec through legacy EGL/OpenGL DMA-BUF interop")
