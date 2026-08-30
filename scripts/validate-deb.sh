#!/usr/bin/env bash
set -euo pipefail

DEB=${1:?usage: validate-deb.sh path/to/stremio.deb}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

dpkg-deb --info "$DEB"
dpkg-deb --contents "$DEB"

ARCH=$(dpkg-deb -f "$DEB" Architecture)
DEPENDS=$(dpkg-deb -f "$DEB" Depends)

[[ "$ARCH" == arm64 ]] || { echo "error: package architecture is $ARCH, expected arm64" >&2; exit 1; }
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
strings "$LIBMPV_REAL" | grep -q 'v4l2request' || {
  echo "error: private libmpv does not contain V4L2-request support" >&2; exit 1;
}

# The private FFmpeg build must expose the V4L2 Request hwdevice ABI.
LIBAVUTIL=$(find "$RK_LIB" -maxdepth 1 -type f -name 'libavutil.so.*' -print -quit)
LIBAVCODEC=$(find "$RK_LIB" -maxdepth 1 -type f -name 'libavcodec.so.*' -print -quit)
[[ -n "$LIBAVUTIL" && -n "$LIBAVCODEC" ]] || {
  echo "error: private FFmpeg runtime libraries are missing" >&2; exit 1;
}
readelf -h "$LIBAVCODEC" | grep -q 'Machine:.*AArch64' || {
  echo "error: private libavcodec is not AArch64" >&2; exit 1;
}

while IFS= read -r -d '' candidate; do
  if readelf -h "$candidate" >/dev/null 2>&1; then
    echo "ELF: ${candidate#${ROOT}}"
    readelf -d "$candidate" | grep -E 'NEEDED|RPATH|RUNPATH' || true
    if readelf -d "$candidate" 2>/dev/null | grep -q 'librubberband\.so\.2'; then
      echo "error: packaged ELF directly requires librubberband.so.2: $candidate" >&2
      exit 1
    fi
  fi
done < <(find "$ROOT" -type f -print0)

echo "Validated: ARM64 package with private RK3588 V4L2-request libmpv/FFmpeg stack and no obsolete librubberband2 dependency."
