from __future__ import annotations

import sys
import os
import tempfile
from collections.abc import Callable

from PySide6.QtCore import QEvent, QSettings, QTimer
from PySide6.QtGui import QFileOpenEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from file_association import register_file_associations
from mpv_setup import IS_LINUX, IS_MAC, IS_WINDOWS, prepare_mpv_library
from constants import APP_DISPLAY_NAME, APP_NAME, ORG_NAME


class MediaApplication(QApplication):
    """Route OS-level file-open requests to the player once it is ready."""

    def __init__(self, argv: list[str]) -> None:
        self._file_open_handler: Callable[[str], None] | None = None
        self._pending_file_opens: list[str] = []
        super().__init__(argv)

    def event(self, event) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            path = event.file() if isinstance(event, QFileOpenEvent) else ""
            if path:
                if self._file_open_handler:
                    self._file_open_handler(path)
                else:
                    self._pending_file_opens.append(path)
            return True
        return super().event(event)

    def set_file_open_handler(self, handler: Callable[[str], None]) -> None:
        self._file_open_handler = handler
        pending, self._pending_file_opens = self._pending_file_opens, []
        for path in pending:
            handler(path)


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

    smoke_test = "--smoke-test" in sys.argv[1:]

    app = MediaApplication(sys.argv)
    _ = app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName(ORG_NAME)

    try:
        prepare_mpv_library(allow_download=not smoke_test)
    except Exception as e:
        if smoke_test:
            print(f"SMOKE_TEST_ERROR: {e}", file=sys.stderr)
            return 1
        raise

    try:
        from player_window import VideoPlayer
    except (ImportError, OSError) as e:
        if smoke_test:
            print(f"SMOKE_TEST_ERROR: {e}", file=sys.stderr)
            return 1
        show_mpv_import_error(e)
        return 1

    if smoke_test:
        with tempfile.TemporaryDirectory(prefix="minimalplayer-smoke-") as temp_dir:
            smoke_settings = QSettings(
                os.path.join(temp_dir, "settings.ini"),
                QSettings.Format.IniFormat,
            )
            try:
                player = VideoPlayer(
                    settings=smoke_settings,
                    interactive_errors=False,
                )
            except Exception as e:
                print(f"SMOKE_TEST_ERROR: {e}", file=sys.stderr)
                return 1

            result = {"code": 1}

            def finish_smoke_test() -> None:
                try:
                    if player.current_media_path is not None:
                        raise RuntimeError("A fresh player unexpectedly has media loaded.")
                    if player.play_btn.text() != "Play":
                        raise RuntimeError(
                            f"Empty player button text is {player.play_btn.text()!r}, not 'Play'."
                        )
                    if player.play_btn.isEnabled():
                        raise RuntimeError("Empty player Play button must be disabled.")
                    player.close()
                    smoke_settings.sync()
                    result["code"] = 0
                    print("SMOKE_TEST_OK")
                except Exception as e:
                    print(f"SMOKE_TEST_ERROR: {e}", file=sys.stderr)
                finally:
                    app.exit(result["code"])

            QTimer.singleShot(0, player, finish_smoke_test)
            app.exec()
            return result["code"]

    player = VideoPlayer()
    player.setAcceptDrops(True)
    player.show()

    scheduled_paths: set[str] = set()

    def schedule_file_open(file_path: str) -> None:
        normalized = os.path.normcase(os.path.abspath(file_path))
        if normalized in scheduled_paths:
            return
        scheduled_paths.add(normalized)

        def load_scheduled_file() -> None:
            scheduled_paths.discard(normalized)
            player.load_video(file_path)

        QTimer.singleShot(100, player, load_scheduled_file)

    app.set_file_open_handler(schedule_file_open)

    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        schedule_file_open(sys.argv[1])

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
