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

clone_head() {
  local repo=$1 branch=$2 dir=$3
  git clone --filter=blob:none --depth=1 --branch "$branch" "$repo" "$dir"
  git -C "$dir" rev-parse HEAD
}

echo "==> Resolving current RK3588 FFmpeg"
FFMPEG_COMMIT=$(clone_head "$RK_FFMPEG_REPOSITORY" "$RK_FFMPEG_BRANCH" "$FFMPEG_DIR")
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
FFMPEG_BUILD_PC="${WORK_ROOT}/ffmpeg-pkgconfig"
mkdir -p "$FFMPEG_BUILD_PC"
cp -a "${FFMPEG_PC}/." "$FFMPEG_BUILD_PC/"
while IFS= read -r -d '' pc; do
  sed -i "s|${RK_STACK_PREFIX}|${PREFIX_DIR}|g" "$pc"
done < <(find "$FFMPEG_BUILD_PC" -type f -name '*.pc' -print0)

echo "==> Resolving current RK3588 mpv/libmpv"
MPV_COMMIT=$(clone_head "$RK_MPV_REPOSITORY" "$RK_MPV_BRANCH" "$MPV_DIR")
rm -rf "$MPV_DIR/subprojects/libplacebo"
LIBPLACEBO_COMMIT=$(clone_head "$RK_LIBPLACEBO_REPOSITORY" "$RK_LIBPLACEBO_BRANCH" "$MPV_DIR/subprojects/libplacebo")
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

while IFS= read -r -d '' elf; do
  [[ -L "$elf" ]] && continue
  if readelf -h "$elf" >/dev/null 2>&1; then
    patchelf --set-rpath '$ORIGIN' "$elf" || true
  fi
done < <(find "${PREFIX_DIR}/lib" -maxdepth 1 -type f -name '*.so*' -print0)

LIBMPV_REAL=$(readlink -f "${PREFIX_DIR}/lib/libmpv.so")
readelf -h "$LIBMPV_REAL" | grep -q 'Machine:.*AArch64'
strings "$LIBMPV_REAL" | grep -q 'v4l2request'

cat >"${WORK_ROOT}/stack.env" <<EOF
RK_STACK_STAGE=${STAGE_DIR}
RK_STACK_PREFIX=${RK_STACK_PREFIX}
RK_STACK_LIBDIR=${PREFIX_DIR}/lib
RK_STACK_INCLUDEDIR=${PREFIX_DIR}/include
RK_FFMPEG_RESOLVED_COMMIT=${FFMPEG_COMMIT}
RK_MPV_RESOLVED_COMMIT=${MPV_COMMIT}
RK_LIBPLACEBO_RESOLVED_COMMIT=${LIBPLACEBO_COMMIT}
EOF

printf 'RK3588 stack built\n  FFmpeg %s\n  mpv %s\n  libplacebo %s\n' \
  "$FFMPEG_COMMIT" "$MPV_COMMIT" "$LIBPLACEBO_COMMIT"
