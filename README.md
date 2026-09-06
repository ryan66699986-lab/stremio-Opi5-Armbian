# Stremio on Orange Pi 5 Pro / RK3588

Unofficial ARM64 packaging and RK3588 multimedia integration for Orange Pi 5 Pro on Armbian / Ubuntu 26.04.

## Working baseline

The last physically proven package is **Stremio 4.4.181-orp2**.

It is preserved permanently at:

- branch: `baseline/orp2-working`
- release: `v4.4.181-orp2`

ORP2 uses the older Qt Stremio shell plus a private RK3588 FFmpeg/libmpv V4L2 Request stack under `/opt/stremio/rk3588`. It does not replace distribution multimedia libraries.

ORP2 is the rollback point. Future development must not destroy or rewrite that baseline.

## Current development policy

Development after ORP2 no longer uses ORP3/ORP4/etc. numbering.

The forward line is simply **current** and follows the newest relevant upstream branch heads at build time:

- Stremio: `Stremio/stremio-linux-shell` → `main`
- RK3588 FFmpeg: `ryanfitz/FFmpeg` → `rk3588-hevc-rps-controls`
- RK3588 mpv/libmpv: `ryanfitz/mpv-rockchip` → `rk3588-nv15-gpu-next`
- libplacebo: current upstream revision required by the mpv build

The current line should contain as little project-specific multimedia code as possible. Prefer upstream fixes. Do not add speculative renderer/copyback/stride hacks merely to produce another candidate.

A moving upstream build is not a supported release just because it compiles. Physical Orange Pi testing remains authoritative. If current upstream regresses, use the preserved ORP2 baseline while waiting for upstream fixes.

See [`docs/maintenance-policy.md`](docs/maintenance-policy.md).

## What ORP2 proved

- H.264 through `h264-v4l2request` / `rkvdec` works and renders correctly as NV12.
- HEVC Main10 hardware decode through `hevc-v4l2request` / `rkvdec` works.
- HEVC Main10/NV15 presentation is not fully solved on this stack.
- A 1920-wide NV15 surface with pitch 2400 can fail Mesa DMA-BUF import alignment checks.
- A 3840-wide NV15 surface with pitch 4800 can import successfully and still display green, so import success is not visual correctness.

See [`docs/runtime-testing.md`](docs/runtime-testing.md) and [`docs/hardware-decode-history.md`](docs/hardware-decode-history.md).

## Archived experiments

ORP3 through ORP10 are rejected research history, not release candidates. Their results are retained because they document what was tried and what failed.

See [`docs/experimental-branches.md`](docs/experimental-branches.md) and [`docs/archive/README.md`](docs/archive/README.md).

## Build layout

The proven ORP2 architecture keeps the RK3588 multimedia stack private:

```text
/opt/stremio/stremio
/opt/stremio/rk3588/lib/...
```

That isolation principle remains useful for future builds: experimental/current multimedia libraries should not overwrite Ubuntu/Armbian FFmpeg, mpv or Mesa packages.

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
