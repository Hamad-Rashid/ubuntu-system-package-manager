# Changelog

## 0.5.3 - 2026-07-13

- Batched multi-step partition mount workflows into a single privileged `pkexec` operation so users are prompted for administrator authentication once per mount/fix action instead of once per internal command.
- Kept per-step partition action logging for mountpoint creation, primary mount, and NTFS fallback attempts.
- Updated partition action tests to cover the grouped privileged workflow.
