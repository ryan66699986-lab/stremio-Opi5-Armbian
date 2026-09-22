#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STREMIO_TAG=v1.2.0
STREMIO_COMMIT=c6e7cd22e23ed6401e573fe7fe1a023fc07399a2
PREFIX=/opt/stremio
RK_PREFIX=/opt/stremio/rk3588
WORK="$ROOT_DIR/.work/final-native-rk3588s"
STAGE="$WORK/stage"
STAGE_APP="$STAGE/opt/stremio"
SRC="$WORK/stremio-linux-shell"
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

# Build the pinned private RK3588 media stack and the current native Stremio shell.
# Distro FFmpeg/mpv/Mesa are not replaced.
bash "$ROOT_DIR/scripts/build-final-native-rk3588s.sh"

test -x "$STAGE_APP/stremio"
test -s "$STAGE_APP/server.js"
test -e "$STAGE$RK_PREFIX/lib/libmpv.so"

# Remove only previous Stremio application installs. User profile/data is preserved.
if dpkg-query -W stremio >/dev/null 2>&1; then
  sudo apt-get purge -y stremio
fi
if command -v flatpak >/dev/null 2>&1; then
  flatpak uninstall --user -y com.stremio.Stremio >/dev/null 2>&1 || true
  flatpak uninstall --user -y com.stremio.Stremio.Devel >/dev/null 2>&1 || true
fi

sudo rm -rf "$PREFIX"
sudo install -d -m755 "$PREFIX"
sudo cp -a "$STAGE_APP/." "$PREFIX/"

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

# Final-state integrity checks only; no synthetic playback/test phase.
[[ $(cat "$PREFIX/VERSION") == "$STREMIO_TAG" ]]
[[ $(cat "$PREFIX/SOURCE_COMMIT") == "$STREMIO_COMMIT" ]]
readelf -h "$PREFIX/stremio" | grep -q 'Machine:.*AArch64'
LD_LIBRARY_PATH="$RK_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ldd "$PREFIX/stremio" | grep -q "$RK_PREFIX/lib/libmpv"
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
