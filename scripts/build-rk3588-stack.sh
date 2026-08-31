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
  -Dsdl2-gamepad=enabled \
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

cat >"${WORK_ROOT}/stack.env" <<EOF
RK_STACK_STAGE=${STAGE_DIR}
RK_STACK_PREFIX=${RK_STACK_PREFIX}
RK_STACK_LIBDIR=${PREFIX_DIR}/lib
RK_STACK_INCLUDEDIR=${PREFIX_DIR}/include
EOF

echo "RK3588 stack built:"
echo "  FFmpeg: ${RK_FFMPEG_COMMIT}"
echo "  mpv: ${RK_MPV_COMMIT}"
echo "  prefix: ${PREFIX_DIR}"
