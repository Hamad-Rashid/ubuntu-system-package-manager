# Ubuntu System Manager (Phase 4)

Ubuntu desktop system manager with GTK4 + Libadwaita for:

- system metrics (RAM/storage)
- package inventory and actions (APT + Snap)
- Bluetooth/USB receiver visibility
- partition mount/fix workflows

## Features

- Package tabs:
  - `All Installed`
  - `Updates Available`
  - `Snap`
  - `APT`
- Per-package actions:
  - `Update`
  - `Remove`
  - `Enable/Disable` (Snap only)
- `Update All` button for all available updates
- Partition panel with contextual actions:
  - mounted: no action
  - unmounted: `Mount`
  - mount/filesystem issue: `Fix`
- Package and partition action logs with collapsible log sections

## Phase 4 Hardening

- Retry handling for transient privileged command failures (lock/busy states)
- Safer action input validation and clearer failure hints
- Refresh watchdog to prevent UI lock on long refresh cycles
- Partition scan hardening with bounded filesystem-check budget per refresh
- Debian package build script and install flow

## Runtime Requirements

Install runtime dependencies:

```bash
sudo apt update
sudo apt install -y \
  python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 \
  util-linux ntfs-3g bluez snapd policykit-1
```

## Run From Source

```bash
cd /media/hamad/Office/hamad/ubuntu-system-manager
./run.sh
```

## Tests

```bash
cd /media/hamad/Office/hamad/ubuntu-system-manager
python3 -m unittest discover -s tests -v
```

## Build `.deb`

```bash
cd /media/hamad/Office/hamad/ubuntu-system-manager
./packaging/build_deb.sh 0.4.0
```

Install the generated package:

```bash
sudo apt install ./dist/ubuntu-system-manager_0.4.0_$(dpkg --print-architecture).deb
```

## Docs

- `docs/permissions-and-recovery.md`
