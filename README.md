# Stremio ARM64 for Orange Pi 5 Pro / RK3588

This repository produces an **unofficial native ARM64 build of Stremio for Orange Pi 5 Pro / compatible RK3588 boards running Armbian on Ubuntu 26.04**. It is not an official Stremio distribution.

The current package is **Stremio 4.4.181-orp2**. It bundles an isolated, pinned RK3588 V4L2-request FFmpeg/libmpv stack under `/opt/stremio/rk3588` so Stremio can use the mainline RK3588 request-decoder userspace path without replacing the system multimedia libraries.

## Current release

| Item | Value |
| --- | --- |
| Hardware target | Orange Pi 5 Pro / RK3588 |
| Architecture | ARM64 / AArch64 |
| OS | Armbian |
| Base distribution | Ubuntu 26.04 “Resolute Raccoon” |
| Stremio shell | 4.4.181 |
| Package revision | `orp2` |
| Debian package | `stremio_4.4.181-orp2_arm64.deb` |
| Private multimedia prefix | `/opt/stremio/rk3588` |
| Release tag | `v4.4.181-orp2` |

Release page:

https://github.com/ryan66699986-lab/stremio-Opi5-Armbian/releases/tag/v4.4.181-orp2

## What `orp2` does

`orp2` keeps the official Stremio 4.4.181 shell as the application base and adds the RK3588-specific multimedia path in a contained way:

- builds the exact pinned official Stremio shell source;
- builds a pinned FFmpeg with V4L2-request enabled;
- builds a pinned mpv/libmpv with `v4l2request` enabled;
- bundles the resulting private multimedia libraries under `/opt/stremio/rk3588/lib`;
- links Stremio against that private libmpv instead of Ubuntu's system libmpv;
- gives `/opt/stremio/stremio` the RPATH `$ORIGIN/rk3588/lib`;
- gives the private multimedia libraries an `$ORIGIN` RPATH so they resolve their peers inside the private stack;
- maps Stremio's generic `hwdec=yes` / `hwdec=auto` request to try `v4l2request` first and then fall back to mpv's normal safe methods;
- fixes Qt WebEngine/OpenGL-context initialization ordering for the ARM64 desktop shell;
- packages everything as a normal Debian package without overwriting distribution multimedia libraries.

The package does not install private FFmpeg/libmpv files into `/usr/lib` and does not replace the OS multimedia stack.

## Pinned sources

All external source revisions are recorded in [`upstream.env`](upstream.env). The current `orp2` pins are:

| Component | Commit |
| --- | --- |
| Stremio shell 4.4.181 | `41659b91c27fbb5812b167a04f2fdc50c82d4e9f` |
| RK3588 FFmpeg | `151f3befc4593d7f8c57946b3338005bdf8ae262` |
| RK3588 mpv/libmpv | `5cf2859a320626a3588622b448292815caf419fc` |
| libplacebo | `cee9b076f2c63104ccfd497fa79c39a867293ec4` |

The build scripts perform clean pinned checkouts rather than tracking moving branches.

## Native ARM64 build

Use a native ARM64 Ubuntu 26.04 environment. The scripts reject non-ARM64 hosts.

```bash
git clone https://github.com/ryan66699986-lab/stremio-Opi5-Armbian.git
cd stremio-Opi5-Armbian

./scripts/install-deps.sh
./scripts/build-rk3588-stack.sh
./scripts/build.sh
./scripts/build-deb.sh
```

The output is:

```text
stremio_4.4.181-orp2_arm64.deb
```

The build order is intentional. `build.sh` refuses to continue unless the private RK3588 multimedia stack has already been built, and `build-deb.sh` refuses to package unless both the Stremio executable and private stack exist.

## Install

```bash
sudo apt install ./stremio_4.4.181-orp2_arm64.deb
stremio
```

Uninstall normally with:

```bash
sudo apt remove stremio
```

## Verify the installed package

The release CI performs these checks automatically, and they can also be repeated on the target system:

```bash
dpkg-query -W -f='${Package} ${Version} ${Architecture}\n' stremio
readlink -f /usr/bin/stremio
patchelf --print-rpath /opt/stremio/stremio
ldd /opt/stremio/stremio
strings "$(readlink -f /opt/stremio/rk3588/lib/libmpv.so)" | grep -m1 v4l2request
```

Expected key results:

- package architecture is `arm64`;
- `/usr/bin/stremio` resolves to `/opt/stremio/stremio`;
- Stremio's RPATH is `$ORIGIN/rk3588/lib`;
- `libmpv.so` and `libavcodec.so` resolve from `/opt/stremio/rk3588/lib`;
- the bundled libmpv contains V4L2-request support.

For package-level validation without installing it:

```bash
./scripts/validate-deb.sh stremio_4.4.181-orp2_arm64.deb
```

## GitHub Actions and release gate

`.github/workflows/build-arm64.yml` uses GitHub's native `ubuntu-26.04-arm` runner. The release workflow:

1. confirms the runner is native ARM64;
2. installs Ubuntu 26.04 build dependencies;
3. inspects the known reference ARM64 package;
4. builds the pinned RK3588 FFmpeg/libmpv stack;
5. builds the pinned official Stremio shell against that private stack;
6. creates `stremio_4.4.181-orp2_arm64.deb`;
7. runs explicit Debian-package validation;
8. installs the package with apt;
9. verifies Stremio's private RPATH and `libmpv` / `libavcodec` resolution;
10. verifies the bundled libmpv contains `v4l2request`;
11. uploads the Debian package as a workflow artifact;
12. on a successful push to `main`, publishes or updates release `v4.4.181-orp2`.

A green CI run proves native ARM64 compilation, packaging, installability, uninstallability, and private multimedia linkage. It cannot prove the physical board's kernel/media-device behavior or a particular stream's decoder selection.

## Runtime testing on Orange Pi 5 Pro

See [`docs/runtime-testing.md`](docs/runtime-testing.md) for the real-board checklist. Hardware decoding must be confirmed from runtime evidence on the Orange Pi rather than inferred from smooth playback or from the build succeeding.

## Troubleshooting

### UI is blank or Qt WebEngine fails

Run Stremio from a terminal and keep the Qt/Chromium output:

```bash
stremio 2>&1 | tee stremio-runtime.log
```

Record `XDG_SESSION_TYPE`, `WAYLAND_DISPLAY`, and `DISPLAY` before applying session-specific workarounds.

### Private libraries are not being used

Do not copy libraries manually into `/usr/lib`. Check the installed loader state:

```bash
patchelf --print-rpath /opt/stremio/stremio
ldd /opt/stremio/stremio | grep -E 'libmpv|libavcodec|libavformat|libavutil'
```

The RK3588 multimedia libraries should resolve from `/opt/stremio/rk3588/lib`.

### Hardware acceleration is not selected

Capture Stremio/mpv output and kernel/media-driver evidence as described in [`docs/runtime-testing.md`](docs/runtime-testing.md). `hwdec=auto` by itself is not proof that RKVDEC is decoding the stream.

## Known limitations

- The final release still requires real-board playback validation for the exact target kernel, display session, media file/stream, and codec profile being used.
- The Stremio server is an upstream JavaScript artifact downloaded from Stremio's pinned CDN URL during package creation; it is not rebuilt from source by this repository.
- `ubuntu-26.04-arm` is a GitHub-hosted runner label; runner availability is controlled by GitHub.

## Attribution and license

Stremio Shell is upstream software from the Stremio project. The source build is pinned to the official repository; Linux compatibility work was informed by `fragarray/stremio-rpi5`. Preserve upstream copyright and licensing when redistributing builds.

This repository's carried Stremio-compatible source changes are distributed under GPL-3.0. See [`LICENSE.md`](LICENSE.md).
