# Stremio ARM64 for Orange Pi 5 Pro / RK3588

Native ARM64 Stremio build for Orange Pi 5 Pro running Armbian/Ubuntu 26.04.

The package keeps its RK3588 FFmpeg/libmpv stack private under `/opt/stremio/rk3588` and uses V4L2-request hardware decoding with the RK3588 VPU.

## Current test build

`4.4.181-orp9`

`orp8` reached V4L2-request hardware decode on the Orange Pi 5 Pro but crashed on the first 4K HEVC Main10 DRM-PRIME frame. The concrete mismatch was in the NV15 OpenGL import path: Stremio's Qt render context is desktop OpenGL and exposes `GL_EXT_EGL_image_storage`, while the NV15 special case still used the OES-only EGLImage texture binding.

`orp9` keeps the previously exercised path and changes that NV15 import to use `glEGLImageTargetTexStorageEXT` on desktop OpenGL. Wrapped NV15 textures are recreated per mapped frame because EXT image storage is immutable.

The candidate includes:

- Stremio gpu-next rendering;
- V4L2-request decoding through `rkvdec`;
- DRM-PRIME hardware frames;
- EGL DMA-BUF import on the Qt desktop-OpenGL context;
- RK3588 Main10/NV15 GPU unpacking;
- render-thread hwdec preload;
- the single shared hwdec mapper used by `orp8`;
- desktop-OpenGL NV15 binding through `GL_EXT_EGL_image_storage`.

**`orp9` is not board-approved yet. Do not merge PR #5 until the physical acceptance test below passes.**

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
stremio_4.4.181-orp9_arm64.deb
```

Pinned source revisions are in `upstream.env`.

## Install

```bash
sudo apt purge stremio -y
sudo rm -rf /opt/stremio
sudo apt install ./stremio_4.4.181-orp9_arm64.deb
```

Run from a terminal when testing:

```bash
stremio 2>&1 | tee ~/stremio-orp9.log
```

## Board acceptance

Use the same 3840x2160 HEVC Main10 Dolby Vision/BT.2020/PQ stream used for the previous tests.

The build passes only when:

1. playback starts and continues normally without green corruption or a crash;
2. the log contains `Using hardware decoding (v4l2request)`;
3. the renderer no longer fails on the first DRM-PRIME/NV15 frame.

CI validates the ARM64 package and the private RK3588 multimedia linkage, but the physical Orange Pi test remains the playback authority.

## License

This is an unofficial build. Stremio and the bundled upstream projects retain their respective licenses. Repository-carried source changes are GPL-3.0; see `LICENSE.md`.
