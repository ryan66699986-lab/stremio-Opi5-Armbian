#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} <mpv-source-dir>")

path = Path(sys.argv[1]) / "video/out/gpu_next/hwdec_compat.c"
data = path.read_text()


def replace_once(old, new):
    global data
    if data.count(old) != 1:
        raise SystemExit("hwdec_compat.c: preload patch anchor not found exactly once")
    data = data.replace(old, new, 1)


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
        return;
    ra_hwdec_ctx_load_fmt(&b->hwdec_ctx, b->devs, params);
}
""",
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

    MP_INFO(b, \"orp5: libmpv gpu-next hwdec bridge enabled\\n\");
""",
)

path.write_text(data)
