# Stremio on Orange Pi 5 Pro / RK3588

Unofficial ARM64 packaging and RK3588 multimedia integration for Orange Pi 5 Pro on Armbian / Ubuntu 26.04.

## Working baseline

The last physically proven package is **Stremio 4.4.181-orp2**.

It is preserved permanently at:

- branch: `baseline/orp2-working`
- release: `v4.4.181-orp2`

ORP2 uses the older Qt Stremio shell plus a private RK3588 FFmpeg/libmpv V4L2 Request stack under `/opt/stremio/rk3588`. It is the rollback point and is not rewritten by forward development.

## Current line

Forward development is simply called **current**. It uses the official Rust/GTK `Stremio/stremio-linux-shell` and resolves the latest commit on these upstream branches at build time:

- Stremio: `Stremio/stremio-linux-shell` → `main`
- RK3588 FFmpeg: `ryanfitz/FFmpeg` → `rk3588-hevc-rps-controls`
- RK3588 mpv/libmpv: `ryanfitz/mpv-rockchip` → `rk3588-nv15-gpu-next`
- libplacebo: `haasn/libplacebo` → `master`

The exact resolved commit IDs are recorded in `.work/current.env` during each build.

The current line carries no ORP3-ORP10 renderer, copyback, direct-rendering, stride or capture-width experiments. It keeps only the private multimedia isolation that was useful in ORP2:

```text
/opt/stremio/stremio
/opt/stremio/server.js
/opt/stremio/rk3588/lib/...
```

The current package uses a minimal `/usr/bin/stremio` launcher only to set the upstream-required `SERVER_PATH` and start `/opt/stremio/stremio`.

## Build

Use native ARM64 Ubuntu 26.04:

```bash
./scripts/install-deps.sh
./scripts/build-rk3588-stack.sh
./scripts/build.sh
./scripts/build-deb.sh
```

The package is named from the Stremio Linux shell version resolved at build time, for example:

```text
stremio_1.2.0-current_arm64.deb
```

A green CI build is not a supported release. Physical Orange Pi 5 Pro testing remains the promotion gate. If current upstream regresses, use `baseline/orp2-working`.

See [`docs/maintenance-policy.md`](docs/maintenance-policy.md).

## What ORP2 proved

- H.264 through `h264-v4l2request` / `rkvdec` works and renders correctly as NV12.
- HEVC Main10 hardware decode through `hevc-v4l2request` / `rkvdec` works.
- HEVC Main10/NV15 presentation is not fully solved on this stack.
- A 1920-wide NV15 surface with pitch 2400 can fail Mesa DMA-BUF import alignment checks.
- A 3840-wide NV15 surface with pitch 4800 can import successfully and still display green, so import success is not visual correctness.

See [`docs/runtime-testing.md`](docs/runtime-testing.md) and [`docs/hardware-decode-history.md`](docs/hardware-decode-history.md).

## Archived experiments

ORP3 through ORP10 are rejected research history, not release candidates. Their results are retained only to document what was tried and what failed.

See [`docs/experimental-branches.md`](docs/experimental-branches.md) and [`docs/archive/README.md`](docs/archive/README.md).

## Runtime rule

CI proves compilation, packaging and linkage. It does not prove playback.

For hardware-decoding tests, record separately:

1. decoder selection,
2. DRM PRIME format/pitch,
3. DMA-BUF import success/failure,
4. actual on-screen image correctness.

A successful `Imported DRM NV15...` message is not by itself a playback pass.

## License

See [`LICENSE.md`](LICENSE.md). Upstream components retain their own licenses and copyright notices.
