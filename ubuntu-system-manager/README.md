# Ubuntu System Manager (Phase 2)

Current implementation of the planned Ubuntu desktop app:

- Dashboard for RAM and storage
- Installed package tabs:
  - `All Installed`
  - `Updates Available`
- Per-package actions:
  - `Update`
  - `Remove`
  - `Enable/Disable` (Snap packages)
- Package action log in UI
- Bluetooth/USB device panel with battery percentage (if available)
- Partition health list (mounted/not mounted/mount error)

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
- `Enable/Disable` is supported for Snap packages; APT packages show this as unsupported.
- Some Bluetooth devices do not expose battery percentage.
