# Orange Pi 5 Pro runtime test checklist

Use this checklist on a real Orange Pi 5 Pro after installing the `orp2` package on the target Armbian / Ubuntu 26.04 system.

CI proves that the package builds, installs, and links to the private RK3588 multimedia stack. These checks prove what happens on the actual board.

## Confirmed ORP2 board findings

Physical Orange Pi 5 Pro testing has established the following for the released ORP2 baseline:

- **H.264 1920x804:** `h264-v4l2request` selected the RK3588 `rkvdec` media driver and mpv reported `Using hardware decoding (v4l2request)`. The decoded DRM PRIME format was NV12 with pitch 1920 and it rendered successfully.
- **HEVC Main10 3840x2160:** `hevc-v4l2request` selected `rkvdec` and mpv reported `Using hardware decoding (v4l2request)`. The decoded DRM PRIME format was NV15 with pitch 4800 and this sample rendered successfully.
- **HEVC Main10 1920x804:** `hevc-v4l2request` again selected `rkvdec` and hardware decoding succeeded, but presentation failed after decode. The NV15 DRM PRIME surface had pitch 2400 and Mesa reported `WSI pitch not properly aligned`, followed by NV15 DMA-BUF import / hardware-surface mapping failure.

These results are important because they separate the remaining failure from decoder selection. ORP2 has proved that the RK3588 V4L2 Request decoder path is functional for both H.264 and HEVC Main10. The unresolved problem is dimension/stride-sensitive presentation of some NV15 hardware-decoded surfaces through the Stremio/libmpv OpenGL render path.

Do not generalize one successful 4K NV15 sample to all HEVC Main10 content: the 3840-wide pitch-4800 sample imported successfully while the 1920-wide pitch-2400 sample did not.

## Install and verify package layout

```bash
sudo apt install ./stremio_4.4.181-orp2_arm64.deb

dpkg-query -W -f='${Package} ${Version} ${Architecture}\n' stremio
readlink -f /usr/bin/stremio
patchelf --print-rpath /opt/stremio/stremio
ldd /opt/stremio/stremio | tee stremio-ldd.log
strings "$(readlink -f /opt/stremio/rk3588/lib/libmpv.so)" | grep -m1 v4l2request
```

Confirm:

- the installed version is `4.4.181-orp2` and architecture is `arm64`;
- `/usr/bin/stremio` resolves to `/opt/stremio/stremio`;
- Stremio's RPATH is `$ORIGIN/rk3588/lib`;
- `libmpv.so` resolves from `/opt/stremio/rk3588/lib`;
- `libavcodec.so`, `libavformat.so`, and related private FFmpeg libraries resolve from `/opt/stremio/rk3588/lib`;
- the private libmpv contains `v4l2request` support.

If any of those fail, stop before playback testing. Do not copy replacement libraries into `/usr/lib`.

## Launch and UI

Capture terminal output during the first launch:

```bash
stremio 2>&1 | tee stremio-runtime.log
```

Confirm:

- the Stremio process starts without loader errors;
- the GUI appears in the desktop session;
- Qt WebEngine renders the application UI;
- the local Stremio server starts and the UI connects to it;
- libmpv initializes and video can be displayed.

## Playback behavior

Test representative media and confirm:

- video playback;
- audio output;
- seeking forward and backward;
- subtitle selection and rendering;
- pause/resume;
- clean stop/exit;
- successful relaunch after exit.

Record the codec and profile for each test file or stream. A result for one H.264/HEVC profile does not prove every profile is supported by the hardware path.

## Hardware decoding evidence

Successful playback is not enough to prove hardware decoding. During playback, keep Stremio output and collect kernel/media evidence:

```bash
journalctl -k -b | grep -Ei 'v4l2|rkvdec|request|media|video|drm'
```

Also inspect the running system's media devices where available:

```bash
ls -l /dev/video* /dev/media* 2>/dev/null || true
```

The package's patch makes generic Stremio `hwdec=yes` / `hwdec=auto` requests try `v4l2request` first, but the runtime result must still be confirmed from the decoder actually selected and from the RK3588 media-driver activity.

For each hardware-decoding test, record:

- codec and profile;
- resolution and frame rate;
- whether `v4l2request` was selected;
- relevant `rkvdec` / V4L2 Request kernel messages;
- hardware frame format (`nv12`, `NV15`, etc.);
- DRM PRIME pitch/stride where reported;
- any DMA-BUF import or mapping errors;
- whether playback remained stable while seeking;
- CPU load as supporting evidence only, not as the primary proof.

Do not mark hardware acceleration as working merely because `hwdec=auto` is accepted or because playback is smooth.

## Desktop/session diagnostics

If Qt WebEngine, rendering, or the window fails, record:

```bash
echo "$XDG_SESSION_TYPE"
echo "$WAYLAND_DISPLAY"
echo "$DISPLAY"
qtpaths --qt-version
```

If another desktop session is available, compare behavior only as a diagnostic step. Avoid making global package changes such as disabling Wayland, sandboxing, or GPU features unless a reproduced target-specific failure proves they are required.

## Uninstall

```bash
sudo apt remove stremio
```

Confirm `/usr/bin/stremio` and the package-owned files under `/opt/stremio` are removed normally by dpkg.

## Pass criteria

Mark the release as board-validated only when all of these are true on the target Orange Pi 5 Pro:

- package layout and private-library linkage are correct;
- UI launches and renders normally;
- normal playback controls work;
- tested hardware-decodable streams select the RK3588 V4L2 Request path with supporting runtime evidence;
- no system multimedia libraries had to be replaced or manually copied;
- uninstall completes normally.
