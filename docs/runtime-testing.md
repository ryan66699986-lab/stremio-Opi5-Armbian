# Orange Pi 5 Pro runtime test checklist

Run these checks on a real Orange Pi 5 Pro after installing the package on the target Armbian / Ubuntu 26.04 image.

## Package and launch

```bash
sudo apt install ./stremio_4.4.181-orp1_arm64.deb
stremio
```

Confirm:

- `dpkg -s stremio` reports `Architecture: arm64`.
- the Stremio process starts without loader errors;
- the GUI appears in KDE Plasma;
- Qt WebEngine renders the application UI;
- the local Stremio server starts and the UI connects to it;
- libmpv initializes and video appears.

## Playback

Test representative streams and confirm:

- video playback;
- audio output;
- seeking forward/backward;
- subtitle selection and rendering;
- clean stop/exit and relaunch.

## Hardware acceleration

Hardware decoding is not proven by a successful package build. During playback, collect evidence from mpv logs and the kernel/media stack. Useful checks include:

```bash
stremio 2>&1 | tee stremio-runtime.log
journalctl -k -b | grep -Ei 'v4l2|rkvdec|mpp|video|drm'
```

Inspect the mpv output for the decoder actually selected. Do not mark hardware acceleration as working merely because `hwdec=auto` is accepted or because the UI plays video.

## Wayland / X11 diagnostics

If Qt WebEngine or the window fails under Wayland, record:

```bash
echo "$XDG_SESSION_TYPE"
echo "$WAYLAND_DISPLAY"
echo "$DISPLAY"
qtpaths --qt-version
```

For diagnosis only, compare behavior from an X11 Plasma session if one is available. Any required workaround should be documented from observed behavior rather than made a global package default without testing.

## Uninstall

```bash
sudo apt remove stremio
```

Confirm `/usr/bin/stremio` and `/opt/stremio` package-owned files are removed normally by dpkg.
