# Rejected ORP experiment history

The ORP-numbered experiment line ended after ORP10.

## Working rollback point

- **ORP2** — last physically proven baseline. Preserved at `baseline/orp2-working` and release `v4.4.181-orp2`.

ORP2 is not part of the rejected experiment set. It remains the known rollback package while current development is evaluated.

## Rejected research

**ORP3 through ORP10 are rejected historical experiments.** They are retained only because their diffs and board results are useful evidence.

Key results:

- clean ORP3 (`vd-lavc-dr=no`) did not change the 1920x804 HEVC Main10 NV15 pitch-2400 import failure;
- historical copy-first/copyback work was not a general Main10 solution;
- later custom renderer/gpu-next experiments were not accepted as deployment candidates;
- ORP9 requested a larger NV15 `bytesperline`, but rkvdec negotiated the original tightly packed stride;
- ORP10 changed NV15 capture width negotiation, but physical 3840x2160 testing still produced a green image even though V4L2 Request decode and NV15 DMA-BUF import succeeded.

The final point corrects an earlier assumption: 3840-wide NV15 pitch 4800 is a known **decode/import** success, not a known visual-rendering success.

## Why these experiments are not the forward plan

The rejected line increasingly moved from packaging/integration into custom multimedia behavior around FFmpeg, mpv and the NV15 presentation path. That made each candidate harder to reason about while still failing to establish a robust HEVC Main10 visual path.

The forward project therefore does not continue with ORP11/ORP12/etc. local experiments.

## Forward development

The forward line is called **current** and is intentionally separate from this archive.

Current moves to the official Rust/GTK `Stremio/stremio-linux-shell` and tracks the newest relevant upstream RK3588 FFmpeg/mpv work. It preserves the useful private-library isolation from ORP2 but does not inherit the rejected multimedia patches listed above.

See:

- [`current-line.md`](current-line.md) for the new architecture and ORP2/current comparison;
- [`maintenance-policy.md`](maintenance-policy.md) for upstream-tracking rules;
- [`runtime-testing.md`](runtime-testing.md) for physical comparison criteria;
- [`archive/README.md`](archive/README.md) for the archive summary.
