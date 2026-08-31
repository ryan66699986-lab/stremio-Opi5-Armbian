#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"

if [[ $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: native arm64 build required" >&2
  exit 1
fi

WORK_ROOT="${ROOT_DIR}/.work"
SOURCE_DIR="${WORK_ROOT}/stremio-shell"
BUILD_DIR="${SOURCE_DIR}/build"
RK_PREFIX="${ROOT_DIR}/.work/rk3588-stack/stage${RK_STACK_PREFIX}"
RK_LIBDIR="${RK_PREFIX}/lib"
RK_INCLUDEDIR="${RK_PREFIX}/include"

rm -rf "${SOURCE_DIR}"
mkdir -p "${WORK_ROOT}"

git clone --filter=blob:none --no-checkout "${STREMIO_SOURCE_REPOSITORY}" "${SOURCE_DIR}"
git -C "${SOURCE_DIR}" fetch --depth=1 origin "${STREMIO_SOURCE_COMMIT}"
git -C "${SOURCE_DIR}" checkout --detach "${STREMIO_SOURCE_COMMIT}"
git -C "${SOURCE_DIR}" submodule update --init --recursive deps/libmpv deps/singleapplication

git -C "${SOURCE_DIR}" apply "${ROOT_DIR}/patches/0001-linux-modern-libmpv.patch"

export PKG_CONFIG_PATH="${RK_LIBDIR}/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
export LD_LIBRARY_PATH="${RK_LIBDIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

cmake -S "${SOURCE_DIR}" -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/ \
  -DMPV_INCLUDE_DIR="${RK_INCLUDEDIR}" \
  -DMPV_LIBRARY_mpv="${RK_LIBDIR}/libmpv.so"
cmake --build "${BUILD_DIR}" --parallel "$(nproc)"

patchelf --set-rpath '$ORIGIN/rk3588/lib' "${BUILD_DIR}/stremio"
echo "Built Stremio ${STREMIO_VERSION}"
