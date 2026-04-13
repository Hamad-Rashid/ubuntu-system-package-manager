# Ubuntu System Manager (Phase 1)

Phase 1 implementation of the planned Ubuntu desktop app:

- Read-only dashboard for RAM and storage
- Read-only installed package list (APT + Snap) with update status
- Read-only connected Bluetooth devices list with battery percentage (if available)
- Read-only partition health list (mounted/not mounted/mount error)

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

- This phase is read-only; no update/remove/enable-disable/fix actions are executed.
- Data is refreshed at startup and every 60 seconds, with manual refresh support.
- Some Bluetooth devices do not expose battery percentage.
