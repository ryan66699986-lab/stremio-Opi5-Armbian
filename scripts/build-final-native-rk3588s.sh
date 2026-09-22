#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STREMIO_REPO=https://github.com/Stremio/stremio-linux-shell.git
STREMIO_TAG=v1.2.0
STREMIO_COMMIT=c6e7cd22e23ed6401e573fe7fe1a023fc07399a2
PATCH_FILE="$ROOT_DIR/patches/0002-stremio-linux-shell-rk3588-v4l2request-copy.patch"
RK_PREFIX=/opt/stremio/rk3588
WORK="$ROOT_DIR/.work/final-native-rk3588s"
SRC="$WORK/stremio-linux-shell"
TARGET="$WORK/cargo-target"
STAGE="$WORK/stage"
STAGE_APP="$STAGE/opt/stremio"
STAGE_RK="$STAGE$RK_PREFIX"

if [[ $(uname -m) != aarch64 || $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: native ARM64 build required" >&2
  exit 1
fi

"$ROOT_DIR/scripts/build-rk3588-stack.sh"
RK_SOURCE="$ROOT_DIR/.work/rk3588-stack/stage$RK_PREFIX"
test -e "$RK_SOURCE/lib/libmpv.so"
test -d "$RK_SOURCE/lib/pkgconfig"

rm -rf "$WORK"
mkdir -p "$WORK" "$STAGE_APP" "$STAGE_RK"

git clone --filter=blob:none --no-checkout "$STREMIO_REPO" "$SRC"
git -C "$SRC" fetch --depth=1 origin "$STREMIO_COMMIT"
git -C "$SRC" checkout --detach "$STREMIO_COMMIT"
[[ $(git -C "$SRC" rev-parse HEAD) == "$STREMIO_COMMIT" ]]
git -C "$SRC" submodule update --init --recursive

git -C "$SRC" apply --check "$PATCH_FILE"
git -C "$SRC" apply "$PATCH_FILE"

export PKG_CONFIG_PATH="$RK_SOURCE/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$RK_SOURCE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CARGO_TARGET_DIR="$TARGET"
export LC_NUMERIC=C
export SERVER_PATH=data/server.js
export RUSTFLAGS="${RUSTFLAGS:-} -C link-arg=-Wl,-rpath,$RK_PREFIX/lib"

cargo build --release --locked --manifest-path "$SRC/Cargo.toml"
test -x "$TARGET/release/stremio-linux-shell"
test -s "$SRC/data/server.js"

install -m755 "$TARGET/release/stremio-linux-shell" "$STAGE_APP/stremio"
install -m644 "$SRC/data/server.js" "$STAGE_APP/server.js"
printf '%s\n' "$STREMIO_TAG" > "$STAGE_APP/VERSION"
printf '%s\n' "$STREMIO_COMMIT" > "$STAGE_APP/SOURCE_COMMIT"
cp -a "$RK_SOURCE/." "$STAGE_RK/"

readelf -h "$STAGE_APP/stremio" | grep -q 'Machine:.*AArch64'
readelf -d "$STAGE_APP/stremio" | grep -E 'NEEDED|RPATH|RUNPATH' || true
strings "$(readlink -f "$STAGE_RK/lib/libmpv.so")" | grep -q v4l2request

echo "Final native RK3588S Stremio stage built at: $STAGE"
echo "Stremio: $STREMIO_TAG ($STREMIO_COMMIT)"
echo "Private media stack: $RK_PREFIX"
