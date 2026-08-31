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

echo "==> FFmpeg RK3588 V4L2-request"
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
  make -j"$(nproc)"
  make DESTDIR="$STAGE_DIR" install
)

# Rebase the staged FFmpeg pkg-config files for the mpv build only.
FFMPEG_BUILD_PC="${WORK_ROOT}/ffmpeg-pkgconfig"
mkdir -p "$FFMPEG_BUILD_PC"
cp -a "${PREFIX_DIR}/lib/pkgconfig/." "$FFMPEG_BUILD_PC/"
while IFS= read -r -d '' pc; do
  sed -i "s|${RK_STACK_PREFIX}|${PREFIX_DIR}|g" "$pc"
done < <(find "$FFMPEG_BUILD_PC" -type f -name '*.pc' -print0)

echo "==> mpv/libmpv gpu-next + RK3588 hwdec"
clone_pinned "$RK_MPV_REPOSITORY" "$RK_MPV_COMMIT" "$MPV_DIR"
git -C "$MPV_DIR" remote add gpu-next "$RK_MPV_GPU_NEXT_REPOSITORY"
git -C "$MPV_DIR" fetch --depth=2 gpu-next "$RK_MPV_GPU_NEXT_COMMIT"
git -C "$MPV_DIR" cherry-pick --no-commit "$RK_MPV_GPU_NEXT_COMMIT"

python3 "${ROOT_DIR}/scripts/patch-gpu-next-hwdec.py" "$MPV_DIR"
python3 "${ROOT_DIR}/scripts/patch-gpu-next-hwdec-opengl.py" "$MPV_DIR"
python3 "${ROOT_DIR}/scripts/patch-gpu-next-hwdec-preload.py" "$MPV_DIR"

# Required by the pinned libplacebo API.
sed -i 's/pl_dispatch_create(ra->log, ra->gpu)/pl_dispatch_create(ra->gpu->log, ra->gpu)/' \
  "$MPV_DIR/video/out/gpu_next/video.c"

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

# Keep the private runtime self-contained under /opt/stremio/rk3588/lib.
while IFS= read -r -d '' elf; do
  [[ -L "$elf" ]] && continue
  readelf -h "$elf" >/dev/null 2>&1 && patchelf --set-rpath '$ORIGIN' "$elf" || true
done < <(find "${PREFIX_DIR}/lib" -maxdepth 1 -type f -name '*.so*' -print0)

cat >"${WORK_ROOT}/stack.env" <<EOF
RK_STACK_STAGE=${STAGE_DIR}
RK_STACK_PREFIX=${RK_STACK_PREFIX}
RK_STACK_LIBDIR=${PREFIX_DIR}/lib
RK_STACK_INCLUDEDIR=${PREFIX_DIR}/include
EOF

echo "RK3588 stack built in ${PREFIX_DIR}"
