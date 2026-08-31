#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"

SOURCE_DIR="${ROOT_DIR}/.work/stremio-shell"
RK_STAGE="${ROOT_DIR}/.work/rk3588-stack/stage${RK_STACK_PREFIX}"
VERSION="${STREMIO_VERSION}-${PACKAGE_REVISION}"
OUTPUT="${ROOT_DIR}/stremio_${VERSION}_arm64.deb"

rm -rf "${SOURCE_DIR}/debian" "${SOURCE_DIR}/rk3588-stack"
cp -a "${ROOT_DIR}/debian" "${SOURCE_DIR}/debian"
mkdir -p "${SOURCE_DIR}/rk3588-stack"
cp -a "${RK_STAGE}/include" "${SOURCE_DIR}/rk3588-stack/include"
cp -a "${RK_STAGE}/lib" "${SOURCE_DIR}/rk3588-stack/lib"

curl --fail --location --proto '=https' --tlsv1.2 \
  --output "${SOURCE_DIR}/server.js" "${STREMIO_SERVER_URL}"

(
  cd "${SOURCE_DIR}"
  dpkg-buildpackage -b -us -uc
)

BUILT=$(find "${ROOT_DIR}/.work" -maxdepth 1 -type f \
  -name "stremio_${VERSION}_arm64.deb" -print -quit)
cp -f "$BUILT" "$OUTPUT"
echo "Package: $OUTPUT"
