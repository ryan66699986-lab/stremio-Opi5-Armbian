#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"
SOURCE_DIR="${ROOT_DIR}/.work/stremio-shell"
EXPECTED_VERSION="${STREMIO_VERSION}-${PACKAGE_REVISION}"
EXPECTED_DEB="${ROOT_DIR}/stremio_${EXPECTED_VERSION}_arm64.deb"

if [[ $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: native arm64 package build required" >&2
  exit 1
fi

if [[ ! -x "${SOURCE_DIR}/build/stremio" ]]; then
  echo "error: source build not found; run ./scripts/build.sh first" >&2
  exit 1
fi

rm -rf "${SOURCE_DIR}/debian"
cp -a "${ROOT_DIR}/debian" "${SOURCE_DIR}/debian"

curl --fail --location --proto '=https' --tlsv1.2 \
  --output "${SOURCE_DIR}/server.js" "${STREMIO_SERVER_URL}"

(
  cd "${SOURCE_DIR}"
  dpkg-buildpackage -b -us -uc
)

BUILT_DEB=$(find "${ROOT_DIR}/.work" -maxdepth 1 -type f -name "stremio_${EXPECTED_VERSION}_arm64.deb" -print -quit)
if [[ -z "${BUILT_DEB}" ]]; then
  echo "error: expected package stremio_${EXPECTED_VERSION}_arm64.deb was not produced" >&2
  exit 1
fi
cp -f "${BUILT_DEB}" "${EXPECTED_DEB}"

"${ROOT_DIR}/scripts/validate-deb.sh" "${EXPECTED_DEB}"
echo "Package: ${EXPECTED_DEB}"
