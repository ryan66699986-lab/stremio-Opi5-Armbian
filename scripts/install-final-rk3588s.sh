#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STREMIO_REPO=https://github.com/Stremio/stremio-linux-shell.git
STREMIO_TAG=v1.2.0
STREMIO_COMMIT=c6e7cd22e23ed6401e573fe7fe1a023fc07399a2
PATCH_FILE="$ROOT_DIR/patches/0002-stremio-linux-shell-rk3588-v4l2request-copy.patch"
PREFIX=/opt/stremio
RK_PREFIX=/opt/stremio/rk3588
WORK="$ROOT_DIR/.work/final-native-rk3588s"
SRC="$WORK/stremio-linux-shell"
TARGET="$WORK/cargo-target"
APP_ID=com.stremio.Stremio

if [[ $(uname -m) != aarch64 || $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: this final installer must run natively on ARM64" >&2
  exit 1
fi

if [[ -r /proc/device-tree/compatible ]]; then
  COMPAT=$(tr '\0' ' ' </proc/device-tree/compatible)
  if ! grep -Eqi 'rk3588|orangepi.*5' <<<"$COMPAT"; then
    echo "error: RK3588/RK3588S device tree not detected: $COMPAT" >&2
    exit 1
  fi
fi

sudo apt-get update
sudo apt-get install -y \
  binutils build-essential ca-certificates cmake curl file git meson ninja-build patch patchelf pkgconf \
  libdrm-dev libegl1-mesa-dev libgbm-dev libgnutls28-dev libudev-dev libvulkan-dev \
  libwayland-dev wayland-protocols libx11-dev libxext-dev libxkbcommon-dev libxpresent-dev libxrandr-dev \
  libasound2-dev libass-dev libdisplay-info-dev libjpeg-dev liblcms2-dev libpipewire-0.3-dev libpulse-dev \
  libgtk-4-dev libadwaita-1-dev libwebkitgtk-6.0-dev libepoxy-dev gettext nodejs rustc cargo

# Keep distro multimedia untouched. Build the known RK3588 V4L2-request stack privately.
"$ROOT_DIR/scripts/build-rk3588-stack.sh"
RK_STAGE="$ROOT_DIR/.work/rk3588-stack/stage$RK_PREFIX"
test -e "$RK_STAGE/lib/libmpv.so"
test -d "$RK_STAGE/lib/pkgconfig"

rm -rf "$WORK"
mkdir -p "$WORK"
git clone --filter=blob:none --no-checkout "$STREMIO_REPO" "$SRC"
git -C "$SRC" fetch --depth=1 origin "$STREMIO_COMMIT"
git -C "$SRC" checkout --detach "$STREMIO_COMMIT"
[[ $(git -C "$SRC" rev-parse HEAD) == "$STREMIO_COMMIT" ]]
git -C "$SRC" submodule update --init --recursive

git -C "$SRC" apply --check "$PATCH_FILE"
git -C "$SRC" apply "$PATCH_FILE"

export PKG_CONFIG_PATH="$RK_STAGE/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
export LD_LIBRARY_PATH="$RK_STAGE/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CARGO_TARGET_DIR="$TARGET"
export LC_NUMERIC=C
export SERVER_PATH=data/server.js
export RUSTFLAGS="${RUSTFLAGS:-} -C link-arg=-Wl,-rpath,$RK_PREFIX/lib"

cargo build --release --locked --manifest-path "$SRC/Cargo.toml"
test -x "$TARGET/release/stremio-linux-shell"
test -s "$SRC/data/server.js"

# Remove only prior Stremio application packages/install locations. Do not replace distro FFmpeg/mpv/Mesa.
if dpkg-query -W stremio >/dev/null 2>&1; then
  sudo apt-get purge -y stremio
fi
if command -v flatpak >/dev/null 2>&1; then
  flatpak uninstall --user -y com.stremio.Stremio >/dev/null 2>&1 || true
fi

sudo install -d -m755 "$PREFIX" "$RK_PREFIX"
sudo rm -rf "$RK_PREFIX"
sudo cp -a "$RK_STAGE" "$RK_PREFIX"
sudo install -m755 "$TARGET/release/stremio-linux-shell" "$PREFIX/stremio"
sudo install -m644 "$SRC/data/server.js" "$PREFIX/server.js"
printf '%s\n' "$STREMIO_TAG" | sudo tee "$PREFIX/VERSION" >/dev/null

sudo tee /usr/bin/stremio >/dev/null <<'EOF'
#!/usr/bin/env bash
set -e
export SERVER_PATH=/opt/stremio/server.js
export LC_NUMERIC=C
export STREMIO_RK3588_V4L2REQUEST=1
export GSK_RENDERER="${GSK_RENDERER:-opengl}"
export LD_LIBRARY_PATH="/opt/stremio/rk3588/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec /opt/stremio/stremio "$@"
EOF
sudo chmod 0755 /usr/bin/stremio

sudo install -Dm644 "$SRC/data/icons/${APP_ID}.svg" "/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
sed '/^DBusActivatable=true$/d' "$SRC/data/${APP_ID}.desktop" | sudo tee "/usr/share/applications/${APP_ID}.desktop" >/dev/null
sudo sed -i 's|^Exec=.*|Exec=/usr/bin/stremio %U|' "/usr/share/applications/${APP_ID}.desktop"
sudo install -Dm644 "$SRC/data/${APP_ID}.metainfo.xml" "/usr/share/metainfo/${APP_ID}.metainfo.xml"
sudo install -Dm644 "$SRC/data/${APP_ID}.gschema.xml" "/usr/share/glib-2.0/schemas/${APP_ID}.gschema.xml"
sudo glib-compile-schemas /usr/share/glib-2.0/schemas
command -v update-desktop-database >/dev/null && sudo update-desktop-database /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && sudo gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true

# Hard final-state checks only: no synthetic playback/test phase.
[[ $(cat "$PREFIX/VERSION") == "$STREMIO_TAG" ]]
readelf -h "$PREFIX/stremio" | grep -q 'Machine:.*AArch64'
ldd "$PREFIX/stremio" | grep -q "$RK_PREFIX/lib/libmpv"
strings "$(readlink -f "$RK_PREFIX/lib/libmpv.so")" | grep -q v4l2request
grep -q 'STREMIO_RK3588_V4L2REQUEST=1' /usr/bin/stremio

cat <<EOF
FINAL RK3588S STREMIO INSTALL COMPLETE
Stremio: $STREMIO_TAG ($STREMIO_COMMIT)
Binary:  $PREFIX/stremio
libmpv:  $RK_PREFIX/lib
hwdec:   v4l2request-copy (forced by native-shell RK3588 shim)
Mesa:    system Panthor/Panfrost stack left untouched
FFmpeg:  system libraries left untouched; Stremio uses its private V4L2-request stack
Launch:  stremio
EOF
