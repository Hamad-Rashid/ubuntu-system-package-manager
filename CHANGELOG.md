# Changelog

## 0.5.8 - 2026-10-19

- Use the distribution-neutral desktop and application identity `System Center` so desktop trays and launchers no longer retain the legacy Ubuntu System Manager label.
- Keep the `ubuntu-system-manager` package and command names unchanged for upgrade compatibility.

## 0.5.7 - 2026-10-19

- Rename the user-facing application to “System Center” while keeping the package and command name unchanged for upgrade compatibility.
- Update the desktop entry and administrator authentication prompt to use the new application name.

## 0.5.6 - 2026-10-19

- Add a PolicyKit action with the friendly “Ubuntu System Manager” name for the startup administrator prompt.
- Run the persistent privileged helper through its own executable entrypoint instead of displaying the Python command path.

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
