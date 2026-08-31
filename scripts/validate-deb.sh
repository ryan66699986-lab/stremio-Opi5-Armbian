#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"

DEB=${1:?usage: validate-deb.sh path/to/stremio.deb}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

EXPECTED_VERSION="${STREMIO_VERSION}-${PACKAGE_REVISION}"
VERSION=$(dpkg-deb -f "$DEB" Version)
ARCH=$(dpkg-deb -f "$DEB" Architecture)
DEPENDS=$(dpkg-deb -f "$DEB" Depends)

[[ "$VERSION" == "$EXPECTED_VERSION" ]] || {
  echo "error: package version is $VERSION, expected $EXPECTED_VERSION" >&2
  exit 1
}
[[ "$ARCH" == arm64 ]] || {
  echo "error: package architecture is $ARCH, expected arm64" >&2
  exit 1
}
if grep -Eqi '(^|[,[:space:]])librubberband2([[:space:],]|$)' <<<"$DEPENDS"; then
  echo "error: obsolete librubberband2 dependency remains: $DEPENDS" >&2
  exit 1
fi

dpkg-deb -x "$DEB" "$TMP/root"
ROOT="$TMP/root"
STREMIO="$ROOT/opt/stremio/stremio"
RK_LIB="$ROOT/opt/stremio/rk3588/lib"

test -x "$STREMIO" || { echo "error: Stremio executable missing" >&2; exit 1; }
test -e "$RK_LIB/libmpv.so" || { echo "error: private RK3588 libmpv missing" >&2; exit 1; }
readelf -h "$STREMIO" | grep -q 'Machine:.*AArch64' || {
  echo "error: Stremio executable is not AArch64" >&2; exit 1;
}
readelf -d "$STREMIO" | grep -q 'Shared library: \[libmpv\.so' || {
  echo "error: Stremio is not linked to libmpv" >&2; exit 1;
}
[[ $(patchelf --print-rpath "$STREMIO") == '$ORIGIN/rk3588/lib' ]] || {
  echo "error: Stremio does not prefer the private RK3588 runtime" >&2; exit 1;
}

LIBMPV_REAL=$(readlink -f "$RK_LIB/libmpv.so")
readelf -h "$LIBMPV_REAL" | grep -q 'Machine:.*AArch64' || {
  echo "error: private libmpv is not AArch64" >&2; exit 1;
}
[[ $(patchelf --print-rpath "$LIBMPV_REAL") == '$ORIGIN' ]] || {
  echo "error: private libmpv is not self-contained under the RK3588 runtime" >&2; exit 1;
}
for marker in \
  'v4l2request' \
  'orp5: libmpv gpu-next hwdec bridge enabled' \
  'GL_EXT_EGL_image_storage' \
  'glEGLImageTargetTexStorageEXT' \
  'NV15 luma unpack'; do
  strings "$LIBMPV_REAL" | grep -Fq "$marker" || {
    echo "error: private libmpv is missing expected renderer marker: $marker" >&2
    exit 1
  }
done

LIBAVCODEC=$(find "$RK_LIB" -maxdepth 1 -type f -name 'libavcodec.so.*' -print -quit)
[[ -n "$LIBAVCODEC" ]] || {
  echo "error: private libavcodec is missing" >&2
  exit 1
}
readelf -h "$LIBAVCODEC" | grep -q 'Machine:.*AArch64' || {
  echo "error: private libavcodec is not AArch64" >&2; exit 1;
}

while IFS= read -r -d '' candidate; do
  if readelf -h "$candidate" >/dev/null 2>&1; then
    if readelf -d "$candidate" 2>/dev/null | grep -q 'librubberband\.so\.2'; then
      echo "error: packaged ELF directly requires librubberband.so.2: $candidate" >&2
      exit 1
    fi
  fi
done < <(find "$ROOT" -type f -print0)

echo "Validated: ${EXPECTED_VERSION} ARM64 package with private RK3588 V4L2-request/gpu-next/NV15 desktop-OpenGL runtime."
