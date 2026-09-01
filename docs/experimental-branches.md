# ORP branch status

This repository has one supported runtime baseline.

## Usable build

- **orp2** — current released baseline. This is the build used for real Orange Pi 5 Pro runtime testing.

## Research-only work

**orp3 and everything after it are research-only. Do not install, merge, or use them as the runtime baseline.**

orp3 is retained only as historical context for the copy-first `v4l2request-copy,v4l2request,auto-safe` experiment. Later gpu-next and custom copyback branches are also retained only because their diffs and failure history may be useful when diagnosing the RK3588 HEVC Main10 / NV15 presentation problem.

These branches contain experimental renderer/copyback approaches and are not deployment candidates.

Closed PRs and branches from orp3 onward should be read as historical investigation only.

## Runtime rule

Physical Orange Pi 5 Pro testing is authoritative. CI proves build/package/linkage properties only; it does not approve playback behavior.
