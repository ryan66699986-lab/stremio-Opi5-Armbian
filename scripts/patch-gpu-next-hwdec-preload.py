#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} <mpv-source-dir>")

root = Path(sys.argv[1])
path = root / "video/out/gpu_next/hwdec_compat.c"
data = path.read_text()


def replace_once(old, new, label):
    global data
    count = data.count(old)
    if count != 1:
        raise SystemExit(f"hwdec_compat.c: expected one {label} anchor, found {count}")
    data = data.replace(old, new, 1)


# Normal vo_gpu_next does not run the hwdec loader directly from the decoder
# requester. It marshals VOCTRL_LOAD_HWDEC_API through the video-output path,
# where the graphics context can be made current before EGL interop probes run.
# The draft libmpv gpu-next backend has no equivalent VO control path, so orp6's
# direct lazy callback could execute after Qt had released the EGL context from
# the calling thread. Rockchip's dmabuf_interop_gl_init() then rejects the probe
# immediately at eglGetCurrentContext(), even though the same legacy GL RA was
# successfully constructed during render-context initialization.
#
# Preload every DRM-PRIME interop while libmpv is still creating the render
# context and Qt's EGL context is current. In particular this registers the
# V4L2-request AVHWDeviceContext before the decoder asks for it. Keep the lazy
# loader for other formats/fallbacks, but don't re-run a DRM-PRIME EGL probe from
# the requester once the V4L2-request device is already available.
replace_once(
    """static void load_hwdec_api(void *ctx, struct hwdec_imgfmt_request *params)
{
    struct orp5_hwdec_bridge *b = ctx;
    ra_hwdec_ctx_load_fmt(&b->hwdec_ctx, b->devs, params);
}
""",
    """static void load_hwdec_api(void *ctx, struct hwdec_imgfmt_request *params)
{
    struct orp5_hwdec_bridge *b = ctx;
    if (params->imgfmt == IMGFMT_DRMPRIME &&
        hwdec_devices_get_by_imgfmt_and_type(
            b->devs, IMGFMT_DRMPRIME, AV_HWDEVICE_TYPE_V4L2REQUEST))
    {
        MP_VERBOSE(b, \"orp7: V4L2-request DRM-PRIME device already preloaded\\n\");
        return;
    }
    ra_hwdec_ctx_load_fmt(&b->hwdec_ctx, b->devs, params);
}
""",
    "lazy loader",
)

replace_once(
    """    hwdec_devices_set_loader(devs, load_hwdec_api, b);
    ra_hwdec_ctx_init(&b->hwdec_ctx, devs, \"auto\", false);
    MP_INFO(b, \"orp5: libmpv gpu-next hwdec bridge enabled\\n\");
""",
    """    hwdec_devices_set_loader(devs, load_hwdec_api, b);
    ra_hwdec_ctx_init(&b->hwdec_ctx, devs, \"auto\", false);

    struct hwdec_imgfmt_request drmprime_request = {
        .imgfmt = IMGFMT_DRMPRIME,
        .probing = true,
    };
    ra_hwdec_ctx_load_fmt(&b->hwdec_ctx, b->devs, &drmprime_request);

    if (hwdec_devices_get_by_imgfmt_and_type(
            b->devs, IMGFMT_DRMPRIME, AV_HWDEVICE_TYPE_V4L2REQUEST))
    {
        MP_INFO(b, \"orp7: V4L2-request DRM-PRIME hwdec preloaded on render/EGL thread\\n\");
    } else {
        MP_WARN(b, \"orp7: V4L2-request DRM-PRIME preload did not create a device\\n\");
    }

    MP_INFO(b, \"orp5: libmpv gpu-next hwdec bridge enabled\\n\");
""",
    "render-thread preload",
)

path.write_text(data)
print("orp7: preloaded V4L2-request DRM-PRIME interop while EGL context is current")
