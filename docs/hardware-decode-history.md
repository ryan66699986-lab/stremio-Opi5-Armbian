# RK3588 hardware-decode investigation history

This document records the board-level findings that led to the current Stremio ORP2 baseline and the later controlled ORP3 experiments. It is historical evidence, not a recommendation to restore the earlier ad-hoc test stack.

## Target system

The investigation was performed on an Orange Pi 5 Pro 4GB running the project Armbian / Ubuntu 26.04 Resolute image with Linux 7.2.2-edge-rockchip64 and KDE Plasma.

## Kernel decoder capabilities observed on board

The V4L2 stateless decoder nodes exposed the following formats:

- `rkvdec`: H.264 (`S264`) and HEVC (`S265`), capture to NV12;
- Hantro block: MPEG-2 (`MG2S`) and VP8 (`VP8F`), capture to NV12;
- RK3588 AV1 Hantro block: AV1 (`AV1F`), capture to VT12/NV12;
- a VP9 helper module was loaded, but no active decoder node exposed a VP9 compressed format during this test.

This established that the running kernel had the stateless decode plumbing needed for the mainline V4L2 Request path. AV1 and VP8 were discovered at the kernel-device level but were not playback-validated during this phase. VP9 was not proven.

## Isolated FFmpeg V4L2 Request proof

Before the packaged Stremio work, an isolated FFmpeg 8-compatible V4L2 Request build was installed under:

```text
/opt/ffmpeg-v4l2request
```

The build compiled the V4L2 Request backend and reported:

```text
Hardware acceleration methods:
drm
v4l2request
```

Direct FFmpeg decode tests proved RK3588 VPU operation for both H.264 and HEVC through `rkvdec`:

### H.264 synthetic 1080p60 test

- decoder selected through `v4l2request`;
- `rkvdec (7.2.2)` selected for `S264`;
- capture format NV12;
- hardware output format `drm_prime`;
- 1200 frames decoded with zero decode errors;
- approximately 5.7x realtime in the recorded test.

### HEVC synthetic 1080p60 test

- decoder selected through `v4l2request`;
- `rkvdec (7.2.2)` selected for `S265`;
- capture format NV12;
- hardware output format `drm_prime`;
- 1200 frames decoded with zero decode errors;
- approximately 12.2x realtime in the recorded test.

These tests settled the low-level question: the kernel and VPU can perform H.264 and HEVC hardware decode through V4L2 Request on this board.

## Stock mpv experiment with the isolated FFmpeg libraries

Ubuntu mpv 0.41 was then run with the isolated FFmpeg libraries injected with `LD_LIBRARY_PATH`.

The process loaded the private `libav*.so.62` libraries successfully and `mpv --hwdec=help` exposed both:

```text
v4l2request
v4l2request-copy
```

for H.264, HEVC, MPEG-2, VP8, VP9 and AV1.

The two mpv paths behaved differently in this early synthetic test:

### Direct `v4l2request`

For both H.264 and HEVC, mpv found the corresponding V4L2 Request decoder but reported:

```text
Could not create device.
Using software decoding.
```

So the direct mpv path was not usable in that particular stock-mpv + `LD_LIBRARY_PATH` arrangement.

### `v4l2request-copy`

For the same synthetic H.264 and HEVC samples, mpv reported:

```text
Using hardware decoding (v4l2request-copy).
```

and presented decoded NV12 frames through `gpu-next`.

This was an important integration proof at the time, but it must not be over-generalized. In particular, later real Stremio / HEVC Main10 testing demonstrated that copy-back is not a universal solution for RK3588 NV15/Main10 surfaces. Historical ORP3 copy-first work remains research-only.

## Cleanup state from the exploratory phase

After proving the path, the source tree, generated clips, logs and build-only development packages were removed. The isolated FFmpeg runtime under `/opt/ffmpeg-v4l2request` was retained at that point, while Ubuntu's system FFmpeg/libav and `/usr/bin/mpv` remained intact.

The current packaged Stremio work should be evaluated from the ORP2 private stack under `/opt/stremio/rk3588`; this older `/opt/ffmpeg-v4l2request` experiment is documented here only because it establishes independent board-level hardware-decode evidence and explains why V4L2 Request became the chosen architecture.

## Relationship to ORP2 runtime evidence

ORP2 later provided the more relevant application-level results inside Stremio:

- H.264/NV12 direct V4L2 Request decode and rendering works;
- at least one 4K HEVC Main10/NV15 sample direct-imports and renders correctly;
- a 1920x804 HEVC Main10/NV15 sample still hardware-decodes successfully but fails during DRM PRIME / DMA-BUF import with Mesa pitch-alignment errors.

Therefore the remaining target problem is not whether RK3588 can decode H.264/HEVC in hardware. It is the presentation/import behavior of specific NV15 Main10 surfaces.
