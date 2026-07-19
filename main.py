from __future__ import annotations

import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from file_association import register_file_associations
from mpv_setup import IS_LINUX, IS_MAC, IS_WINDOWS, prepare_mpv_library


def show_mpv_import_error(error: BaseException) -> None:
    if QApplication.instance() is None:
        QApplication(sys.argv)
    if isinstance(error, ImportError):
        hint = "The python-mpv module is missing from this build. Rebuild MinimalPlayer with the bundled mpv hidden import."
    elif IS_MAC:
        hint = "mpv is not installed. Install it with Homebrew:\n\n    brew install mpv\n\nThen restart MinimalPlayer."
    elif IS_LINUX:
        hint = (
            "libmpv is not installed. Install it with your package manager, e.g.:\n\n"
            "    sudo apt install libmpv2   (Debian/Ubuntu)\n"
            "    sudo dnf install mpv-libs  (Fedora)\n\n"
            "Then restart MinimalPlayer."
        )
    else:
        hint = "Could not load mpv-1.dll.\nPlease place 'mpv-1.dll' next to the executable and restart."
    _ = QMessageBox.critical(
        None,
        "mpv Library Not Found",
        f"Failed to load the mpv media library.\n\n{hint}\n\nDetails: {error}",
    )


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--register":
        if not IS_WINDOWS:
            print("--register is a Windows-only feature (registers a Windows Registry file association).")
            return 1
        success = register_file_associations(silent=False)
        print("MinimalPlayer registered successfully to registry." if success else "An error occurred during registry registration.")
        return 0 if success else 1

    app = QApplication(sys.argv)
    _ = app.setStyle("Fusion")
    prepare_mpv_library()

    try:
        from player_window import VideoPlayer
    except (ImportError, OSError) as e:
        show_mpv_import_error(e)
        return 1

    player = VideoPlayer()
    player.setAcceptDrops(True)
    player.show()

    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        QTimer.singleShot(100, player, lambda: player.load_video(file_path))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
