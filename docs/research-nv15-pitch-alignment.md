# Research note: RK3588 NV15 pitch alignment and Panfrost import

> **Archived research.** This note records a rejected experiment line and does not prescribe a current project patch.
>
> Corrected 2026-09-06 after ORP10 board validation.

## What the board evidence actually shows

Two different NV15 presentation failures were observed:

- HEVC Main10 at **1920x804** hardware-decodes to NV15 with pitch **2400**, but Mesa rejects the surface with `WSI pitch not properly aligned`.
- HEVC Main10 at **3840x2160** hardware-decodes to NV15 with pitch **4800** and DMA-BUF import succeeds, but ORP10 physical testing still produced a green image.

The original interpretation incorrectly treated the 3840-wide import result as a known-good visual path.

## Pitch correlation

For tightly packed NV15:

```text
pitch = width * 5 / 4
```

Therefore:

```text
1920 -> 2400 bytes
3840 -> 4800 bytes
```

The observed alignment correlation is:

```text
2400 % 64 = 32
4800 % 64 = 0
```

That still supports a 64-byte-alignment hypothesis for the **DMA-BUF import boundary**. Under tightly packed NV15, it predicts widths divisible by 256 are alignment-friendly.

It does **not** predict correct rendered pixels after import.

## Correct capability split

Track these independently:

1. RKVDEC successfully decodes HEVC Main10.
2. The exported NV15 layout satisfies the consumer's import requirements.
3. Mesa/libmpv successfully imports the DMA-BUF.
4. The imported pixels are interpreted and displayed correctly.

The board has proven step 1. The tested 3840-wide case proves steps 2 and 3 for that layout. It does not prove step 4.

## Rejected local experiments

ORP9 and ORP10 tried to influence producer-side NV15 layout. Neither produced a supported solution:

- ORP9: rkvdec recomputed/negotiated the original stride instead of honoring the requested larger `bytesperline`.
- ORP10: capture-width experimentation did not produce a validated visual path; a 3840-wide stream still displayed green despite successful decode/import.

The project should not continue stacking local stride/renderer patches on this research line. Future fixes should preferably come from the upstream RK3588 FFmpeg/mpv/Mesa work and then be board-tested here.

See [`maintenance-policy.md`](maintenance-policy.md) and [`archive/README.md`](archive/README.md).
