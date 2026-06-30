import locale
import os
import sys
import importlib
from typing import Any, cast

from PySide6.QtCore import QEvent, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QOpenGLContext, QPixmap
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from constants import (
    APP_DISPLAY_NAME,
    APP_NAME,
    DEFAULT_VOLUME,
    ORG_NAME,
    RECENT_FILES_LIMIT,
    RESUME_THRESHOLD_SECONDS,
)
from file_association import register_file_associations
from mpv_setup import IS_LINUX, IS_MAC, IS_WINDOWS
from utils import convert_smi_file_to_temp_srt, convert_subtitle_to_utf8, find_matching_image, find_matching_subtitle, format_time, is_supported_audio, is_supported_media, normalize_recent_files

mpv = cast(Any, importlib.import_module("mpv"))


def _gl_get_proc_address(_ctx, name):
    glctx = QOpenGLContext.currentContext()
    if glctx is None:
        return 0
    if isinstance(name, str):
        name = name.encode("utf-8")
    return int(glctx.getProcAddress(name))


class MpvGLWidget(QOpenGLWidget):
    _frame_ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = None
        self._ctx = None
        self._proc_addr = None
        self._frame_ready.connect(self.update)

    def set_player(self, player):
        self._player = player

    def initializeGL(self):
        if self._player is None or self._ctx is not None:
            return
        self._proc_addr = mpv.MpvGlGetProcAddressFn(_gl_get_proc_address)
        self._ctx = mpv.MpvRenderContext(
            self._player,
            "opengl",
            opengl_init_params={"get_proc_address": self._proc_addr},
        )
        self._ctx.update_cb = self._on_mpv_update

    def _on_mpv_update(self):
        self._frame_ready.emit()

    def paintGL(self):
        if self._ctx is None:
            self.initializeGL()
            if self._ctx is None:
                return
        ratio = self.devicePixelRatioF()
        width = max(1, int(round(self.width() * ratio)))
        height = max(1, int(round(self.height() * ratio)))
        self._ctx.render(
            flip_y=True,
            opengl_fbo={"w": width, "h": height, "fbo": self.defaultFramebufferObject()},
        )

    def shutdown(self):
        if self._ctx is not None:
            try:
                self.makeCurrent()
                self._ctx.update_cb = None
                self._ctx.free()
                self.doneCurrent()
            except Exception:
                pass
            self._ctx = None


STYLE = (
    "QMainWindow { background-color: #121212; }"
    "#VideoContainer { background-color: #000000; }"
    "#TitleBar { background-color: #1e1e1e; border-bottom: 1px solid #333; }"
    "#ControlBar { background-color: rgba(30, 30, 30, 220); border-top: 1px solid #333; }"
    "QPushButton { background: transparent; color: #eee; border: none; "
    "font-family: 'Segoe UI', 'Helvetica Neue', 'Arial', sans-serif; font-size: 14px; padding: 5px; outline: none; }"
    "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }"
    "QPushButton:pressed { background-color: rgba(255, 255, 255, 0.2); }"
    "QPushButton:focus { background: transparent; }"
    "QSlider::groove:horizontal { border: 1px solid #444; height: 4px; background: #222; margin: 2px 0; }"
    "QSlider::handle:horizontal { background: #888; border: 1px solid #888; width: 14px; height: 14px; "
    "margin: -5px 0; border-radius: 7px; }"
    "QLabel { color: #aaa; font-size: 12px; }"
    "#TitleLabel { color: #eee; font-weight: bold; }"
    "QMenu { background-color: #1e1e1e; color: #eee; border: 1px solid #333; }"
    "QMenu::item { background-color: transparent; padding: 6px 20px; }"
    "QMenu::item:selected { background-color: rgba(255, 255, 255, 0.1); }"
    "QMenu::separator { height: 1px; background: #333; margin: 4px 0; }"
)


class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.width() > 0:
            new_value = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
            self.setValue(int(new_value))
            self.sliderMoved.emit(int(new_value))
            event.accept()
        else:
            super().mousePressEvent(event)


class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.current_media_path = None
        self.media_ended = False
        self.last_time_pos = 0
        self.last_duration = 0
        self._drag_pos = None
        self._audio_pixmap: QPixmap = None
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.resize(1000, 600)
        self.setStyleSheet(STYLE)

        self._build_ui()

        self.settings = QSettings(ORG_NAME, APP_NAME)

        self.recent_actions: list[QAction] = []
        self._update_recent_menu()

        self.converted_subtitle_paths: list[str] = []
        self.temp_files_to_clean = set()

        saved_vol = self.settings.value("volume", DEFAULT_VOLUME, type=int)
        self.vol_slider.setValue(saved_vol)

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_status)
        self.timer.start()

        self.mouse_timer = QTimer(self)
        self.mouse_timer.setInterval(3000)
        self.mouse_timer.setSingleShot(True)
        self.mouse_timer.timeout.connect(self._hide_controls_on_timeout)

        self.setMouseTracking(True)
        self.central_widget.setMouseTracking(True)
        self.media_stack.setMouseTracking(True)
        self.video_container.setMouseTracking(True)
        self.audio_label.setMouseTracking(True)
        self.title_bar.setMouseTracking(True)
        self.control_bar.setMouseTracking(True)

        self.central_widget.installEventFilter(self)
        self.media_stack.installEventFilter(self)
        self.video_container.installEventFilter(self)
        self.audio_label.installEventFilter(self)
        self.title_bar.installEventFilter(self)
        self.control_bar.installEventFilter(self)

        self.setFocus()
        self._init_player()

    def _build_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.title_bar = QFrame()
        self.title_bar.setObjectName("TitleBar")
        self.title_bar.setFixedHeight(35)
        self.title_bar_layout = QHBoxLayout(self.title_bar)
        self.title_bar_layout.setContentsMargins(15, 0, 0, 0)

        self.title_label = QLabel(APP_DISPLAY_NAME)
        self.title_label.setObjectName("TitleLabel")
        self.title_bar_layout.addWidget(self.title_label)
        self.title_bar_layout.addStretch()

        self.min_btn = QPushButton("-")
        self.min_btn.setFixedSize(40, 35)
        self.min_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.min_btn.clicked.connect(self.showMinimized)

        self.close_btn = QPushButton("x")
        self.close_btn.setFixedSize(40, 35)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("QPushButton:hover { background-color: #e81123; color: white; }")

        self.title_bar_layout.addWidget(self.min_btn)
        self.title_bar_layout.addWidget(self.close_btn)
        self.main_layout.addWidget(self.title_bar)

        self.media_stack = QStackedWidget()
        self.media_stack.setObjectName("VideoContainer")

        self.video_widget = MpvGLWidget(self.media_stack)
        self.media_stack.addWidget(self.video_widget)
        self.video_container = self.video_widget

        self.audio_label = QLabel("♪")
        self.audio_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.audio_label.setStyleSheet("QLabel { background-color: #000; color: #444; font-size: 80px; }")

        self.audio_sub_label = QLabel("", self.audio_label)
        self.audio_sub_label.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        self.audio_sub_label.setWordWrap(True)
        self.audio_sub_label.setStyleSheet(
            "QLabel { background-color: transparent; color: #fff; font-size: 22px; "
            "font-weight: bold; padding: 6px; }"
        )
        self.audio_sub_label.hide()

        self.media_stack.addWidget(self.audio_label)

        self.main_layout.addWidget(self.media_stack, 1)

        self.control_bar = QFrame()
        self.control_bar.setObjectName("ControlBar")
        self.control_bar.setFixedHeight(70)
        self.control_layout = QVBoxLayout(self.control_bar)
        self.control_layout.setContentsMargins(15, 5, 15, 10)

        self.seek_slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.seek_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seek_slider.sliderMoved.connect(self.seek)
        self.control_layout.addWidget(self.seek_slider)

        self.btns_layout = QHBoxLayout()
        self.btns_layout.setSpacing(10)
        self.btns_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.open_btn = QPushButton("Open")
        self.open_btn.setFixedSize(45, 35)
        self.open_btn.setToolTip("Open File")
        self.open_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open_btn.clicked.connect(self.open_file_dialog)
        self.btns_layout.addWidget(self.open_btn)

        self.back_btn = QPushButton("<<")
        self.back_btn.setFixedSize(45, 35)
        self.back_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.back_btn.clicked.connect(lambda: self.skip(-10))
        self.btns_layout.addWidget(self.back_btn)

        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedSize(60, 35)
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.clicked.connect(self.toggle_pause)
        self.btns_layout.addWidget(self.play_btn)

        self.fwd_btn = QPushButton(">>")
        self.fwd_btn.setFixedSize(45, 35)
        self.fwd_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fwd_btn.clicked.connect(lambda: self.skip(10))
        self.btns_layout.addWidget(self.fwd_btn)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedHeight(35)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btns_layout.addWidget(self.time_label)
        self.btns_layout.addStretch()

        self.vol_label = QLabel("Volume")
        self.vol_label.setFixedHeight(35)
        self.vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btns_layout.addWidget(self.vol_label)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setFixedHeight(35)
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(DEFAULT_VOLUME)
        self.vol_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.vol_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_slider.valueChanged.connect(lambda val: self.set_volume(val, show_osd=False))
        self.btns_layout.addWidget(self.vol_slider)

        self.control_layout.addLayout(self.btns_layout)
        self.main_layout.addWidget(self.control_bar)

    def _init_player(self):
        locale.setlocale(locale.LC_NUMERIC, "C")
        try:
            self.player = mpv.MPV(vo="libmpv", ytdl=True, osc=False, keep_open=True)
            self.video_container.set_player(self.player)
            self.player.volume = self.vol_slider.value()
        except Exception as e:
            if IS_MAC:
                detail = "Install mpv via Homebrew ('brew install mpv') and restart."
            elif IS_LINUX:
                detail = "Install libmpv via your package manager and restart."
            else:
                detail = "Please download 'mpv-1.dll' from the GitHub releases page and place it next to the executable."
            _ = QMessageBox.critical(self, "Library Load Error", "Could not initialize the mpv media engine.\n\n" + detail)
            print(f"MPV initialization error: {e}")
            sys.exit(1)

    def has_video(self):
        return bool(self.current_media_path)

    def _setting_key_for_path(self, path: str) -> str:
        return "positions/" + path.replace("/", "_").replace("\\", "_").replace(":", "_")

    def _save_current_position(self):
        if not self.has_video():
            return
        try:
            pos = float(self.player.time_pos or 0)
            duration = float(self.player.duration or 0)
        except Exception:
            return
        if pos > RESUME_THRESHOLD_SECONDS and (duration == 0 or pos < duration - 5):
            self.settings.setValue(self._setting_key_for_path(str(self.current_media_path)), pos)

    def _maybe_resume(self, path):
        try:
            if not self.player or not self.current_media_path or path != self.current_media_path:
                return
            saved = float(str(self.settings.value(self._setting_key_for_path(path), 0) or 0))
            if saved < RESUME_THRESHOLD_SECONDS:
                return

            duration = self.player.duration
            if duration is None or duration <= 0:
                QTimer.singleShot(100, self, lambda: self._maybe_resume(path))
                return

            was_paused = self.player.pause
            self.player.pause = True
            answer = QMessageBox.question(
                self,
                "Resume Playback",
                f"Resume from {format_time(saved)}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.player.time_pos = saved
                self.player.pause = False
                self.media_ended = False
            else:
                self.player.pause = was_paused
        except Exception as e:
            print(f"Error in resume playback check: {e}")

    def _recent_files(self):
        value = self.settings.value("recentFiles", [])
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            value = []
        return normalize_recent_files(value, limit=RECENT_FILES_LIMIT)

    def _remember_recent_file(self, path: str) -> None:
        self.settings.setValue("recentFiles", normalize_recent_files(self._recent_files(), path, RECENT_FILES_LIMIT))
        self._update_recent_menu()

    def clear_recent_files(self) -> None:
        self.settings.setValue("recentFiles", [])
        self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        self.recent_actions = []

    def _cleanup_paths(self, paths: list[str]) -> None:
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
                    self.temp_files_to_clean.discard(path)
            except OSError:
                pass

    def _remove_from_recent_files(self, path: str) -> None:
        recent = self._recent_files()
        if path in recent:
            recent.remove(path)
            self.settings.setValue("recentFiles", recent)
            self._update_recent_menu()

    def _cleanup_converted_subtitles(self):
        for path in self.converted_subtitle_paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        self.converted_subtitle_paths = []

    def _subtitle_path_for_player(self, subtitle_path: str) -> str:
        _, ext = os.path.splitext(subtitle_path)
        if ext.lower() == ".smi":
            converted_path = convert_smi_file_to_temp_srt(subtitle_path)
            if converted_path:
                self.converted_subtitle_paths.append(converted_path)
                self.temp_files_to_clean.add(converted_path)
                return converted_path
        else:
            converted_path = convert_subtitle_to_utf8(subtitle_path)
            if converted_path:
                self.converted_subtitle_paths.append(converted_path)
                self.temp_files_to_clean.add(converted_path)
                return converted_path
        return subtitle_path

    def toggle_pause(self):
        if not self.has_video():
            return
        if self.media_ended:
            self.player.time_pos = 0
            self.player.pause = False
            self.media_ended = False
            self.play_btn.setText("Pause")
            return
        self.player.pause = not self.player.pause
        self.play_btn.setText("Play" if self.player.pause else "Pause")

    def seek(self, position: int) -> None:
        if self.has_video():
            try:
                self.player.time_pos = position
            except (AttributeError, mpv.ShutdownError):
                pass

    def set_volume(self, value: int, show_osd: bool = False) -> None:
        if not hasattr(self, "player") or not self.player:
            return
        new_vol = max(0, min(100, value))
        try:
            self.player.volume = new_vol
            if self.vol_slider.value() != new_vol:
                self.vol_slider.blockSignals(True)
                self.vol_slider.setValue(new_vol)
                self.vol_slider.blockSignals(False)
            if show_osd:
                self.player.show_text(f"Volume: {new_vol}%", duration=1500)
        except (AttributeError, mpv.ShutdownError):
            pass

    def skip(self, seconds: int) -> None:
        if self.has_video():
            try:
                if self.media_ended:
                    if seconds < 0:
                        self.media_ended = False
                        self.player.time_pos = max(0, self.last_duration + seconds)
                else:
                    self.player.seek(seconds, reference="relative")
            except (AttributeError, mpv.ShutdownError):
                pass

    def adjust_sub_delay(self, delta: float) -> None:
        if not self.has_video():
            return
        try:
            current = self.player.sub_delay
            new_delay = round(current + delta, 1)
            self.player.sub_delay = new_delay
            self.player.show_text(f"Subtitle Sync: {new_delay:+.1f}s", duration=1500)
        except (AttributeError, mpv.ShutdownError):
            pass

    def adjust_sub_scale(self, delta: float) -> None:
        if not self.has_video():
            return
        try:
            current = self.player.sub_scale
            new_scale = round(max(0.1, min(5.0, current + delta)), 1)
            self.player.sub_scale = new_scale
            self.player.show_text(f"Subtitle Scale: {new_scale:.1f}x", duration=1500)
        except (AttributeError, mpv.ShutdownError):
            pass

    def update_status(self):
        try:
            if not self.player:
                return
            if self._audio_subtitle_on:
                text = self.player.sub_text or ""
                if self.audio_sub_label.text() != text:
                    self.audio_sub_label.setText(text)
                    self.audio_sub_label.setVisible(bool(text.strip()))
            play_text = "Play"
            time_pos = self.player.time_pos
            duration = self.player.duration
            idle_active = bool(getattr(self.player, "idle_active", False))
            eof_reached = bool(getattr(self.player, "eof_reached", False))

            if self.has_video() and (eof_reached or (idle_active and time_pos is None)) and self.last_duration > 0:
                self.media_ended = True
                self.seek_slider.setMaximum(self.last_duration)
                self.seek_slider.setValue(self.last_duration)
                self.time_label.setText(f"{format_time(self.last_duration)} / {format_time(self.last_duration)}")
                if self.play_btn.text() != "Play":
                    self.play_btn.setText("Play")
                return

            if self.has_video() and time_pos is not None:
                self.media_ended = False
                play_text = "Play" if self.player.pause else "Pause"
            if self.play_btn.text() != play_text:
                self.play_btn.setText(play_text)

            if self.has_video() and time_pos is not None:
                curr = int(time_pos)
                total = int(duration or 0)
                self.last_time_pos = curr
                if total > 0:
                    self.last_duration = total
                self.seek_slider.setMaximum(total)
                if not self.seek_slider.isSliderDown():
                    self.seek_slider.setValue(curr)
                self.time_label.setText(f"{format_time(curr)} / {format_time(total)}")
        except (mpv.ShutdownError, AttributeError):
            if hasattr(self, "timer"):
                self.timer.stop()

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Media File",
            "",
            "Media Files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.3gp *.mpeg *.mpg *.ts *.tp *.asf *.m4v "
            "*.wav *.mp3 *.flac *.aac *.ogg *.m4a *.opus *.wma *.aiff *.aif *.ape *.alac);;"
            "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.3gp *.mpeg *.mpg *.ts *.tp *.asf *.m4v);;"
            "Audio Files (*.wav *.mp3 *.flac *.aac *.ogg *.m4a *.opus *.wma *.aiff *.aif *.ape *.alac);;"
            "All Files (*)",
        )
        if file_path:
            self.load_video(file_path)

    def load_video(self, path):
        if not self.player:
            return
        if not os.path.isfile(path):
            _ = QMessageBox.warning(self, "File Not Found", "The selected file does not exist.")
            self._remove_from_recent_files(path)
            return
        if not is_supported_media(path):
            _ = QMessageBox.warning(self, "Unsupported File", "Please select a supported video or audio file.")
            return

        self._save_current_position()
        old_paths = list(self.converted_subtitle_paths)
        self.converted_subtitle_paths = []
        self.current_media_path = os.path.abspath(path)
        self.media_ended = False
        self.last_time_pos = 0
        self.last_duration = 0

        sub_path = find_matching_subtitle(self.current_media_path)
        is_audio = is_supported_audio(self.current_media_path)
        image_path = find_matching_image(self.current_media_path) if is_audio else None

        self.title_label.setText(os.path.basename(self.current_media_path))
        self._remember_recent_file(self.current_media_path)

        if is_audio:
            self._set_audio_image(image_path)
            self._audio_subtitle_on = bool(sub_path)
            self.audio_sub_label.setText("")
            self.audio_sub_label.setVisible(False)
            self.media_stack.setCurrentWidget(self.audio_label)
            QTimer.singleShot(50, self, self._reposition_audio_subtitle)
        else:
            self._audio_subtitle_on = False
            self.audio_sub_label.hide()
            self.media_stack.setCurrentWidget(self.video_container)

        player_sub_path = None
        if sub_path:
            try:
                player_sub_path = self._subtitle_path_for_player(sub_path)
                print(f"Subtitle found and prepared: {player_sub_path}")
            except Exception as e:
                print(f"Error preparing subtitle: {e}")

        if player_sub_path:
            self.player.loadfile(self.current_media_path, sub_file=player_sub_path)
        else:
            self.player.loadfile(self.current_media_path)

        self.player.pause = False

        QTimer.singleShot(1000, self, lambda: self._cleanup_paths(old_paths))
        QTimer.singleShot(500, self, lambda path=self.current_media_path: self._maybe_resume(path))

    def _set_audio_image(self, image_path: str | None) -> None:
        if image_path:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                self._audio_pixmap = pixmap
                self._update_audio_label()
                return
        self._audio_pixmap = None
        self.audio_label.clear()
        self.audio_label.setText("♪")

    def _update_audio_label(self) -> None:
        if self._audio_pixmap and not self._audio_pixmap.isNull():
            size = self.audio_label.size()
            if size.width() > 0 and size.height() > 0:
                self.audio_label.setPixmap(
                    self._audio_pixmap.scaled(
                        size,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )

    def _reposition_audio_subtitle(self) -> None:
        margin = 24
        w = self.audio_label.width()
        h = self.audio_label.height()
        label_h = min(160, max(48, h // 4))
        self.audio_sub_label.setGeometry(margin, h - label_h - margin, max(1, w - 2 * margin), label_h)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child in (self.video_container, self.audio_label, self.media_stack):
                if self.isFullScreen():
                    self.showNormal()
                    self.title_bar.show()
                    self.control_bar.show()
                    self.unsetCursor()
                    self.mouse_timer.stop()
                else:
                    self.showFullScreen()
                    self.handle_mouse_activity()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event) -> None:
        delta = event.angleDelta().y()
        if delta > 0:
            self.set_volume(self.vol_slider.value() + 5, show_osd=True)
        elif delta < 0:
            self.set_volume(self.vol_slider.value() - 5, show_osd=True)
        event.accept()

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.MouseMove:
            self.handle_mouse_activity()
        return super().eventFilter(obj, event)

    def handle_mouse_activity(self) -> None:
        if self.isFullScreen():
            self.unsetCursor()
            self.title_bar.show()
            self.control_bar.show()
            self.mouse_timer.start()

    def _hide_controls_on_timeout(self) -> None:
        if self.isFullScreen():
            pos = self.mapFromGlobal(self.cursor().pos())
            if self.control_bar.geometry().contains(pos) or self.title_bar.geometry().contains(pos):
                self.mouse_timer.start()
                return
            self.title_bar.hide()
            self.control_bar.hide()
            self.setCursor(Qt.CursorShape.BlankCursor)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_audio_label()
        self._reposition_audio_subtitle()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Space:
            self.toggle_pause()
        elif key == Qt.Key.Key_Left:
            self.skip(-5)
        elif key == Qt.Key.Key_Right:
            self.skip(5)
        elif key == Qt.Key.Key_Up:
            self.set_volume(self.vol_slider.value() + 5, show_osd=True)
        elif key == Qt.Key.Key_Down:
            self.set_volume(self.vol_slider.value() - 5, show_osd=True)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.isFullScreen():
                self.showNormal()
                self.title_bar.show()
                self.control_bar.show()
                self.unsetCursor()
                self.mouse_timer.stop()
            else:
                self.showFullScreen()
                self.handle_mouse_activity()
        elif key == Qt.Key.Key_Z:
            self.adjust_sub_delay(0.1)
        elif key == Qt.Key.Key_X:
            self.adjust_sub_delay(-0.1)
        elif key == Qt.Key.Key_BracketLeft:
            self.adjust_sub_scale(-0.1)
        elif key == Qt.Key.Key_BracketRight:
            self.adjust_sub_scale(0.1)
        elif key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
                self.title_bar.show()
                self.control_bar.show()
                self.unsetCursor()
                self.mouse_timer.stop()
            else:
                self.close()
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            draggable = {
                self.video_container, self.audio_label, self.media_stack, 
                self.title_bar, self.control_bar,
                self.title_label, self.time_label, self.vol_label
            }
            if not self.isFullScreen() and (child is None or child in draggable):
                self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self._drag_pos = event.globalPosition().toPoint()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    def closeEvent(self, event):
        self._save_current_position()
        self.settings.setValue("volume", self.vol_slider.value())
        self._cleanup_converted_subtitles()
        for path in list(self.temp_files_to_clean):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
        if self.video_container and isinstance(self.video_container, MpvGLWidget):
            self.video_container.shutdown()
        if hasattr(self, "player") and self.player:
            try:
                self.player.terminate()
            except Exception:
                pass
        super().closeEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            files = [u.toLocalFile() for u in event.mimeData().urls()]
            if files and is_supported_media(files[0]):
                event.acceptProposedAction()
            else:
                event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.load_video(files[0])

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        open_action = QAction("Open File...", self)
        open_action.triggered.connect(self.open_file_dialog)
        menu.addAction(open_action)

        recent_files = self._recent_files()
        if recent_files:
            recent_menu = menu.addMenu("Recent Files")
            for path in recent_files:
                action = QAction(os.path.basename(path), self)
                action.setToolTip(path)
                action.triggered.connect(lambda checked=False, p=path: self.load_video(p))
                recent_menu.addAction(action)
            recent_menu.addSeparator()
            clear_action = QAction("Clear Recent Files", self)
            clear_action.triggered.connect(self.clear_recent_files)
            recent_menu.addAction(clear_action)

        menu.addSeparator()

        if IS_WINDOWS:
            register_action = QAction("Set as Default App", self)
            register_action.triggered.connect(self.setup_default_program)
            menu.addAction(register_action)
            menu.addSeparator()

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)

        menu.exec(event.globalPos())

    def setup_default_program(self):
        success = register_file_associations(silent=True)
        if not success:
            _ = QMessageBox.warning(
                self,
                "Error",
                "An error occurred during registry write for default program registration.\n"
                "Please check if your antivirus software is blocking registry writes.",
            )
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Default Program Settings")
        msg_box.setText(
            "MinimalPlayer has been registered to the file association list.\n\n"
            "Due to Windows policies, you must manually select the default app in Settings to apply the change.\n\n"
            "Click OK to open the Windows 'Default Apps' Settings page.\n"
            "Search for 'MinimalPlayer' and set it as the default app."
        )
        msg_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)
        msg_box.setButtonText(QMessageBox.StandardButton.Yes, "OK (Open Settings)")
        msg_box.setButtonText(QMessageBox.StandardButton.No, "Cancel")

        if msg_box.exec() == QMessageBox.StandardButton.Yes:
            try:
                os.startfile("ms-settings:defaultapps?registeredApp=MinimalPlayer")
            except Exception:
                try:
                    os.startfile("ms-settings:defaultapps")
                except Exception as e:
                    _ = QMessageBox.critical(
                        self,
                        "Execution Failed",
                        f"Failed to open Settings:\n{e}\n\nPlease search for 'Default apps' manually in the Windows Start menu.",
                    )
