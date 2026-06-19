import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from file_association import register_file_associations
from mpv_setup import IS_LINUX, IS_MAC, prepare_mpv_library


def show_mpv_import_error(error: BaseException) -> None:
    if QApplication.instance() is None:
        QApplication(sys.argv)
    if IS_MAC:
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
        player.load_video(sys.argv[1])

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
