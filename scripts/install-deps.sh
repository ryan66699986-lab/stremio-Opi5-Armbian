#!/usr/bin/env bash
set -euo pipefail

if [[ $(dpkg --print-architecture) != arm64 ]]; then
  echo "error: this project builds natively for arm64; current dpkg architecture is $(dpkg --print-architecture)" >&2
  exit 1
fi

sudo apt-get update
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
