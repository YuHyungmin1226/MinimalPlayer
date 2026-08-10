import os
import sys
import tempfile
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess, QSettings, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox


fake_mpv = types.ModuleType("mpv")
fake_mpv.ShutdownError = type("ShutdownError", (Exception,), {})
with mock.patch.dict(sys.modules, {"mpv": fake_mpv}):
    from player_window import VideoPlayer


class _Label:
    def __init__(self, text=""):
        self._text = text

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text


class _Slider:
    def __init__(self):
        self.minimum = None
        self.maximum = None
        self.value = None

    def setRange(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum

    def setMaximum(self, maximum):
        self.maximum = maximum

    def isSliderDown(self):
        return False

    def setValue(self, value):
        self.value = value


class PlayerStateTest(unittest.TestCase):
    def test_status_without_media_stays_play_and_disables_media_controls(self):
        window = types.SimpleNamespace(
            player=types.SimpleNamespace(pause=False),
            current_media_path=None,
            media_ended=True,
            play_btn=_Label("Pause"),
            time_label=_Label("01:00 / 02:00"),
            seek_slider=_Slider(),
            _set_media_controls_enabled=mock.Mock(),
        )

        VideoPlayer.update_status(window)

        self.assertEqual(window.play_btn.text(), "Play")
        self.assertEqual(window.time_label.text(), "00:00 / 00:00")
        self.assertEqual((window.seek_slider.minimum, window.seek_slider.maximum), (0, 0))
        window._set_media_controls_enabled.assert_called_once_with(False)
        self.assertFalse(window.media_ended)

    def test_save_position_ignores_non_finite_duration(self):
        settings = mock.Mock()
        window = types.SimpleNamespace(
            current_media_path="/media/live.mp4",
            player=types.SimpleNamespace(time_pos=20, duration=float("inf")),
            settings=settings,
            has_video=lambda: True,
        )

        VideoPlayer._save_current_position(window)

        settings.setValue.assert_not_called()

    def test_status_ignores_non_finite_duration(self):
        window = types.SimpleNamespace(
            player=types.SimpleNamespace(
                track_list=[],
                time_pos=5,
                duration=float("inf"),
                pause=False,
                idle_active=False,
                eof_reached=False,
            ),
            current_media_path="/media/live.mkv",
            media_stack=types.SimpleNamespace(currentWidget=lambda: None),
            video_container=object(),
            _audio_subtitle_on=False,
            media_ended=False,
            last_duration=0,
            last_time_pos=0,
            seek_slider=_Slider(),
            time_label=_Label(),
            play_btn=_Label("Play"),
        )

        VideoPlayer.update_status(window)

        self.assertEqual(window.seek_slider.maximum, 0)
        self.assertEqual(window.time_label.text(), "00:05 / 00:00")

    def test_resume_position_past_new_duration_is_discarded(self):
        path = "/media/replaced.mp4"
        window = types.SimpleNamespace(
            player=types.SimpleNamespace(duration=20, pause=False, time_pos=0),
            current_media_path=path,
            settings=types.SimpleNamespace(value=lambda *_args, **_kwargs: 90),
            _setting_key_for_path=lambda _path: "positions/key",
            _clear_saved_position=mock.Mock(),
        )

        VideoPlayer._maybe_resume(window, path)

        window._clear_saved_position.assert_called_once_with(path)
        self.assertEqual(window.player.time_pos, 0)
        self.assertFalse(window.player.pause)


class NativeWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_native_frame_and_standard_menus_are_available(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = QSettings(
                os.path.join(temp_dir, "settings.ini"),
                QSettings.Format.IniFormat,
            )

            def init_fake_player(window):
                window.player = types.SimpleNamespace(terminate=lambda: None)

            with mock.patch.object(VideoPlayer, "_init_player", init_fake_player):
                window = VideoPlayer(settings=settings, interactive_errors=False)
            try:
                self.assertFalse(
                    bool(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
                )
                self.assertEqual(
                    [action.text() for action in window.menuBar().actions()],
                    ["&File", "&Playback", "&View"],
                )
                self.assertEqual(window.windowTitle(), "Minimal Portable Player")
                self.assertFalse(hasattr(window, "title_bar"))
                self.assertFalse(window.export_action.isEnabled())
                self.assertTrue(window.fullscreen_action.shortcuts())

                close = mock.Mock()
                window.close = close
                escape = QKeyEvent(
                    QKeyEvent.Type.KeyPress,
                    Qt.Key.Key_Escape,
                    Qt.KeyboardModifier.NoModifier,
                )
                window.keyPressEvent(escape)
                close.assert_not_called()
            finally:
                window.timer.stop()
                window.mouse_timer.stop()
                window.player = None
                window.deleteLater()


class ExportSafetyTest(unittest.TestCase):
    def _window_for_export(self, output_path, work_path):
        export_paths = {work_path}

        def cleanup():
            for path in list(export_paths):
                if os.path.exists(path):
                    os.remove(path)
            export_paths.clear()

        process = types.SimpleNamespace(
            readAllStandardError=lambda: types.SimpleNamespace(data=lambda: b"ffmpeg failed")
        )
        return types.SimpleNamespace(
            _closing=False,
            export_dialog=types.SimpleNamespace(close=mock.Mock()),
            export_cancelled=False,
            export_process=process,
            export_temp_paths=export_paths,
            _export_output_path=output_path,
            _export_work_path=work_path,
            _cleanup_export_temp_paths=cleanup,
        )

    def test_successful_export_atomically_replaces_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "song.mp4")
            with open(output_path, "wb") as output_file:
                output_file.write(b"original")
            work_path = VideoPlayer._create_export_work_path(output_path)
            with open(work_path, "wb") as work_file:
                work_file.write(b"complete export")
            window = self._window_for_export(output_path, work_path)

            with mock.patch.object(QMessageBox, "information"):
                VideoPlayer._handle_export_finished(
                    window, 0, QProcess.ExitStatus.NormalExit
                )

            with open(output_path, "rb") as output_file:
                self.assertEqual(output_file.read(), b"complete export")
            self.assertFalse(os.path.exists(work_path))

    def test_failed_export_keeps_existing_output_and_removes_partial_work(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = os.path.join(temp_dir, "song.mp4")
            with open(output_path, "wb") as output_file:
                output_file.write(b"original")
            work_path = VideoPlayer._create_export_work_path(output_path)
            with open(work_path, "wb") as work_file:
                work_file.write(b"partial export")
            window = self._window_for_export(output_path, work_path)

            with mock.patch.object(QMessageBox, "critical"):
                VideoPlayer._handle_export_finished(
                    window, 1, QProcess.ExitStatus.NormalExit
                )

            with open(output_path, "rb") as output_file:
                self.assertEqual(output_file.read(), b"original")
            self.assertFalse(os.path.exists(work_path))

    def test_export_progress_preserves_a_line_split_across_process_chunks(self):
        class _ByteArray:
            def __init__(self, value):
                self.value = value

            def data(self):
                return self.value

        class _Process:
            def __init__(self):
                self.chunks = [b"out_time_us=500", b"000\n"]

            def readAllStandardOutput(self):
                return _ByteArray(self.chunks.pop(0))

        progress = mock.Mock()
        window = types.SimpleNamespace(
            export_process=_Process(),
            export_dialog=progress,
            _export_progress_buffer="",
            _export_total_seconds=10,
            last_duration=10,
        )

        VideoPlayer._handle_export_progress(window)
        progress.setValue.assert_not_called()
        VideoPlayer._handle_export_progress(window)
        progress.setValue.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
