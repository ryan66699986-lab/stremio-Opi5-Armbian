#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} <mpv-source-dir>")

root = Path(sys.argv[1])


def replace_once(rel, old, new):
    path = root / rel
    data = path.read_text()
    count = data.count(old)
    if count != 1:
        raise SystemExit(f"{rel}: expected one patch anchor, found {count}")
    path.write_text(data.replace(old, new, 1))


def write(rel, content):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ---------------------------------------------------------------------------
# Build the libplacebo DMA-BUF interop for V4L2-request even though this
# private RK3588 stack intentionally has VAAPI disabled. Also compile the
# compatibility bridge in its own translation unit so legacy mpv RA symbols do
# not collide with the draft gpu-next RA API.
# ---------------------------------------------------------------------------
replace_once(
    "meson.build",
    """    'video/out/gpu_next/libmpv_gpu_next.c',
    'video/out/gpu_next/ra.c',
    'video/out/gpu_next/video.c',
""",
    """    'video/out/gpu_next/libmpv_gpu_next.c',
    'video/out/gpu_next/ra.c',
    'video/out/gpu_next/video.c',
    'video/out/gpu_next/hwdec_compat.c',
""",
)

replace_once(
    "meson.build",
    """if features['vaapi']
    dependencies += libva
    sources += files('video/filter/vf_vavpp.c',
                     'video/vaapi.c',
                     'video/out/hwdec/hwdec_vaapi.c',
                     'video/out/hwdec/dmabuf_interop_pl.c')
endif
""",
    """if features['vaapi']
    dependencies += libva
    sources += files('video/filter/vf_vavpp.c',
                     'video/vaapi.c',
                     'video/out/hwdec/hwdec_vaapi.c',
                     'video/out/hwdec/dmabuf_interop_pl.c')
endif

# orp5: the libplacebo DMA-BUF importer is also required by V4L2-request.
if features['drm'] and not features['vaapi']
    sources += files('video/out/hwdec/dmabuf_interop_pl.c')
endif
""",
)

# The drmprime hwdec driver normally exposes the libplacebo interop only when
# VAAPI was enabled. orp5 builds it independently for V4L2-request.
replace_once(
    "video/out/hwdec/hwdec_drmprime.c",
    """#if HAVE_VAAPI
    dmabuf_interop_pl_init,
#endif
""",
    """    dmabuf_interop_pl_init,
""",
)

# ---------------------------------------------------------------------------
# Teach the libplacebo DMA-BUF importer how to carry RK3588 NV15. NV15 is not
# ordinary P010: four 10-bit samples are packed into five bytes. Import the two
# packed planes as R8 byte streams; gpu-next will unpack them with a shader.
# ---------------------------------------------------------------------------
replace_once(
    "video/out/hwdec/dmabuf_interop_pl.c",
    """    struct dmabuf_interop_priv *p = mapper->priv;
    pl_gpu gpu = ra_pl_get(mapper->ra);

    struct ra_imgfmt_desc desc = {0};
""",
    """    struct dmabuf_interop_priv *p = mapper->priv;
    pl_gpu gpu = ra_pl_get(mapper->ra);

    if (p->external_nv15) {
        if (p->desc.nb_layers != 1 || p->desc.layers[0].nb_planes != 2)
            return false;

        pl_fmt r8 = pl_find_named_fmt(gpu, \"r8\");
        if (!r8)
            return false;

        for (int n = 0; n < 2; n++) {
            const AVDRMPlaneDescriptor *plane = &p->desc.layers[0].planes[n];
            const AVDRMObjectDescriptor *object =
                &p->desc.objects[plane->object_index];
            int fd = object->fd;
            size_t size = object->size;

            if (!size) {
                off_t end = lseek(fd, 0, SEEK_END);
                if (end < 0) {
                    MP_ERR(mapper, \"Cannot obtain NV15 object size for fd %d: %s\\n\",
                           fd, mp_strerror(errno));
                    return false;
                }
                size = end;
                if (lseek(fd, 0, SEEK_SET) < 0) {
                    MP_ERR(mapper, \"Failed to reset NV15 fd %d: %s\\n\",
                           fd, mp_strerror(errno));
                    return false;
                }
            }

            mppl_log_set_probing(gpu->log, probing);
            pl_tex pltex = pl_tex_create(gpu, pl_tex_params(
                .w = plane->pitch,
                .h = n ? mapper->src_params.h / 2 : mapper->src_params.h,
                .format = r8,
                .sampleable = true,
                .import_handle = PL_HANDLE_DMA_BUF,
                .shared_mem = {
                    .handle = {.fd = fd},
                    .size = size,
                    .offset = plane->offset,
                    .drm_format_mod = object->format_modifier,
                    .stride_w = plane->pitch,
                },
            ));
            mppl_log_set_probing(gpu->log, false);
            if (!pltex)
                return false;

            struct ra_tex *ratex = talloc_ptrtype(NULL, ratex);
            if (!mppl_wrap_tex(mapper->ra, pltex, ratex)) {
                pl_tex_destroy(gpu, &pltex);
                talloc_free(ratex);
                return false;
            }
            mapper->tex[n] = ratex;
            MP_VERBOSE(mapper,
                       \"Imported NV15 packed byte plane %d as R8 DMA-BUF\\n\", n);
        }
        return true;
    }

    struct ra_imgfmt_desc desc = {0};
""",
)

replace_once(
    "video/out/hwdec/dmabuf_interop_pl.c",
    """    MP_VERBOSE(hw, \"using libplacebo dmabuf interop\\n\");

    dmabuf_interop->interop_map = vaapi_pl_map;
""",
    """    MP_VERBOSE(hw, \"using libplacebo dmabuf interop\\n\");

    dmabuf_interop->supports_nv15_byte_planes = true;
    dmabuf_interop->interop_map = vaapi_pl_map;
""",
)

# ---------------------------------------------------------------------------
# Opaque legacy-hwdec adapter. This is deliberately separate from video.c:
# video/out/gpu/ra.h and video/out/gpu_next/ra.h both define RA names and are
# not source-compatible in one translation unit.
# ---------------------------------------------------------------------------
write("video/out/gpu_next/hwdec_compat.h", r'''#pragma once

#include <stdbool.h>
#include <libplacebo/gpu.h>
#include "video/mp_image.h"

struct mp_hwdec_devices;
struct mp_log;
struct mpv_global;
struct orp5_hwdec_bridge;

struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct mp_hwdec_devices *devs);
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

#include "common/msg.h"
#include "ta/ta_talloc.h"
#include "video/hwdec.h"
#include "video/img_format.h"
#include "video/out/gpu/context.h"
#include "video/out/gpu/hwdec.h"
#include "video/out/gpu/ra.h"
#include "video/out/placebo/ra_pl.h"

struct orp5_hwdec_bridge {
    struct mp_log *log;
    struct mp_hwdec_devices *devs;
    struct ra *ra;
    struct ra_ctx ra_ctx;
    struct ra_hwdec_ctx hwdec_ctx;
    struct ra_hwdec *active_hwdec;
    struct ra_hwdec_mapper *mapper;
};

static void load_hwdec_api(void *ctx, struct hwdec_imgfmt_request *params)
{
    struct orp5_hwdec_bridge *b = ctx;
    ra_hwdec_ctx_load_fmt(&b->hwdec_ctx, b->devs, params);
}

struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct mp_hwdec_devices *devs)
{
    struct orp5_hwdec_bridge *b = talloc_zero(NULL, struct orp5_hwdec_bridge);
    b->log = log;
    b->devs = devs;
    b->ra = ra_create_pl(gpu, log);
    if (!b->ra) {
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
    ra_hwdec_mapper_free(&b->mapper);
    ra_hwdec_ctx_uninit(&b->hwdec_ctx);
    ra_free(&b->ra);
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
        ra_hwdec_mapper_free(&b->mapper);
        b->mapper = ra_hwdec_mapper_create(hwdec, src);
        if (!b->mapper) {
            MP_ERR(b, "orp5: initializing hwdec mapper failed\n");
            b->active_hwdec = NULL;
            return false;
        }
        b->active_hwdec = hwdec;
    }

    *dst = b->mapper->dst_params;
    if (is_nv15) {
        const char *subfmt = mp_imgfmt_to_name(src->hw_subfmt);
        *is_nv15 = subfmt && strcmp(subfmt, "yuv420p10") == 0 &&
                   b->mapper->dst_params.imgfmt == IMGFMT_P010;
    }
    return true;
}

int orp5_hwdec_bridge_map(struct orp5_hwdec_bridge *b, struct mp_image *img)
{
    return b->mapper ? ra_hwdec_mapper_map(b->mapper, img) : -1;
}

void orp5_hwdec_bridge_unmap(struct orp5_hwdec_bridge *b)
{
    if (b->mapper)
        ra_hwdec_mapper_unmap(b->mapper);
}

pl_tex orp5_hwdec_bridge_tex(struct orp5_hwdec_bridge *b, int plane)
{
    if (!b->mapper || plane < 0 || plane >= 4 || !b->mapper->tex[plane])
        return NULL;
    if (!ra_pl_get(b->mapper->ra))
        return NULL;
    return (pl_tex)b->mapper->tex[plane]->priv;
}
''')

# ---------------------------------------------------------------------------
# Wire the opaque adapter into gpu-next video.c, while keeping the new RA API
# isolated. For NV15, use the same GPU unpack shader as the Rockchip vo_gpu_next
# implementation that already renders these packed surfaces correctly.
# ---------------------------------------------------------------------------
video_c = "video/out/gpu_next/video.c"
replace_once(
    video_c,
    """#include \"libplacebo/renderer.h\"           // for pl_frame_mix, pl_frame
""",
    """#include \"libplacebo/renderer.h\"           // for pl_frame_mix, pl_frame
#include <libplacebo/shaders/custom.h>
#include <string.h>
""",
)
replace_once(
    video_c,
    """#include \"video/out/gpu_next/ra.h\"         // for ra_next_find_fmt, ra_next_...
""",
    """#include \"video/out/gpu_next/ra.h\"         // for ra_next_find_fmt, ra_next_...
#include \"video/out/gpu_next/hwdec_compat.h\"
#include \"video/hwdec.h\"
""",
)

replace_once(
    video_c,
    """struct pl_video_osd_state {
    struct pl_video_osd_entry entries[MAX_OSD_PARTS]; // Storage for individual OSD parts.
    struct pl_overlay overlays[MAX_OSD_PARTS];      // The final overlays to be rendered.
};
""",
    """struct pl_video_osd_state {
    struct pl_video_osd_entry entries[MAX_OSD_PARTS]; // Storage for individual OSD parts.
    struct pl_overlay overlays[MAX_OSD_PARTS];      // The final overlays to be rendered.
};

#define ORP5_NV15_TEX_POOL_SIZE 8
struct orp5_nv15_tex_pair {
    pl_tex planes[2];
    bool in_use;
};
""",
)

replace_once(
    video_c,
    """    struct mp_log *log;
    struct ra_next *ra;    // The libplacebo rendering abstraction
    ra_queue queue;        // The frame queue for handling video frames and interpolation.
""",
    """    struct mp_log *log;
    struct ra_next *ra;    // The libplacebo rendering abstraction
    ra_queue queue;        // The frame queue for handling video frames and interpolation.
    struct orp5_hwdec_bridge *hwdec_bridge;
    pl_dispatch nv15_dispatch;
    struct orp5_nv15_tex_pair nv15_pool[ORP5_NV15_TEX_POOL_SIZE];
""",
)

replace_once(
    video_c,
    """struct frame_priv {
    struct pl_video *p; // A pointer back to the main pl_video engine struct.
};
""",
    r'''struct frame_priv {
    struct pl_video *p; // A pointer back to the main pl_video engine struct.
    bool hwdec;
    bool nv15;
    int nv15_pool_idx;
};

static bool nv15_unpack_plane(struct pl_video *p, pl_tex dst, pl_tex src,
                              bool chroma)
{
    static const char *header =
        "uint nv15_byte(int x, int y) {\n"
        "    return uint(texelFetch(nv15_src, ivec2(x, y), 0).r * 255.0 + 0.5);\n"
        "}\n"
        "uint nv15_sample(int x, int y) {\n"
        "    int o = (x >> 2) * 5; int k = x & 3;\n"
        "    uint a=nv15_byte(o+k,y), b=nv15_byte(o+k+1,y);\n"
        "    if (k == 0) return a | ((b & 3u) << 8);\n"
        "    if (k == 1) return (a >> 2) | ((b & 15u) << 6);\n"
        "    if (k == 2) return (a >> 4) | ((b & 63u) << 4);\n"
        "    return (a >> 6) | (b << 2);\n"
        "}\n"
        "uvec2 nv15_pair(int x, int y) {\n"
        "    int o = (x >> 1) * 5; int k = (x & 1) * 2;\n"
        "    uint a=nv15_byte(o+k,y), b=nv15_byte(o+k+1,y);\n"
        "    uint c=nv15_byte(o+k+2,y);\n"
        "    if (k == 0) return uvec2(a | ((b & 3u) << 8),\n"
        "                             (b >> 2) | ((c & 15u) << 6));\n"
        "    return uvec2((a >> 4) | ((b & 63u) << 4),\n"
        "                 (b >> 6) | (c << 2));\n"
        "}\n";
    const char *body = chroma
        ? "ivec2 p=ivec2(gl_FragCoord.xy); "
          "color=vec4(vec2(nv15_pair(p.x,p.y))*64.0/65535.0,0.0,1.0);"
        : "ivec2 p=ivec2(gl_FragCoord.xy); "
          "color=vec4(float(nv15_sample(p.x,p.y)*64u)/65535.0,0.0,0.0,1.0);";
    struct pl_shader_desc desc = {
        .desc = {.name = "nv15_src", .type = PL_DESC_SAMPLED_TEX},
        .binding = {.object = src, .sample_mode = PL_TEX_SAMPLE_NEAREST},
    };
    pl_shader sh = pl_dispatch_begin(p->nv15_dispatch);
    if (!pl_shader_custom(sh, &(struct pl_custom_shader) {
            .description = chroma ? "NV15 chroma unpack" : "NV15 luma unpack",
            .header = header,
            .body = body,
            .output = PL_SHADER_SIG_COLOR,
            .descriptors = &desc,
            .num_descriptors = 1,
            .output_w = dst->params.w,
            .output_h = dst->params.h,
        }))
        return false;
    return pl_dispatch_finish(p->nv15_dispatch, pl_dispatch_params(
        .shader = &sh,
        .target = dst,
    ));
}

static bool hwdec_unpack_nv15(struct pl_video *p, struct frame_priv *fp,
                              struct pl_frame *frame)
{
    pl_fmt formats[2] = {pl_find_named_fmt(p->ra->gpu, "r16"),
                         pl_find_named_fmt(p->ra->gpu, "rg16")};
    if (!formats[0] || !formats[1])
        return false;

    int pool_idx = -1;
    for (int i = 0; i < ORP5_NV15_TEX_POOL_SIZE; i++) {
        if (!p->nv15_pool[i].in_use) {
            pool_idx = i;
            break;
        }
    }
    if (pool_idx < 0) {
        mp_msg(p->log, MSGL_ERR, "orp5: no free NV15 unpack texture pair\n");
        return false;
    }

    struct orp5_nv15_tex_pair *pair = &p->nv15_pool[pool_idx];
    pair->in_use = true;
    fp->nv15_pool_idx = pool_idx;
    pl_dispatch_reset_frame(p->nv15_dispatch);

    for (int n = 0; n < 2; n++) {
        pl_tex src = orp5_hwdec_bridge_tex(p->hwdec_bridge, n);
        if (!src)
            goto fail;
        if (!pl_tex_recreate(p->ra->gpu, &pair->planes[n], pl_tex_params(
            .w = n ? p->current_params.w / 2 : p->current_params.w,
            .h = n ? p->current_params.h / 2 : p->current_params.h,
            .format = formats[n],
            .sampleable = true,
            .renderable = true,
        )) || !nv15_unpack_plane(p, pair->planes[n], src, n == 1))
            goto fail;
        frame->planes[n].texture = pair->planes[n];
    }

    mp_msg(p->log, MSGL_V, "orp5: unpacked NV15 with libplacebo GPU dispatch\n");
    return true;

fail:
    for (int n = 0; n < 2; n++)
        frame->planes[n].texture = NULL;
    pair->in_use = false;
    fp->nv15_pool_idx = -1;
    return false;
}

static bool hwdec_acquire(pl_gpu gpu, struct pl_frame *frame)
{
    struct mp_image *mpi = frame->user_data;
    struct frame_priv *fp = mpi->priv;
    struct pl_video *p = fp->p;

    if (orp5_hwdec_bridge_map(p->hwdec_bridge, mpi) < 0) {
        mp_msg(p->log, MSGL_ERR, "orp5: mapping hardware decoded surface failed\n");
        return false;
    }

    if (fp->nv15) {
        if (!hwdec_unpack_nv15(p, fp, frame)) {
            orp5_hwdec_bridge_unmap(p->hwdec_bridge);
            return false;
        }
    } else {
        for (int n = 0; n < frame->num_planes; n++) {
            frame->planes[n].texture =
                orp5_hwdec_bridge_tex(p->hwdec_bridge, n);
            if (!frame->planes[n].texture) {
                orp5_hwdec_bridge_unmap(p->hwdec_bridge);
                return false;
            }
        }
    }
    return true;
}

static void hwdec_release(pl_gpu gpu, struct pl_frame *frame)
{
    struct mp_image *mpi = frame->user_data;
    struct frame_priv *fp = mpi->priv;
    struct pl_video *p = fp->p;

    for (int n = 0; n < frame->num_planes; n++)
        frame->planes[n].texture = NULL;

    if (fp->nv15 && fp->nv15_pool_idx >= 0) {
        p->nv15_pool[fp->nv15_pool_idx].in_use = false;
        fp->nv15_pool_idx = -1;
    }
    orp5_hwdec_bridge_unmap(p->hwdec_bridge);
}
''',
)

old_map = r'''static bool map_frame(pl_gpu gpu, pl_tex *tex, const struct pl_source_frame *src,
                      struct pl_frame *frame)
{
    struct mp_image *mpi = src->frame_data;
    struct frame_priv *fp = mpi->priv;
    struct pl_video *p = fp->p;

    // Use the RA helper to upload the mp_image data to a new set of textures
    // and populate the pl_frame struct with the result.
    if (!ra_upload_mp_image(p->ra, frame, mpi)) {
        talloc_free(mpi); // Clean up the mp_image reference on failure
        return false;
    }

    // Store a pointer back to the original mp_image. This is used to get a unique
    // signature for the frame and to access metadata (like colorspace) later.
    frame->user_data = mpi;
    return true;
}
'''
new_map = r'''static bool map_frame(pl_gpu gpu, pl_tex *tex, const struct pl_source_frame *src,
                      struct pl_frame *frame)
{
    struct mp_image *mpi = src->frame_data;
    struct frame_priv *fp = mpi->priv;
    struct pl_video *p = fp->p;
    struct mp_image_params par = mpi->params;

    fp->hwdec = orp5_hwdec_bridge_prepare(p->hwdec_bridge, &mpi->params,
                                          &par, &fp->nv15);
    fp->nv15_pool_idx = -1;

    if (fp->hwdec) {
        mp_image_params_guess_csp(&par);
        *frame = (struct pl_frame) {
            .color = par.color,
            .repr = par.repr,
            .rotation = par.rotate / 90,
            .user_data = mpi,
            .acquire = hwdec_acquire,
            .release = hwdec_release,
        };

        struct mp_imgfmt_desc desc = mp_imgfmt_get_desc(par.imgfmt);
        frame->num_planes = desc.num_planes;
        for (int n = 0; n < frame->num_planes; n++) {
            struct pl_plane *plane = &frame->planes[n];
            int *map = plane->component_mapping;
            for (int c = 0; c < mp_imgfmt_desc_get_num_comps(&desc); c++) {
                if (desc.comps[c].plane != n)
                    continue;
                uint8_t offset = desc.comps[c].offset;
                int index = plane->components++;
                while (index > 0 && desc.comps[map[index - 1]].offset > offset) {
                    map[index] = map[index - 1];
                    index--;
                }
                map[index] = c;
            }
        }
        pl_frame_set_chroma_location(frame, par.chroma_location);
        return true;
    }

    // Software frames keep the original gpu-next upload path.
    if (!ra_upload_mp_image(p->ra, frame, mpi)) {
        talloc_free(mpi);
        return false;
    }
    frame->user_data = mpi;
    return true;
}
'''
replace_once(video_c, old_map, new_map)

replace_once(
    video_c,
    """    // Use the RA helper to destroy the GPU textures associated with the frame.
    ra_cleanup_pl_frame(p->ra, frame);
    // Free the mp_image reference itself.
""",
    """    // Hardware textures are owned by the mapper/acquire-release path.
    if (!fp->hwdec)
        ra_cleanup_pl_frame(p->ra, frame);
    // Free the mp_image reference itself.
""",
)

replace_once(
    video_c,
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log, struct ra_next *ra) {
    struct pl_video *p = talloc_zero(NULL, struct pl_video);
    p->log = log;
    p->ra = ra;
    p->queue = ra_next_queue_create(ra);

    // Pre-find the texture formats we'll need for OSD bitmaps for efficiency.
""",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra,
                               struct mp_hwdec_devices *hwdec_devs) {
    struct pl_video *p = talloc_zero(NULL, struct pl_video);
    p->log = log;
    p->ra = ra;
    p->queue = ra_next_queue_create(ra);
    p->hwdec_bridge = orp5_hwdec_bridge_create(global, log, ra->gpu, hwdec_devs);
    p->nv15_dispatch = pl_dispatch_create(ra->log, ra->gpu);
    if (!p->hwdec_bridge || !p->nv15_dispatch) {
        orp5_hwdec_bridge_destroy(&p->hwdec_bridge);
        pl_dispatch_destroy(&p->nv15_dispatch);
        ra_next_queue_destroy(&p->queue);
        talloc_free(p);
        return NULL;
    }

    // Pre-find the texture formats we'll need for OSD bitmaps for efficiency.
""",
)

replace_once(
    video_c,
    """    ra_next_queue_destroy(&p->queue);

    // Clean up all allocated OSD GPU resources
""",
    """    orp5_hwdec_bridge_destroy(&p->hwdec_bridge);
    for (int i = 0; i < ORP5_NV15_TEX_POOL_SIZE; i++) {
        for (int n = 0; n < 2; n++)
            pl_tex_destroy(p->ra->gpu, &p->nv15_pool[i].planes[n]);
    }
    pl_dispatch_destroy(&p->nv15_dispatch);
    ra_next_queue_destroy(&p->queue);

    // Clean up all allocated OSD GPU resources
""",
)

# Update public video-engine signature.
replace_once(
    "video/out/gpu_next/video.h",
    """struct mpv_global;
struct osd_state;
""",
    """struct mpv_global;
struct mp_hwdec_devices;
struct osd_state;
""",
)
replace_once(
    "video/out/gpu_next/video.h",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log, struct ra_next *ra);
""",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra,
                               struct mp_hwdec_devices *hwdec_devs);
""",
)

# Create the shared hwdec device collection before video-engine initialization,
# and destroy it only after the bridge has removed its loader and mappers.
replace_once(
    "video/out/gpu_next/libmpv_gpu_next.c",
    """    // Initialize our synchronous libplacebo rendering engine.
    p->video_engine = pl_video_init(ctx->global, ctx->log, p->context->ra);
    if (!p->video_engine) {
        p->context->fns->destroy(p->context);
        talloc_free(p->context);
        return MPV_ERROR_VO_INIT_FAILED;
    }

    // Create hardware decoder devices.
    ctx->hwdec_devs = hwdec_devices_create();
    ctx->driver_caps = VO_CAP_ROTATE90 | VO_CAP_VFLIP;
""",
    """    // Create hardware decoder devices before the gpu-next video engine so
    // orp5 can install mpv's normal lazy V4L2-request loader.
    ctx->hwdec_devs = hwdec_devices_create();

    // Initialize our synchronous libplacebo rendering engine.
    p->video_engine = pl_video_init(ctx->global, ctx->log, p->context->ra,
                                    ctx->hwdec_devs);
    if (!p->video_engine) {
        hwdec_devices_destroy(ctx->hwdec_devs);
        ctx->hwdec_devs = NULL;
        p->context->fns->destroy(p->context);
        talloc_free(p->context);
        return MPV_ERROR_VO_INIT_FAILED;
    }

    ctx->driver_caps = VO_CAP_ROTATE90 | VO_CAP_VFLIP;
""",
)
replace_once(
    "video/out/gpu_next/libmpv_gpu_next.c",
    """    hwdec_devices_destroy(ctx->hwdec_devs);
    pl_video_uninit(&p->video_engine);
""",
    """    pl_video_uninit(&p->video_engine);
    hwdec_devices_destroy(ctx->hwdec_devs);
""",
)

print("orp5: patched isolated gpu-next V4L2-request/DRM-PRIME/NV15 bridge")
