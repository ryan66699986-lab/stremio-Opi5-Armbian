# ORP10 NV15 capture-width experiment

ORP10 was an experimental physical-board candidate. ORP2 remains the supported runtime baseline. ORP10 has now been physically rejected and must not be merged.

## Why this experiment existed

Physical ORP9 testing showed that a direct userspace NV15 `bytesperline=2432` request for 1920-wide HEVC Main10 was ignored: rkvdec negotiated 2400 and Mesa again rejected the DMA-BUF with `WSI pitch not properly aligned`.

The Linux rkvdec capture-format path derives `bytesperline` from capture width using `v4l2_fill_pixfmt_mp()`. For HEVC the driver permits capture width at least as large as coded width and applies its frame-size constraints. ORP10 therefore changed one thing only: for NV15 CAPTURE, FFmpeg asks for capture width rounded up to 256 pixels before `VIDIOC_S_FMT`.

Expected layout if the driver honored the larger capture width:

- coded/visible width 1920 -> requested capture width 2048 -> expected NV15 pitch 2560 (64-byte aligned)
- coded/visible width 3840 -> requested capture width 3840 -> expected NV15 pitch 4800 (unchanged)
- NV12/H.264 and all non-NV15 formats -> unchanged

The Stremio, FFmpeg, mpv-rockchip and libplacebo upstream commit pins were unchanged from ORP2.

## Physical-board result

A 3840x2160 HEVC Main10 sample produced the expected ORP10 diagnostic:

```text
V4L2 Request NV15 capture layout: requested width 3840, negotiated width 3840, pitch 4800
Using hardware decoding (v4l2request).
```

The exported DRM PRIME surface remained NV15 with pitch 4800 and libmpv repeatedly reported:

```text
Imported DRM NV15 as two packed R8 textures
```

However, the physical display was still visibly green.

This corrects an earlier project assumption: the 3840-wide NV15 case was previously described as a known-good visual baseline because DMA-BUF import succeeded. The board evidence only proves that this case decodes and imports successfully. It does **not** prove correct pixel presentation. Import success and correct rendering must be tracked as separate outcomes.

## Corrected interpretation

- H.264/NV12 remains the genuinely known-good visual playback path.
- 1920-wide HEVC Main10/NV15 is known to hardware-decode but fail DMA-BUF import at pitch 2400.
- 3840-wide HEVC Main10/NV15 at pitch 4800 is known to hardware-decode and import successfully, but visual correctness is not established; the ORP10 board test showed a green screen despite successful import.

Therefore 3840-wide HEVC must no longer be used as a regression-success criterion merely because `Imported DRM NV15...` appears in the log.

## Acceptance / rejection

A future candidate must separately record:

1. decoder success (`Using hardware decoding (v4l2request)`),
2. DRM PRIME format/pitch,
3. DMA-BUF import success/failure,
4. actual on-screen visual correctness.

A candidate fails if any one of those required layers is broken for a stream expected to work visually.

ORP10 is rejected because physical output was green on the tested 3840x2160 HEVC Main10/NV15 stream even though hardware decode and DMA-BUF import succeeded. ORP2 remains the supported runtime baseline while the presentation issue continues to be investigated.
