# Final native Stremio for Orange Pi 5 Pro / RK3588S

This is the final native-source path for the Orange Pi 5 Pro RK3588S target.

It uses the current stable `Stremio/stremio-linux-shell` release `v1.2.0` at commit `c6e7cd22e23ed6401e573fe7fe1a023fc07399a2`, linked against the project's pinned private RK3588 V4L2-request FFmpeg/libmpv stack under `/opt/stremio/rk3588`.

The distro multimedia stack is left intact. System Mesa, FFmpeg and mpv are not replaced.

## Install on the Orange Pi

Run as the normal desktop user:

```bash
rm -rf ~/stremio-rk3588s-final && \
git clone --depth 1 --branch final/native-rk3588s-v1.2.0-mainline \
  https://github.com/ryan66699986-lab/stremio-Opi5-Armbian.git \
  ~/stremio-rk3588s-final && \
bash ~/stremio-rk3588s-final/scripts/install-final-rk3588s.sh
```

Then launch normally:

```bash
stremio
```

## Final architecture

- Native Rust/GTK Stremio Linux shell, not Flatpak.
- Upstream Stremio release pinned to `v1.2.0` for reproducibility.
- Private V4L2-request FFmpeg/libmpv stack under `/opt/stremio/rk3588`.
- Stremio binary and `server.js` under `/opt/stremio`.
- `/usr/bin/stremio` is a small launcher; desktop integration uses that launcher.
- `STREMIO_RK3588_V4L2REQUEST=1` activates the RK3588-specific shell shim.
- The shim forces `hwdec=v4l2request-copy` at libmpv initialization and prevents the web UI from replacing it with another `hwdec` value.
- Copy-back is deliberate: decode remains on the RK3588S VPU while decoded frames are copied into the GL presentation path, avoiding the NV15 DMA-BUF import/presentation failure that blocked the direct path.
- No distro FFmpeg/mpv/Mesa libraries are overwritten.
- Existing Stremio application packages are removed, but the user's Stremio profile/data is not deleted.

## Reproducible build

For build-only use on native ARM64:

```bash
bash scripts/install-deps.sh
sudo apt-get install -y libgtk-4-dev libadwaita-1-dev libwebkitgtk-6.0-dev libepoxy-dev gettext nodejs rustc cargo
bash scripts/build-final-native-rk3588s.sh
```

The staged final application is produced at:

```text
.work/final-native-rk3588s/stage/opt/stremio
```

GitHub Actions performs this ARM64 build and archives the staged result. It does not run synthetic media playback tests.

## Preserved baseline

`baseline/orp2-working` remains untouched as the known-working Qt/ORP2 historical baseline. The final native-shell work is separate from that preserved branch.
