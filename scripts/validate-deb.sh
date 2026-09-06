#!/usr/bin/env bash
set -euo pipefail

DEB=${1:?usage: validate-deb.sh path/to/stremio.deb}
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

dpkg-deb --info "$DEB"
dpkg-deb --contents "$DEB"

ARCH=$(dpkg-deb -f "$DEB" Architecture)
[[ "$ARCH" == arm64 ]] || { echo "error: package architecture is $ARCH, expected arm64" >&2; exit 1; }

dpkg-deb -x "$DEB" "$TMP/root"
ROOT="$TMP/root"
STREMIO="$ROOT/opt/stremio/stremio"
RK_LIB="$ROOT/opt/stremio/rk3588/lib"

test -x "$STREMIO" || { echo "error: Stremio executable missing" >&2; exit 1; }
test -x "$ROOT/usr/bin/stremio" || { echo "error: Stremio launcher missing" >&2; exit 1; }
test -f "$ROOT/opt/stremio/server.js" || { echo "error: Stremio server.js missing" >&2; exit 1; }
test -e "$RK_LIB/libmpv.so" || { echo "error: private RK3588 libmpv missing" >&2; exit 1; }

readelf -h "$STREMIO" | grep 'Machine:.*AArch64' >/dev/null || {
  echo "error: Stremio executable is not AArch64" >&2; exit 1;
}
readelf -d "$STREMIO" | grep 'Shared library: \[libmpv\.so' >/dev/null || {
  echo "error: Stremio is not linked to libmpv" >&2; exit 1;
}
[[ $(patchelf --print-rpath "$STREMIO") == '$ORIGIN/rk3588/lib' ]] || {
  echo "error: Stremio does not prefer the private RK3588 runtime" >&2; exit 1;
}

LIBMPV_REAL=$(readlink -f "$RK_LIB/libmpv.so")
readelf -h "$LIBMPV_REAL" | grep 'Machine:.*AArch64' >/dev/null || {
  echo "error: private libmpv is not AArch64" >&2; exit 1;
}
# Consume the complete strings output. grep -q can make strings exit on SIGPIPE
# under pipefail even when the requested marker was found.
strings "$LIBMPV_REAL" | grep 'v4l2request' >/dev/null || {
  echo "error: private libmpv does not contain V4L2-request support" >&2; exit 1;
}

LIBAVCODEC=$(find "$RK_LIB" -maxdepth 1 -type f -name 'libavcodec.so.*' -print -quit)
[[ -n "$LIBAVCODEC" ]] || { echo "error: private libavcodec missing" >&2; exit 1; }
readelf -h "$LIBAVCODEC" | grep 'Machine:.*AArch64' >/dev/null || {
  echo "error: private libavcodec is not AArch64" >&2; exit 1;
}

echo "Validated current ARM64 Stremio package with private RK3588 V4L2-request stack."
