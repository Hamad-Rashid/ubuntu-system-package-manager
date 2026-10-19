# Changelog

## 0.5.5 - 2026-10-19

- Keep the app open after an incorrect administrator password and retry authentication.
- Close the app immediately when the administrator authentication dialog is canceled.
- Preserve the distinction between PolicyKit authentication failure and dialog dismissal.

## 0.5.4 - 2026-10-19

- Authenticate once when the app opens and reuse a private privileged helper for all modifying actions until the app exits.
- Disable privileged action controls until administrator authentication succeeds.
- Close the helper on application shutdown so authorization is not retained after quitting.
- Enforce command timeouts inside the persistent helper.
- Embed the special NTFS fallback mount command directly in the application instead of depending on `diskfix.sh`.
- Keep the app open for incorrect administrator passwords and retry authentication, while closing immediately when the dialog is canceled.

## 0.5.3 - 2026-07-13

- Batched multi-step partition mount workflows into a single privileged `pkexec` operation so users are prompted for administrator authentication once per mount/fix action instead of once per internal command.
- Kept per-step partition action logging for mountpoint creation, primary mount, and NTFS fallback attempts.
- Updated partition action tests to cover the grouped privileged workflow.
