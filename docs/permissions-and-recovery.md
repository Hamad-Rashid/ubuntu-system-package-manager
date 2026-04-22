# Permissions and Recovery Guide

## Privileged operations

The app uses `pkexec` for all modifying operations:

- `apt-get install --only-upgrade`
- `apt-get remove`
- `snap refresh/remove/enable/disable`
- `mount`, `umount`, `fsck`, `ntfsfix`, `mkdir`

If authentication is canceled or denied, the operation fails safely and logs the exact command and stderr tail.

## Mount/Fix behavior

- Mounted partitions show no action button.
- Unmounted partitions show `Mount`.
- Mount failure or filesystem error shows `Fix`.

Special NTFS path behavior:

- For `/media/hamad/Other*` targets, the workflow uses:
  - `mount -t ntfs-3g <device> /media/hamad/Other`
  - fallback device `/dev/sda1` when needed
- Verification is retried briefly to avoid false negatives from delayed mount visibility.

## Common failure hints

- `wrong fs type`:
  - filesystem mismatch; for NTFS install and use `ntfs-3g`
- `device is busy`:
  - close file manager/windows using the disk and retry
- `not authorized` or auth errors:
  - re-run and approve the privilege prompt

## Refresh watchdog

If automatic refresh hangs due slow system commands, the UI unlocks after watchdog timeout and keeps last good data. Use `Refresh` to retry.

