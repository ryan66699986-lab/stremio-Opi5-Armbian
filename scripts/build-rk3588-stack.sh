#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"

if [[ $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: native arm64 build required" >&2
  exit 1
fi

WORK_ROOT="${ROOT_DIR}/.work/rk3588-stack"
FFMPEG_DIR="${WORK_ROOT}/ffmpeg"
MPV_DIR="${WORK_ROOT}/mpv"
STAGE_DIR="${WORK_ROOT}/stage"
PREFIX_DIR="${STAGE_DIR}${RK_STACK_PREFIX}"

rm -rf "${WORK_ROOT}"
mkdir -p "${WORK_ROOT}" "${STAGE_DIR}"

clone_pinned() {
  local repo=$1 commit=$2 dir=$3
  git clone --filter=blob:none --no-checkout "$repo" "$dir"
  git -C "$dir" fetch --depth=1 origin "$commit"
  git -C "$dir" checkout --detach "$commit"
}

echo "==> Building pinned FFmpeg V4L2-request stack"
clone_pinned "$RK_FFMPEG_REPOSITORY" "$RK_FFMPEG_COMMIT" "$FFMPEG_DIR"
(
  cd "$FFMPEG_DIR"
  ./configure \
    --prefix="$RK_STACK_PREFIX" \
    --libdir="$RK_STACK_PREFIX/lib" \
    --incdir="$RK_STACK_PREFIX/include" \
    --enable-shared \
    --disable-static \
    --disable-programs \
    --disable-doc \
    --disable-debug \
    --enable-pic \
    --enable-gnutls \
    --enable-libdrm \
    --enable-libudev \
    --enable-v4l2-request
  grep -E 'CONFIG_V4L2_REQUEST[[:space:]]+1' config.h
  make -j"$(nproc)"
  make DESTDIR="$STAGE_DIR" install
)

FFMPEG_PC="${PREFIX_DIR}/lib/pkgconfig"
test -f "${FFMPEG_PC}/libavcodec.pc"
test -f "${PREFIX_DIR}/include/libavutil/hwcontext.h"
grep -q 'AV_HWDEVICE_TYPE_V4L2REQUEST' "${PREFIX_DIR}/include/libavutil/hwcontext.h"

# FFmpeg's installed .pc files intentionally describe the final runtime prefix
# (/opt/stremio/rk3588). During this staged package build, however, mpv must
# compile and link against the DESTDIR copy. Give Meson a temporary pkg-config
# view with every final-prefix occurrence rebased to the staging tree. The
# package contents themselves retain the correct final /opt paths.
FFMPEG_BUILD_PC="${WORK_ROOT}/ffmpeg-pkgconfig"
rm -rf "$FFMPEG_BUILD_PC"
mkdir -p "$FFMPEG_BUILD_PC"
cp -a "${FFMPEG_PC}/." "$FFMPEG_BUILD_PC/"
while IFS= read -r -d '' pc; do
  sed -i "s|${RK_STACK_PREFIX}|${PREFIX_DIR}|g" "$pc"
done < <(find "$FFMPEG_BUILD_PC" -type f -name '*.pc' -print0)

echo "==> Verifying staged FFmpeg pkg-config paths"
PKG_CONFIG_PATH="$FFMPEG_BUILD_PC" pkg-config --cflags libavutil | tee /tmp/rk-libavutil-cflags.txt
grep -F "${PREFIX_DIR}/include" /tmp/rk-libavutil-cflags.txt
PKG_CONFIG_PATH="$FFMPEG_BUILD_PC" pkg-config --libs libavutil | tee /tmp/rk-libavutil-libs.txt
grep -F "${PREFIX_DIR}/lib" /tmp/rk-libavutil-libs.txt

echo "==> Building pinned mpv/libmpv V4L2-request stack"
clone_pinned "$RK_MPV_REPOSITORY" "$RK_MPV_COMMIT" "$MPV_DIR"

# Stremio uses the libmpv render API rather than mpv's standalone vo_gpu_next.
# Apply the pinned upstream gpu-next render-API backend on top of the Rockchip
# fork without replacing its RK3588 V4L2-request/NV15 work.
echo "==> Applying pinned libmpv gpu-next render backend"
git -C "$MPV_DIR" remote add gpu-next "$RK_MPV_GPU_NEXT_REPOSITORY"
git -C "$MPV_DIR" fetch --depth=2 gpu-next "$RK_MPV_GPU_NEXT_COMMIT"
git -C "$MPV_DIR" cherry-pick --no-commit "$RK_MPV_GPU_NEXT_COMMIT"
grep -q 'MPV_RENDER_PARAM_BACKEND' "$MPV_DIR/include/mpv/render.h"
test -f "$MPV_DIR/video/out/gpu_next/libmpv_gpu_next.c"

# orp5 restores the hwdec side that the draft libmpv gpu-next backend does not
# implement upstream: V4L2-request device loading, DRM-PRIME DMA-BUF mapping,
# and RK3588 NV15 GPU unpacking into libplacebo-compatible 10-bit planes.
echo "==> Applying libmpv gpu-next RK3588 hwdec bridge"
python3 "${ROOT_DIR}/scripts/patch-gpu-next-hwdec.py" "$MPV_DIR"
# libplacebo's queue can retain multiple mapped source frames. Do not share one
# mpv ra_hwdec_mapper across those queue entries: mapping a new image unmaps the
# previous one. Give each hardware frame its own mapper before compiling.
python3 "${ROOT_DIR}/scripts/patch-gpu-next-hwdec-frame-lifetime.py" "$MPV_DIR"
# Queue entries can span a resolution transition, so size the NV15 unpack target
# from the acquired frame rather than mutable engine-global current_params.
# This script also installs the orp6 legacy OpenGL/EGL texture bridge.
python3 "${ROOT_DIR}/scripts/patch-gpu-next-hwdec-frame-geometry.py" "$MPV_DIR"
# In libmpv the decoder can request hwdec from a thread where Qt's EGL context
# is not current. Preload DRM-PRIME/V4L2-request while the render context is
# being created, matching the context-thread requirement of dmabuf_interop_gl.
python3 "${ROOT_DIR}/scripts/patch-gpu-next-hwdec-preload.py" "$MPV_DIR"
# The pinned libplacebo dispatch API expects its own pl_log, not mpv's mp_log.
sed -i 's/pl_dispatch_create(ra->log, ra->gpu)/pl_dispatch_create(ra->gpu->log, ra->gpu)/' \
  "$MPV_DIR/video/out/gpu_next/video.c"
grep -q 'orp5: libmpv gpu-next hwdec bridge enabled' "$MPV_DIR/video/out/gpu_next/hwdec_compat.c"
grep -q 'orp5: per-frame hwdec mapper lifetime enabled' "$MPV_DIR/video/out/gpu_next/hwdec_compat.c"
grep -q 'orp6: EGL/OpenGL DMA-BUF hwdec interop enabled' "$MPV_DIR/video/out/gpu_next/hwdec_compat.c"
grep -q 'orp7: V4L2-request DRM-PRIME hwdec preloaded on render/EGL thread' "$MPV_DIR/video/out/gpu_next/hwdec_compat.c"
grep -q 'AV_HWDEVICE_TYPE_V4L2REQUEST' "$MPV_DIR/video/out/gpu_next/hwdec_compat.c"
grep -q 'supports_nv15_byte_planes = true' "$MPV_DIR/video/out/hwdec/dmabuf_interop_gl.c"
grep -q 'struct mp_image \*mpi = frame->user_data;' "$MPV_DIR/video/out/gpu_next/video.c"
grep -q 'mpi->params.w / 2' "$MPV_DIR/video/out/gpu_next/video.c"
grep -q 'pl_dispatch_create(ra->gpu->log, ra->gpu)' "$MPV_DIR/video/out/gpu_next/video.c"

clone_pinned "$RK_LIBPLACEBO_REPOSITORY" "$RK_LIBPLACEBO_COMMIT" "$MPV_DIR/subprojects/libplacebo"
git -C "$MPV_DIR/subprojects/libplacebo" submodule update --init --recursive

export PKG_CONFIG_PATH="${FFMPEG_BUILD_PC}${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
export LD_LIBRARY_PATH="${PREFIX_DIR}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

meson setup "${MPV_DIR}/build" "$MPV_DIR" \
  --prefix="$RK_STACK_PREFIX" \
  --libdir=lib \
  --buildtype=release \
  --force-fallback-for=libplacebo \
  -Dcplayer=false \
  -Dlibmpv=true \
  -Dbuild-date=false \
  -Dtests=false \
  -Dmanpage-build=disabled \
  -Dhtml-build=disabled \
  -Dpdf-build=disabled \
  -Dv4l2request=enabled \
  -Ddrm=enabled \
  -Degl=enabled \
  -Dplain-gl=enabled \
  -Dwayland=enabled \
  -Dx11=enabled \
  -Dvaapi=disabled \
  -Dvdpau=disabled \
  -Dcuda-hwaccel=disabled \
  -Dcuda-interop=disabled

meson compile -C "${MPV_DIR}/build" -j "$(nproc)"
DESTDIR="$STAGE_DIR" meson install -C "${MPV_DIR}/build"

test -e "${PREFIX_DIR}/lib/libmpv.so"
test -e "${PREFIX_DIR}/include/mpv/client.h"
grep -q 'MPV_RENDER_PARAM_BACKEND' "${PREFIX_DIR}/include/mpv/render.h"

# Keep the private multimedia stack self-contained. Stremio gets its own
# $ORIGIN/rk3588/lib RPATH; private libmpv/FFmpeg libraries resolve peers here.
while IFS= read -r -d '' elf; do
  if [[ -L "$elf" ]]; then
    continue
  fi
  if readelf -h "$elf" >/dev/null 2>&1; then
    patchelf --set-rpath '$ORIGIN' "$elf" || true
  fi
done < <(find "${PREFIX_DIR}/lib" -maxdepth 1 -type f -name '*.so*' -print0)

LIBMPV_REAL=$(readlink -f "${PREFIX_DIR}/lib/libmpv.so")
readelf -h "$LIBMPV_REAL" | grep -q 'Machine:.*AArch64'
readelf -d "$LIBMPV_REAL" | grep NEEDED
strings "$LIBMPV_REAL" | grep -q 'v4l2request'
strings "$LIBMPV_REAL" | grep -q 'gpu-next'
strings "$LIBMPV_REAL" | grep -q 'orp5: libmpv gpu-next hwdec bridge enabled'
strings "$LIBMPV_REAL" | grep -q 'orp5: per-frame hwdec mapper lifetime enabled'
strings "$LIBMPV_REAL" | grep -q 'orp6: EGL/OpenGL DMA-BUF hwdec interop enabled'
strings "$LIBMPV_REAL" | grep -q 'orp7: V4L2-request DRM-PRIME hwdec preloaded on render/EGL thread'
strings "$LIBMPV_REAL" | grep -q 'unpacked NV15 with libplacebo GPU dispatch'

cat >"${WORK_ROOT}/stack.env" <<EOF
RK_STACK_STAGE=${STAGE_DIR}
RK_STACK_PREFIX=${RK_STACK_PREFIX}
RK_STACK_LIBDIR=${PREFIX_DIR}/lib
RK_STACK_INCLUDEDIR=${PREFIX_DIR}/include
EOF

echo "RK3588 stack built:"
echo "  FFmpeg: ${RK_FFMPEG_COMMIT}"
echo "  mpv: ${RK_MPV_COMMIT}"
echo "  libmpv gpu-next: ${RK_MPV_GPU_NEXT_COMMIT}"
echo "  RK3588 hwdec bridge: EGL DMA-BUF + per-frame mappers + render-thread V4L2-request preload"
echo "  prefix: ${PREFIX_DIR}"
