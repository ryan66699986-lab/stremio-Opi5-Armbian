# Research note: RK3588 NV15 pitch alignment and Panfrost import

> **Scope:** research/documentation only. This note does not prescribe or implement a code change.
>
> **Date:** 2026-09-01

## Why this note exists

The current real-board evidence in this repository shows a useful split:

- HEVC Main10 at **3840x2160** hardware-decodes to **NV15** with pitch **4800** and renders successfully;
- HEVC Main10 at **1920x804** hardware-decodes to **NV15** with pitch **2400**, but Mesa rejects the imported surface with `WSI pitch not properly aligned`.

That pattern is consistent with a pitch-alignment problem in the Panfrost DMA-BUF/explicit-layout import path rather than a decoder failure.

## NV15 packing explains the observed pitches

Linux defines `DRM_FORMAT_NV15` as a 10-bit, two-plane 4:2:0 format where four 10-bit samples occupy five bytes. In other words, a tightly packed luma row consumes:

```text
pitch = width * 5 / 4
```

For the two board-tested widths:

```text
1920 * 5 / 4 = 2400 bytes
3840 * 5 / 4 = 4800 bytes
```

So both observed pitches are exactly the expected tightly packed NV15 row size; neither contains extra row padding.

Linux format definition:

- https://github.com/torvalds/linux/blob/master/include/uapi/drm/drm_fourcc.h

## Why 2400 vs 4800 is significant

Current Mesa Panfrost layout code rejects an explicitly supplied WSI/DMA-BUF row pitch when the pitch does not satisfy the driver's required alignment. The relevant paths emit the exact error already observed on the Orange Pi:

```text
WSI pitch not properly aligned
```

Current Mesa source:

- https://gitlab.freedesktop.org/mesa/mesa/-/blob/main/src/panfrost/lib/pan_mod.c

A particularly useful numerical correlation is:

```text
2400 % 64 = 32
4800 % 64 = 0
```

That makes a **64-byte row-alignment requirement** a strong working hypothesis for the observed success/failure split.

This is not yet proof of the exact `align_mask` used for the failing NV15 import. The exact value should be treated as unconfirmed until it is observed from the relevant Mesa path or a controlled width matrix reproduces the boundary. What is proven is that Mesa rejects the 2400-byte explicit pitch as misaligned, while the 4800-byte surface succeeds.

## A useful prediction for controlled testing

For tightly packed NV15:

```text
pitch = 5 * width / 4
```

If the effective requirement is 64-byte pitch alignment, then:

```text
(5 * width / 4) % 64 == 0
```

Because 5 and 256 are coprime, this simplifies to:

```text
width % 256 == 0
```

That predicts a simple width-dependent boundary for tightly packed NV15 surfaces:

| Width | Tight NV15 pitch | Pitch % 64 | Prediction under 64-byte hypothesis |
| ---: | ---: | ---: | --- |
| 1280 | 1600 | 0 | aligned |
| 1920 | 2400 | 32 | misaligned |
| 2048 | 2560 | 0 | aligned |
| 2560 | 3200 | 0 | aligned |
| 3840 | 4800 | 0 | aligned |
| 4096 | 5120 | 0 | aligned |

This matches the two existing real-board observations: 1920 fails at import, while 3840 succeeds.

A future **research test**, without changing the application stack, could use otherwise comparable Main10 samples at widths on both sides of this predicted boundary. If widths divisible by 256 consistently import and nearby non-divisible widths consistently fail, that would substantially strengthen the alignment diagnosis.

## Mesa does support NV15 as a format

This is not simply a case of Panfrost lacking NV15 format recognition. Mesa 25.0 added both generic NV15/NV20 texture handling and Panfrost support for NV15/NV16/NV20.

Mesa 25.0 release notes:

- https://docs.mesa3d.org/relnotes/25.0.0.html

The important distinction is therefore:

```text
NV15 format support != every externally supplied NV15 stride being importable
```

The current Mesa source still contains explicit-layout pitch validation, so the existence of newer Mesa releases alone is not evidence that this particular stride issue has been removed.

## Kernel/display support is a separate layer

Mainline Rockchip VOP2 code recognizes `DRM_FORMAT_NV15` as 10-bit YUV420 and maps it to the VOP2 10-bit YUV420 format.

Linux Rockchip VOP2 source:

- https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/rockchip/rockchip_drm_vop2.c

That is consistent with the broader board evidence: RK3588 hardware decode itself succeeds, and at least one NV15 surface is usable end-to-end. The failure occurs later, when a particular decoded DMA-BUF surface is imported into the Mesa/Panfrost rendering path.

This also means three distinct capabilities should not be conflated:

1. **RKVDEC can decode HEVC Main10 into NV15.** Already proven on board.
2. **Rockchip DRM/VOP2 knows NV15.** Present in mainline kernel code.
3. **Panfrost can import a particular externally allocated NV15 surface with its supplied pitch/modifier.** This is the dimension/stride-sensitive part currently failing.

## Research implication for possible solution classes

Without selecting or implementing any one solution, the evidence narrows future investigation to the boundary between the producer's decoded surface layout and the consumer's import requirements.

The broad solution classes worth evaluating upstream are therefore:

- producer-side allocation/padding that yields a Panfrost-acceptable NV15 stride;
- a GPU- or hardware-assisted repack/conversion into an importable 10-bit format/layout;
- a presentation route that can use the decoded NV15 surface without the failing Panfrost texture-import path;
- an upstream Mesa change, but only if the hardware can safely consume the currently rejected explicit pitch and Mesa's restriction is shown to be unnecessarily strict.

The existing evidence does **not** justify assuming that simply forcing Mesa to accept the stride is safe. Alignment checks generally encode hardware/layout constraints, so any relaxation would need upstream-level justification.

## Related contemporary RK3588 work

Current community work around RK3588 V4L2 Request also confirms that NV15/Main10 presentation is a distinct problem from stateless decode itself. One recent RK3588 build guide describes dedicated mpv work for NV15 GPU presentation on Mali, again separating decode from rendering/import concerns:

- https://gist.github.com/ryanfitz

This is supporting context only; the strongest evidence for this repository remains the direct Orange Pi 5 Pro runtime results already recorded in `runtime-testing.md` and `hardware-decode-history.md`.

## Current research conclusion

The best-supported interpretation of the ORP2 Main10 failure is:

```text
HEVC Main10 decode succeeds
        ↓
RKVDEC produces tightly packed NV15
        ↓
1920-wide surface has 2400-byte pitch
        ↓
Panfrost explicit DMA-BUF import rejects that pitch as misaligned
        ↓
presentation fails
```

while the successful 3840-wide case naturally produces a 4800-byte pitch that is 64-byte aligned.

The **width-multiple-of-256 prediction** is the most useful new research result from this comparison. It is testable without changing application code and can help determine whether the unresolved ORP2 problem is fundamentally a deterministic stride-alignment boundary rather than content-specific HEVC behavior.
