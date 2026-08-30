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
        raise SystemExit(f"{rel}: expected one EGL/GL bridge anchor, found {count}")
    path.write_text(data.replace(old, new, 1))


# The libmpv gpu-next backend owns a libplacebo OpenGL GPU, but libplacebo's
# OpenGL backend does not expose PL_HANDLE_DMA_BUF import on the Qt context used
# by Stremio. Recreate mpv's normal legacy OpenGL RA on that *same* client GL
# context instead. This lets hwdec_drmprime/v4l2request select mpv's proven EGL
# DMA-BUF importer (including the Rockchip NV15 byte-plane path), then wraps the
# resulting GL textures back into libplacebo without taking ownership.
replace_once(
    "video/out/gpu_next/hwdec_compat.h",
    """struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct mp_hwdec_devices *devs);
""",
    """struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct mp_hwdec_devices *devs,
    void *(*get_proc_address)(void *ctx, const char *name),
    void *get_proc_address_ctx);
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """#include <string.h>

#include \"common/msg.h\"
#include \"ta/ta_talloc.h\"
#include \"video/hwdec.h\"
#include \"video/img_format.h\"
#include \"video/out/gpu/context.h\"
#include \"video/out/gpu/hwdec.h\"
#include \"video/out/gpu/ra.h\"
#include \"video/out/placebo/ra_pl.h\"
""",
    """#include <string.h>
#include <EGL/egl.h>
#include <libplacebo/opengl.h>

#include \"common/msg.h\"
#include \"ta/ta_talloc.h\"
#include \"video/hwdec.h\"
#include \"video/img_format.h\"
#include \"video/out/gpu/context.h\"
#include \"video/out/gpu/hwdec.h\"
#include \"video/out/gpu/ra.h\"
#include \"video/out/opengl/common.h\"
#include \"video/out/opengl/ra_gl.h\"
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
};

struct orp5_hwdec_frame {
    struct ra_hwdec_mapper *mapper;
};
""",
    """struct orp5_hwdec_bridge {
    struct mp_log *log;
    struct mp_hwdec_devices *devs;
    pl_gpu gpu;
    GL *gl;
    struct ra *ra;
    struct ra_ctx ra_ctx;
    struct ra_hwdec_ctx hwdec_ctx;
};

struct orp5_hwdec_frame {
    struct ra_hwdec_mapper *mapper;
    pl_gpu gpu;
    pl_tex wrapped[4];
};
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
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
""",
    """struct orp5_hwdec_bridge *orp5_hwdec_bridge_create(
    struct mpv_global *global, struct mp_log *log, pl_gpu gpu,
    struct mp_hwdec_devices *devs,
    void *(*get_proc_address)(void *ctx, const char *name),
    void *get_proc_address_ctx)
{
    struct orp5_hwdec_bridge *b = talloc_zero(NULL, struct orp5_hwdec_bridge);
    b->log = log;
    b->devs = devs;
    b->gpu = gpu;

    if (!pl_opengl_get(gpu) || !get_proc_address) {
        MP_ERR(b, \"orp5: gpu-next hwdec bridge requires the OpenGL render API\\n\");
        talloc_free(b);
        return NULL;
    }

    // The render API client owns the GL context. Touching its resolver mirrors
    // the gpu-next context's make-current callback and ensures the Qt context is
    // current before the legacy EGL importer probes it.
    get_proc_address(get_proc_address_ctx, \"glGetString\");
    if (eglGetCurrentContext() == EGL_NO_CONTEXT ||
        eglGetCurrentDisplay() == EGL_NO_DISPLAY)
    {
        MP_ERR(b, \"orp5: no current EGL context for DMA-BUF hwdec interop\\n\");
        talloc_free(b);
        return NULL;
    }

    b->gl = talloc_zero(b, GL);
    mpgl_load_functions2(b->gl, get_proc_address, get_proc_address_ctx, NULL, log);
    b->ra = ra_create_gl(b->gl, log);
    if (!b->ra) {
        MP_ERR(b, \"orp5: creating legacy OpenGL RA for hwdec failed\\n\");
        talloc_free(b);
        return NULL;
    }
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """    MP_INFO(b, \"orp5: libmpv gpu-next hwdec bridge enabled\\n\");
    MP_INFO(b, \"orp5: per-frame hwdec mapper lifetime enabled\\n\");
""",
    """    MP_INFO(b, \"orp5: libmpv gpu-next hwdec bridge enabled\\n\");
    MP_INFO(b, \"orp5: per-frame hwdec mapper lifetime enabled\\n\");
    MP_INFO(b, \"orp5: legacy EGL DMA-BUF interop bridge enabled\\n\");
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """    struct orp5_hwdec_frame *f = talloc_zero(NULL, struct orp5_hwdec_frame);
    f->mapper = ra_hwdec_mapper_create(hwdec, src);
""",
    """    struct orp5_hwdec_frame *f = talloc_zero(NULL, struct orp5_hwdec_frame);
    f->gpu = b->gpu;
    f->mapper = ra_hwdec_mapper_create(hwdec, src);
""",
)

replace_once(
    "video/out/gpu_next/hwdec_compat.c",
    """void orp5_hwdec_frame_destroy(struct orp5_hwdec_frame **frame)
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
    """static void destroy_wrapped_textures(struct orp5_hwdec_frame *f)
{
    if (!f)
        return;
    for (int n = 0; n < 4; n++)
        pl_tex_destroy(f->gpu, &f->wrapped[n]);
}

void orp5_hwdec_frame_destroy(struct orp5_hwdec_frame **frame)
{
    struct orp5_hwdec_frame *f = frame ? *frame : NULL;
    if (!f)
        return;
    destroy_wrapped_textures(f);
    ra_hwdec_mapper_free(&f->mapper);
    talloc_free(f);
    *frame = NULL;
}

int orp5_hwdec_frame_map(struct orp5_hwdec_frame *f, struct mp_image *img)
{
    if (!f || !f->mapper)
        return -1;
    destroy_wrapped_textures(f);
    return ra_hwdec_mapper_map(f->mapper, img);
}

void orp5_hwdec_frame_unmap(struct orp5_hwdec_frame *f)
{
    if (!f || !f->mapper)
        return;
    // libplacebo wrappers carry no ownership of the GL textures, but must stop
    // referencing them before the EGL importer detaches/destroys its images.
    destroy_wrapped_textures(f);
    ra_hwdec_mapper_unmap(f->mapper);
}

pl_tex orp5_hwdec_frame_tex(struct orp5_hwdec_frame *f, int plane)
{
    if (!f || !f->mapper || plane < 0 || plane >= 4 || !f->mapper->tex[plane])
        return NULL;
    if (f->wrapped[plane])
        return f->wrapped[plane];

    struct ra_tex *ratex = f->mapper->tex[plane];
    GLuint texture = 0;
    GLenum target = 0;
    GLint iformat = 0;
    GLenum format = 0;
    GLenum type = 0;
    ra_gl_get_raw_tex(f->mapper->ra, ratex, &texture, &target);
    ra_gl_get_format(ratex->params.format, &iformat, &format, &type);
    if (!texture || !target || !iformat)
        return NULL;

    f->wrapped[plane] = pl_opengl_wrap(f->gpu, pl_opengl_wrap_params(
        .texture = texture,
        .width = ratex->params.w,
        .height = ratex->params.h,
        .target = target,
        .iformat = iformat,
    ));
    return f->wrapped[plane];
}
""",
)

# Thread the render client's OpenGL function resolver down to the bridge. This
# avoids linking/loading a second unrelated GL context and guarantees both RAs
# operate on the same Qt-owned objects.
replace_once(
    "video/out/gpu_next/video.h",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra,
                               struct mp_hwdec_devices *hwdec_devs);
""",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra,
                               struct mp_hwdec_devices *hwdec_devs,
                               void *(*get_proc_address)(void *ctx, const char *name),
                               void *get_proc_address_ctx);
""",
)

replace_once(
    "video/out/gpu_next/video.c",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra,
                               struct mp_hwdec_devices *hwdec_devs) {
""",
    """struct pl_video *pl_video_init(struct mpv_global *global, struct mp_log *log,
                               struct ra_next *ra,
                               struct mp_hwdec_devices *hwdec_devs,
                               void *(*get_proc_address)(void *ctx, const char *name),
                               void *get_proc_address_ctx) {
""",
)

replace_once(
    "video/out/gpu_next/video.c",
    """    p->hwdec_bridge = orp5_hwdec_bridge_create(global, log, ra->gpu, hwdec_devs);
""",
    """    p->hwdec_bridge = orp5_hwdec_bridge_create(
        global, log, ra->gpu, hwdec_devs,
        get_proc_address, get_proc_address_ctx);
""",
)

replace_once(
    "video/out/gpu_next/libmpv_gpu_next.c",
    """#include \"mpv/render.h\"                          // for mpv_render_param, mpv_render_param_type
""",
    """#include \"mpv/render.h\"                          // for mpv_render_param, mpv_render_param_type
#include \"mpv/render_gl.h\"                       // for mpv_opengl_init_params
""",
)

replace_once(
    "video/out/gpu_next/libmpv_gpu_next.c",
    """    // Create hardware decoder devices before the gpu-next video engine so
    // orp5 can install mpv's normal lazy V4L2-request loader.
    ctx->hwdec_devs = hwdec_devices_create();

    // Initialize our synchronous libplacebo rendering engine.
    p->video_engine = pl_video_init(ctx->global, ctx->log, p->context->ra,
                                    ctx->hwdec_devs);
""",
    """    // Create hardware decoder devices before the gpu-next video engine so
    // orp5 can install mpv's normal lazy V4L2-request loader.
    ctx->hwdec_devs = hwdec_devices_create();

    mpv_opengl_init_params *gl_params =
        get_mpv_render_param(params, MPV_RENDER_PARAM_OPENGL_INIT_PARAMS, NULL);
    if (!gl_params || !gl_params->get_proc_address) {
        hwdec_devices_destroy(ctx->hwdec_devs);
        ctx->hwdec_devs = NULL;
        p->context->fns->destroy(p->context);
        talloc_free(p->context);
        p->context = NULL;
        return MPV_ERROR_INVALID_PARAMETER;
    }

    // Initialize our synchronous libplacebo rendering engine and give the
    // hwdec bridge access to the exact GL resolver/context owned by Stremio.
    p->video_engine = pl_video_init(
        ctx->global, ctx->log, p->context->ra, ctx->hwdec_devs,
        gl_params->get_proc_address, gl_params->get_proc_address_ctx);
""",
)

print("orp5: switched gpu-next hwdec to legacy EGL DMA-BUF import + GL texture wrapping")
