# RK3588 hardware-decode investigation history

This document records the board-level findings that led to the ORP2 baseline and the later rejected ORP experiments. It is historical evidence, not a recommendation to restore the earlier ad-hoc test stack.

## Target system

The investigation was performed on an Orange Pi 5 Pro 4GB running the project Armbian / Ubuntu 26.04 Resolute image with Linux 7.2.2-edge-rockchip64 and KDE Plasma.

## Kernel decoder capabilities observed on board

The V4L2 stateless decoder nodes exposed the expected RK3588 media blocks. Direct FFmpeg tests established that the board and kernel can perform H.264 and HEVC hardware decode through V4L2 Request / `rkvdec`.

## ORP2 application-level evidence

ORP2 later provided the more relevant Stremio results:

- H.264/NV12 direct V4L2 Request decode and visual rendering works;
- 3840-wide HEVC Main10/NV15 can direct-import successfully at pitch 4800, but import success must not be treated as proof of correct visual presentation;
- a 1920x804 HEVC Main10/NV15 sample hardware-decodes successfully but fails during DRM PRIME / DMA-BUF import with Mesa pitch-alignment errors.

Later ORP10 physical testing made the distinction explicit: a 3840x2160 HEVC Main10 stream again used `v4l2request`, exported NV15 at pitch 4800, and repeatedly logged successful DMA-BUF import, while the actual displayed video remained green.

That means the previously recorded 3840-wide result is a **decode/import success**, not a validated end-to-end visual success.

The remaining HEVC/Main10 problem has at least two observed failure modes:

1. **1920-wide / pitch 2400:** Mesa rejects the DMA-BUF pitch during import.
2. **3840-wide / pitch 4800:** DMA-BUF import can succeed, yet the displayed image can still be visually wrong (green).

Future testing must record decoder success, surface layout, import outcome and actual visual correctness independently.

## Rejected experiments

ORP3 through ORP10 are archived research. Important conclusions include:

- disabling libavcodec direct rendering did not change the failing 1920-wide NV15 stride;
- copyback was not a general Main10 solution;
- forcing a larger NV15 `bytesperline` did not override the driver-generated layout;
- padding the capture width did not establish a correct HEVC/NV15 presentation path;
- successful NV15 import is insufficient evidence of correct rendering.

The complete archive status is in [`experimental-branches.md`](experimental-branches.md).

## Current direction

The project no longer creates another numbered local experiment for each hypothesis. The forward line tracks current upstream Stremio/RK3588 multimedia work and keeps ORP2 as a permanent rollback baseline.

See [`maintenance-policy.md`](maintenance-policy.md).
