# ORP9 NV15 64-byte stride experiment

ORP9 is an **experimental physical-board candidate** built directly from current `main`, where ORP2 remains the only supported runtime baseline. Do not merge or promote ORP9 because CI passes.

## Single experiment

The pinned FFmpeg V4L2 Request stack is patched only at CAPTURE format negotiation for `V4L2_PIX_FMT_NV15`.

Before `VIDIOC_S_FMT`, FFmpeg requests a real NV15 `bytesperline` rounded up to 64 bytes. NV15 packs four 10-bit pixels into five bytes, so the candidate requests:

- width 1920: tightly packed 2400 -> requested **2432** bytes;
- width 3840: tightly packed 4800 -> requested **4800** bytes.

The patch does not rewrite the DRM PRIME descriptor after allocation. The V4L2 driver remains authoritative and may return a different stride. The returned capture format is what FFmpeg later exports in the DRM PRIME plane descriptor.

NV12, other capture formats, Stremio's hwdec mapping, mpv settings, and all pinned upstream revisions are unchanged. In particular, ORP9 does **not** reuse the rejected ORP3 `vd-lavc-dr=no` experiment or the historical gpu-next/copyback renderer work.

## What this experiment answers

The physical ORP2/clean-ORP3 evidence shows that decode succeeds before the failing import and that changing a generic libmpv direct-rendering setting did not alter NV15 pitch 2400. The narrow question for ORP9 is therefore:

> Can the existing RK3588 V4L2 Request capture queue negotiate an actually padded 64-byte-aligned NV15 layout, and if it can, does Mesa import the resulting 1920-wide DRM PRIME surface successfully?

A positive result tests the stride-alignment hypothesis without changing renderer architecture. A driver response that stays at 2400 is also useful: it would show that this userspace `VIDIOC_S_FMT` request is not sufficient to control the allocation and would move the next investigation below/around the driver allocator rather than toward another mpv toggle.

## Install

```bash
sudo apt install ./stremio_4.4.181-orp9_arm64.deb

dpkg-query -W -f='${Package} ${Version} ${Architecture}\n' stremio
```

Confirm exactly `stremio 4.4.181-orp9 arm64` before playback testing.

Run Stremio from a terminal and retain the complete log:

```bash
stremio 2>&1 | tee stremio-orp9-runtime.log
```

For NV15 streams, look for the new FFmpeg diagnostic:

```text
V4L2 Request NV15 capture pitch: requested <N>, negotiated <N>
```

Also retain the normal mpv/V4L2 evidence, especially `Using hardware decoding (v4l2request)`, decoder/media-driver selection, DRM PRIME format and pitch, and any DMA-BUF import error.

## Physical test order

1. **Known-failing HEVC Main10 1920x804 first.** Required success evidence: `hevc-v4l2request`, `rkvdec`, `Using hardware decoding (v4l2request)`, negotiated/requested NV15 pitch evidence, DRM PRIME NV15 pitch, and whether the image renders. The key expected experimental value is 2432 if the driver honors the request. Record any `WSI pitch not properly aligned`, NV15 import, DMA-BUF mapping, or hardware-surface mapping errors verbatim.
2. **Known-good H.264 1920x804 second.** It must remain `h264-v4l2request` / `rkvdec`, report `Using hardware decoding (v4l2request)`, remain DRM PRIME NV12 pitch 1920, and render successfully. Any regression here rejects ORP9.
3. **Known-good 3840-wide HEVC Main10 samples third.** Test 3840x2160 and, where available, 3840x1608. They must remain hardware decoded through V4L2 Request / `rkvdec`; expected NV15 pitch is 4800 and playback must remain successful.

## Acceptance / rejection

ORP9 may replace ORP2 only after physical testing shows the failing 1920-wide HEVC Main10 case is materially fixed **without** breaking the known-good H.264 or 3840-wide HEVC cases and while retaining `Using hardware decoding (v4l2request)`.

If 1920-wide NV15 still negotiates pitch 2400, negotiates 2432 but still fails import, hardware decoding falls back, or either control sample regresses, document the exact result, close/reject the candidate without merging, and keep ORP2 as the supported baseline. Any subsequent experiment must start fresh from current `main` / ORP2 rather than stacking on ORP9.
