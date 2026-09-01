# ORP branch status

This repository has one supported runtime baseline and a deliberately narrow experimental boundary.

## Usable builds

- **orp2** — current released baseline. This is the build used for real Orange Pi 5 Pro runtime testing.
- **orp3** — the only acceptable next experiment. It is a small copy-first variation on the orp2 design and must not be treated as a release until it passes board testing.

## Research-only work

**orp4 and everything derived from later gpu-next / custom copyback experiments are research-only. Do not install, merge, or use them as the runtime baseline.**

Those branches are retained only because their diffs and failure history may be useful when diagnosing the remaining RK3588 HEVC Main10 / NV15 presentation problem. They contain substantially more custom renderer/copyback code than the accepted orp2/orp3 design.

Closed PRs and branches beyond the orp3 cutoff should be read as historical investigation, not as candidates for deployment.

## Runtime rule

Physical Orange Pi 5 Pro testing is authoritative. CI proves build/package/linkage properties only; it does not approve playback behavior.
