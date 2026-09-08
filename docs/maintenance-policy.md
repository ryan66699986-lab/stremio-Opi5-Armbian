# Maintenance policy

## Baseline

`baseline/orp2-working` is the permanent rollback branch for the last physically proven package, `4.4.181-orp2`.

Do not rewrite that branch to follow future development.

## Forward line

New development is called **current**, not ORP3/ORP4/etc.

The current line follows the newest relevant upstream code:

- `Stremio/stremio-linux-shell` `main`
- `ryanfitz/FFmpeg` `rk3588-hevc-rps-controls`
- `ryanfitz/mpv-rockchip` `rk3588-nv15-gpu-next`
- `haasn/libplacebo` `master`

The build resolves branch heads at build time and records the exact commit IDs in `.work/current.env` so a physical test can always be tied back to the exact source revisions used.

## What “current” means

The default is the latest commit on each relevant upstream branch, not a permanently frozen project pin.

If two upstream projects temporarily become API-incompatible, do not invent local multimedia code merely to force the combination to build. Use the newest compatible upstream revision only as a temporary compatibility pin, record it explicitly, and return to branch-head tracking as soon as upstream compatibility is restored.

This exception is intended for upstream API compatibility only. It is not a license to maintain our own renderer or decoder fork.

## Application shell

Current uses the official Rust/GTK `Stremio/stremio-linux-shell`, not the legacy Qt `Stremio/stremio-shell` used by ORP2.

That changes the application and final libmpv presentation integration substantially, while preserving the same high-level RK3588 decoder model:

```text
Stremio → private libmpv → private FFmpeg V4L2 Request → rkvdec → RK3588 VPU
```

See [`current-line.md`](current-line.md) for the detailed comparison.

## Project-specific code

Keep local multimedia changes minimal.

Do not carry forward rejected ORP3-ORP10 renderer, copyback, direct-rendering, stride or capture-width experiments into the current line unless new upstream evidence specifically requires investigation of the same area.

Prefer an upstream implementation over a local workaround.

Do not patch Mesa locally without a specific reproduced upstream bug and a defensible upstream-quality fix.

## Promotion rule

A build is not supported merely because CI is green.

CI proves compilation, packaging and intended private-library linkage. Physical Orange Pi 5 Pro testing decides whether a current build replaces the previous supported build.

If current regresses, keep using `baseline/orp2-working` and test the next meaningful upstream change rather than starting another numbered local experiment chain.

For HEVC Main10/NV15, record these independently:

1. decoder success;
2. DRM PRIME format/layout/pitch;
3. DMA-BUF import success/failure;
4. actual on-screen visual correctness.

## Research history

Rejected ORP experiments remain available as historical evidence. They should be clearly marked rejected and should not be treated as candidate branches.
