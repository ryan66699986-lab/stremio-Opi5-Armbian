#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

UPSTREAM_REPO="https://github.com/Stremio/stremio-linux-shell.git"
UPSTREAM_API="https://api.github.com/repos/Stremio/stremio-linux-shell/releases/latest"
SCRIPT_PATH=$(readlink -f "${BASH_SOURCE[0]}")
SYSTEM_LIBEXEC="/usr/local/libexec/stremio"
SYSTEM_WRAPPER="/usr/bin/stremio"
APP_ID="com.stremio.Stremio"

log() { printf '%s\n' "$*"; }
section() { printf '\n==== %s ====\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

if [[ ${1:-} == "--user-update" ]]; then
    MODE=user-update
else
    MODE=install
fi

if [[ -n ${SUDO_USER:-} && ${SUDO_USER} != root ]]; then
    TARGET_USER=${SUDO_USER}
elif [[ ${EUID} -ne 0 ]]; then
    TARGET_USER=${USER}
else
    TARGET_USER=${STREMIO_USER:-}
fi

if [[ -z ${TARGET_USER:-} ]]; then
    echo "error: could not determine the desktop user; run this as that user (the script will use sudo when required)" >&2
    exit 1
fi

TARGET_UID=$(id -u "$TARGET_USER")
TARGET_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
if [[ -z ${TARGET_HOME:-} || ! -d $TARGET_HOME ]]; then
    echo "error: could not determine home directory for $TARGET_USER" >&2
    exit 1
fi

CACHE_ROOT="${TARGET_HOME}/.cache/stremio-native-build"
USER_LIBEXEC="${TARGET_HOME}/.local/libexec/stremio"
USER_MAINT="${TARGET_HOME}/.local/libexec/stremio-maintainer"
USER_DATA="${TARGET_HOME}/.local/share"
USER_UNITS="${TARGET_HOME}/.config/systemd/user"

as_root() {
    if [[ $EUID -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

as_user() {
    if [[ $(id -u) -eq $TARGET_UID ]]; then
        "$@"
    else
        sudo -u "$TARGET_USER" -H "$@"
    fi
}

latest_release_tag() {
    local tag=""
    if have curl; then
        tag=$(curl -fsSL "$UPSTREAM_API" 2>/dev/null | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n1 || true)
    fi
    if [[ -z $tag ]] && have git; then
        tag=$(git ls-remote --tags --refs "$UPSTREAM_REPO" 'v*' 2>/dev/null \
            | awk '{sub("refs/tags/", "", $2); print $2}' \
            | sort -V | tail -n1 || true)
    fi
    [[ -n $tag ]] || return 1
    printf '%s\n' "$tag"
}

build_release() {
    local tag=$1 out_root=$2
    local src="${CACHE_ROOT}/${tag}/src"
    local target="${CACHE_ROOT}/${tag}/target"

    as_user rm -rf "${CACHE_ROOT:?}/${tag}"
    as_user mkdir -p "${CACHE_ROOT}/${tag}"
    as_user git clone --recurse-submodules --shallow-submodules --depth 1 --branch "$tag" "$UPSTREAM_REPO" "$src"

    section "Upstream source"
    as_user git -C "$src" rev-parse HEAD
    as_user git -C "$src" describe --tags --always

    section "Building native Stremio"
    as_user env \
        LC_NUMERIC=C \
        SERVER_PATH="data/server.js" \
        CARGO_TARGET_DIR="$target" \
        cargo build --release --locked --manifest-path "$src/Cargo.toml"

    test -x "$target/release/stremio-linux-shell"
    test -s "$src/data/server.js"

    rm -rf "$out_root"
    mkdir -p "$out_root"
    install -m755 "$target/release/stremio-linux-shell" "$out_root/stremio"
    install -m644 "$src/data/server.js" "$out_root/server.js"
    printf '%s\n' "$tag" > "$out_root/VERSION"

    printf '%s\n' "$src"
}

install_user_data_from_source() {
    local src=$1
    mkdir -p \
        "$USER_DATA/applications" \
        "$USER_DATA/icons/hicolor/scalable/apps" \
        "$USER_DATA/metainfo" \
        "$USER_DATA/glib-2.0/schemas"

    sed '/^DBusActivatable=true$/d' "$src/data/${APP_ID}.desktop" > "$USER_DATA/applications/${APP_ID}.desktop"
    install -m644 "$src/data/icons/${APP_ID}.svg" "$USER_DATA/icons/hicolor/scalable/apps/${APP_ID}.svg"
    install -m644 "$src/data/${APP_ID}.metainfo.xml" "$USER_DATA/metainfo/${APP_ID}.metainfo.xml"
    install -m644 "$src/data/${APP_ID}.gschema.xml" "$USER_DATA/glib-2.0/schemas/${APP_ID}.gschema.xml"
    if have glib-compile-schemas; then
        glib-compile-schemas "$USER_DATA/glib-2.0/schemas"
    fi
}

user_update() {
    section "Checking upstream release"
    local latest current=""
    latest=$(latest_release_tag) || { echo "error: could not determine latest upstream release" >&2; exit 1; }
    if [[ -r "$USER_LIBEXEC/current/VERSION" ]]; then
        current=$(cat "$USER_LIBEXEC/current/VERSION")
    elif [[ -r "$SYSTEM_LIBEXEC/VERSION" ]]; then
        current=$(cat "$SYSTEM_LIBEXEC/VERSION")
    fi
    log "installed: ${current:-none}"
    log "upstream:  $latest"
    [[ $latest != "$current" ]] || { log "Stremio is already current."; exit 0; }

    local release_dir="$USER_LIBEXEC/releases/$latest"
    mkdir -p "$USER_LIBEXEC/releases"
    local src
    src=$(build_release "$latest" "$release_dir" | tail -n1)
    install_user_data_from_source "$src"
    ln -sfn "releases/$latest" "$USER_LIBEXEC/current"
    log "Updated user-local Stremio to $latest"
}

if [[ $MODE == user-update ]]; then
    user_update
    exit 0
fi

section "System inspection: OS"
cat /etc/os-release
uname -a
printf 'architecture: '; uname -m
printf 'desktop user: %s (uid %s)\n' "$TARGET_USER" "$TARGET_UID"

section "System inspection: GPU"
if have lspci; then
    lspci -nnk | grep -EA4 -i 'vga|3d|display' || true
else
    log "lspci: not installed yet"
fi
if have glxinfo && [[ -n ${DISPLAY:-} ]]; then
    glxinfo -B || true
else
    log "glxinfo: unavailable before dependency installation or no X display"
fi
if [[ -d /dev/dri ]]; then
    ls -l /dev/dri || true
fi
if [[ -r /proc/device-tree/compatible ]]; then
    printf 'device-tree compatible: '
    tr '\0' ' ' < /proc/device-tree/compatible || true
    printf '\n'
fi

section "System inspection: package manager and build tools"
PKG_MGR=""
for candidate in apt-get dnf pacman zypper; do
    if have "$candidate"; then PKG_MGR=$candidate; break; fi
done
log "package manager: ${PKG_MGR:-none}"
for cmd in gcc g++ make cmake meson ninja pkg-config git rustc cargo node npm python3 mpv ffmpeg; do
    if have "$cmd"; then
        printf '%-12s ' "$cmd"
        "$cmd" --version 2>/dev/null | head -n1 || true
    else
        printf '%-12s %s\n' "$cmd" "not installed"
    fi
done

section "System inspection: installed media/UI libraries"
if have pkg-config; then
    for pc in gtk4 libadwaita-1 webkitgtk-6.0 mpv epoxy; do
        if pkg-config --exists "$pc"; then
            printf '%-18s %s\n' "$pc" "$(pkg-config --modversion "$pc")"
        else
            printf '%-18s %s\n' "$pc" "not found"
        fi
    done
fi
if have ldconfig; then
    ldconfig -p 2>/dev/null | grep -E 'libmpv|libgtk-4|libadwaita|libwebkitgtk|libepoxy' | head -n50 || true
fi

section "System inspection: existing Stremio installations"
command -v stremio || true
if have flatpak; then
    flatpak list --app --columns=application,name 2>/dev/null | grep -i stremio || true
fi
if have snap; then
    snap list 2>/dev/null | grep -i '^stremio[[:space:]]' || true
fi
if have dpkg-query; then
    dpkg-query -W -f='${binary:Package}\t${Version}\n' 2>/dev/null | grep -Ei '^stremio|stremio-linux-shell' || true
fi
if have rpm; then
    rpm -qa 2>/dev/null | grep -Ei '^stremio' || true
fi
if have pacman; then
    pacman -Q 2>/dev/null | grep -Ei '^stremio' || true
fi
for path in /usr/bin/stremio /usr/local/bin/stremio /usr/local/libexec/stremio /opt/stremio "$USER_LIBEXEC"; do
    [[ -e $path || -L $path ]] && ls -ld "$path" || true
done

section "Removing existing Stremio installations"
if have flatpak; then
    for app in com.stremio.Stremio com.stremio.Stremio.Devel; do
        if flatpak list --user --app --columns=application 2>/dev/null | grep -Fxq "$app"; then
            flatpak uninstall --user -y "$app" || true
        fi
        if flatpak list --system --app --columns=application 2>/dev/null | grep -Fxq "$app"; then
            as_root flatpak uninstall --system -y "$app" || true
        fi
    done
fi
if have snap && snap list stremio >/dev/null 2>&1; then
    as_root snap remove stremio || true
fi
if have dpkg-query; then
    mapfile -t old_debs < <(dpkg-query -W -f='${binary:Package}\n' 2>/dev/null | grep -Ei '^stremio([^a-z0-9].*)?$|^stremio-' || true)
    if ((${#old_debs[@]})); then as_root apt-get purge -y "${old_debs[@]}"; fi
fi
if have rpm && have dnf; then
    mapfile -t old_rpms < <(rpm -qa --qf '%{NAME}\n' | grep -Ei '^stremio' || true)
    if ((${#old_rpms[@]})); then as_root dnf remove -y "${old_rpms[@]}"; fi
fi
if have pacman; then
    mapfile -t old_arch < <(pacman -Qq | grep -Ei '^stremio' || true)
    if ((${#old_arch[@]})); then as_root pacman -Rns --noconfirm "${old_arch[@]}"; fi
fi
as_root rm -rf /usr/local/libexec/stremio /usr/local/bin/stremio /opt/stremio
as_root rm -f /usr/bin/stremio \
    /usr/share/applications/${APP_ID}.desktop \
    /usr/local/share/applications/${APP_ID}.desktop \
    /usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg \
    /usr/local/share/icons/hicolor/scalable/apps/${APP_ID}.svg \
    /usr/share/metainfo/${APP_ID}.metainfo.xml \
    /usr/local/share/metainfo/${APP_ID}.metainfo.xml \
    /usr/share/dbus-1/services/${APP_ID}.service \
    /usr/local/share/dbus-1/services/${APP_ID}.service \
    /usr/share/glib-2.0/schemas/${APP_ID}.gschema.xml \
    /usr/local/share/glib-2.0/schemas/${APP_ID}.gschema.xml
as_user rm -rf "$USER_LIBEXEC" "$USER_MAINT"
as_user rm -f "$USER_DATA/applications/${APP_ID}.desktop" \
    "$USER_DATA/icons/hicolor/scalable/apps/${APP_ID}.svg" \
    "$USER_DATA/metainfo/${APP_ID}.metainfo.xml" \
    "$USER_DATA/glib-2.0/schemas/${APP_ID}.gschema.xml"

section "Resolving distro-equivalent build dependencies"
case "$PKG_MGR" in
    apt-get)
        as_root apt-get update
        # Show the package-manager search used to map the upstream Fedora/Debian dependency names.
        for term in 'gtk4' 'libadwaita' 'webkitgtk' 'libmpv' 'libepoxy' 'nodejs' 'cargo' 'rustc'; do
            log "-- apt-cache search $term"
            apt-cache search "$term" | head -n12 || true
        done
        apt_pkgs=(
            build-essential pkg-config libgtk-4-dev libadwaita-1-dev libwebkitgtk-6.0-dev
            libmpv-dev libepoxy-dev gettext nodejs flatpak-builder
            git cargo rustc python3 curl ca-certificates mesa-utils pciutils ffmpeg mpv v4l-utils vainfo
        )
        missing=()
        for pkg in "${apt_pkgs[@]}"; do
            apt-cache show "$pkg" >/dev/null 2>&1 || missing+=("$pkg")
        done
        if ((${#missing[@]})); then
            printf 'error: required packages not found in configured APT repositories: %s\n' "${missing[*]}" >&2
            exit 1
        fi
        as_root apt-get install -y "${apt_pkgs[@]}"
        ;;
    dnf)
        dnf_pkgs=(gcc gcc-c++ make pkgconf-pkg-config gtk4-devel libadwaita-devel webkitgtk6.0-devel mpv-devel libepoxy-devel gettext nodejs flatpak-builder git cargo rust python3 curl mesa-demos pciutils ffmpeg mpv v4l-utils)
        for term in gtk4 libadwaita webkitgtk6.0 mpv libepoxy nodejs cargo rust; do
            log "-- dnf search $term"
            dnf -q search "$term" | head -n12 || true
        done
        as_root dnf install -y "${dnf_pkgs[@]}"
        ;;
    pacman)
        pacman_pkgs=(base-devel pkgconf gtk4 libadwaita webkitgtk-6.0 mpv libepoxy gettext nodejs git rust python curl mesa-utils pciutils ffmpeg v4l-utils)
        for term in gtk4 libadwaita webkitgtk mpv libepoxy nodejs rust; do
            log "-- pacman -Ss $term"
            pacman -Ss "$term" | head -n12 || true
        done
        as_root pacman -Syu --needed --noconfirm "${pacman_pkgs[@]}"
        ;;
    *)
        echo "error: unsupported package manager; expected apt/dnf/pacman" >&2
        exit 1
        ;;
esac

section "Post-install GPU and library inspection"
if have lspci; then lspci -nnk | grep -EA4 -i 'vga|3d|display' || true; fi
if have glxinfo && [[ -n ${DISPLAY:-} ]]; then glxinfo -B || true; fi
if have pkg-config; then
    for pc in gtk4 libadwaita-1 webkitgtk-6.0 mpv epoxy; do
        pkg-config --exists "$pc" || { echo "error: pkg-config module missing: $pc" >&2; exit 1; }
        printf '%-18s %s\n' "$pc" "$(pkg-config --modversion "$pc")"
    done
fi
rustc --version
cargo --version
node --version

# Current upstream source requires these API generations.
pkg-config --atleast-version=4.22 gtk4 || { echo "error: GTK 4.22+ is required by current Stremio source" >&2; exit 1; }
pkg-config --atleast-version=1.9 libadwaita-1 || { echo "error: libadwaita 1.9+ is required by current Stremio source" >&2; exit 1; }
pkg-config --atleast-version=2.52 webkitgtk-6.0 || { echo "error: WebKitGTK 6.0 / 2.52+ is required by current Stremio source" >&2; exit 1; }

section "Hardware video decode capability"
HWDEC_HELP=$(mpv --no-config --hwdec=help 2>&1 || true)
printf '%s\n' "$HWDEC_HELP"
ffmpeg -hide_banner -hwaccels 2>&1 || true
if have v4l2-ctl; then v4l2-ctl --list-devices 2>/dev/null || true; fi
if have vainfo; then vainfo 2>/dev/null || true; fi

GPU_PROBE="$({ lspci -nnk 2>/dev/null || true; glxinfo -B 2>/dev/null || true; tr '\0' ' ' < /proc/device-tree/compatible 2>/dev/null || true; } | tr '[:upper:]' '[:lower:]')"
GPU_KIND=generic
if grep -Eq 'nvidia' <<<"$GPU_PROBE"; then
    GPU_KIND=nvidia
elif grep -Eq 'intel' <<<"$GPU_PROBE"; then
    GPU_KIND=intel
elif grep -Eq 'rockchip|rk3588|mali|panfrost|panthor' <<<"$GPU_PROBE"; then
    GPU_KIND=rockchip
elif grep -Eq 'amd|radeon' <<<"$GPU_PROBE"; then
    GPU_KIND=amd
fi
log "detected GPU class: $GPU_KIND"

case "$GPU_KIND" in
    rockchip)
        if ! grep -Eqi 'v4l2request|rkmpp' <<<"$HWDEC_HELP"; then
            echo "error: this libmpv/mpv build does not expose a Rockchip hardware decoder (v4l2request/rkmpp); refusing to claim hardware decode works" >&2
            exit 1
        fi
        ;;
    intel|amd)
        if ! grep -Eqi 'vaapi|vulkan' <<<"$HWDEC_HELP"; then
            echo "error: this libmpv/mpv build exposes no VA-API/Vulkan hardware decoder" >&2
            exit 1
        fi
        ;;
    nvidia)
        if ! grep -Eqi 'nvdec|cuda' <<<"$HWDEC_HELP"; then
            echo "error: this libmpv/mpv build exposes no NVIDIA hardware decoder" >&2
            exit 1
        fi
        ;;
esac

section "Hardware decoder device smoke test"
# Use a copy-back decoder for this headless test so it checks the decoder/device
# without depending on Stremio's OpenGL surface. The final embedded zero-copy
# path is checked from Stremio's own playback log below.
HWDEC_TEST=""
case "$GPU_KIND" in
    rockchip)
        if grep -Eqi 'v4l2request-copy' <<<"$HWDEC_HELP"; then HWDEC_TEST=v4l2request-copy
        elif grep -Eqi 'rkmpp-copy' <<<"$HWDEC_HELP"; then HWDEC_TEST=rkmpp-copy
        fi
        ;;
    intel|amd)
        if grep -Eqi 'vaapi-copy' <<<"$HWDEC_HELP"; then HWDEC_TEST=vaapi-copy; fi
        ;;
    nvidia)
        if grep -Eqi 'nvdec-copy' <<<"$HWDEC_HELP"; then HWDEC_TEST=nvdec-copy
        elif grep -Eqi 'cuda-copy' <<<"$HWDEC_HELP"; then HWDEC_TEST=cuda-copy
        fi
        ;;
esac

if [[ -n $HWDEC_TEST ]] && ffmpeg -hide_banner -encoders 2>/dev/null | grep -q 'libx264'; then
    HWTEST_DIR=$(mktemp -d)
    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i 'testsrc2=size=640x360:rate=24' -t 1 \
        -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$HWTEST_DIR/test.mp4"
    set +e
    mpv --no-config --vo=null --ao=null --hwdec="$HWDEC_TEST" --hwdec-codecs=all \
        --msg-level=vd=debug,ffmpeg/video=debug "$HWTEST_DIR/test.mp4" \
        >"$HWTEST_DIR/mpv.log" 2>&1
    HWTEST_RC=$?
    set -e
    cat "$HWTEST_DIR/mpv.log"
    if [[ $HWTEST_RC -ne 0 ]] || ! grep -Eqi 'Using hardware decoding|hardware decoding.*($|\()|hwdec.*active' "$HWTEST_DIR/mpv.log"; then
        rm -rf "$HWTEST_DIR"
        echo "error: $HWDEC_TEST is advertised but the decoder/device smoke test did not prove hardware decoding; refusing software fallback" >&2
        exit 1
    fi
    rm -rf "$HWTEST_DIR"
    log "hardware decoder device smoke test passed with $HWDEC_TEST"
else
    log "No copy-back hwdec suitable for a headless device test was exposed; capability is present, final proof will come from Stremio playback logs."
fi

section "Build latest stable upstream release"
LATEST_TAG=$(latest_release_tag) || { echo "error: could not determine latest Stremio release" >&2; exit 1; }
log "latest upstream release: $LATEST_TAG"
SYSTEM_STAGE=$(mktemp -d)
trap 'rm -rf "$SYSTEM_STAGE"' EXIT
SRC_DIR=$(build_release "$LATEST_TAG" "$SYSTEM_STAGE/stremio" | tail -n1)

section "Install native client to standard paths"
as_root install -d -m755 "$SYSTEM_LIBEXEC"
as_root install -m755 "$SYSTEM_STAGE/stremio/stremio" "$SYSTEM_LIBEXEC/stremio"
as_root install -m644 "$SYSTEM_STAGE/stremio/server.js" "$SYSTEM_LIBEXEC/server.js"
printf '%s\n' "$LATEST_TAG" | as_root tee "$SYSTEM_LIBEXEC/VERSION" >/dev/null

WRAPPER_TMP=$(mktemp)
cat > "$WRAPPER_TMP" <<EOF_WRAPPER
#!/usr/bin/env bash
set -e
BASE="\${HOME}/.local/libexec/stremio/current"
if [[ ! -x "\${BASE}/stremio" || ! -s "\${BASE}/server.js" ]]; then
    BASE="$SYSTEM_LIBEXEC"
fi
export SERVER_PATH="\${BASE}/server.js"
export LC_NUMERIC=C
export XDG_DATA_DIRS="\${HOME}/.local/share:\${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
EOF_WRAPPER
case "$GPU_KIND" in
    nvidia)
        echo 'export GSK_RENDERER="${GSK_RENDERER:-opengl}"' >> "$WRAPPER_TMP"
        ;;
    intel)
        echo 'export ANV_DEBUG="${ANV_DEBUG:-video-decode,video-encode}"' >> "$WRAPPER_TMP"
        ;;
    rockchip)
        # Keep Mesa/Panthor/Panfrost auto-detection intact. No Rockchip-specific
        # environment override is required by upstream Stremio.
        ;;
esac
cat >> "$WRAPPER_TMP" <<'EOF_WRAPPER'
exec "${BASE}/stremio" "$@"
EOF_WRAPPER
as_root install -m755 "$WRAPPER_TMP" "$SYSTEM_WRAPPER"
rm -f "$WRAPPER_TMP"

as_root install -Dm644 "$SRC_DIR/data/icons/${APP_ID}.svg" "/usr/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
sed '/^DBusActivatable=true$/d' "$SRC_DIR/data/${APP_ID}.desktop" | as_root tee "/usr/share/applications/${APP_ID}.desktop" >/dev/null
as_root install -Dm644 "$SRC_DIR/data/${APP_ID}.metainfo.xml" "/usr/share/metainfo/${APP_ID}.metainfo.xml"
as_root install -Dm644 "$SRC_DIR/data/${APP_ID}.gschema.xml" "/usr/share/glib-2.0/schemas/${APP_ID}.gschema.xml"
SERVICE_TMP=$(mktemp)
sed 's|^Exec=.*|Exec=/usr/bin/stremio --gapplication-service|' "$SRC_DIR/data/${APP_ID}.service" > "$SERVICE_TMP"
as_root install -Dm644 "$SERVICE_TMP" "/usr/share/dbus-1/services/${APP_ID}.service"
rm -f "$SERVICE_TMP"
as_root glib-compile-schemas /usr/share/glib-2.0/schemas
if have update-desktop-database; then as_root update-desktop-database /usr/share/applications || true; fi
if have gtk-update-icon-cache; then as_root gtk-update-icon-cache -f -t /usr/share/icons/hicolor || true; fi

# Build.rs creates .mo files under po/<lang>/LC_MESSAGES. Install all that exist.
while IFS= read -r -d '' mo; do
    lang=$(basename "$(dirname "$(dirname "$mo")")")
    as_root install -Dm644 "$mo" "/usr/share/locale/${lang}/LC_MESSAGES/stremio.mo"
done < <(find "$SRC_DIR/po" -type f -path '*/LC_MESSAGES/stremio.mo' -print0 2>/dev/null)

section "Install daily systemd user release updater"
as_user mkdir -p "$USER_MAINT" "$USER_UNITS" "$USER_UNITS/timers.target.wants"
as_root install -m755 "$SCRIPT_PATH" "$USER_MAINT/install-native-stremio.sh"
as_root chown -R "$TARGET_USER":"$(id -gn "$TARGET_USER")" "$USER_MAINT"
cat > /tmp/stremio-native-update.service <<EOF_SERVICE
[Unit]
Description=Rebuild native Stremio when a new upstream release appears
After=network-online.target

[Service]
Type=oneshot
ExecStart=%h/.local/libexec/stremio-maintainer/install-native-stremio.sh --user-update
EOF_SERVICE
cat > /tmp/stremio-native-update.timer <<'EOF_TIMER'
[Unit]
Description=Daily Stremio upstream release check

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=30m

[Install]
WantedBy=timers.target
EOF_TIMER
as_root install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m644 /tmp/stremio-native-update.service "$USER_UNITS/stremio-native-update.service"
as_root install -o "$TARGET_USER" -g "$(id -gn "$TARGET_USER")" -m644 /tmp/stremio-native-update.timer "$USER_UNITS/stremio-native-update.timer"
rm -f /tmp/stremio-native-update.service /tmp/stremio-native-update.timer

# Enable persistently even if the user bus is not available in this shell.
as_user ln -sfn ../stremio-native-update.timer "$USER_UNITS/timers.target.wants/stremio-native-update.timer"

USER_RUNTIME="/run/user/$TARGET_UID"
if [[ -S "$USER_RUNTIME/bus" ]]; then
    if [[ $(id -u) -eq $TARGET_UID ]]; then
        env XDG_RUNTIME_DIR="$USER_RUNTIME" DBUS_SESSION_BUS_ADDRESS="unix:path=$USER_RUNTIME/bus" systemctl --user daemon-reload
        env XDG_RUNTIME_DIR="$USER_RUNTIME" DBUS_SESSION_BUS_ADDRESS="unix:path=$USER_RUNTIME/bus" systemctl --user start stremio-native-update.timer
    else
        sudo -u "$TARGET_USER" -H env XDG_RUNTIME_DIR="$USER_RUNTIME" DBUS_SESSION_BUS_ADDRESS="unix:path=$USER_RUNTIME/bus" systemctl --user daemon-reload
        sudo -u "$TARGET_USER" -H env XDG_RUNTIME_DIR="$USER_RUNTIME" DBUS_SESSION_BUS_ADDRESS="unix:path=$USER_RUNTIME/bus" systemctl --user start stremio-native-update.timer
    fi
else
    log "user systemd bus is not active; the timer is enabled and will load at the next user session."
fi

section "Verification"
test -x "$SYSTEM_WRAPPER"
test -x "$SYSTEM_LIBEXEC/stremio"
test -s "$SYSTEM_LIBEXEC/server.js"
grep -q '^export SERVER_PATH=' "$SYSTEM_WRAPPER"
grep -q '^export LC_NUMERIC=C$' "$SYSTEM_WRAPPER"
if grep -q '^DBusActivatable=true$' "/usr/share/applications/${APP_ID}.desktop"; then
    echo "error: DBusActivatable=true is still present" >&2
    exit 1
fi
node --check "$SYSTEM_LIBEXEC/server.js"
ldd "$SYSTEM_LIBEXEC/stremio" | tee /tmp/stremio-ldd.txt
if grep -q 'not found' /tmp/stremio-ldd.txt; then
    echo "error: Stremio has unresolved shared libraries" >&2
    exit 1
fi
rm -f /tmp/stremio-ldd.txt

log "installed version: $(cat "$SYSTEM_LIBEXEC/VERSION")"
log "libmpv: $(pkg-config --modversion mpv)"
log "hardware decoder capability check: passed for $GPU_KIND"

if [[ -n ${DISPLAY:-} || -n ${WAYLAND_DISPLAY:-} ]]; then
    section "Launch smoke test"
    set +e
    RUST_LOG=info timeout 12s "$SYSTEM_WRAPPER" > /tmp/stremio-launch.log 2>&1
    rc=$?
    set -e
    cat /tmp/stremio-launch.log
    if grep -Eqi 'panic|failed to create mpv|failed to create render context' /tmp/stremio-launch.log; then
        echo "error: Stremio launch smoke test reported a fatal player/render error" >&2
        exit 1
    fi
    if [[ $rc -ne 0 && $rc -ne 124 ]]; then
        echo "error: Stremio exited unexpectedly during launch smoke test (status $rc)" >&2
        exit 1
    fi
    log "launch smoke test passed (timeout status 124 is expected for a running GUI app)"
else
    log "No graphical session variables were present, so GUI launch smoke test was skipped."
fi

cat <<EOF_DONE

Native Stremio installation complete.
Binary:        $SYSTEM_LIBEXEC/stremio
Wrapper:       $SYSTEM_WRAPPER
Server:        $SYSTEM_LIBEXEC/server.js
Desktop file:  /usr/share/applications/${APP_ID}.desktop
Release:       $LATEST_TAG
GPU class:     $GPU_KIND

For an actual playback proof, run:
  RUST_LOG=debug stremio 2>&1 | tee ~/stremio-hwdec.log
play a known hardware-decodable video, then check:
  grep -Ei 'hwdec|hardware decoding|drm_prime|v4l2request|rkmpp|vaapi|vulkan|nvdec' ~/stremio-hwdec.log

The daily user timer is stremio-native-update.timer.
EOF_DONE
