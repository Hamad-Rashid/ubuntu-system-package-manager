# Ubuntu System Package Manager App Plan

## 1. Objective
Build an Ubuntu desktop app that provides:
- Total RAM and current RAM usage
- Total storage and per-partition usage
- Installed packages list (APT + Snap)
- Update action per package (enabled only when update exists)
- Remove/Delete action per package
- Enable/Disable action per package (when supported)
- Connected Bluetooth devices with battery percentage
- Partition mount health checks and a Fix action when mount issues are detected

## 2. Core Constraints and Behavior
- `/dev/sda2` is a block device; app logic works on mounted paths/partitions, not on device files as folders.
- Enable/Disable is package-system dependent:
  - Snap: supports `snap disable` / `snap enable`
  - APT: no true disable/enable; use service-level toggles when applicable (`systemctl`) or show as unsupported
- Risky actions (remove, filesystem fix, mount repair) require privilege escalation via PolicyKit (`pkexec`).

## 3. Tech Stack
- Language: Python 3
- UI: GTK4 + Libadwaita
- System APIs:
  - D-Bus (BlueZ for Bluetooth + battery)
  - subprocess wrappers for package tools and mount/fs checks
- Packaging: `.deb` for Ubuntu

## 4. Feature Modules

### 4.1 System Metrics Module
- RAM source: `/proc/meminfo` or `psutil`
- Storage source: `lsblk -f`, `findmnt`, `df -h`
- Output cards in dashboard: total RAM, used RAM, total storage, used storage

### 4.2 Package Inventory Module
Data sources:
- APT installed: `dpkg-query -W -f='${Package}\t${Version}\n'`
- APT upgradable: `apt list --upgradable`
- Snap installed: `snap list`
- Snap upgradable: `snap refresh --list`

UI table columns:
- Package Name
- Source (`apt` / `snap`)
- Installed Version
- Latest Version
- Status (`Up-to-date`, `Update available`, `Disabled`, `Error`)
- Actions (`Update`, `Remove`, `Enable/Disable`)

Action states:
- Update button:
  - Enabled only if package appears in upgradable list
  - Disabled otherwise
- Remove button:
  - Enabled with confirmation dialog
- Enable/Disable button:
  - Enabled only for supported package type or service-backed package
  - Disabled with tooltip for unsupported cases

### 4.3 Bluetooth Devices Module
- Source: BlueZ D-Bus (`org.bluez.Device1`, `org.bluez.Battery1`)
- Show connected devices only
- For each connected device:
  - Device name
  - Connection status
  - Battery percentage (if exposed by device)

### 4.4 Partition Health + Mount Error Module
Purpose:
- Detect partitions that fail to mount or have filesystem errors
- Apply a dedicated fix path for `/media/hamad/other` using a custom script

Checks:
- Enumerate partitions: `lsblk -f`
- Mount state: `findmnt` and `/etc/fstab` target validation
- Last mount/FS issues:
  - ext*: `fsck -N` dry-run precheck and error parsing
  - ntfs: `ntfsfix -n` style check (read-only check mode where possible)
- Attempt mount test for unmounted partitions (safe mode)

UI:
- Partition list panel with columns:
  - Device
  - Filesystem
  - Mountpoint
  - Status (`Mounted`, `Not mounted`, `Mount error`, `Filesystem error`)
  - Action (`Fix`)

Fix button behavior:
- Button enabled only when status is `Mount error` or `Filesystem error`
- On click:
  1. Show confirmation + warning (possible repair risk)
  2. Run privileged fix workflow
  3. Re-check partition status
  4. Show success/failure log

Fix workflow (per filesystem type):
- Dedicated rule for `/media/hamad/other`:
  - Run `/media/hamad/Office/diskfix.sh` as the first and required fix method
  - If script exit code is non-zero or mount still fails after script run, mark status as `Fix failed` and show actionable error details
- ext2/3/4:
  - Unmount if mounted safely
  - `fsck -y /dev/<partition>`
  - Remount if configured
- ntfs:
  - `ntfsfix /dev/<partition>`
  - Remount attempt
- If auto-fix unsupported, show guided manual steps

## 5. Privileged Operations Layer
All modifying commands go through a single privileged runner:
- Update package
- Remove package
- Enable/Disable package or service
- Filesystem repair and remount
- Custom disk fix script execution: `/media/hamad/Office/diskfix.sh`

Runner requirements:
- Queue operations (avoid apt lock conflicts)
- Capture stdout/stderr logs
- Return structured status for UI notifications

## 6. UX Flow
1. App loads dashboard + package list + partitions + bluetooth devices
2. Background refresh updates package and partition status
3. Action buttons reflect live status
4. Long operations show progress and logs
5. Final toast + status badge update per row

## 7. Safety Rules
- Confirm before remove/fix actions
- Block dangerous fixes on system root partition unless explicit advanced confirmation
- Keep an operation history log
- Cancel/Retry controls for failed operations

## 8. Implementation Phases (4 Phases)

### Phase 1: Foundation + Read-Only Monitoring
Scope:
- Create app skeleton (GTK4 + Libadwaita), navigation, and data refresh loop
- Implement read-only dashboard cards (RAM and storage)
- Implement read-only package inventory (APT + Snap) with versions and update availability markers
- Implement Bluetooth connected-device list with battery percentage (when available)
- Implement partition health detection view (status only, no fix action yet)

Deliverable:
- Stable read-only app showing all required data panels

### Phase 2: Package Actions + Privileged Runner
Scope:
- Build central privileged action runner using `pkexec`
- Add per-package action buttons: `Update`, `Remove`, `Enable/Disable`
- Enforce button state rules:
  - `Update` enabled only if update exists
  - `Enable/Disable` enabled only where supported (Snap/service-backed)
- Add confirmation dialogs, progress UI, and operation logs

Deliverable:
- Package management actions fully working with safe UI behavior

### Phase 3: Partition Fix Workflow + Custom Script Rule
Scope:
- Add active `Fix` action in partition panel
- Implement dedicated rule for `/media/hamad/other`:
  - First run `/media/hamad/Office/diskfix.sh`
  - If script fails or partition still fails to mount, show `Fix failed` with error details
- Add generic filesystem repair flow for other partitions (`fsck`, `ntfsfix`, remount checks)
- Re-scan partition state after every fix attempt

Deliverable:
- End-to-end partition diagnosis and repair workflow, including your custom `diskfix.sh` path

### Phase 4: Hardening, QA, and Packaging
Scope:
- Add retry handling, edge-case validation, and improved error messages
- Test on Ubuntu LTS targets with real package and mount scenarios
- Finalize `.deb` packaging and installation steps
- Write user/admin documentation for permissions and recovery behavior

Deliverable:
- Production-ready Ubuntu package with install docs and validated workflows
