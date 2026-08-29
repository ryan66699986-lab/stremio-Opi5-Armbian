# Stremio ARM64 for Orange Pi 5 Pro / Armbian Ubuntu 26.04

This is an **unofficial ARM64 build/package of Stremio for Orange Pi 5 Pro / compatible ARM64 SBCs**. It is not an official Stremio distribution.

The project builds Stremio 4.4.181 natively on ARM64 and produces a normal Debian package for Ubuntu 26.04 "Resolute Raccoon". The primary target is an Orange Pi 5 Pro running Armbian and KDE Plasma.

## Target

| Item | Target |
| --- | --- |
| Hardware | Orange Pi 5 Pro |
| Architecture | ARM64 / AArch64 |
| OS | Armbian |
| Base distribution | Ubuntu 26.04 "Resolute Raccoon" |
| Desktop | KDE Plasma |
| Stremio shell | 4.4.181 |
| Package revision | `orp1` |
| Output | `stremio_4.4.181-orp1_arm64.deb` |

`upstream.env` pins every external source used by the build. Stremio 4.4.181 is taken from the official `Stremio/stremio-shell` repository at commit `41659b91c27fbb5812b167a04f2fdc50c82d4e9f`.

## Why this project exists

The previously available ARM64 package declares a dependency on `librubberband2`. Ubuntu 26.04 does not provide that package; its current mpv stack uses `librubberband3`.

Stremio itself does **not** link to Rubber Band. It links to `libmpv`. On Ubuntu 26.04, `libmpv2` owns the Rubber Band relationship and depends on `librubberband3`. This project therefore does not invent a compatibility library, copy shared objects by hand, mix Ubuntu releases, or rename a newer ABI to an older SONAME.

The package uses `dpkg-shlibdeps` through debhelper to derive the Stremio ELF's actual direct shared-library dependencies. The CI pipeline also downloads the exact reference package and inspects every packaged ELF with `readelf` before building ours. It fails if a reference ELF actually has a `NEEDED` entry for `librubberband.so.2`.

## Upstream strategy

The repository intentionally does not vendor a full copy of the Raspberry Pi fork. It fetches the exact official Stremio 4.4.181 source and applies one reviewable compatibility patch.

The patch is based on the useful Linux compatibility work found in `fragarray/stremio-rpi5` and is limited to:

- selecting Qt 5 explicitly on Linux;
- linking against Ubuntu's system `libmpv` headers/library while using only upstream's bundled `qthelper.hpp` helper;
- adapting code to current libmpv API/properties;
- translating a few legacy mpv properties emitted by the Stremio web UI;
- initializing Qt WebEngine before the QML engine.

It does not add a Rubber Band link and does not claim Orange Pi hardware decoding is working.

## Local build on Ubuntu 26.04 ARM64

Use a native ARM64 Ubuntu 26.04 environment. The scripts deliberately reject a non-ARM64 host rather than silently producing or labelling an x86 build as ARM64.

```bash
git clone https://github.com/ryan66699986-lab/stremio-Opi5-Armbian.git
cd stremio-Opi5-Armbian
./scripts/install-deps.sh
./scripts/build.sh
./scripts/build-deb.sh
```

`build.sh` performs a clean checkout of the pinned official source each time, initializes the required `libmpv` and `SingleApplication` submodules, applies the compatibility patch, and compiles the shell.

`build-deb.sh` downloads the Stremio server from the pinned official Stremio CDN URL, builds the package with debhelper, and runs package/ELF validation. The result is:

```text
stremio_4.4.181-orp1_arm64.deb
```

To inspect the old reference package independently:

```bash
./scripts/inspect-upstream-deb.sh
```

## Install

```bash
sudo apt install ./stremio_4.4.181-orp1_arm64.deb
```

Launch from KDE's application menu or run:

```bash
stremio
```

Uninstall normally through apt:

```bash
sudo apt remove stremio
```

## Package validation

The build runs:

```bash
dpkg-deb --info stremio_4.4.181-orp1_arm64.deb
dpkg-deb --contents stremio_4.4.181-orp1_arm64.deb
dpkg-deb -f stremio_4.4.181-orp1_arm64.deb Architecture
./scripts/validate-deb.sh stremio_4.4.181-orp1_arm64.deb
```

Validation requires `Architecture: arm64`, a generated `libmpv2` dependency, no `librubberband2` package dependency, and no packaged ELF `NEEDED` entry for `librubberband.so.2`.

## GitHub Actions

`.github/workflows/build-arm64.yml` uses GitHub's native `ubuntu-26.04-arm` hosted runner. It does not emulate ARM64 on an x86 runner. The workflow:

1. confirms the runner is `arm64`;
2. installs dependencies from Ubuntu 26.04 repositories;
3. downloads and ELF-inspects the exact known reference `.deb`;
4. builds the pinned official Stremio source;
5. builds and validates `stremio_4.4.181-orp1_arm64.deb`;
6. installs the package with apt and checks dynamic linking;
7. uninstalls it again;
8. uploads the `.deb` as a workflow artifact.

A CI pass proves compilation, packaging, dependency resolution, installability, dynamic loader resolution, and uninstallability on the ARM64 Ubuntu runner. It does **not** prove Orange Pi display, video playback, or hardware decoding behavior.

## Runtime testing on Orange Pi 5 Pro

See [`docs/runtime-testing.md`](docs/runtime-testing.md). The real-board checklist covers KDE startup, Qt WebEngine, mpv, video/audio, seeking, subtitles, shutdown, and hardware-decoding evidence.

Hardware decoding must be verified from the decoder actually selected at runtime. This project makes no hardware-acceleration success claim until that has been tested on the board.

## Troubleshooting

### Qt WebEngine fails or the UI is blank

Run Stremio from a terminal and retain all Qt/Chromium output. Confirm `libqt5webengine-data` and `qml-module-qtwebengine` are installed by apt. Record whether the KDE session is Wayland or X11 before trying session-specific workarounds.

### Missing shared libraries

Do not copy libraries manually into `/usr/lib`. Check the package and loader state instead:

```bash
ldd /opt/stremio/stremio
dpkg-deb -f stremio_4.4.181-orp1_arm64.deb Depends
apt-cache policy libmpv2
```

### mpv fails

Check that Ubuntu's `libmpv2` is installed and inspect terminal logs from `stremio`. The application is intentionally built against the distribution libmpv rather than a bundled binary mpv library.

### Hardware acceleration

Do not infer hardware decoding from smooth playback or `hwdec=auto`. Capture mpv logs and kernel/media-driver evidence as described in `docs/runtime-testing.md`.

### Wayland / X11 or KDE launch problems

Record `XDG_SESSION_TYPE`, `WAYLAND_DISPLAY`, and `DISPLAY`, then compare logs. Do not globally disable Wayland, sandboxing, or GPU features without a reproduced target-specific reason.

## Known limitations

- Real Orange Pi 5 Pro runtime validation is still required after a package is produced.
- Hardware decoding is intentionally not claimed until verified on actual RK3588 hardware.
- The Stremio server is an upstream JavaScript artifact downloaded from Stremio's pinned CDN URL during package creation; it is not rebuilt from source by this repository.
- `ubuntu-26.04-arm` is currently a GitHub-hosted runner label in public preview, so runner availability is controlled by GitHub.

## Attribution and license

Stremio Shell is upstream software from the Stremio project. The source build is pinned to the official repository; compatibility work was informed by `fragarray/stremio-rpi5`. Preserve upstream copyright and licensing when redistributing builds.

This repository's carried Stremio-compatible source changes are distributed under GPL-3.0. See `LICENSE.md`.
