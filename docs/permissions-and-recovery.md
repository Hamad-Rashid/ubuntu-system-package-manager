# Permissions and Recovery Guide

## Privileged operations

When the app opens, it asks for administrator authentication once and starts a private
`pkexec` helper for the lifetime of that app process. All modifying operations reuse
that authenticated helper, so package, mount, and filesystem actions do not prompt
again during the same session.

The helper is closed when the app quits. Opening the app again requires authentication
again. The app never stores the administrator password.

The helper runs these modifying operations:

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
  - inline fallback `mount -t ntfs-3g /dev/sda1 /media/hamad/Other` when needed
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

