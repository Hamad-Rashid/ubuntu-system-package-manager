# Ubuntu System Manager (Phase 3)

Current implementation of the planned Ubuntu desktop app:

- Dashboard for RAM and storage
- Installed package tabs:
  - `All Installed`
  - `Updates Available`
- Per-package actions:
  - `Update`
  - `Remove`
  - `Enable/Disable` (Snap packages)
- Bulk action:
  - `Update All` for all currently upgradable packages
- Package action log in UI
- Bluetooth/USB device panel with battery percentage (if available)
- Partition health panel with per-partition `Fix` action and fix logs

## Requirements

- Ubuntu desktop with GTK4 + Libadwaita available
- Python 3.10+
- Python package: `PyGObject`

On Ubuntu, install runtime dependencies:

```bash
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

## Run

```bash
cd /media/hamad/Office/hamad/ubuntu-system-manager
./run.sh
```

## Notes

- Data is refreshed at startup and every 60 seconds, with manual refresh support.
- Package update/remove/enable-disable actions run through a central privileged runner (`pkexec`) and will request admin authentication.
- Privileged operations are serialized to avoid package manager lock conflicts.
- `Update All` runs grouped APT and Snap updates from a single click.
- `Enable/Disable` is supported for Snap packages; APT packages show this as unsupported.
- Partition `Fix` supports:
  - dedicated `/media/hamad/other` mount workflow using in-app `ntfs-3g` commands (no external script execution)
  - generic `fsck` flow for ext filesystems
  - generic `ntfsfix` flow for NTFS
  - remount + verification after fix
- Some Bluetooth devices do not expose battery percentage.
