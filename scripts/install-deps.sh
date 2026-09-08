#!/usr/bin/env bash
set -euo pipefail

if [[ $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: this project builds natively for arm64; current dpkg architecture is $(dpkg --print-architecture)" >&2
  exit 1
fi

sudo apt-get update

# GitHub's Ubuntu 26.04 ARM64 image can start with the archive component that
# carries WebKitGTK development headers disabled. The current Stremio Linux
# shell requires libwebkitgtk-6.0-dev, so enable Universe only when apt has no
# install candidate for it. Avoid grep -q under pipefail so apt-cache is always
# allowed to finish writing its output.
if ! apt-cache policy libwebkitgtk-6.0-dev | grep -E 'Candidate: [^()]' >/dev/null; then
  sudo apt-get install -y software-properties-common
  sudo add-apt-repository -y universe
  sudo apt-get update
fi

sudo apt-get install -y \
  binutils \
  build-essential \
  ca-certificates \
  cargo \
  curl \
  debhelper \
  devscripts \
  dpkg-dev \
  fakeroot \
  file \
  gettext \
  git \
  libadwaita-1-dev \
  libasound2-dev \
  libass-dev \
  libdisplay-info-dev \
  libdrm-dev \
  libegl1-mesa-dev \
  libepoxy-dev \
  libgbm-dev \
  libgnutls28-dev \
  libgtk-4-dev \
  libjpeg-dev \
  liblcms2-dev \
  libpipewire-0.3-dev \
  libpulse-dev \
  libssl-dev \
  libudev-dev \
  libvulkan-dev \
  libwayland-dev \
  libwebkitgtk-6.0-dev \
  libx11-dev \
  libxext-dev \
  libxkbcommon-dev \
  libxpresent-dev \
  libxrandr-dev \
  libxss-dev \
  meson \
  ninja-build \
  nodejs \
  patch \
  patchelf \
  pkgconf \
  rustc \
  wayland-protocols \
  zlib1g-dev
