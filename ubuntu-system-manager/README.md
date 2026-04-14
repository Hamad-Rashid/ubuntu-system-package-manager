# Ubuntu System Manager

Desktop app for Ubuntu (GTK4 + Libadwaita) to monitor and manage:

- RAM and storage usage
- Installed packages (APT + Snap)
- Package updates/remove/enable-disable (where supported)
- Bluetooth/USB receiver visibility
- Partition mount and fix workflows

## Quick Start For Public Users

This is the easiest method for someone installing from your public GitHub repo.

1. Open your repository Releases page.
2. Download the latest `.deb` file (example: `ubuntu-system-manager_0.4.1_amd64.deb`).
3. Install and run:

```bash
sudo apt update
sudo apt install -y ./ubuntu-system-manager_0.4.1_amd64.deb
ubuntu-system-manager
```

If the `.deb` is in another folder, use full path:

```bash
sudo apt install -y /path/to/ubuntu-system-manager_0.4.1_amd64.deb
```

## Install Directly From GitHub Release URL

Replace `<user>`, `<repo>`, and version/tag as needed.

```bash
wget -O /tmp/ubuntu-system-manager_0.4.1_amd64.deb \
  https://github.com/<user>/<repo>/releases/download/v0.4.1/ubuntu-system-manager_0.4.1_amd64.deb

sudo apt update
sudo apt install -y /tmp/ubuntu-system-manager_0.4.1_amd64.deb
ubuntu-system-manager
```

## Runtime Dependencies

Most dependencies are installed automatically through the `.deb` package.  
For source runs, install:

```bash
sudo apt update
sudo apt install -y \
  python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  util-linux ntfs-3g bluez snapd policykit-1
```

## Run From Source

```bash
git clone https://github.com/<user>/<repo>.git
cd <repo>/ubuntu-system-manager
./run.sh
```

## Build `.deb` (Maintainer)

```bash
cd /media/hamad/Office/hamad/ubuntu-system-manager
./packaging/build_deb.sh 0.4.1
```

Output:

- `dist/ubuntu-system-manager_0.4.1_amd64.deb` (architecture depends on build machine)

## Publish A New Release (Maintainer)

1. Build package: `./packaging/build_deb.sh <version>`
2. Create Git tag: `v<version>`
3. Create GitHub Release for that tag
4. Upload `.deb` file from `dist/`
5. Share release URL with users

## Uninstall

```bash
sudo apt remove -y ubuntu-system-manager
```

To clean up configs/leftovers before reinstalling, run:

```bash
sudo apt purge -y ubuntu-system-manager
sudo apt autoremove -y
```

## Troubleshooting

- Warning: `Download is performed unsandboxed as root...`
  - This is usually harmless for local-path installs from restricted folders (like `/media/...`).
  - To avoid it, copy `.deb` to `/tmp` before install.

- App icon not updated immediately:
  - Log out and log back in, or reboot once.

- Missing dependencies after manual `dpkg -i`:
  - Run `sudo apt -f install -y`

## Extra Docs

- `docs/permissions-and-recovery.md`
