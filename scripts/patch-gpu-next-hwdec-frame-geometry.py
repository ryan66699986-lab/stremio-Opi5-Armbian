#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {sys.argv[0]} <mpv-source-dir>")

root = Path(sys.argv[1])
path = root / "video/out/gpu_next/video.c"
data = path.read_text()


def replace_once(old, new):
    global data
    count = data.count(old)
    if count != 1:
        raise SystemExit(
            f"video/out/gpu_next/video.c: expected one geometry anchor, found {count}"
        )
    data = data.replace(old, new, 1)


# The queue can retain frames across a format/resolution transition. Size the
# NV15 unpack targets from the frame being acquired rather than the engine's
# mutable current_params state.
replace_once(
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
    """            .w = n ? p->current_params.w / 2 : p->current_params.w,
            .h = n ? p->current_params.h / 2 : p->current_params.h,
""",
    """            .w = n ? mpi->params.w / 2 : mpi->params.w,
            .h = n ? mpi->params.h / 2 : mpi->params.h,
""",
)

path.write_text(data)
print("orp5: bound NV15 unpack geometry to each queued frame")
