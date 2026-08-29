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
  libmpv-dev \
  libqt5opengl5-dev \
  libqt5webchannel5-dev \
  libssl-dev \
  patch \
  pkgconf \
  qtbase5-dev \
  qtdeclarative5-dev \
  qtwebengine5-dev
