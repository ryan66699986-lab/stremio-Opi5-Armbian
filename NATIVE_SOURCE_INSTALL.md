# Native Stremio source install

This is the clean native-source path for the current `Stremio/stremio-linux-shell` Rust/GTK client.

The installer intentionally does **not** accept software video decoding as success. On Rockchip/RK3588 it requires the system `mpv/libmpv` stack to expose `v4l2request` or `rkmpp`; otherwise it stops with the inspection output instead of installing a misleading CPU-decoding setup.

## Run on the target Linux desktop

Run this as the normal desktop user, not from a root shell. The script invokes `sudo` only for system package/install operations.

```bash
rm -rf ~/stremio-native-installer && \
git clone --depth 1 --branch native-stremio-source-install \
  https://github.com/ryan66699986-lab/stremio-Opi5-Armbian.git \
  ~/stremio-native-installer && \
bash ~/stremio-native-installer/scripts/install-native-stremio.sh 2>&1 | tee ~/stremio-native-install.log
```

## What it does

1. Reads `/etc/os-release`, kernel/architecture and the device tree.
2. Inspects GPU/display state with `lspci`, `glxinfo`, `/dev/dri`, and Rockchip/Mali/Panfrost/Panthor device-tree detection.
3. Detects the package manager and existing compiler/build tools.
4. Inspects installed GTK4, libadwaita, WebKitGTK, libmpv and libepoxy versions.
5. Detects existing Stremio Flatpak, Snap, Debian/RPM/pacman and manual/native installations.
6. Removes those existing Stremio installations while leaving the user's Stremio profile/data alone.
7. Uses the detected package manager's search command before installing the distro-equivalent dependencies from the upstream README.
8. Verifies the API versions required by current Stremio source.
9. Inspects `mpv --hwdec=help`, FFmpeg hwaccels and video devices. On RK3588, `v4l2request` or `rkmpp` is mandatory.
10. Where a copy-back hwdec exists, creates a small H.264 test clip and proves the decoder/device can actually hardware-decode it.
11. Resolves the latest stable upstream Stremio release, clones that exact tag recursively, and builds it with Cargo in release mode.
12. Installs the native app to standard paths:
    - `/usr/local/libexec/stremio/stremio`
    - `/usr/local/libexec/stremio/server.js`
    - `/usr/bin/stremio`
    - desktop/icon/metainfo/schema files under `/usr/share`
13. Installs `/usr/bin/stremio` as a wrapper which sets `SERVER_PATH` and `LC_NUMERIC=C`, plus the upstream GPU-specific environment overrides where applicable.
14. Removes `DBusActivatable=true` from the installed desktop file.
15. Compiles the GLib schema and checks the installed binary for unresolved shared libraries.
16. Launch-smoke-tests Stremio when a graphical session is available.
17. Installs and enables the daily `stremio-native-update.timer` **user** timer.

## Daily updates

The timer checks the upstream GitHub release once per day. If a newer stable release exists it rebuilds it as the desktop user and installs it under:

```text
~/.local/libexec/stremio/releases/<tag>
```

`/usr/bin/stremio` automatically prefers the newest successfully built user-local release and falls back to the system baseline if none exists. This avoids giving a user systemd timer passwordless root access.

Check the timer with:

```bash
systemctl --user status stremio-native-update.timer
systemctl --user list-timers stremio-native-update.timer
```

## Final embedded hardware-decode proof

The installer proves that the system libmpv has the required hardware backend and, where possible, that the decoder device actually works. To prove the same path from inside Stremio, launch it once with debug logging:

```bash
RUST_LOG=debug stremio 2>&1 | tee ~/stremio-hwdec.log
```

Play a known hardware-decodable title, then inspect:

```bash
grep -Ei 'hwdec|hardware decoding|drm_prime|v4l2request|rkmpp|vaapi|vulkan|nvdec' ~/stremio-hwdec.log
```

For RK3588, success means the log shows `v4l2request` or `rkmpp` hardware decoding and does **not** report a software-decoding fallback.
