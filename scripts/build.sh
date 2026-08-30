#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"

if [[ $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: native arm64 build required; current architecture is $(dpkg --print-architecture)" >&2
  exit 1
fi

WORK_ROOT="${ROOT_DIR}/.work"
SOURCE_DIR="${WORK_ROOT}/stremio-shell"
BUILD_DIR="${SOURCE_DIR}/build"
RK_WORK="${ROOT_DIR}/.work/rk3588-stack"
RK_STAGE="${RK_WORK}/stage"
RK_PREFIX="${RK_STAGE}${RK_STACK_PREFIX}"
RK_LIBDIR="${RK_PREFIX}/lib"
RK_INCLUDEDIR="${RK_PREFIX}/include"

if [[ ! -e "${RK_LIBDIR}/libmpv.so" ]]; then
  echo "error: RK3588 multimedia stack not found; run ./scripts/build-rk3588-stack.sh first" >&2
  exit 1
fi

rm -rf "${SOURCE_DIR}"
mkdir -p "${WORK_ROOT}"

git clone --filter=blob:none --no-checkout "${STREMIO_SOURCE_REPOSITORY}" "${SOURCE_DIR}"
git -C "${SOURCE_DIR}" fetch --depth=1 origin "${STREMIO_SOURCE_COMMIT}"
git -C "${SOURCE_DIR}" checkout --detach "${STREMIO_SOURCE_COMMIT}"
git -C "${SOURCE_DIR}" submodule update --init --recursive deps/libmpv deps/singleapplication

git -C "${SOURCE_DIR}" apply --check "${ROOT_DIR}/patches/0001-linux-modern-libmpv.patch"
git -C "${SOURCE_DIR}" apply "${ROOT_DIR}/patches/0001-linux-modern-libmpv.patch"

export PKG_CONFIG_PATH="${RK_LIBDIR}/pkgconfig${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
export LD_LIBRARY_PATH="${RK_LIBDIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

cmake -S "${SOURCE_DIR}" -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/ \
  -DMPV_INCLUDE_DIR="${RK_INCLUDEDIR}" \
  -DMPV_LIBRARY_mpv="${RK_LIBDIR}/libmpv.so"
cmake --build "${BUILD_DIR}" --parallel "$(nproc)"

# The installed executable lives in /opt/stremio, with the private multimedia
# stack in /opt/stremio/rk3588/lib.
patchelf --set-rpath '$ORIGIN/rk3588/lib' "${BUILD_DIR}/stremio"

file "${BUILD_DIR}/stremio"
readelf -h "${BUILD_DIR}/stremio" | grep -E 'Class:|Machine:'
readelf -d "${BUILD_DIR}/stremio" | grep -E 'NEEDED|RPATH|RUNPATH' || true

if ! readelf -h "${BUILD_DIR}/stremio" | grep -q 'Machine:.*AArch64'; then
  echo "error: build output is not AArch64" >&2
  exit 1
fi
if ! readelf -d "${BUILD_DIR}/stremio" | grep -q 'Shared library: \[libmpv\.so'; then
  echo "error: Stremio did not link against libmpv" >&2
  exit 1
fi
if ! patchelf --print-rpath "${BUILD_DIR}/stremio" | grep -qx '\$ORIGIN/rk3588/lib'; then
  echo "error: Stremio private multimedia RPATH is missing" >&2
  exit 1
fi

echo "Built Stremio ${STREMIO_VERSION} from ${STREMIO_SOURCE_COMMIT} against RK3588 V4L2-request libmpv"
