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
if ! grep -Eq '(^|[,[:space:]])libmpv2([[:space:],]|$)' <<<"$DEPENDS"; then
  echo "error: generated package metadata does not depend on libmpv2: $DEPENDS" >&2
  exit 1
fi

dpkg-deb -x "$DEB" "$TMP/root"
FOUND_ELF=0
while IFS= read -r -d '' candidate; do
  if readelf -h "$candidate" >/dev/null 2>&1; then
    FOUND_ELF=1
    echo "ELF: ${candidate#${TMP}/root}"
    readelf -d "$candidate" | grep NEEDED || true
    if readelf -d "$candidate" 2>/dev/null | grep -q 'librubberband\.so\.2'; then
      echo "error: packaged ELF directly requires librubberband.so.2: $candidate" >&2
      exit 1
    fi
  fi
done < <(find "$TMP/root" -type f -print0)

[[ "$FOUND_ELF" == 1 ]] || { echo "error: no ELF file found in package" >&2; exit 1; }
echo "Validated: arm64 package, libmpv2 dependency present, no librubberband2 metadata or librubberband.so.2 NEEDED entry."
