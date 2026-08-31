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
  cmake \
  curl \
  debhelper \
  devscripts \
  dpkg-dev \
  fakeroot \
  file \
  git \
  libasound2-dev \
  libass-dev \
  libdisplay-info-dev \
  libdrm-dev \
  libegl1-mesa-dev \
  libgbm-dev \
  libgnutls28-dev \
  libjpeg-dev \
  liblcms2-dev \
  libpipewire-0.3-dev \
  libpulse-dev \
  libqt5opengl5-dev \
  libqt5webchannel5-dev \
  libsdl2-dev \
  libssl-dev \
  libudev-dev \
  libvulkan-dev \
  libwayland-dev \
  libx11-dev \
  libxext-dev \
  libxkbcommon-dev \
  libxpresent-dev \
  libxrandr-dev \
  libxss-dev \
  meson \
  ninja-build \
  patch \
  patchelf \
  pkgconf \
  qtbase5-dev \
  qtdeclarative5-dev \
  qtwebengine5-dev \
  wayland-protocols \
  zlib1g-dev
