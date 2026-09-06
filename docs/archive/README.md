# Rejected ORP research archive

ORP3 through ORP10 are historical experiments only.

They are retained to document failed hypotheses and board evidence. They are not supported packages, not future release candidates, and should not be rebased onto the current development line.

The permanent working rollback point is `baseline/orp2-working`.

The forward development line follows the maintenance policy in [`../maintenance-policy.md`](../maintenance-policy.md).

Important retained conclusions:

- ORP3 `vd-lavc-dr=no` did not change the 1920-wide NV15 pitch/import failure.
- copyback experiments were not a general HEVC Main10 solution.
- ORP9 proved that requesting a larger NV15 `bytesperline` is overridden by rkvdec layout negotiation.
- ORP10 showed that successful 3840-wide NV15 DMA-BUF import does not imply correct visual output; the tested stream still displayed green.

Read the historical documents as evidence only, not instructions to restore those patches.
