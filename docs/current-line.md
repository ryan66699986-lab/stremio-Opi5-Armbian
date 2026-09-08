# Current-line architecture

The **current** line is the forward development path after the preserved `4.4.181-orp2` baseline.

It is intentionally not named ORP11/ORP12/etc. The ORP-numbered experiment sequence ended with the rejected ORP10 work.

## Purpose

The current line answers a simple question:

> Does the newest official Stremio Linux client, combined with the newest relevant upstream RK3588 multimedia work, improve or preserve real Orange Pi 5 Pro playback without carrying our own renderer hacks?

## Application change

ORP2 used the legacy Qt5 `Stremio/stremio-shell` application.

Current uses the official `Stremio/stremio-linux-shell`, which is a different application implementation built around:

- Rust;
- GTK4;
- libadwaita;
- WebKitGTK;
- libmpv through the `libmpv2` Rust crate;
- a GTK `GLArea` and libmpv OpenGL render context for video presentation.

This is therefore a real shell/rendering migration, not merely a Stremio version bump.

## Multimedia stack

Current retains the useful ORP2 isolation model:

```text
/opt/stremio/rk3588
```

but resolves upstream branch heads at build time:

- `ryanfitz/FFmpeg` → `rk3588-hevc-rps-controls`
- `ryanfitz/mpv-rockchip` → `rk3588-nv15-gpu-next`
- `haasn/libplacebo` → `master`

The exact commits used by a build are recorded in `.work/current.env`.

As of 2026-09-06, the two Ryan Fitzgerald branch heads had not advanced beyond the commits already used in ORP2:

```text
FFmpeg      151f3befc4593d7f8c57946b3338005bdf8ae262
mpv-rockchip 5cf2859a320626a3588622b448292815caf419fc
```

So the first current candidate primarily tests the newer official Stremio Linux shell and its different libmpv presentation integration. It is not yet a test of a fundamentally newer RK3588 decoder implementation.

## What has deliberately not been carried forward

Current does not inherit the rejected ORP3-ORP10 multimedia experiments. In particular, it does not carry forward:

- `vd-lavc-dr=no` from clean ORP3;
- copy-first/copyback experiments;
- custom NV15 renderer work;
- ORP9 `bytesperline` forcing;
- ORP10 capture-width padding;
- local Mesa modifications.

Those results remain documentation/research only.

## Expected integration risks

The likely failure points in the first current build are ordinary integration issues rather than the RK3588 VPU itself:

1. The official Rust/GTK shell may require newer GTK4, libadwaita or WebKitGTK APIs than the target Ubuntu 26.04 environment provides.
2. The Rust `libmpv2` build must link against the private RK3588 `libmpv`, not silently fall back to the distro library.
3. Runtime RPATH/library resolution must keep libmpv and its private FFmpeg dependencies under `/opt/stremio/rk3588`.
4. `libplacebo` master may occasionally move ahead of the mpv-rockchip branch API. If that happens, use the newest compatible upstream combination and record the temporary compatibility revision rather than adding local multimedia patches.

These are build/integration concerns. A successful build still says nothing about HEVC Main10 visual correctness.

## Why the shell change may matter to NV15

The unresolved HEVC Main10 problem in ORP2 is not decoder failure. RKVDEC hardware decoding is proven. The unresolved part is presentation of NV15 hardware surfaces.

Current changes the application-side rendering host from the old Qt path to GTK `GLArea` + libmpv's OpenGL render API. That may change behavior around the final presentation path even when FFmpeg and mpv commits are unchanged.

No outcome should be assumed in advance. Physical testing must determine whether the result is better, identical or worse.

## Promotion rule

Current becomes the supported direction only after real Orange Pi 5 Pro testing.

Minimum comparison against ORP2:

- H.264 known-good sample still decodes with V4L2 Request and renders correctly;
- HEVC Main10 1920-wide case is checked for decoder result, NV15 pitch, import result and visual result;
- HEVC Main10 3840-wide case is checked for decoder result, NV15 pitch, import result and actual on-screen image;
- seeking, audio, subtitles and normal application behavior remain usable.

CI green is necessary for a build candidate, not sufficient for promotion.
