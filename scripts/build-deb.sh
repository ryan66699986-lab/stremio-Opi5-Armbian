#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"

CURRENT_ENV="${ROOT_DIR}/.work/current.env"
if [[ ! -f "$CURRENT_ENV" ]]; then
  echo "error: current Stremio build metadata missing; run ./scripts/build.sh first" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$CURRENT_ENV"

SOURCE_DIR="${ROOT_DIR}/.work/stremio-linux-shell"
RK_STAGE="${ROOT_DIR}/.work/rk3588-stack/stage${RK_STACK_PREFIX}"
EXPECTED_VERSION="${STREMIO_VERSION}-${PACKAGE_REVISION}"
EXPECTED_DEB="${ROOT_DIR}/stremio_${EXPECTED_VERSION}_arm64.deb"

if [[ $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: native arm64 package build required" >&2
  exit 1
fi

test -x "${SOURCE_DIR}/target/release/stremio-linux-shell"
test -e "${RK_STAGE}/lib/libmpv.so"

rm -rf "${SOURCE_DIR}/debian" "${SOURCE_DIR}/rk3588-stack"
cp -a "${ROOT_DIR}/debian" "${SOURCE_DIR}/debian"
cp "${ROOT_DIR}/packaging/stremio" "${SOURCE_DIR}/debian/stremio-launcher"
mkdir -p "${SOURCE_DIR}/rk3588-stack"
cp -a "${RK_STAGE}/lib" "${SOURCE_DIR}/rk3588-stack/lib"

OLD_CHANGELOG="${SOURCE_DIR}/debian/changelog.old"
mv "${SOURCE_DIR}/debian/changelog" "$OLD_CHANGELOG"
cat >"${SOURCE_DIR}/debian/changelog" <<EOF
stremio (${EXPECTED_VERSION}) resolute; urgency=medium

  * Build the latest Stremio Linux shell from ${STREMIO_SOURCE_BRANCH}.
  * Build current RK3588 FFmpeg/mpv/libplacebo branch heads.
  * Keep the multimedia stack isolated under /opt/stremio/rk3588.

 -- stremio-Opi5-Armbian maintainers <noreply@github.com>  $(date -R)

EOF
cat "$OLD_CHANGELOG" >>"${SOURCE_DIR}/debian/changelog"
rm -f "$OLD_CHANGELOG"

(
  cd "$SOURCE_DIR"
  dpkg-buildpackage -b -us -uc
)

BUILT_DEB=$(find "${ROOT_DIR}/.work" -maxdepth 1 -type f -name "stremio_${EXPECTED_VERSION}_arm64.deb" -print -quit)
if [[ -z "$BUILT_DEB" ]]; then
  echo "error: expected package stremio_${EXPECTED_VERSION}_arm64.deb was not produced" >&2
  exit 1
fi
cp -f "$BUILT_DEB" "$EXPECTED_DEB"

"${ROOT_DIR}/scripts/validate-deb.sh" "$EXPECTED_DEB"
echo "Package: $EXPECTED_DEB"
