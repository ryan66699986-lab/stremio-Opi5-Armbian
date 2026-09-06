# Stremio on Orange Pi 5 Pro / RK3588

Unofficial ARM64 packaging and RK3588 multimedia integration for Orange Pi 5 Pro on Armbian / Ubuntu 26.04.

## Working baseline

The last physically proven package is **Stremio 4.4.181-orp2**.

It is preserved permanently at:

- branch: `baseline/orp2-working`
- release: `v4.4.181-orp2`

ORP2 uses the legacy Qt `Stremio/stremio-shell` application plus a private RK3588 FFmpeg/libmpv V4L2 Request stack under `/opt/stremio/rk3588`. It is the rollback point and is not rewritten by forward development.

## Current line

Forward development is simply called **current**. It moves to the official Rust/GTK `Stremio/stremio-linux-shell` and resolves the latest commit on the relevant upstream branches at build time:

- Stremio: `Stremio/stremio-linux-shell` → `main`
- RK3588 FFmpeg: `ryanfitz/FFmpeg` → `rk3588-hevc-rps-controls`
- RK3588 mpv/libmpv: `ryanfitz/mpv-rockchip` → `rk3588-nv15-gpu-next`
- libplacebo: `haasn/libplacebo` → `master`

The exact resolved commit IDs are recorded in `.work/current.env` during each build.

As of the initial current-line migration on 2026-09-06, Ryan Fitzgerald's two RK3588 branch heads were still the same commits used by ORP2:

- FFmpeg: `151f3befc4593d7f8c57946b3338005bdf8ae262`
- mpv-rockchip: `5cf2859a320626a3588622b448292815caf419fc`

That means the first current candidate primarily changes the **Stremio application/rendering shell**, while keeping the same fundamental RK3588 V4L2 Request decoder architecture. Future current builds automatically follow newer upstream branch heads when they move.

### ORP2 versus current

| Area | ORP2 | current |
| --- | --- | --- |
| Stremio application | legacy Qt5 `stremio-shell` | official Rust + GTK4/libadwaita `stremio-linux-shell` |
| Web UI host | Qt WebEngine | WebKitGTK |
| libmpv integration | Qt/C++ shell integration | upstream Rust shell using `libmpv2` |
| video presentation host | Qt/OpenGL path | GTK `GLArea` + libmpv OpenGL render context |
| RK3588 FFmpeg | fixed tested commit | latest `rk3588-hevc-rps-controls` head |
| RK3588 mpv | fixed tested commit | latest `rk3588-nv15-gpu-next` head |
| libplacebo | fixed tested commit | latest upstream head used by the current build |
| local multimedia experiments | none in supported ORP2 | none; ORP3-ORP10 hacks remain rejected |
| status | physically proven rollback baseline | test candidate until board-validated |

The decoder model remains:

```text
Stremio
  ↓
private libmpv
  ↓
private FFmpeg with V4L2 Request
  ↓
rkvdec
  ↓
RK3588 VPU
```

What changes substantially is the application and final rendering/presentation integration around libmpv.

## Project rule: upstream first

The current line should contain as little project-specific multimedia code as possible. Do not add another chain of speculative renderer, copyback, stride, capture-width or Mesa-adjacent patches simply to produce a new candidate.

Track upstream work first. If an upstream head stops building because two upstream projects temporarily disagree on an API, document the incompatibility rather than inventing a local multimedia workaround. A compatibility pin is acceptable only when necessary to build the latest usable upstream combination and must be recorded explicitly.

The private multimedia stack remains isolated from the distribution:

```text
/opt/stremio/stremio
/opt/stremio/server.js
/opt/stremio/rk3588/lib/...
```

The distro FFmpeg, mpv and Mesa packages are not replaced.

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

A green CI build proves compilation, packaging and linkage only. It does **not** make current a supported release. Physical Orange Pi 5 Pro testing remains the promotion gate.

See [`docs/current-line.md`](docs/current-line.md) and [`docs/maintenance-policy.md`](docs/maintenance-policy.md).

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

For hardware-decoding tests, record separately:

1. decoder selection,
2. DRM PRIME format/pitch,
3. DMA-BUF import success/failure,
4. actual on-screen image correctness.

A successful `Imported DRM NV15...` message is not by itself a playback pass.

## License

See [`LICENSE.md`](LICENSE.md). Upstream components retain their own licenses and copyright notices.
