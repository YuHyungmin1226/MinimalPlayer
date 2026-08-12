import os
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QProcess, QSettings, Qt, QUrl
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


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

    def setRange(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum


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
                close.assert_called_once()
            finally:
                window.timer.stop()
                window.mouse_timer.stop()
                window.player = None
                window.deleteLater()

    def test_playback_controls_stay_out_of_the_keyboard_focus_chain(self):
        """Buttons/sliders must not accept keyboard focus.

        Otherwise clicking the seek bar (Jump-to-Click) or a control button
        steals focus from the main window, and the global arrow-key/Space
        shortcuts get swallowed by that widget's own default key handling
        (e.g. QSlider nudging by one step) instead of reaching
        VideoPlayer.keyPressEvent.
        """
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
                no_focus = Qt.FocusPolicy.NoFocus
                for widget in (
                    window.seek_slider,
                    window.vol_slider,
                    window.open_btn,
                    window.prev_btn,
                    window.back_btn,
                    window.play_btn,
                    window.fwd_btn,
                    window.next_btn,
                ):
                    self.assertEqual(widget.focusPolicy(), no_focus)
            finally:
                window.timer.stop()
                window.mouse_timer.stop()
                window.player = None
                window.deleteLater()

    def test_close_event_is_reentrancy_guarded(self):
        """closeEvent() can pump the event loop (export_process.waitForFinished),
        so a second close request arriving before the first finishes tearing
        down must not re-run terminate()/shutdown()/cleanup a second time."""
        from PySide6.QtGui import QCloseEvent

        with tempfile.TemporaryDirectory() as temp_dir:
            settings = QSettings(
                os.path.join(temp_dir, "settings.ini"),
                QSettings.Format.IniFormat,
            )

            def init_fake_player(window):
                window.player = types.SimpleNamespace(terminate=mock.Mock())

            with mock.patch.object(VideoPlayer, "_init_player", init_fake_player):
                window = VideoPlayer(settings=settings, interactive_errors=False)
            try:
                window.video_container.shutdown = mock.Mock()

                window.closeEvent(QCloseEvent())
                window.closeEvent(QCloseEvent())

                window.player.terminate.assert_called_once()
                window.video_container.shutdown.assert_called_once()
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


class _FakeMimeData:
    def __init__(self, path):
        self._path = path

    def hasUrls(self):
        return True

    def urls(self):
        return [QUrl.fromLocalFile(self._path)]


class _FakeDropEvent:
    def __init__(self, path):
        self._mime = _FakeMimeData(path)
        self.accepted = None

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


class ManualSubtitleLoadingTest(unittest.TestCase):
    """Covers loading a subtitle (e.g. .ass) that doesn't share the video's
    base filename, so auto-detection alone can't find it — via the
    "Load Subtitle..." dialog/menu action and via drag-and-drop."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, media_path=None):
        settings_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(settings_dir, ignore_errors=True))
        settings = QSettings(os.path.join(settings_dir, "settings.ini"), QSettings.Format.IniFormat)

        def init_fake_player(window):
            window.player = types.SimpleNamespace(terminate=lambda: None, sub_add=mock.Mock())

        with mock.patch.object(VideoPlayer, "_init_player", init_fake_player):
            window = VideoPlayer(settings=settings, interactive_errors=False)
        window.current_media_path = media_path
        self.addCleanup(self._teardown, window)
        return window

    @staticmethod
    def _teardown(window):
        window.timer.stop()
        window.mouse_timer.stop()
        window.player = None
        window.deleteLater()

    def test_open_subtitle_dialog_without_media_warns_instead_of_opening_file_dialog(self):
        window = self._window(media_path=None)
        with mock.patch.object(QMessageBox, "information") as info, \
                mock.patch.object(QFileDialog, "getOpenFileName") as dialog:
            window.open_subtitle_dialog()
        info.assert_called_once()
        dialog.assert_not_called()

    def test_load_subtitle_file_rejects_a_non_subtitle_extension(self):
        window = self._window(media_path="/media/video.mp4")
        with mock.patch.object(QMessageBox, "warning") as warn:
            window.load_subtitle_file("/media/video.mp4")
        warn.assert_called_once()
        window.player.sub_add.assert_not_called()

    def test_load_subtitle_file_attaches_ass_subtitle_not_matching_video_name(self):
        window = self._window(media_path="/media/video.mp4")
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
            f.write("[Script Info]\n".encode("utf-8"))
            sub_path = f.name
        self.addCleanup(lambda: os.path.exists(sub_path) and os.remove(sub_path))

        window.load_subtitle_file(sub_path)

        window.player.sub_add.assert_called_once()
        called_path = window.player.sub_add.call_args.args[0]
        called_flags = window.player.sub_add.call_args.kwargs.get("flags")
        self.assertTrue(os.path.exists(called_path))
        self.assertEqual(called_flags, "select")

    def test_load_subtitle_file_sets_audio_overlay_flag_only_for_audio_media(self):
        """_audio_subtitle_on gates the custom on-screen text overlay used
        only in audio-file mode; mpv renders subtitles onto video frames
        itself, so this must stay False for video media."""
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
            f.write("[Script Info]\n".encode("utf-8"))
            sub_path = f.name
        self.addCleanup(lambda: os.path.exists(sub_path) and os.remove(sub_path))

        video_window = self._window(media_path="/media/video.mp4")
        video_window.load_subtitle_file(sub_path)
        self.assertFalse(video_window._audio_subtitle_on)

        audio_window = self._window(media_path="/media/song.mp3")
        audio_window.load_subtitle_file(sub_path)
        self.assertTrue(audio_window._audio_subtitle_on)

    def test_load_subtitle_file_cleans_up_previously_converted_temp_file(self):
        """Trying several candidate subtitles in a row (without reloading the
        video) must not leak a converted temp file per attempt."""
        window = self._window(media_path="/media/video.mp4")
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\n한글 자막 A\n".encode("cp949"))
            sub_a = f.name
        with tempfile.NamedTemporaryFile(suffix=".srt", delete=False) as f:
            f.write("1\n00:00:00,000 --> 00:00:01,000\n한글 자막 B\n".encode("cp949"))
            sub_b = f.name
        self.addCleanup(lambda: os.path.exists(sub_a) and os.remove(sub_a))
        self.addCleanup(lambda: os.path.exists(sub_b) and os.remove(sub_b))

        window.load_subtitle_file(sub_a)
        first_temp = window._manual_subtitle_temp_path
        self.assertIsNotNone(first_temp, "cp949 source should have produced a converted temp file")
        self.assertTrue(os.path.exists(first_temp))
        self.addCleanup(lambda: os.path.exists(first_temp) and os.remove(first_temp))

        window.load_subtitle_file(sub_b)
        second_temp = window._manual_subtitle_temp_path
        self.assertIsNotNone(second_temp)
        self.assertNotEqual(first_temp, second_temp)
        self.assertFalse(os.path.exists(first_temp), "superseded manual subtitle temp file should be removed")
        self.assertTrue(os.path.exists(second_temp))
        self.addCleanup(lambda: os.path.exists(second_temp) and os.remove(second_temp))

    def test_drag_enter_accepts_lone_subtitle_only_once_media_is_loaded(self):
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
            sub_path = f.name
        self.addCleanup(lambda: os.path.exists(sub_path) and os.remove(sub_path))

        no_media_window = self._window(media_path=None)
        rejected = _FakeDropEvent(sub_path)
        no_media_window.dragEnterEvent(rejected)
        self.assertFalse(rejected.accepted)

        loaded_window = self._window(media_path="/media/video.mp4")
        accepted = _FakeDropEvent(sub_path)
        loaded_window.dragEnterEvent(accepted)
        self.assertTrue(accepted.accepted)

    def test_drop_event_routes_subtitle_to_load_subtitle_file(self):
        window = self._window(media_path="/media/video.mp4")
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
            sub_path = f.name
        self.addCleanup(lambda: os.path.exists(sub_path) and os.remove(sub_path))

        window.dropEvent(_FakeDropEvent(sub_path))

        window.player.sub_add.assert_called_once()


if __name__ == "__main__":
    unittest.main()
