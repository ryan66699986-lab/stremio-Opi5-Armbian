# Maintenance policy

## Baseline

`baseline/orp2-working` is the permanent rollback branch for the last physically proven package, `4.4.181-orp2`.

Do not rewrite that branch to follow future development.

## Forward line

New development is called **current**, not ORP3/ORP4/etc.

The current line follows the latest commit on the relevant upstream branches at build time:

- `Stremio/stremio-linux-shell` `main`
- `ryanfitz/FFmpeg` `rk3588-hevc-rps-controls`
- `ryanfitz/mpv-rockchip` `rk3588-nv15-gpu-next`
- `haasn/libplacebo` `master`

The exact resolved commit IDs should be recorded by CI/build output so a tested package can be identified after the moving branches advance.

## Project-specific code

Keep local multimedia changes minimal.

Do not carry forward rejected ORP3-ORP10 renderer, copyback, direct-rendering, stride or capture-width experiments into the current line unless new upstream evidence specifically requires them.

Prefer an upstream implementation over a local workaround.

## Promotion rule

A build is not supported merely because CI is green.

Physical Orange Pi 5 Pro testing decides whether a current build replaces the previous supported build. If it regresses, keep using `baseline/orp2-working` and wait for/follow the next upstream change.

For HEVC Main10/NV15, decode success, surface layout, DMA-BUF import and actual visual correctness are separate results.

## Research history

Rejected ORP experiments remain available as historical evidence. They should be clearly marked rejected and should not be treated as candidate branches.
