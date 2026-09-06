# Research note: RK3588 NV15 pitch alignment and Panfrost import

> **Scope:** research/documentation only. This note does not prescribe or implement a code change.
>
> **Date:** 2026-09-01, corrected 2026-09-06 after ORP10 board validation.

## Why this note exists

The real-board evidence shows two different NV15 presentation outcomes that must not be conflated:

- HEVC Main10 at **1920x804** hardware-decodes to **NV15** with pitch **2400**, but Mesa rejects the imported surface with `WSI pitch not properly aligned`.
- HEVC Main10 at **3840x2160** hardware-decodes to **NV15** with pitch **4800** and the DMA-BUF import succeeds, but later ORP10 physical testing showed that successful import can still produce a visibly green image.

The original version of this note incorrectly described the 3840-wide case as rendering successfully. The evidence actually supported successful decode and DMA-BUF import, not confirmed correct pixel presentation.

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

## Why 2400 vs 4800 is still significant

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

That makes a **64-byte row-alignment requirement** a strong working hypothesis for the difference between the 1920-wide import failure and 3840-wide import success.

This is not proof that pitch alignment is the entire HEVC/Main10 presentation problem. ORP10 proved that a surface can pass the import stage and still display incorrectly as green. The pitch hypothesis therefore explains an **import boundary**, not necessarily end-to-end visual correctness.

## A useful prediction for controlled import testing

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

| Width | Tight NV15 pitch | Pitch % 64 | Prediction for DMA-BUF import under 64-byte hypothesis |
| ---: | ---: | ---: | --- |
| 1280 | 1600 | 0 | aligned/importable candidate |
| 1920 | 2400 | 32 | misaligned/import failure candidate |
| 2048 | 2560 | 0 | aligned/importable candidate |
| 2560 | 3200 | 0 | aligned/importable candidate |
| 3840 | 4800 | 0 | aligned/importable candidate |
| 4096 | 5120 | 0 | aligned/importable candidate |

This matches the existing real-board import observations: 1920 fails at import, while 3840 imports. It does **not** predict whether an imported frame will display with correct colors/content.

A future research test could use otherwise comparable Main10 samples at widths on both sides of this predicted boundary to validate the import rule. Visual correctness must be recorded separately for every sample.

## Mesa does support NV15 as a format

This is not simply a case of Panfrost lacking NV15 format recognition. Mesa 25.0 added both generic NV15/NV20 texture handling and Panfrost support for NV15/NV16/NV20.

Mesa 25.0 release notes:

- https://docs.mesa3d.org/relnotes/25.0.0.html

The important distinction is therefore:

```text
NV15 format support != every externally supplied NV15 stride being importable
NV15 import success != correct on-screen pixel presentation
```

The current Mesa source still contains explicit-layout pitch validation, so the existence of newer Mesa releases alone is not evidence that either the import issue or the green-output issue has been removed.

## Kernel/display support is a separate layer

Mainline Rockchip VOP2 code recognizes `DRM_FORMAT_NV15` as 10-bit YUV420 and maps it to the VOP2 10-bit YUV420 format.

Linux Rockchip VOP2 source:

- https://github.com/torvalds/linux/blob/master/drivers/gpu/drm/rockchip/rockchip_drm_vop2.c

That is consistent with the broader board evidence: RK3588 hardware decode itself succeeds. But capability at one layer does not prove correctness at the next.

Four distinct capabilities must now be tracked independently:

1. **RKVDEC can decode HEVC Main10 into NV15.** Proven on board.
2. **The exported NV15 layout satisfies the consumer's import constraints.** Dimension/stride-sensitive; 1920/pitch2400 fails, 3840/pitch4800 imports.
3. **Mesa/libmpv accepts/imports the DMA-BUF.** Proven for tested 3840-wide pitch4800 surfaces.
4. **The imported pixels are interpreted and displayed correctly.** Not proven for HEVC/NV15; ORP10 showed a green screen despite successful import.

## Research implication for possible solution classes

The evidence now points to at least two separate subproblems in the NV15 presentation path:

- producer/consumer layout compatibility for some pitches;
- correct interpretation/presentation after import for surfaces that do pass the layout checks.

Without selecting or implementing any one solution, useful solution classes include:

- producer-side allocation/padding that yields a Panfrost-acceptable NV15 stride for widths such as 1920;
- investigation of NV15 plane geometry, offsets, texture interpretation, color/chroma handling, and any format assumptions in the libmpv/Mesa import path that could explain green output after successful import;
- a GPU- or hardware-assisted repack/conversion into a known-correct importable format/layout;
- a presentation route that can use the decoded NV15 surface without the failing or visually incorrect Panfrost texture-import path;
- an upstream Mesa change, but only if the hardware can safely consume the layout and the current interpretation is shown to be wrong or unnecessarily restricted.

The existing evidence does **not** justify simply forcing Mesa to accept arbitrary strides, nor does an accepted stride prove the NV15 byte/plane interpretation is correct.

## Current research conclusion

The best-supported model is now:

```text
HEVC Main10 decode succeeds
        ↓
RKVDEC exports tightly packed NV15
        ↓
1920-wide / pitch 2400
        ↓
Panfrost explicit DMA-BUF import rejects pitch
        ↓
no usable presentation
```

and separately:

```text
HEVC Main10 decode succeeds
        ↓
3840-wide / pitch 4800
        ↓
DMA-BUF import succeeds
        ↓
actual displayed image can still be green
```

So the **width-multiple-of-256 prediction remains useful for the import-alignment boundary only**. It must no longer be treated as an end-to-end rendering-success predictor.
