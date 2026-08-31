# Stremio on Orange Pi 5 Pro — official upstream install

This recovery branch intentionally does **not** build or patch Stremio, mpv, FFmpeg, libplacebo, or any RK3588-specific multimedia component.

The supported application is the official Linux Stremio client published by Stremio on Flathub:

- App ID: `com.stremio.Stremio`
- Upstream client: `https://github.com/Stremio/stremio-linux-shell`
- Official install command: `flatpak install flathub com.stremio.Stremio`
- Run command: `flatpak run com.stremio.Stremio`

Flathub publishes the application for `aarch64`, which is the Orange Pi 5 Pro architecture.

## Install on Armbian / Ubuntu

```bash
sudo apt update
sudo apt install -y flatpak
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install -y flathub com.stremio.Stremio
flatpak run com.stremio.Stremio
```

No project-local multimedia libraries, renderer patches, hwdec bridges, or private `/opt/stremio/rk3588` stack are used by this recovery direction.

The older repository build files remain on historical branches only; they are not the supported path for this recovery direction.
