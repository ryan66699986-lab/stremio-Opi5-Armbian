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


# The Rockchip V4L2-request driver can use mpv's libplacebo DMA-BUF interop
# independently of VAAPI. Build and expose that interop for this private stack.
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

# orp5: V4L2-request also needs the libplacebo DMA-BUF interop when VAAPI is
# deliberately disabled in the private RK3588 stack.
if features['drm'] and not features['vaapi']
    sources += files('video/out/hwdec/dmabuf_interop_pl.c')
endif
""",
)

replace_once(
    "video/out/hwdec/hwdec_drmprime.c",
    """#if HAVE_VAAPI
    dmabuf_interop_pl_init,
#endif
""",
    """    // orp5: libplacebo DMA-BUF import is useful for V4L2-request too;
    // it does not require VAAPI when the source is built explicitly.
    dmabuf_interop_pl_init,
""",
)

# Teach the libplacebo DMA-BUF interop about the RK3588 packed NV15 layout.
# The normal P010 import cannot describe NV15's 4x10-bit-in-5-byte packing, so
# expose each packed plane as R8 and let gpu-next unpack it on the GPU.
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
            uint32_t size = object->size;

            if (size == 0) {
                size = lseek(fd, 0, SEEK_END);
                if (size == (uint32_t)-1) {
                    MP_ERR(mapper, \"Cannot obtain NV15 object size for fd %d: %s\\n\",
                           fd, mp_strerror(errno));
                    return false;
                }
                if (lseek(fd, 0, SEEK_SET) == -1) {
                    MP_ERR(mapper, \"Failed to reset NV15 fd %d: %s\\n\",
                           fd, mp_strerror(errno));
                    return false;
                }
            }

            pl_tex pltex = pl_tex_create(gpu, &(struct pl_tex_params) {
                // NV15 stores four 10-bit samples in five bytes. Import the
                // packed byte stream verbatim; gpu-next performs unpacking.
                .w = plane->pitch,
                .h = n ? mapper->src_params.h / 2 : mapper->src_params.h,
                .d = 0,
                .format = r8,
                .sampleable = true,
                .import_handle = PL_HANDLE_DMA_BUF,
                .shared_mem = (struct pl_shared_mem) {
                    .handle = {.fd = fd},
                    .size = size,
                    .offset = plane->offset,
                    .drm_format_mod = object->format_modifier,
                    .stride_w = plane->pitch,
                },
            });
            if (!pltex)
                return false;

            struct ra_tex *ratex = talloc_ptrtype(NULL, ratex);
            if (!mppl_wrap_tex(mapper->ra, pltex, ratex)) {
                pl_tex_destroy(gpu, &pltex);
                talloc_free(ratex);
                return false;
            }
            mapper->tex[n] = ratex;
            MP_VERBOSE(mapper, \"Imported NV15 packed byte plane %d as R8 DMA-BUF\\n\", n);
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

    // orp5: RK3588 Main10 V4L2-request exports DRM_FORMAT_NV15. Ask the
    // common DRM PRIME mapper to expose that layout as packed byte planes.
    dmabuf_interop->supports_nv15_byte_planes = true;
    dmabuf_interop->interop_map = vaapi_pl_map;
""",
)

# Pass the render backend's hwdec device collection into the synchronous
# gpu-next video engine, where the lazy V4L2-request loader and mapper live.
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
    """#include \"video/mp_image.h\"                // for mp_image, mp_image_params
#include \"video/out/gpu_next/ra.h\"         // for ra_next_find_fmt, ra_next_...
""",
    """#include \"video/mp_image.h\"                // for mp_image, mp_image_params
#include \"video/hwdec.h\"
#include \"video/out/gpu/context.h\"
#include \"video/out/gpu/hwdec.h\"
#include \"video/out/gpu/ra.h\"
#include \"video/out/placebo/ra_pl.h\"
#include \"video/out/gpu_next/ra.h\"         // for ra_next_find_fmt, ra_next_...
""",
)

replace_once(
    video_c,
    """struct pl_video_osd_state {
    struct pl_video_osd_entry entries[MAX_OSD_PARTS]; // Storage for individual OSD parts.
    struct pl_overlay overlays[MAX_OSD_PARTS];      // The final overlays that will be passed to the renderer.
};
""" if False else """struct pl_video_osd_state {
    struct pl_video_osd_entry entries[MAX_OSD_PARTS]; // Storage for individual OSD parts.
    struct pl_overlay overlays[MAX_OSD_PARTS];      // The final overlays that will be passed to the renderer.
};
""",
    """struct pl_video_osd_state {
    struct pl_video_osd_entry entries[MAX_OSD_PARTS]; // Storage for individual OSD parts.
    struct pl_overlay overlays[MAX_OSD_PARTS];      // The final overlays that will be passed to the renderer.
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

    // orp5: bridge the libplacebo GPU to mpv's existing DRM PRIME/V4L2-request
    // hwdec machinery. The legacy RA is only an interop facade over this same
    // pl_gpu; no second graphics context is created.
    struct ra *hwdec_ra;
    struct ra_ctx hwdec_ra_ctx;
    struct ra_hwdec_ctx hwdec_ctx;
    struct ra_hwdec_mapper *hwdec_mapper;
    struct mp_hwdec_devices *hwdec_devs;
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
    """struct frame_priv {
    struct pl_video *p; // A pointer back to the main pl_video engine struct.
    struct ra_hwdec *hwdec;
    bool nv15;
    int nv15_pool_idx;
};

static void orp5_load_hwdec_api(void *ctx, struct hwdec_imgfmt_request *params)
{
    struct pl_video *p = ctx;
    ra_hwdec_ctx_load_fmt(&p->hwdec_ctx, p->hwdec_devs, params);
}

static bool orp5_hwdec_reconfig(struct pl_video *p, struct ra_hwdec *hwdec,
                                const struct mp_image_params *par)
{
    if (p->hwdec_mapper) {
        if (mp_image_params_static_equal(par, &p->hwdec_mapper->src_params)) {
            p->hwdec_mapper->src_params.repr.dovi = par->repr.dovi;
            p->hwdec_mapper->dst_params.repr.dovi = par->repr.dovi;
            p->hwdec_mapper->src_params.color.hdr = par->color.hdr;
            p->hwdec_mapper->dst_params.color.hdr = par->color.hdr;
            return true;
        }
        ra_hwdec_mapper_free(&p->hwdec_mapper);
    }

    p->hwdec_mapper = ra_hwdec_mapper_create(hwdec, par);
    if (!p->hwdec_mapper) {
        MP_ERR(p, \"orp5: initializing hwdec mapper failed\\n\");
        return false;
    }
    return true;
}

static pl_tex orp5_hwdec_get_tex(struct pl_video *p, int n)
{
    if (!p->hwdec_mapper || !p->hwdec_mapper->tex[n])
        return NULL;
    if (!ra_pl_get(p->hwdec_mapper->ra)) {
        MP_ERR(p, \"orp5: expected libplacebo hwdec RA\\n\");
        return NULL;
    }
    return (pl_tex)p->hwdec_mapper->tex[n]->priv;
}

static bool orp5_nv15_unpack_plane(struct pl_video *p, pl_tex dst, pl_tex src,
                                    bool chroma)
{
    static const char *header =
        \"uint nv15_byte(int x, int y) {\\n\"
        \"    return uint(texelFetch(nv15_src, ivec2(x, y), 0).r * 255.0 + 0.5);\\n\"
        \"}\\n\"
        \"uint nv15_sample(int x, int y) {\\n\"
        \"    int o = (x >> 2) * 5; int k = x & 3;\\n\"
        \"    uint a=nv15_byte(o+k,y), b=nv15_byte(o+k+1,y);\\n\"
        \"    if (k == 0) return a | ((b & 3u) << 8);\\n\"
        \"    if (k == 1) return (a >> 2) | ((b & 15u) << 6);\\n\"
        \"    if (k == 2) return (a >> 4) | ((b & 63u) << 4);\\n\"
        \"    return (a >> 6) | (b << 2);\\n\"
        \"}\\n\"
        \"uvec2 nv15_pair(int x, int y) {\\n\"
        \"    int o = (x >> 1) * 5; int k = (x & 1) * 2;\\n\"
        \"    uint a=nv15_byte(o+k,y), b=nv15_byte(o+k+1,y);\\n\"
        \"    uint c=nv15_byte(o+k+2,y);\\n\"
        \"    if (k == 0) return uvec2(a | ((b & 3u) << 8),\\n\"
        \"                             (b >> 2) | ((c & 15u) << 6));\\n\"
        \"    return uvec2((a >> 4) | ((b & 63u) << 4),\\n\"
        \"                 (b >> 6) | (c << 2));\\n\"
        \"}\\n\";
    const char *body = chroma
        ? \"ivec2 p=ivec2(gl_FragCoord.xy); \"
          \"color=vec4(vec2(nv15_pair(p.x,p.y))*64.0/65535.0,0.0,1.0);\"
        : \"ivec2 p=ivec2(gl_FragCoord.xy); \"
          \"color=vec4(float(nv15_sample(p.x,p.y)*64u)/65535.0,0.0,0.0,1.0);\";
    struct pl_shader_desc desc = {
        .desc = {.name = \"nv15_src\", .type = PL_DESC_SAMPLED_TEX},
        .binding = {.object = src, .sample_mode = PL_TEX_SAMPLE_NEAREST},
    };
    pl_shader sh = pl_dispatch_begin(p->nv15_dispatch);
    if (!pl_shader_custom(sh, &(struct pl_custom_shader) {
            .description = chroma ? \"NV15 chroma unpack\" : \"NV15 luma unpack\",
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

static bool orp5_hwdec_unpack_nv15(struct pl_video *p, struct frame_priv *fp,
                                    struct pl_frame *frame)
{
    pl_fmt formats[2] = {pl_find_named_fmt(p->ra->gpu, \"r16\"),
                         pl_find_named_fmt(p->ra->gpu, \"rg16\")};
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
        MP_ERR(p, \"orp5: no free NV15 unpack texture pair\\n\");
        return false;
    }

    struct orp5_nv15_tex_pair *pair = &p->nv15_pool[pool_idx];
    pair->in_use = true;
    fp->nv15_pool_idx = pool_idx;
    pl_dispatch_reset_frame(p->nv15_dispatch);

    for (int n = 0; n < 2; n++) {
        pl_tex src = orp5_hwdec_get_tex(p, n);
        if (!src)
            goto fail;
        if (!pl_tex_recreate(p->ra->gpu, &pair->planes[n], pl_tex_params(
            .w = n ? p->hwdec_mapper->src_params.w / 2
                   : p->hwdec_mapper->src_params.w,
            .h = n ? p->hwdec_mapper->src_params.h / 2
                   : p->hwdec_mapper->src_params.h,
            .format = formats[n],
            .sampleable = true,
            .renderable = true,
        )) || !orp5_nv15_unpack_plane(p, pair->planes[n], src, n == 1))
            goto fail;
        frame->planes[n].texture = pair->planes[n];
    }

    fp->nv15 = true;
    MP_VERBOSE(p, \"orp5: unpacked NV15 with libplacebo GPU dispatch\\n\");
    return true;

fail:
    for (int n = 0; n < 2; n++)
        frame->planes[n].texture = NULL;
    pair->in_use = false;
    fp->nv15_pool_idx = -1;
    return false;
}

static bool orp5_hwdec_acquire(pl_gpu gpu, struct pl_frame *frame)
{
    struct mp_image *mpi = frame->user_data;
    struct frame_priv *fp = mpi->priv;
    struct pl_video *p = fp->p;

    if (!orp5_hwdec_reconfig(p, fp->hwdec, &mpi->params))
        return false;

    bool nv15 = strcmp(mp_imgfmt_to_name(mpi->params.hw_subfmt), \"yuv420p10\") == 0 &&
                p->hwdec_mapper->dst_params.imgfmt == IMGFMT_P010;

    if (ra_hwdec_mapper_map(p->hwdec_mapper, mpi) < 0) {
        MP_ERR(p, \"orp5: mapping hardware-decoded surface failed\\n\");
        return false;
    }

    if (nv15) {
        if (!orp5_hwdec_unpack_nv15(p, fp, frame)) {
            ra_hwdec_mapper_unmap(p->hwdec_mapper);
            return false;
        }
    } else {
        for (int n = 0; n < frame->num_planes; n++) {
            frame->planes[n].texture = orp5_hwdec_get_tex(p, n);
            if (!frame->planes[n].texture) {
                ra_hwdec_mapper_unmap(p->hwdec_mapper);
                return false;
            }
        }
    }

    return true;
}

static void orp5_hwdec_release(pl_gpu gpu, struct pl_frame *frame)
{
    struct mp_image *mpi = frame->user_data;
    struct frame_priv *fp = mpi->priv;
    struct pl_video *p = fp->p;

    for (int n = 0; n < frame->num_planes; n++)
        frame->planes[n].texture = NULL;

    if (fp->nv15 && fp->nv15_pool_idx >= 0) {
        p->nv15_pool[fp->nv15_pool_idx].in_use = false;
        fp->nv15 = false;
        fp->nv15_pool_idx = -1;
    }

    ra_hwdec_mapper_unmap(p->hwdec_mapper);
}
""",
)

old_map = """static bool map_frame(pl_gpu gpu, pl_tex *tex, const struct pl_source_frame *src,
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
"""
new_map = """static bool map_frame(pl_gpu gpu, pl_tex *tex, const struct pl_source_frame *src,
                      struct pl_frame *frame)
{
    struct mp_image *mpi = src->frame_data;
    struct frame_priv *fp = mpi->priv;
    struct pl_video *p = fp->p;

    fp->hwdec = ra_hwdec_get(&p->hwdec_ctx, mpi->imgfmt);
    fp->nv15 = false;
    fp->nv15_pool_idx = -1;

    if (fp->hwdec) {
        if (!orp5_hwdec_reconfig(p, fp->hwdec, &mpi->params)) {
            talloc_free(mpi);
            return false;
        }

        struct mp_image_params par = p->hwdec_mapper->dst_params;
        mp_image_params_guess_csp(&par);
        *frame = (struct pl_frame) {
            .color = par.color,
            .repr = par.repr,
            .crop = {.x0 = 0, .y0 = 0, .x1 = par.w, .y1 = par.h},
            .rotation = par.rotate / 90,
            .user_data = mpi,
            .acquire = orp5_hwdec_acquire,
            .release = orp5_hwdec_release,
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
"""
replace_once(video_c, old_map, new_map)

replace_once(
    video_c,
    """    // Use the RA helper to destroy the GPU textures associated with the frame.
    ra_cleanup_pl_frame(p->ra, frame);
    // Free the mp_image reference itself.
""",
    """    // HW textures are owned/unmapped by the acquire/release callbacks.
    // Software frames still own the uploaded textures directly.
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
    p->hwdec_devs = hwdec_devs;

    p->hwdec_ra = ra_create_pl(ra->gpu, log);
    if (!p->hwdec_ra) {
        talloc_free(p);
        return NULL;
    }
    p->hwdec_ra_ctx = (struct ra_ctx) {
        .ra = p->hwdec_ra,
        .global = global,
        .log = log,
    };
    p->hwdec_ctx = (struct ra_hwdec_ctx) {
        .log = log,
        .global = global,
        .ra_ctx = &p->hwdec_ra_ctx,
    };
    hwdec_devices_set_loader(hwdec_devs, orp5_load_hwdec_api, p);
    ra_hwdec_ctx_init(&p->hwdec_ctx, hwdec_devs, \"auto\", false);

    p->nv15_dispatch = pl_dispatch_create(ra_get_pl_log(ra), ra->gpu);
    if (!p->nv15_dispatch) {
        hwdec_devices_set_loader(hwdec_devs, NULL, NULL);
        ra_hwdec_ctx_uninit(&p->hwdec_ctx);
        ra_free(&p->hwdec_ra);
        talloc_free(p);
        return NULL;
    }

    MP_INFO(p, \"orp5: libmpv gpu-next hwdec bridge enabled\\n\");

    // Pre-find the texture formats we'll need for OSD bitmaps for efficiency.
""",
)

replace_once(
    video_c,
    """    ra_next_queue_destroy(&p->queue);

    // Clean up all allocated OSD GPU resources
""",
    """    hwdec_devices_set_loader(p->hwdec_devs, NULL, NULL);
    ra_hwdec_mapper_free(&p->hwdec_mapper);
    ra_hwdec_ctx_uninit(&p->hwdec_ctx);
    ra_free(&p->hwdec_ra);

    for (int i = 0; i < ORP5_NV15_TEX_POOL_SIZE; i++) {
        for (int n = 0; n < 2; n++)
            pl_tex_destroy(p->ra->gpu, &p->nv15_pool[i].planes[n]);
    }
    pl_dispatch_destroy(&p->nv15_dispatch);

    ra_next_queue_destroy(&p->queue);

    // Clean up all allocated OSD GPU resources
""",
)

# Create hwdec devices before constructing the video engine so its lazy loader
# is active when the decoder probes hevc-v4l2request.
libmpv = "video/out/gpu_next/libmpv_gpu_next.c"
replace_once(
    libmpv,
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
    """    // Create hardware decoder devices first. orp5 installs the normal
    // V4L2-request lazy loader inside the gpu-next video engine.
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
    libmpv,
    """    hwdec_devices_destroy(ctx->hwdec_devs);
    pl_video_uninit(&p->video_engine);
""",
    """    // The video engine owns the loader/interop state; tear it down
    // before destroying the shared device collection.
    pl_video_uninit(&p->video_engine);
    hwdec_devices_destroy(ctx->hwdec_devs);
""",
)

print("orp5: patched gpu-next V4L2-request/DRM-PRIME/NV15 bridge")
