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

rm -rf "${SOURCE_DIR}"
mkdir -p "${WORK_ROOT}"

git clone --filter=blob:none --no-checkout "${STREMIO_SOURCE_REPOSITORY}" "${SOURCE_DIR}"
git -C "${SOURCE_DIR}" fetch --depth=1 origin "${STREMIO_SOURCE_COMMIT}"
git -C "${SOURCE_DIR}" checkout --detach "${STREMIO_SOURCE_COMMIT}"
git -C "${SOURCE_DIR}" submodule update --init --recursive deps/libmpv deps/singleapplication

git -C "${SOURCE_DIR}" apply --check "${ROOT_DIR}/patches/0001-linux-modern-libmpv.patch"
git -C "${SOURCE_DIR}" apply "${ROOT_DIR}/patches/0001-linux-modern-libmpv.patch"

cmake -S "${SOURCE_DIR}" -B "${BUILD_DIR}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/
cmake --build "${BUILD_DIR}" --parallel "$(nproc)"

file "${BUILD_DIR}/stremio"
readelf -h "${BUILD_DIR}/stremio" | grep -E 'Class:|Machine:'
readelf -d "${BUILD_DIR}/stremio" | grep NEEDED || true

if ! readelf -h "${BUILD_DIR}/stremio" | grep -q 'Machine:.*AArch64'; then
  echo "error: build output is not AArch64" >&2
  exit 1
fi

echo "Built Stremio ${STREMIO_VERSION} from ${STREMIO_SOURCE_COMMIT}"
