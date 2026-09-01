# ORP3 board test

ORP3 is a clean test candidate branched directly from the released ORP2 baseline.

It intentionally changes one runtime variable only:

- ORP2: `vd-lavc-dr=auto` (mpv default)
- ORP3: `vd-lavc-dr=no`

The pinned Stremio, FFmpeg, mpv/libmpv, and libplacebo revisions remain unchanged from ORP2. The hardware decode mapping remains `v4l2request,auto-safe`. No code from the historical ORP3 copy-first branch or any later gpu-next/custom copyback branch is carried forward.

## Why this test exists

ORP2 board logs proved that RK3588 V4L2-request hardware decoding works. H.264/NV12 rendered correctly and one 4K HEVC Main10/NV15 sample also rendered correctly. A 1920x804 HEVC Main10 sample reached hardware decode but failed while importing the NV15 DRM PRIME surface, with Mesa reporting that the WSI pitch was not properly aligned.

Disabling libavcodec direct rendering is a controlled diagnostic: it keeps the proven V4L2-request decoder path but asks mpv/libavcodec not to use the render-client direct-rendering allocation path. The test determines whether that allocation path is responsible for the failing NV15 stride/pitch.

## Acceptance sequence

1. Install ORP3 over ORP2.
2. Launch Stremio from a terminal and capture the complete log.
3. Confirm hardware acceleration is enabled in Stremio.
4. Test the same 1920x804 HEVC Main10 sample that failed under ORP2 first.
5. If it plays, test the known-good H.264/NV12 sample.
6. Then test the known-good 4K HEVC Main10/NV15 sample.

A useful result requires the log to still contain `Using hardware decoding (v4l2request)`.

For the previously failing 1920x804 sample, record whether the NV15 pitch changes and whether these ORP2 errors disappear:

- `WSI pitch not properly aligned`
- `Failed to import NV15`
- `Mapping hardware decoded surface failed`

If the same failure remains unchanged, reject ORP3 and return to ORP2. Do not add a second workaround to this branch; the next experiment should start fresh from ORP2 again.
