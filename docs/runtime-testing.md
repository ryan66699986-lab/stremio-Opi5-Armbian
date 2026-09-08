# Orange Pi 5 Pro runtime test checklist

Use this checklist on a real Orange Pi 5 Pro after installing a candidate package on the target Armbian / Ubuntu 26.04 system.

CI proves that the package builds, installs, and links to the private RK3588 multimedia stack. These checks prove what happens on the actual board.

## Confirmed ORP2 board findings

Physical Orange Pi 5 Pro testing established the following for the preserved ORP2 baseline:

- **H.264 1920x804:** `h264-v4l2request` selected the RK3588 `rkvdec` media driver and mpv reported `Using hardware decoding (v4l2request)`. The decoded DRM PRIME format was NV12 with pitch 1920 and it rendered successfully. This is the genuinely known-good visual playback path.
- **HEVC Main10 3840x2160:** `hevc-v4l2request` selected `rkvdec` and mpv reported `Using hardware decoding (v4l2request)`. The decoded DRM PRIME format was NV15 with pitch 4800 and the DMA-BUF imported successfully. **Do not treat that import as proof of correct visual presentation.** Later ORP10 physical testing reproduced the same successful decode/import characteristics while the actual screen was green.
- **HEVC Main10 1920x804:** `hevc-v4l2request` again selected `rkvdec` and hardware decoding succeeded, but presentation failed after decode. The NV15 DRM PRIME surface had pitch 2400 and Mesa reported `WSI pitch not properly aligned`, followed by NV15 DMA-BUF import / hardware-surface mapping failure.

These results separate several layers that must not be conflated. ORP2 proved that the RK3588 V4L2 Request decoder path is functional for H.264 and HEVC Main10. The unresolved HEVC/Main10 problem is presentation of NV15 hardware-decoded surfaces.

For every HEVC/NV15 result, record separately:

1. decoder success (`Using hardware decoding (v4l2request)`),
2. DRM PRIME format and pitch,
3. DMA-BUF import success/failure,
4. actual on-screen visual correctness.

A successful `Imported DRM NV15...` log line proves only the import step. It does not prove the displayed pixels are correct.

## Current-line comparison test

The first current-line candidate is not just another ORP2 package rebuild. It changes from the legacy Qt shell to the official Rust/GTK `stremio-linux-shell`, whose video host uses GTK `GLArea` and libmpv's OpenGL render context.

As of the initial migration on 2026-09-06, Ryan Fitzgerald's FFmpeg and mpv-rockchip branch heads were still the same commits used by ORP2. Therefore the first current test is especially useful as an application/presentation comparison rather than as proof of a new decoder implementation.

Use the same representative streams that established the ORP2 baseline where possible and compare:

| Test | ORP2 reference | Current result to record |
| --- | --- | --- |
| H.264 1920x804 | V4L2 Request + rkvdec, NV12 pitch 1920, visually correct | decoder, format/pitch, visual correctness |
| HEVC Main10 1920x804 | V4L2 Request decode succeeds, NV15 pitch 2400, import fails | decoder, pitch, import result, visual result |
| HEVC Main10 3840x2160 | V4L2 Request decode succeeds, NV15 pitch 4800, import succeeds; visual correctness not established by import | decoder, pitch, import result, actual screen result |

Do not declare current better merely because the UI launches or because the same import log appears. The meaningful question is whether actual playback behavior changes.

## Install and verify package layout

For the frozen ORP2 fallback:

```bash
sudo apt install ./stremio_4.4.181-orp2_arm64.deb
```

For a current candidate, install the generated `stremio_*current_arm64.deb` package.

Then inspect the installed package:

```bash
dpkg-query -W -f='${Package} ${Version} ${Architecture}\n' stremio
file /opt/stremio/stremio
ldd /opt/stremio/stremio | tee stremio-ldd.log
strings "$(readlink -f /opt/stremio/rk3588/lib/libmpv.so)" | grep -m1 v4l2request
```

Confirm:

- package architecture is `arm64`;
- `/opt/stremio/stremio` is AArch64;
- `libmpv.so`, `libavcodec.so`, `libavformat.so`, and related private libraries resolve from `/opt/stremio/rk3588/lib`;
- the private libmpv contains `v4l2request` support.

ORP2 and current do not necessarily have identical launcher/RPATH details because the Stremio shell implementation changed. Judge linkage by the actual installed library resolution, not by assuming the old Qt executable layout must remain byte-for-byte identical.

If private multimedia libraries do not resolve correctly, stop before playback testing. Do not copy replacement libraries into `/usr/lib`.

## Launch and UI

Capture terminal output during launch:

```bash
stremio 2>&1 | tee stremio-runtime.log
```

Confirm the application starts, the UI renders, the Stremio service connects, libmpv initializes, and video can actually be displayed.

For current, also watch for GTK4/libadwaita/WebKitGTK or GL-context failures that did not exist in the old Qt shell.

## Playback behavior

Test representative media and confirm:

- video playback and **actual visual correctness**;
- audio output;
- seeking forward and backward;
- subtitle selection and rendering;
- pause/resume;
- clean stop/exit;
- successful relaunch after exit.

Record codec/profile and resolution for each test. A result for one H.264/HEVC profile does not prove every profile.

## Hardware decoding evidence

During playback, keep Stremio output and collect kernel/media evidence where useful:

```bash
journalctl -k -b | grep -Ei 'v4l2|rkvdec|request|media|video|drm'
ls -l /dev/video* /dev/media* 2>/dev/null || true
```

For each hardware-decoding test, record:

- codec and profile;
- resolution and frame rate;
- whether `v4l2request` was selected;
- relevant `rkvdec` / V4L2 Request messages;
- hardware frame format (`NV12`, `NV15`, etc.);
- DRM PRIME pitch/stride where reported;
- DMA-BUF import or mapping errors;
- whether the **actual displayed image is visually correct** (including green/black/corrupt output);
- whether playback remains stable while seeking.

Do not mark hardware acceleration or visual playback as working merely because `hwdec=auto` is accepted, playback is smooth, or a DMA-BUF import succeeds.

## Pass criteria

Promote a current build only when all of these are true on the target Orange Pi 5 Pro:

- package layout/private-library linkage are correct;
- UI launches and renders normally;
- normal playback controls work;
- tested hardware-decodable streams use the expected RK3588 hardware path;
- tested video is actually visually correct on-screen;
- the known-good H.264 path has not regressed;
- HEVC/NV15 results are explicitly compared against the ORP2 evidence rather than inferred from logs;
- no system multimedia libraries had to be replaced manually;
- uninstall completes normally.

If a current build regresses, fall back to `baseline/orp2-working` rather than carrying another local ORP experiment forward.
