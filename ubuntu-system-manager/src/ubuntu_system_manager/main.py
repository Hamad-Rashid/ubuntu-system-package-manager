from __future__ import annotations

import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from ubuntu_system_manager.ui.window import MainWindow


class SystemManagerApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id="com.hamad.UbuntuSystemManager", flags=0)

    def do_activate(self) -> None:
        win = self.props.active_window
        if win is None:
            win = MainWindow(self)
        win.present()


def main() -> int:
    app = SystemManagerApplication()
    return int(app.run(sys.argv))


if __name__ == "__main__":
    raise SystemExit(main())
