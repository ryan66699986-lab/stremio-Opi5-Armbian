# Stremio ARM64 for Orange Pi 5 Pro / RK3588

Native ARM64 Stremio build for Orange Pi 5 Pro running Armbian/Ubuntu 26.04.

The package keeps its RK3588 FFmpeg/libmpv stack private under `/opt/stremio/rk3588` and uses V4L2-request hardware decoding with the RK3588 VPU.

## Current test build

`4.4.181-orp8`

`orp8` keeps the parts already proven on the board:

- Stremio gpu-next rendering;
- V4L2-request decoding through `rkvdec`;
- DRM-PRIME hardware frames;
- EGL DMA-BUF import on the Qt/OpenGL context;
- RK3588 Main10/NV15 GPU unpacking;
- render-thread hwdec preload.

It removes the extra per-frame hwdec mapper layer and uses one mapper like the working Rockchip `vo_gpu_next` path.

## Build

Use native ARM64 Ubuntu 26.04:

```bash
git clone https://github.com/ryan66699986-lab/stremio-Opi5-Armbian.git
cd stremio-Opi5-Armbian
./scripts/install-deps.sh
./scripts/build-rk3588-stack.sh
./scripts/build.sh
./scripts/build-deb.sh
```

Output:

```text
stremio_4.4.181-orp8_arm64.deb
```

Pinned source revisions are in `upstream.env`.

## Install

```bash
sudo apt purge stremio -y
sudo rm -rf /opt/stremio
sudo apt install ./stremio_4.4.181-orp8_arm64.deb
```

Run from a terminal when testing:

```bash
stremio 2>&1 | tee ~/stremio-orp8.log
```

## Board acceptance

Use the same 4K HEVC Main10 stream used for previous tests.

The build passes when:

1. video plays normally with no green corruption or crash;
2. the log contains `Using hardware decoding (v4l2request)`.

The physical Orange Pi test is the playback authority. CI only builds the ARM64 package.

## License

This is an unofficial build. Stremio and the bundled upstream projects retain their respective licenses. Repository-carried source changes are GPL-3.0; see `LICENSE.md`.
