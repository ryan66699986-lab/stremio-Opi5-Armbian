# Rejected ORP experiment history

The ORP-numbered experiment line ended after ORP10.

## Working rollback point

- **ORP2** — last physically proven baseline. Preserved at `baseline/orp2-working` and release `v4.4.181-orp2`.

## Rejected research

**ORP3 through ORP10 are rejected historical experiments.** They are retained only because their diffs and board results are useful evidence.

Key results:

- clean ORP3 (`vd-lavc-dr=no`) did not change the 1920x804 HEVC Main10 NV15 pitch-2400 import failure;
- historical copy-first/copyback work was not a general Main10 solution;
- later custom renderer/gpu-next experiments were not accepted as deployment candidates;
- ORP9 requested a larger NV15 `bytesperline`, but rkvdec negotiated the original tightly packed stride;
- ORP10 changed NV15 capture width negotiation, but physical 3840x2160 testing still produced a green image even though V4L2 Request decode and NV15 DMA-BUF import succeeded.

The final point corrects an earlier assumption: 3840-wide NV15 pitch 4800 is a known **decode/import** success, not a known visual-rendering success.

## Forward development

Do not create ORP11/ORP12/etc. as another chain of local multimedia experiments.

New work follows [`maintenance-policy.md`](maintenance-policy.md): track current upstream Stremio/RK3588 multimedia work, keep local patches minimal, and use physical board testing before promotion.

See [`archive/README.md`](archive/README.md) for the archive summary.
