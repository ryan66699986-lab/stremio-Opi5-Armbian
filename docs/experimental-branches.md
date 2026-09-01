# ORP branch status

This repository has one supported runtime baseline.

## Usable build

- **orp2** — current released baseline. This is the build used for real Orange Pi 5 Pro runtime testing.

## Research-only work

**orp3 and everything after it are research-only. Do not install, merge, or use them as the runtime baseline.**

There are two different ORP3 histories in the repository and both are research-only:

- the historical ORP3 copy-first `v4l2request-copy,v4l2request,auto-safe` experiment;
- the later clean ORP3 candidate from ORP2 that changed only `vd-lavc-dr=no` to test whether libavcodec direct rendering caused the 1920x804 Main10 NV15 stride failure.

The clean ORP3 candidate passed CI but failed the physical-board acceptance test. On the failing 1920x804 HEVC Main10 stream it still produced NV15 pitch 2400 and the same Mesa `WSI pitch not properly aligned` / DMA-BUF import failure. Disabling direct rendering therefore did not change the problematic allocation and did not solve presentation.

Control tests remained healthy: H.264 1920x804 continued to use V4L2 Request / rkvdec with NV12 pitch 1920, and HEVC Main10 at both 3840x2160 and 3840x1608 used V4L2 Request / rkvdec with NV15 pitch 4800 and imported successfully.

These results strengthen the width/pitch alignment diagnosis and narrow future work toward the NV15 producer/consumer stride boundary. The 64-byte alignment explanation remains a working hypothesis until confirmed by a controlled width matrix or direct observation of the relevant Mesa alignment requirement.

Later gpu-next and custom copyback branches are also retained only because their diffs and failure history may be useful when diagnosing the RK3588 HEVC Main10 / NV15 presentation problem. These branches contain experimental renderer/copyback approaches and are not deployment candidates.

Closed PRs and branches from orp3 onward should be read as historical investigation only.

## Runtime rule

Physical Orange Pi 5 Pro testing is authoritative. CI proves build/package/linkage properties only; it does not approve playback behavior.
