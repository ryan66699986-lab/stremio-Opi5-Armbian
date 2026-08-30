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
        raise SystemExit(f"{rel}: expected one lifetime-fix anchor, found {count}")
    path.write_text(data.replace(old, new, 1))


# libplacebo's frame queue may keep several source frames mapped concurrently.
# A ra_hwdec_mapper cannot be shared between those frames: ra_hwdec_mapper_map()
# starts by unmapping whatever image is currently attached to that mapper.
# Give every queued hardware frame its own mapper and keep only the hwdec driver
# collection/RA context in the long-lived bridge.
replace_once(
    "video/out/gpu_next/hwdec_compat.h",
    """struct mpv_global;
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
""",
    """struct mpv_global;
struct orp5_hwdec_bridge;
struct orp5_hwdec_frame;

struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct mp_hwdec_devices *devs);
void orp5_hwdec_bridge_destroy(struct orp5_hwdec_bridge **bridge);

struct orp5_hwdec_frame *orp5_hwdec_frame_create(
    struct orp5_hwdec_bridge *bridge, const struct mp_image_params *src,
    struct mp_image_params *dst, bool *is_nv15);
void orp5_hwdec_frame_destroy(struct orp5_hwdec_frame **frame);
int orp5_hwdec_frame_map(struct orp5_hwdec_frame *frame,
                         struct mp_image *img);
void orp5_hwdec_frame_unmap(struct orp5_hwdec_frame *frame);
pl_tex orp5_hwdec_frame_tex(struct orp5_hwdec_frame *frame, int plane);
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """struct orp5_hwdec_bridge {
    struct mp_log *log;
    struct mp_hwdec_devices *devs;
    struct ra *ra;
    struct ra_ctx ra_ctx;
    struct ra_hwdec_ctx hwdec_ctx;
    struct ra_hwdec *active_hwdec;
    struct ra_hwdec_mapper *mapper;
};
""",
    """struct orp5_hwdec_bridge {
    struct mp_log *log;
    struct mp_hwdec_devices *devs;
    struct ra *ra;
    struct ra_ctx ra_ctx;
    struct ra_hwdec_ctx hwdec_ctx;
};

struct orp5_hwdec_frame {
    struct ra_hwdec_mapper *mapper;
};
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """    ra_hwdec_ctx_init(&b->hwdec_ctx, devs, \"auto\", false);
    MP_INFO(b, \"orp5: libmpv gpu-next hwdec bridge enabled\\n\");
""",
    """    ra_hwdec_ctx_init(&b->hwdec_ctx, devs, \"auto\", false);
    MP_INFO(b, \"orp5: libmpv gpu-next hwdec bridge enabled\\n\");
    MP_INFO(b, \"orp5: per-frame hwdec mapper lifetime enabled\\n\");
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """    hwdec_devices_set_loader(b->devs, NULL, NULL);
    ra_hwdec_mapper_free(&b->mapper);
    ra_hwdec_ctx_uninit(&b->hwdec_ctx);
""",
    """    hwdec_devices_set_loader(b->devs, NULL, NULL);
    ra_hwdec_ctx_uninit(&b->hwdec_ctx);
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """bool orp5_hwdec_bridge_prepare(struct orp5_hwdec_bridge *b,
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
            MP_ERR(b, \"orp5: initializing hwdec mapper failed\\n\");
            b->active_hwdec = NULL;
            return false;
        }
        b->active_hwdec = hwdec;
    }

    *dst = b->mapper->dst_params;
    if (is_nv15) {
        const char *subfmt = mp_imgfmt_to_name(src->hw_subfmt);
        *is_nv15 = subfmt && strcmp(subfmt, \"yuv420p10\") == 0 &&
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
""",
    """struct orp5_hwdec_frame *orp5_hwdec_frame_create(
    struct orp5_hwdec_bridge *b, const struct mp_image_params *src,
    struct mp_image_params *dst, bool *is_nv15)
{
    struct ra_hwdec *hwdec = ra_hwdec_get(&b->hwdec_ctx, src->imgfmt);
    if (!hwdec)
        return NULL;

    struct orp5_hwdec_frame *f = talloc_zero(NULL, struct orp5_hwdec_frame);
    f->mapper = ra_hwdec_mapper_create(hwdec, src);
    if (!f->mapper) {
        MP_ERR(b, \"orp5: initializing per-frame hwdec mapper failed\\n\");
        talloc_free(f);
        return NULL;
    }

    *dst = f->mapper->dst_params;
    if (is_nv15) {
        const char *subfmt = mp_imgfmt_to_name(src->hw_subfmt);
        *is_nv15 = subfmt && strcmp(subfmt, \"yuv420p10\") == 0 &&
                   f->mapper->dst_params.imgfmt == IMGFMT_P010;
    }
    return f;
}

void orp5_hwdec_frame_destroy(struct orp5_hwdec_frame **frame)
{
    struct orp5_hwdec_frame *f = frame ? *frame : NULL;
    if (!f)
        return;
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
    if (f && f->mapper)
        ra_hwdec_mapper_unmap(f->mapper);
}

pl_tex orp5_hwdec_frame_tex(struct orp5_hwdec_frame *f, int plane)
{
    if (!f || !f->mapper || plane < 0 || plane >= 4 || !f->mapper->tex[plane])
        return NULL;
    if (!ra_pl_get(f->mapper->ra))
        return NULL;
    return (pl_tex)f->mapper->tex[plane]->priv;
}
""",
)

replace_once(
    "video/out/gpu_next/video.c",
    """struct frame_priv {
    struct pl_video *p; // A pointer back to the main pl_video engine struct.
    bool hwdec;
    bool nv15;
    int nv15_pool_idx;
};
""",
    """struct frame_priv {
    struct pl_video *p; // A pointer back to the main pl_video engine struct.
    struct orp5_hwdec_frame *hwdec_frame;
    bool hwdec;
    bool nv15;
    int nv15_pool_idx;
};
""",
)

replace_once(
    "video/out/gpu_next/video.c",
    """        pl_tex src = orp5_hwdec_bridge_tex(p->hwdec_bridge, n);
""",
    """        pl_tex src = orp5_hwdec_frame_tex(fp->hwdec_frame, n);
""",
)

replace_once(
    "video/out/gpu_next/video.c",
    """    if (orp5_hwdec_bridge_map(p->hwdec_bridge, mpi) < 0) {
""",
    """    if (orp5_hwdec_frame_map(fp->hwdec_frame, mpi) < 0) {
""",
)

replace_once(
    "video/out/gpu_next/video.c",
    """            frame->planes[n].texture =
                orp5_hwdec_bridge_tex(p->hwdec_bridge, n);
""",
    """            frame->planes[n].texture =
                orp5_hwdec_frame_tex(fp->hwdec_frame, n);
""",
)

replace_once(
    "video/out/gpu_next/video.c",
    """            orp5_hwdec_bridge_unmap(p->hwdec_bridge);
""",
    """            orp5_hwdec_frame_unmap(fp->hwdec_frame);
""",
)

# There are two remaining bridge-unmap calls: the NV15 unpack failure and the
# normal release callback. Convert both deliberately after the single inner-loop
# occurrence above has been replaced.
video_path = root / "video/out/gpu_next/video.c"
video_data = video_path.read_text()
old = "orp5_hwdec_bridge_unmap(p->hwdec_bridge);"
if video_data.count(old) != 2:
    raise SystemExit(
        f"video/out/gpu_next/video.c: expected two remaining bridge unmaps, found {video_data.count(old)}"
    )
video_path.write_text(video_data.replace(old, "orp5_hwdec_frame_unmap(fp->hwdec_frame);"))

replace_once(
    "video/out/gpu_next/video.c",
    """    fp->hwdec = orp5_hwdec_bridge_prepare(p->hwdec_bridge, &mpi->params,
                                          &par, &fp->nv15);
    fp->nv15_pool_idx = -1;
""",
    """    fp->hwdec_frame = orp5_hwdec_frame_create(
        p->hwdec_bridge, &mpi->params, &par, &fp->nv15);
    fp->hwdec = fp->hwdec_frame != NULL;
    fp->nv15_pool_idx = -1;
""",
)

replace_once(
    "video/out/gpu_next/video.c",
    """    // Hardware textures are owned by the mapper/acquire-release path.
    if (!fp->hwdec)
        ra_cleanup_pl_frame(p->ra, frame);
    // Free the mp_image reference itself.
""",
    """    // Hardware frames own an independent mapper for the full queue-entry
    // lifetime. Software frames keep the original gpu-next upload cleanup.
    if (fp->hwdec)
        orp5_hwdec_frame_destroy(&fp->hwdec_frame);
    else
        ra_cleanup_pl_frame(p->ra, frame);
    // Free the mp_image reference itself.
""",
)

# Queue destruction runs source-frame unmap callbacks. Those callbacks now free
# per-frame mappers, so the bridge/hwdec drivers must outlive the queue.
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
    """    // Drain/unmap queued frames before tearing down their hwdec drivers.
    ra_next_queue_destroy(&p->queue);
    orp5_hwdec_bridge_destroy(&p->hwdec_bridge);
    for (int i = 0; i < ORP5_NV15_TEX_POOL_SIZE; i++) {
        for (int n = 0; n < 2; n++)
            pl_tex_destroy(p->ra->gpu, &p->nv15_pool[i].planes[n]);
    }
    pl_dispatch_destroy(&p->nv15_dispatch);
""",
)

print("orp5: fixed gpu-next hwdec lifetime with one mapper per queued frame")
