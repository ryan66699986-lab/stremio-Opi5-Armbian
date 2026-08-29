#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
DEB="${TMP}/upstream.deb"

curl --fail --location --proto '=https' --tlsv1.2 --output "$DEB" "$FRAGARRAY_REFERENCE_DEB_URL"
echo "${FRAGARRAY_REFERENCE_DEB_SHA256}  ${DEB}" | sha256sum --check --status || {
  echo "error: upstream reference package checksum mismatch" >&2
  exit 1
}

echo '=== dpkg-deb --info ==='
dpkg-deb --info "$DEB"
echo '=== dpkg-deb --contents ==='
dpkg-deb --contents "$DEB"
echo '=== declared dependencies ==='
dpkg-deb -f "$DEB" Depends

dpkg-deb -x "$DEB" "${TMP}/root"
DIRECT_RUBBERBAND2=0
FOUND_ELF=0
while IFS= read -r -d '' candidate; do
  if readelf -h "$candidate" >/dev/null 2>&1; then
    FOUND_ELF=1
    echo "=== ELF ${candidate#${TMP}/root} ==="
    readelf -h "$candidate" | grep -E 'Class:|Machine:' || true
    readelf -d "$candidate" | grep NEEDED || true
    if readelf -d "$candidate" 2>/dev/null | grep -q 'librubberband\.so\.2'; then
      DIRECT_RUBBERBAND2=1
    fi
  fi
done < <(find "${TMP}/root" -type f -print0)

[[ "$FOUND_ELF" == 1 ]] || { echo 'error: reference package contains no ELF files' >&2; exit 1; }
if [[ "$DIRECT_RUBBERBAND2" == 1 ]]; then
  echo 'error: reference package contains an ELF object that directly needs librubberband.so.2; packaging-only removal is not justified.' >&2
  exit 1
fi

echo 'Result: the reference package declares librubberband2 in package metadata, but no packaged ELF directly needs librubberband.so.2.'
