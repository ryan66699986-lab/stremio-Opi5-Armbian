#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck disable=SC1091
source "${ROOT_DIR}/upstream.env"

if [[ $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: native arm64 build required" >&2
  exit 1
fi

RK_ENV="${ROOT_DIR}/.work/rk3588-stack/stack.env"
if [[ ! -f "$RK_ENV" ]]; then
  echo "error: RK3588 stack not found; run ./scripts/build-rk3588-stack.sh first" >&2
  exit 1
fi
# shellcheck disable=SC1090
source "$RK_ENV"

SOURCE_DIR="${ROOT_DIR}/.work/stremio-linux-shell"
rm -rf "$SOURCE_DIR"
git clone --filter=blob:none --depth=1 --branch "$STREMIO_SOURCE_BRANCH" \
  "$STREMIO_SOURCE_REPOSITORY" "$SOURCE_DIR"
STREMIO_COMMIT=$(git -C "$SOURCE_DIR" rev-parse HEAD)
STREMIO_VERSION=$(awk -F'"' '/^version = "/ {print $2; exit}' "$SOURCE_DIR/Cargo.toml")

BUILD_PC="${ROOT_DIR}/.work/current-pkgconfig"
rm -rf "$BUILD_PC"
mkdir -p "$BUILD_PC"
cp -a "${RK_STACK_LIBDIR}/pkgconfig/." "$BUILD_PC/"
while IFS= read -r -d '' pc; do
  sed -i "s|${RK_STACK_PREFIX}|${RK_STACK_STAGE}${RK_STACK_PREFIX}|g" "$pc"
done < <(find "$BUILD_PC" -type f -name '*.pc' -print0)

export PKG_CONFIG_PATH="${BUILD_PC}${PKG_CONFIG_PATH:+:${PKG_CONFIG_PATH}}"
export LD_LIBRARY_PATH="${RK_STACK_LIBDIR}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"

(
  cd "$SOURCE_DIR"
  cargo build --release --locked
)

BINARY="${SOURCE_DIR}/target/release/stremio-linux-shell"
test -x "$BINARY"
patchelf --set-rpath '$ORIGIN/rk3588/lib' "$BINARY"
readelf -h "$BINARY" | grep -q 'Machine:.*AArch64'
readelf -d "$BINARY" | grep -q 'Shared library: \[libmpv\.so'

grep -q 'env::var("SERVER_PATH")' "$SOURCE_DIR/src/server.rs"
test -f "$SOURCE_DIR/data/server.js"

cat >"${ROOT_DIR}/.work/current.env" <<EOF
STREMIO_VERSION=${STREMIO_VERSION}
PACKAGE_REVISION=${PACKAGE_REVISION}
STREMIO_RESOLVED_COMMIT=${STREMIO_COMMIT}
RK_FFMPEG_RESOLVED_COMMIT=${RK_FFMPEG_RESOLVED_COMMIT}
RK_MPV_RESOLVED_COMMIT=${RK_MPV_RESOLVED_COMMIT}
RK_LIBPLACEBO_RESOLVED_COMMIT=${RK_LIBPLACEBO_RESOLVED_COMMIT}
EOF

printf 'Stremio current built\n  version %s\n  Stremio %s\n  FFmpeg %s\n  mpv %s\n  libplacebo %s\n' \
  "$STREMIO_VERSION" "$STREMIO_COMMIT" "$RK_FFMPEG_RESOLVED_COMMIT" \
  "$RK_MPV_RESOLVED_COMMIT" "$RK_LIBPLACEBO_RESOLVED_COMMIT"
