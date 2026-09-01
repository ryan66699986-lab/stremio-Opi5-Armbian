# ORP10 NV15 capture-width experiment

ORP10 is an experimental physical-board candidate. ORP2 remains the supported runtime baseline and ORP10 must not be merged merely because CI passes.

## Why this experiment exists

Physical ORP9 testing showed that a direct userspace NV15 `bytesperline=2432` request for 1920-wide HEVC Main10 was ignored: rkvdec negotiated 2400 and Mesa again rejected the DMA-BUF with `WSI pitch not properly aligned`.

The Linux rkvdec capture-format path derives `bytesperline` from capture width using `v4l2_fill_pixfmt_mp()`. For HEVC the driver permits capture width at least as large as coded width and applies its frame-size constraints. ORP10 therefore changes one thing only: for NV15 CAPTURE, FFmpeg asks for capture width rounded up to 256 pixels before `VIDIOC_S_FMT`.

Expected layout if the driver honors the larger capture width:

- coded/visible width 1920 -> requested capture width 2048 -> expected NV15 pitch 2560 (64-byte aligned)
- coded/visible width 3840 -> requested capture width 3840 -> expected NV15 pitch 4800 (unchanged)
- NV12/H.264 and all non-NV15 formats -> unchanged

The Stremio, FFmpeg, mpv-rockchip and libplacebo upstream commit pins are unchanged from ORP2.

## What to capture from each stream

Stream order does not matter. For every tested stream, save enough terminal output to identify codec/profile, dimensions, `Using hardware decoding (v4l2request)`, the ORP10 `V4L2 Request NV15 capture layout` diagnostic when present, DRM PRIME fourcc/pitch, and whether video rendered.

The three most useful cases are:

1. HEVC Main10 around 1920x804. Desired result: requested width 2048, negotiated width 2048, pitch 2560, `Using hardware decoding (v4l2request)`, DRM PRIME NV15 pitch 2560, and successful import/render with no Mesa pitch-alignment error.
2. H.264 around 1920x804. Must remain V4L2 Request/rkvdec, DRM PRIME NV12 pitch 1920, and render normally. No ORP10 NV15 layout diagnostic is expected.
3. 3840-wide HEVC Main10 such as 3840x2160 or 3840x1608. Must remain V4L2 Request/rkvdec, requested/negotiated capture width 3840, NV15 pitch 4800, and render normally.

## Acceptance / rejection

ORP10 is interesting only if the failing 1920-wide Main10 case genuinely receives a larger driver-allocated capture layout and renders successfully without regressing known-good paths.

Reject ORP10 and leave ORP2 supported if any of these occur:

- rkvdec negotiates capture width back to 1920 and pitch 2400;
- capture width becomes 2048/another padded value but DRM PRIME still exports pitch 2400;
- padded layout causes decode/control/IOMMU/buffer errors;
- NV15 remains unimportable despite an aligned pitch;
- H.264/NV12 or known-good 3840-wide HEVC regresses;
- hardware decoding falls back from `v4l2request`.

If rejected, document the physical result, close the ORP10 PR unmerged, keep ORP2 as the supported runtime, and start the next experiment fresh from `main`.
