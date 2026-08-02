from __future__ import annotations

import hashlib
import locale
import os
import sys
import importlib
import shutil
import subprocess
import tempfile
from typing import Any, cast

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QSettings, Qt, QTimer, Signal, QProcess
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence, QOpenGLContext, QPixmap
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
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
    QProgressDialog,
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
from utils import convert_smi_file_to_temp_srt, convert_subtitle_to_utf8, find_adjacent_media_in_folder, find_matching_image, find_matching_subtitle, find_next_media_in_folder, find_previous_media_in_folder, format_time, is_supported_audio, is_supported_media, normalize_recent_files

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

    def has_video_track(self) -> bool:
        if self._player is None:
            return False
        try:
            vid = self._player.vid
            if vid in (False, "no", None):
                return False
            tracks = getattr(self._player, "track_list", None)
            if tracks:
                return any(t.get("type") == "video" for t in tracks)
            return False
        except Exception:
            return False

    def paintGL(self):
        if self._ctx is None:
            self.initializeGL()
            if self._ctx is None:
                return

        if not self.has_video_track():
            try:
                funcs = self.context().functions()
                funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
                funcs.glClear(0x00004000)  # GL_COLOR_BUFFER_BIT
            except Exception:
                pass
            return

        ratio = self.devicePixelRatioF()
        width = max(1, int(round(self.width() * ratio)))
        height = max(1, int(round(self.height() * ratio)))
        try:
            self._ctx.render(
                flip_y=True,
                opengl_fbo={"w": width, "h": height, "fbo": self.defaultFramebufferObject()},
            )
        except Exception as e:
            print(f"MpvGLWidget: Render context failed to render: {e}")
            try:
                funcs = self.context().functions()
                funcs.glClearColor(0.0, 0.0, 0.0, 1.0)
                funcs.glClear(0x00004000)  # GL_COLOR_BUFFER_BIT
            except Exception:
                pass

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
        # Drop the player reference so a paintGL() that races in after shutdown
        # (Qt can still deliver a queued repaint before the widget is actually
        # destroyed) can't have initializeGL() recreate a render context
        # against a core that terminate() is about to tear down.
        self._player = None


STYLE = (
    "QMainWindow { background-color: #121212; }"
    "#VideoContainer { background-color: #000000; }"
    "#ControlBar { background-color: rgba(30, 30, 30, 220); border-top: 1px solid #333; }"
    "QPushButton { background: transparent; color: #eee; border: none; "
    "font-size: 14px; padding: 5px; outline: none; }"
    "QPushButton:hover { background-color: rgba(255, 255, 255, 0.1); }"
    "QPushButton:pressed { background-color: rgba(255, 255, 255, 0.2); }"
    "QPushButton:focus { background-color: rgba(53, 120, 229, 0.22); border: 1px solid #4c9aff; }"
    "QPushButton:disabled { color: #555; background: transparent; }"
    "QSlider { outline: none; }"
    "QSlider::groove:horizontal { border: 1px solid #444; height: 4px; background: #222; margin: 2px 0; }"
    "QSlider::handle:horizontal { background: #888; border: 1px solid #888; width: 14px; height: 14px; "
    "margin: -5px 0; border-radius: 7px; }"
    "QSlider::handle:horizontal:focus { background: #4c9aff; border: 1px solid #8dc0ff; }"
    "QLabel { color: #aaa; font-size: 12px; }"
    "QMenuBar { background-color: #1e1e1e; color: #eee; border-bottom: 1px solid #333; }"
    "QMenuBar::item { background: transparent; padding: 5px 9px; }"
    "QMenuBar::item:selected { background-color: rgba(255, 255, 255, 0.12); }"
    "QMenu { background-color: #1e1e1e; color: #eee; border: 1px solid #333; }"
    "QMenu::item { background-color: transparent; padding: 6px 20px; }"
    "QMenu::item:selected { background-color: rgba(255, 255, 255, 0.1); }"
    "QMenu::separator { height: 1px; background: #333; margin: 4px 0; }"
    # 대화상자는 배경색을 명시적으로 지정합니다. 지정하지 않으면 배경이 OS 테마를
    # 따라가는데, 위의 전역 규칙이 상속되어 밝은 테마에서는 #eee 글자에 테두리도
    # 없는 버튼이 흰 배경 위에 놓여 완전히 보이지 않게 됩니다.
    "QMessageBox, QProgressDialog { background-color: #1e1e1e; }"
    "QMessageBox QLabel, QProgressDialog QLabel { color: #eee; font-size: 13px; }"
    "QMessageBox QPushButton, QProgressDialog QPushButton {"
    " background-color: #2d2d2d; color: #eee; border: 1px solid #555;"
    " border-radius: 4px; min-width: 72px; min-height: 28px; padding: 2px 12px; }"
    "QMessageBox QPushButton:hover, QProgressDialog QPushButton:hover { background-color: #3a3a3a; }"
    "QMessageBox QPushButton:pressed, QProgressDialog QPushButton:pressed { background-color: #454545; }"
    "QMessageBox QPushButton:default { border: 2px solid #3578e5; }"
    "QProgressBar { border: 1px solid #444; border-radius: 3px; background-color: #222;"
    " color: #eee; text-align: center; }"
    "QProgressBar::chunk { background-color: #3578e5; }"
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

    def keyPressEvent(self, event):
        old_value = self.value()
        super().keyPressEvent(event)
        if self.value() != old_value:
            self.sliderMoved.emit(self.value())


class VideoPlayer(QMainWindow):
    def __init__(self, settings: QSettings | None = None, interactive_errors: bool = True):
        super().__init__()
        self.settings = settings if settings is not None else QSettings(ORG_NAME, APP_NAME)
        self._interactive_errors = interactive_errors
        self.current_media_path = None
        self.media_ended = False
        self.last_time_pos = 0
        self.last_duration = 0
        self._audio_pixmap: QPixmap = None
        self._audio_subtitle_on = False
        # 재생이 실제로 진행된 파일에 대해서만 EOF 자동 넘김을 허용하기 위한 플래그.
        # loadfile() 직후 mpv가 이전 파일의 eof-reached를 잠시 더 보고할 수 있는데,
        # 이 플래그가 없으면 그 값을 보고 폴더 전체를 순식간에 건너뛰게 됩니다.
        self._eof_armed = False
        
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1000, 600)
        self.setStyleSheet(STYLE)

        # Set window icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
        if getattr(sys, "frozen", False):
            # When frozen, check next to executable or in bundle resources
            icon_path = os.path.join(os.path.dirname(sys.executable), "icon.png")
            if not os.path.exists(icon_path):
                # Fallback to _MEIPASS if it's there
                meipass = getattr(sys, "_MEIPASS", None)
                if meipass:
                    icon_path = os.path.join(meipass, "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self._build_ui()
        self._init_fade_animations()

        self.converted_subtitle_paths: list[str] = []
        self.temp_files_to_clean = set()
        self.export_temp_paths: set[str] = set()

        saved_vol = self.settings.value("volume", DEFAULT_VOLUME, type=int)
        self.vol_slider.setValue(saved_vol)

        self._auto_advance_enabled = bool(self.settings.value("autoAdvance", True, type=bool))
        self.recent_actions: list[QAction] = []
        self._build_menus()

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
        self.control_bar.setMouseTracking(True)

        self.central_widget.installEventFilter(self)
        self.media_stack.installEventFilter(self)
        self.video_container.installEventFilter(self)
        self.audio_label.installEventFilter(self)
        self.control_bar.installEventFilter(self)

        self.setFocus()
        self._init_player()

    def _build_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

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
        subtitle_shadow = QGraphicsDropShadowEffect(self.audio_sub_label)
        subtitle_shadow.setBlurRadius(5)
        subtitle_shadow.setColor(QColor(0, 0, 0, 230))
        subtitle_shadow.setOffset(1.5, 1.5)
        self.audio_sub_label.setGraphicsEffect(subtitle_shadow)
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
        self.seek_slider.setToolTip("Seek Position")
        self.seek_slider.setAccessibleName("Seek Position")
        # Keep keyboard focus on the main window so the global playback
        # shortcuts (arrow keys, Space, ...) always work, even right after
        # clicking the seek bar to jump to a position.
        self.seek_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.seek_slider.sliderMoved.connect(self.seek)
        self.control_layout.addWidget(self.seek_slider)

        self.btns_layout = QHBoxLayout()
        self.btns_layout.setSpacing(10)
        self.btns_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.open_btn = QPushButton("Open")
        self.open_btn.setFixedSize(45, 35)
        self.open_btn.setToolTip("Open File")
        self.open_btn.setAccessibleName("Open File")
        self.open_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.open_btn.clicked.connect(self.open_file_dialog)
        self.btns_layout.addWidget(self.open_btn)

        self.prev_btn = QPushButton("|<")
        self.prev_btn.setFixedSize(45, 35)
        self.prev_btn.setToolTip("Previous File in Folder")
        self.prev_btn.setAccessibleName("Previous File in Folder")
        self.prev_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self.play_previous_in_folder)
        self.btns_layout.addWidget(self.prev_btn)

        self.back_btn = QPushButton("<<")
        self.back_btn.setFixedSize(45, 35)
        self.back_btn.setToolTip("Back 10 Seconds")
        self.back_btn.setAccessibleName("Back 10 Seconds")
        self.back_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.back_btn.clicked.connect(lambda: self.skip(-10))
        self.btns_layout.addWidget(self.back_btn)

        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedSize(60, 35)
        self.play_btn.setToolTip("Play or Pause")
        self.play_btn.setAccessibleName("Play or Pause")
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.clicked.connect(self.toggle_pause)
        self.btns_layout.addWidget(self.play_btn)

        self.fwd_btn = QPushButton(">>")
        self.fwd_btn.setFixedSize(45, 35)
        self.fwd_btn.setToolTip("Forward 10 Seconds")
        self.fwd_btn.setAccessibleName("Forward 10 Seconds")
        self.fwd_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fwd_btn.clicked.connect(lambda: self.skip(10))
        self.btns_layout.addWidget(self.fwd_btn)

        self.next_btn = QPushButton(">|")
        self.next_btn.setFixedSize(45, 35)
        self.next_btn.setToolTip("Next File in Folder")
        self.next_btn.setAccessibleName("Next File in Folder")
        self.next_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self.play_next_in_folder)
        self.btns_layout.addWidget(self.next_btn)

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
        self.vol_slider.setToolTip("Volume")
        self.vol_slider.setAccessibleName("Volume")
        self.vol_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol_slider.valueChanged.connect(lambda val: self.set_volume(val, show_osd=False))
        self.btns_layout.addWidget(self.vol_slider)

        self.control_layout.addLayout(self.btns_layout)
        self.main_layout.addWidget(self.control_bar)
        self._set_media_controls_enabled(False)

    def _build_menus(self) -> None:
        menu_bar = self.menuBar()

        self.file_menu = menu_bar.addMenu("&File")
        self.open_action = QAction("&Open File...", self)
        self.open_action.setShortcuts(
            QKeySequence.keyBindings(QKeySequence.StandardKey.Open)
        )
        self.open_action.triggered.connect(self.open_file_dialog)
        self.file_menu.addAction(self.open_action)

        self.recent_menu = self.file_menu.addMenu("Open &Recent")

        self.export_action = QAction("Export to MP4 Video...", self)
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(self.export_as_video)
        self.file_menu.addAction(self.export_action)

        if IS_WINDOWS:
            self.file_menu.addSeparator()
            self.default_app_action = QAction("Set as Default App", self)
            self.default_app_action.triggered.connect(self.setup_default_program)
            self.file_menu.addAction(self.default_app_action)

        self.file_menu.addSeparator()
        self.close_window_action = QAction("Close Window", self)
        self.close_window_action.setShortcuts(
            QKeySequence.keyBindings(QKeySequence.StandardKey.Close)
        )
        self.close_window_action.triggered.connect(self.close)
        self.file_menu.addAction(self.close_window_action)

        self.quit_action = QAction("Quit", self)
        self.quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self.quit_action.setShortcuts(
            QKeySequence.keyBindings(QKeySequence.StandardKey.Quit)
        )
        self.quit_action.triggered.connect(self.close)
        self.file_menu.addAction(self.quit_action)

        self.playback_menu = menu_bar.addMenu("&Playback")
        self.play_pause_action = QAction("Play/Pause", self)
        self.play_pause_action.triggered.connect(self.toggle_pause)
        self.playback_menu.addAction(self.play_pause_action)

        self.back_action = QAction("Back 10 Seconds", self)
        self.back_action.triggered.connect(lambda: self.skip(-10))
        self.playback_menu.addAction(self.back_action)

        self.forward_action = QAction("Forward 10 Seconds", self)
        self.forward_action.triggered.connect(lambda: self.skip(10))
        self.playback_menu.addAction(self.forward_action)

        self.playback_menu.addSeparator()
        self.previous_action = QAction("Previous File in Folder", self)
        self.previous_action.triggered.connect(self.play_previous_in_folder)
        self.playback_menu.addAction(self.previous_action)

        self.next_action = QAction("Next File in Folder", self)
        self.next_action.triggered.connect(self.play_next_in_folder)
        self.playback_menu.addAction(self.next_action)

        self.playback_menu.addSeparator()
        self.auto_advance_action = QAction("Autoplay Next in Folder", self)
        self.auto_advance_action.setCheckable(True)
        self.auto_advance_action.setChecked(self._auto_advance_enabled)
        self.auto_advance_action.toggled.connect(self.set_auto_advance_enabled)
        self.playback_menu.addAction(self.auto_advance_action)

        self.playback_menu.addSeparator()
        subtitle_delay_back = QAction("Subtitle 0.1s Later", self)
        subtitle_delay_back.triggered.connect(lambda: self.adjust_sub_delay(0.1))
        self.playback_menu.addAction(subtitle_delay_back)
        subtitle_delay_forward = QAction("Subtitle 0.1s Earlier", self)
        subtitle_delay_forward.triggered.connect(lambda: self.adjust_sub_delay(-0.1))
        self.playback_menu.addAction(subtitle_delay_forward)
        subtitle_smaller = QAction("Smaller Subtitles", self)
        subtitle_smaller.triggered.connect(lambda: self.adjust_sub_scale(-0.1))
        self.playback_menu.addAction(subtitle_smaller)
        subtitle_larger = QAction("Larger Subtitles", self)
        subtitle_larger.triggered.connect(lambda: self.adjust_sub_scale(0.1))
        self.playback_menu.addAction(subtitle_larger)

        self.view_menu = menu_bar.addMenu("&View")
        self.fullscreen_action = QAction("Full Screen", self)
        self.fullscreen_action.setCheckable(True)
        self.fullscreen_action.setShortcuts(
            QKeySequence.keyBindings(QKeySequence.StandardKey.FullScreen)
        )
        self.fullscreen_action.triggered.connect(self.toggle_fullscreen)
        self.view_menu.addAction(self.fullscreen_action)

        self._update_recent_menu()
        self._set_media_controls_enabled(False)
        self.previous_action.setEnabled(False)
        self.next_action.setEnabled(False)

    def _set_media_controls_enabled(self, enabled: bool) -> None:
        for control in (self.seek_slider, self.back_btn, self.play_btn, self.fwd_btn):
            control.setEnabled(enabled)
        for action_name in ("play_pause_action", "back_action", "forward_action"):
            action = getattr(self, action_name, None)
            if action is not None:
                action.setEnabled(enabled)

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
            print(f"MPV initialization error: {e}")
            if self._interactive_errors:
                _ = QMessageBox.critical(
                    self,
                    "Library Load Error",
                    "Could not initialize the mpv media engine.\n\n" + detail,
                )
                sys.exit(1)
            raise RuntimeError(f"Could not initialize mpv. {detail}") from e

    def has_video(self):
        return bool(self.current_media_path)

    def _setting_key_for_path(self, path: str) -> str:
        return "positions/" + hashlib.sha256(os.path.normcase(path).encode("utf-8")).hexdigest()

    def _clear_saved_position(self, path: str) -> None:
        self.settings.remove(self._setting_key_for_path(path))

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
        elif duration > 0 and pos >= duration - 5:
            self._clear_saved_position(str(self.current_media_path))

    def _maybe_resume(self, path, attempts_remaining: int = 50):
        if getattr(self, "_is_resuming", False):
            return
        try:
            if not self.player or not self.current_media_path or path != self.current_media_path:
                return
            saved = float(str(self.settings.value(self._setting_key_for_path(path), 0) or 0))
            if saved < RESUME_THRESHOLD_SECONDS:
                return

            duration = self.player.duration
            if duration is None or duration <= 0:
                if attempts_remaining > 0:
                    QTimer.singleShot(
                        100,
                        self,
                        lambda: self._maybe_resume(path, attempts_remaining - 1),
                    )
                return

            # The file may have been replaced with a shorter one at the same
            # path. Never seek to (or beyond) its EOF using a stale path-only
            # resume entry, as that can immediately trigger auto-advance.
            if saved >= float(duration) - 5:
                self._clear_saved_position(path)
                return

            self._is_resuming = True
            self.player.pause = True
            dialog = QMessageBox(self)
            dialog.setIcon(QMessageBox.Icon.Question)
            dialog.setWindowTitle("Resume Playback")
            dialog.setText("Continue from where you left off?")
            dialog.setInformativeText(f"Saved position: {format_time(saved)}")
            resume_button = dialog.addButton("YES", QMessageBox.ButtonRole.AcceptRole)
            dialog.addButton("NO", QMessageBox.ButtonRole.RejectRole)
            dialog.setDefaultButton(resume_button)
            dialog.exec()
            # The dialog above is modal but still re-enters the Qt event loop,
            # so another load_video() call (drag-drop, recent file, double-open)
            # may have swapped in a different file while we were waiting for
            # the user's answer. If that happened, applying the saved position
            # or restoring pause state now would corrupt playback of the new
            # file, so bail out instead.
            if self.current_media_path != path:
                return
            if dialog.clickedButton() is resume_button:
                self.player.time_pos = saved
                self.player.pause = False
                self.media_ended = False
            else:
                self._clear_saved_position(path)
                self.player.time_pos = 0
                self.player.pause = False
                self.media_ended = False
        except Exception as e:
            print(f"Error in resume playback check: {e}")
        finally:
            self._is_resuming = False

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
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        recent_files = self._recent_files()
        if not recent_files:
            empty_action = self.recent_menu.addAction("No Recent Files")
            empty_action.setEnabled(False)
            return

        for path in recent_files:
            action = QAction(os.path.basename(path), self.recent_menu)
            action.setToolTip(path)
            action.triggered.connect(
                lambda checked=False, p=path: QTimer.singleShot(
                    100, self, lambda: self.load_video(p)
                )
            )
            self.recent_menu.addAction(action)
            self.recent_actions.append(action)

        self.recent_menu.addSeparator()
        clear_action = QAction("Clear Recent Files", self.recent_menu)
        clear_action.triggered.connect(self.clear_recent_files)
        self.recent_menu.addAction(clear_action)

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

    def _cleanup_export_temp_paths(self) -> None:
        self._cleanup_paths(list(self.export_temp_paths))
        self.export_temp_paths.clear()

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

            if not self.current_media_path:
                self.media_ended = False
                self._set_media_controls_enabled(False)
                if hasattr(self, "export_action"):
                    self.export_action.setEnabled(False)
                self.seek_slider.setRange(0, 0)
                self.time_label.setText("00:00 / 00:00")
                if self.play_btn.text() != "Play":
                    self.play_btn.setText("Play")
                return

            if self.media_stack.currentWidget() == self.video_container:
                tracks = getattr(self.player, "track_list", None)
                if tracks:
                    has_vid = any(t.get("type") == "video" for t in tracks)
                    if not has_vid:
                        try:
                            self.player.vid = "no"
                        except Exception:
                            pass
                        image_path = find_matching_image(self.current_media_path)
                        self._set_audio_image(image_path)
                        self._audio_subtitle_on = bool(find_matching_subtitle(self.current_media_path))
                        self.audio_sub_label.setText("")
                        self.audio_sub_label.setVisible(False)
                        self.media_stack.setCurrentWidget(self.audio_label)
                        self._reposition_audio_subtitle()

            if self._audio_subtitle_on:
                text = self.player.sub_text or ""
                if self.audio_sub_label.text() != text:
                    self.audio_sub_label.setText(text)
                    self.audio_sub_label.setVisible(bool(text.strip()))

            try:
                time_pos = self.player.time_pos
                duration = self.player.duration
                is_paused = bool(self.player.pause)
                idle_active = bool(getattr(self.player, "idle_active", False))
                eof_reached = bool(getattr(self.player, "eof_reached", False))
            except (AttributeError, mpv.ShutdownError):
                return

            if duration is not None and duration > 0:
                self.last_duration = int(duration)

            if duration is not None and duration > 0:
                if (eof_reached or (idle_active and time_pos is None)):
                    self.media_ended = True
                    if self.current_media_path:
                        self._clear_saved_position(self.current_media_path)
                    self.seek_slider.setMaximum(self.last_duration)
                    self.seek_slider.setValue(self.last_duration)
                    self.time_label.setText(f"{format_time(self.last_duration)} / {format_time(self.last_duration)}")
                    if self.play_btn.text() != "Play":
                        self.play_btn.setText("Play")
                    if self._eof_armed:
                        self._eof_armed = False
                        self._request_auto_advance()
                    return

            if time_pos is not None:
                self.media_ended = False
                if not eof_reached and self.current_media_path:
                    self._eof_armed = True
                curr = int(time_pos)
                total = self.last_duration if self.last_duration > 0 else int(duration or 0)
                
                if total > 0:
                    curr = min(curr, total)
                
                self.last_time_pos = curr
                self.seek_slider.setMaximum(total)
                if not self.seek_slider.isSliderDown():
                    self.seek_slider.setValue(curr)
                self.time_label.setText(f"{format_time(curr)} / {format_time(total)}")

            if self.media_ended:
                play_text = "Play"
            else:
                play_text = "Play" if is_paused else "Pause"

            if self.play_btn.text() != play_text:
                self.play_btn.setText(play_text)

        except mpv.ShutdownError as e:
            print(f"Error in update_status: {e}")
            if hasattr(self, "timer"):
                try:
                    self.timer.stop()
                except Exception:
                    pass
        except Exception as e:
            print(f"Error in update_status: {e}")

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
            QTimer.singleShot(100, self, lambda: self.load_video(file_path))

    def load_video(self, path, ask_resume: bool = True):
        """파일을 로드해 재생합니다.

        ask_resume=False는 폴더 순차 이동(자동 넘김, 이전/다음 버튼)에서 사용합니다.
        연속 재생 중에 모달 이어보기 대화상자가 뜨면 재생이 멈춰버리기 때문입니다.
        """
        if not self.player:
            return
        if getattr(self, "_is_loading", False):
            return
        self._is_loading = True
        try:
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
            self._eof_armed = False
            self.last_time_pos = 0
            self.last_duration = 0

            sub_path = find_matching_subtitle(self.current_media_path)
            is_audio = is_supported_audio(self.current_media_path)
            image_path = find_matching_image(self.current_media_path) if is_audio else None

            self.setWindowTitle(
                f"{os.path.basename(self.current_media_path)} — {APP_DISPLAY_NAME}"
            )
            self._remember_recent_file(self.current_media_path)

            if is_audio:
                try:
                    self.player.vid = "no"
                except Exception:
                    pass
                self._set_audio_image(image_path)
                self._audio_subtitle_on = bool(sub_path)
                self.audio_sub_label.setText("")
                self.audio_sub_label.setVisible(False)
                self.media_stack.setCurrentWidget(self.audio_label)
                QTimer.singleShot(50, self, self._reposition_audio_subtitle)
            else:
                try:
                    self.player.vid = "auto"
                except Exception:
                    pass
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

            try:
                if player_sub_path:
                    self.player.loadfile(self.current_media_path, sub_file=player_sub_path)
                else:
                    self.player.loadfile(self.current_media_path)
            except Exception as e:
                print(f"Error loading file into mpv: {e}")
                self.current_media_path = None
                self._audio_subtitle_on = False
                self.setWindowTitle(APP_DISPLAY_NAME)
                self._set_media_controls_enabled(False)
                self.export_action.setEnabled(False)
                self.seek_slider.setRange(0, 0)
                self.time_label.setText("00:00 / 00:00")
                _ = QMessageBox.critical(
                    self,
                    "Playback Error",
                    f"Failed to load the media file into the player.\n\nDetails: {e}",
                )
                return

            self._set_media_controls_enabled(True)
            self.export_action.setEnabled(is_audio)
            self.player.pause = False
            if self.video_container:
                self.video_container.update()
            self.setFocus()

            QTimer.singleShot(1000, self, lambda: self._cleanup_paths(old_paths))
            if ask_resume:
                QTimer.singleShot(500, self, lambda path=self.current_media_path: self._maybe_resume(path))
        finally:
            self._is_loading = False
            self._update_nav_buttons()

    def _update_nav_buttons(self) -> None:
        prev_path = next_path = None
        if self.current_media_path:
            try:
                prev_path, next_path = find_adjacent_media_in_folder(self.current_media_path)
            except Exception as e:
                print(f"Error scanning the folder for adjacent files: {e}")
        self.prev_btn.setEnabled(prev_path is not None)
        self.next_btn.setEnabled(next_path is not None)
        if hasattr(self, "previous_action"):
            self.previous_action.setEnabled(prev_path is not None)
            self.next_action.setEnabled(next_path is not None)

    def play_previous_in_folder(self) -> None:
        self._play_sibling(find_previous_media_in_folder)

    def play_next_in_folder(self) -> None:
        self._play_sibling(find_next_media_in_folder)

    def _play_sibling(self, finder) -> None:
        """폴더 내 이웃 파일로 이동합니다(수동 조작이므로 자동 넘김 설정과 무관).

        버튼 활성화 상태는 로드 시점 기준이라 재생 중 폴더가 바뀌었을 수 있어,
        클릭 시점에 다시 스캔합니다.
        """
        if not self.current_media_path:
            return
        try:
            target = finder(self.current_media_path)
        except Exception as e:
            print(f"Error finding the adjacent media file: {e}")
            return
        if not target:
            self._update_nav_buttons()
            return
        self.load_video(target, ask_resume=False)

    def set_auto_advance_enabled(self, enabled: bool) -> None:
        self._auto_advance_enabled = bool(enabled)
        self.settings.setValue("autoAdvance", self._auto_advance_enabled)
        action = getattr(self, "auto_advance_action", None)
        if action is not None and action.isChecked() != self._auto_advance_enabled:
            action.blockSignals(True)
            action.setChecked(self._auto_advance_enabled)
            action.blockSignals(False)

    def _request_auto_advance(self) -> None:
        """재생이 끝나면 같은 폴더의 다음 파일을 예약합니다.

        update_status()는 100ms 타이머 슬롯이고 load_video()는 모달 대화상자를
        띄울 수 있으므로, 실제 로드는 singleShot(0)으로 현재 슬롯 밖에서 실행합니다.
        """
        if not self._auto_advance_enabled:
            return
        if getattr(self, "_is_loading", False) or getattr(self, "_is_resuming", False):
            return
        current = self.current_media_path
        if not current:
            return
        try:
            next_path = find_next_media_in_folder(current)
        except Exception as e:
            print(f"Error finding the next media file: {e}")
            return
        if not next_path:
            return
        QTimer.singleShot(0, self, lambda: self._play_next_if_unchanged(current, next_path))

    def _play_next_if_unchanged(self, expected_path: str, next_path: str) -> None:
        # 예약과 실행 사이에 사용자가 다른 파일을 열었거나 다시 재생을 시작했다면
        # 자동 넘김을 포기합니다.
        if self.current_media_path != expected_path or not self.media_ended:
            return
        self.load_video(next_path, ask_resume=False)

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

    def _init_fade_animations(self) -> None:
        """Set up the fullscreen control-bar fade animation."""
        self._control_opacity_effect = QGraphicsOpacityEffect(self.control_bar)
        self._control_opacity_effect.setOpacity(1.0)
        self.control_bar.setGraphicsEffect(self._control_opacity_effect)

        self._control_fade_anim = QPropertyAnimation(self._control_opacity_effect, b"opacity", self)
        self._control_fade_anim.setDuration(210)
        self._control_fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._control_fade_anim.finished.connect(
            lambda: self._on_fade_finished(self.control_bar, self._control_opacity_effect)
        )

    def _on_fade_finished(self, widget, effect) -> None:
        # `finished` fires for both fade-in and fade-out; only hide the
        # widget if the animation actually settled at (near) zero opacity.
        if effect.opacity() <= 0.01:
            widget.hide()

    def _fade_widget_in(self, widget, effect, anim) -> None:
        anim.stop()
        if not widget.isVisible():
            effect.setOpacity(0.0)
            widget.show()
        anim.setStartValue(effect.opacity())
        anim.setEndValue(1.0)
        anim.start()

    def _fade_widget_out(self, widget, effect, anim) -> None:
        if not widget.isVisible():
            return
        anim.stop()
        anim.setStartValue(effect.opacity())
        anim.setEndValue(0.0)
        anim.start()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if child in (self.video_container, self.audio_label, self.media_stack):
                self.toggle_fullscreen()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def toggle_fullscreen(self, _checked: bool = False) -> None:
        self._set_fullscreen(not self.isFullScreen())

    def _set_fullscreen(self, enabled: bool) -> None:
        if enabled == self.isFullScreen():
            self._sync_fullscreen_ui()
            return
        if enabled:
            self._was_maximized_before_fullscreen = self.isMaximized()
            self.showFullScreen()
            self._sync_fullscreen_ui()
            self.handle_mouse_activity()
            return

        if getattr(self, "_was_maximized_before_fullscreen", False):
            self.showMaximized()
        else:
            self.showNormal()
        self._sync_fullscreen_ui()

    def _sync_fullscreen_ui(self) -> None:
        fullscreen = self.isFullScreen()
        action = getattr(self, "fullscreen_action", None)
        if action is not None and action.isChecked() != fullscreen:
            action.blockSignals(True)
            action.setChecked(fullscreen)
            action.blockSignals(False)

        menu_bar = self.menuBar()
        if fullscreen and not menu_bar.isNativeMenuBar():
            menu_bar.hide()
        elif not fullscreen:
            menu_bar.show()
            self._control_fade_anim.stop()
            self._control_opacity_effect.setOpacity(1.0)
            self.control_bar.show()
            self.unsetCursor()
            self.mouse_timer.stop()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self, self._sync_fullscreen_ui)

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
            self._fade_widget_in(self.control_bar, self._control_opacity_effect, self._control_fade_anim)
            self.mouse_timer.start()

    def _hide_controls_on_timeout(self) -> None:
        if self.isFullScreen():
            pos = self.control_bar.mapFromGlobal(self.cursor().pos())
            if self.control_bar.rect().contains(pos):
                self.mouse_timer.start()
                return
            self._fade_widget_out(self.control_bar, self._control_opacity_effect, self._control_fade_anim)
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
        elif key == Qt.Key.Key_PageUp:
            self.play_previous_in_folder()
        elif key == Qt.Key.Key_PageDown:
            self.play_next_in_folder()
        elif key == Qt.Key.Key_Up:
            self.set_volume(self.vol_slider.value() + 5, show_osd=True)
        elif key == Qt.Key.Key_Down:
            self.set_volume(self.vol_slider.value() - 5, show_osd=True)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.toggle_fullscreen()
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
                self._set_fullscreen(False)
            else:
                self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "timer"):
            self.timer.stop()
        if hasattr(self, "mouse_timer"):
            self.mouse_timer.stop()
        self._save_current_position()
        self.settings.setValue("volume", self.vol_slider.value())

        if hasattr(self, "export_process") and self.export_process and self.export_process.state() != QProcess.ProcessState.NotRunning:
            self._closing = True
            self.export_cancelled = True
            self.export_process.kill()
            self.export_process.waitForFinished(3000)

        if self.video_container and isinstance(self.video_container, MpvGLWidget):
            try:
                self.video_container.shutdown()
            except Exception:
                pass

        if hasattr(self, "player") and self.player:
            try:
                self.player.terminate()
            except Exception:
                pass

        self._cleanup_converted_subtitles()
        self._cleanup_export_temp_paths()
        for path in list(self.temp_files_to_clean):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
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

        auto_advance_action = QAction("Autoplay Next in Folder", self)
        auto_advance_action.setCheckable(True)
        auto_advance_action.setChecked(self._auto_advance_enabled)
        auto_advance_action.toggled.connect(self.set_auto_advance_enabled)
        menu.addAction(auto_advance_action)

        # WAV/Audio to Video Export Option
        if self.current_media_path and is_supported_audio(self.current_media_path):
            export_action = QAction("Export to MP4 Video...", self)
            export_action.triggered.connect(self.export_as_video)
            menu.addAction(export_action)

        recent_files = self._recent_files()
        if recent_files:
            recent_menu = menu.addMenu("Recent Files")
            for path in recent_files:
                action = QAction(os.path.basename(path), self)
                action.setToolTip(path)
                action.triggered.connect(lambda checked=False, p=path: QTimer.singleShot(100, self, lambda: self.load_video(p)))
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

    def export_as_video(self):
        if not self.current_media_path or not is_supported_audio(self.current_media_path):
            return

        if hasattr(self, "export_process") and self.export_process and self.export_process.state() != QProcess.ProcessState.NotRunning:
            _ = QMessageBox.information(
                self,
                "Export In Progress",
                "An export is already running. Please wait for it to finish or cancel it first.",
            )
            return

        self._cleanup_export_temp_paths()

        # 1. Verify FFmpeg installation
        ffmpeg_path = self._find_ffmpeg()
        if not ffmpeg_path:
            _ = QMessageBox.critical(
                self,
                "FFmpeg Required",
                "FFmpeg media utility is required to export videos.\n\n"
                "Please install FFmpeg and add it to your system PATH."
            )
            return

        # 2. Get Cover Image
        image_path = find_matching_image(self.current_media_path)
        if not image_path:
            _ = QMessageBox.information(
                self,
                "No Cover Image Found",
                "No matching cover image was automatically found for this audio.\n\n"
                "Please select an image file to use as the video background."
            )
            image_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select Cover Image",
                "",
                "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
            )
            if not image_path:
                return

        # 3. Get Output path
        base_name, _ = os.path.splitext(os.path.basename(self.current_media_path))
        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Video",
            os.path.join(os.path.dirname(self.current_media_path), f"{base_name}.mp4"),
            "MP4 Video (*.mp4)"
        )
        if not output_path:
            return

        # 4. Check for subtitles
        sub_path = find_matching_subtitle(self.current_media_path)
        if not sub_path:
            subtitle_prompt = QMessageBox(self)
            subtitle_prompt.setIcon(QMessageBox.Icon.Question)
            subtitle_prompt.setWindowTitle("No Subtitle Found")
            subtitle_prompt.setText("No matching subtitle was found for this audio file.")
            subtitle_prompt.setInformativeText("Select a subtitle to burn in, or continue without subtitles.")
            select_subtitle_button = subtitle_prompt.addButton(
                "Select Subtitle...", QMessageBox.ButtonRole.ActionRole
            )
            without_subtitle_button = subtitle_prompt.addButton(
                "Continue Without", QMessageBox.ButtonRole.AcceptRole
            )
            subtitle_prompt.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
            subtitle_prompt.setDefaultButton(without_subtitle_button)
            subtitle_prompt.exec()
            clicked_button = subtitle_prompt.clickedButton()
            if clicked_button not in (select_subtitle_button, without_subtitle_button):
                return
            if clicked_button is select_subtitle_button:
                sub_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select Subtitle",
                    os.path.dirname(self.current_media_path),
                    "Subtitle Files (*.srt *.ass *.vtt *.smi);;All Files (*)",
                )
                if not sub_path:
                    return

        if sub_path and not self._ffmpeg_has_filter(ffmpeg_path, "subtitles"):
            _ = QMessageBox.critical(
                self,
                "FFmpeg Subtitle Support Required",
                "The installed FFmpeg does not include the subtitles filter required to burn subtitles.\n\n"
                "macOS: install the full build with 'brew install ffmpeg-full'.\n"
                "Windows: install a full FFmpeg build that includes libass.",
            )
            return

        # 5. Build FFmpeg command arguments
        args = ["-y"]
        # -loop is specific to image2 and fails for GIF covers. Repeating the
        # complete input works for both still images and animated GIFs.
        args += ["-stream_loop", "-1", "-i", image_path]
        args += ["-i", self.current_media_path]

        vf_filters = ["scale=trunc(iw/2)*2:trunc(ih/2)*2"]
        if sub_path:
            srt_path = self._subtitle_path_for_player(sub_path)
            if srt_path != sub_path:
                self.converted_subtitle_paths.remove(srt_path)
                self.export_temp_paths.add(srt_path)
            escaped_sub = self._escape_ffmpeg_path(srt_path)
            vf_filters.append(f"subtitles=filename='{escaped_sub}'")

        if vf_filters:
            args += ["-vf", ",".join(vf_filters)]

        args += ["-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p"]
        args += ["-c:a", "aac", "-b:a", "192k"]
        args += ["-shortest"]
        args += ["-progress", "pipe:1"]

        try:
            export_work_path = self._create_export_work_path(output_path)
        except OSError as e:
            _ = QMessageBox.critical(
                self,
                "Export Path Error",
                f"Could not create a temporary output next to the selected file.\n\nDetails: {e}",
            )
            self._cleanup_export_temp_paths()
            return
        self._export_output_path = output_path
        self._export_work_path = export_work_path
        self.export_temp_paths.add(export_work_path)
        args += [export_work_path]

        # 6. Initialize progress dialog
        self.export_dialog = QProgressDialog(
            "Encoding audio, cover, and subtitles to MP4...",
            "Cancel",
            0,
            100,
            self
        )
        self.export_dialog.setWindowTitle("Exporting Video")
        self.export_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.export_dialog.canceled.connect(self._cancel_export)
        self.export_dialog.show()

        # 7. Start QProcess
        # 진행률 기준 길이는 시작 시점에 고정합니다. 내보내는 동안 자동 넘김이나
        # 드래그 앤 드롭으로 다른 파일이 로드되면 self.last_duration이 바뀌기 때문입니다.
        self._export_total_seconds = self.last_duration
        self.export_cancelled = False
        self.export_process = QProcess(self)
        self.export_process.readyReadStandardOutput.connect(self._handle_export_progress)
        self.export_process.errorOccurred.connect(self._handle_export_error)
        self.export_process.finished.connect(self._handle_export_finished)
        self.export_process.start(ffmpeg_path, args)

    @staticmethod
    def _create_export_work_path(output_path: str) -> str:
        """Create an atomic-export staging path beside the requested output."""
        output_path = os.path.abspath(output_path)
        output_dir = os.path.dirname(output_path)
        stem = os.path.splitext(os.path.basename(output_path))[0] or "export"
        handle = tempfile.NamedTemporaryFile(
            prefix=f".{stem}-",
            suffix=".tmp.mp4",
            dir=output_dir,
            delete=False,
        )
        handle.close()
        return handle.name

    def _find_ffmpeg(self) -> str | None:
        candidates: list[str] = []
        if IS_MAC:
            brew_candidates = [
                shutil.which("brew"),
                "/opt/homebrew/bin/brew",
                "/usr/local/bin/brew",
                os.path.expanduser("~/.homebrew/bin/brew"),
            ]
            brew = next(
                (path for path in brew_candidates if path and os.path.isfile(path) and os.access(path, os.X_OK)),
                None,
            )
            if brew:
                try:
                    prefix = subprocess.check_output(
                        [brew, "--prefix", "ffmpeg-full"],
                        text=True,
                        stderr=subprocess.DEVNULL,
                    ).strip()
                    candidates.append(os.path.join(prefix, "bin", "ffmpeg"))
                except (OSError, subprocess.CalledProcessError):
                    pass
            candidates.extend(
                [
                    "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
                    "/usr/local/opt/ffmpeg-full/bin/ffmpeg",
                    os.path.expanduser("~/.homebrew/opt/ffmpeg-full/bin/ffmpeg"),
                    "/opt/homebrew/bin/ffmpeg",
                    "/usr/local/bin/ffmpeg",
                    os.path.expanduser("~/.homebrew/bin/ffmpeg"),
                ]
            )
        system_ffmpeg = shutil.which("ffmpeg")
        if system_ffmpeg:
            candidates.append(system_ffmpeg)
        return next((path for path in candidates if os.path.isfile(path) and os.access(path, os.X_OK)), None)

    def _ffmpeg_has_filter(self, ffmpeg_path: str, filter_name: str) -> bool:
        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-filters"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return any(
            len(parts) >= 2 and parts[1] == filter_name
            for line in result.stdout.splitlines()
            if (parts := line.split())
        )

    def _escape_ffmpeg_path(self, path: str) -> str:
        path = path.replace("\\", "/")
        path = path.replace(":", "\\:")
        path = path.replace(",", "\\,")
        path = path.replace("'", "'\\\\\\''")
        return path

    def _cancel_export(self):
        self.export_cancelled = True
        if hasattr(self, "export_process") and self.export_process and self.export_process.state() == QProcess.ProcessState.Running:
            self.export_process.kill()

    def _handle_export_progress(self):
        data = self.export_process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.startswith("out_time_us="):
                try:
                    us = int(line.split("=")[1])
                    current_sec = us / 1000000.0
                    total = getattr(self, "_export_total_seconds", 0) or self.last_duration
                    if total > 0:
                        pct = min(100, max(0, int((current_sec / total) * 100)))
                        self.export_dialog.setValue(pct)
                except ValueError:
                    pass

    def _handle_export_finished(self, exit_code, exit_status):
        if getattr(self, "_closing", False):
            self._cleanup_export_temp_paths()
            return
        self.export_dialog.close()
        if self.export_cancelled:
            self._cleanup_export_temp_paths()
            _ = QMessageBox.information(self, "Export Cancelled", "Video export was cancelled by the user.")
            return

        if getattr(self, "_export_error_shown", False):
            self._export_error_shown = False
            self._cleanup_export_temp_paths()
            return

        if exit_status == QProcess.ExitStatus.NormalExit and exit_code == 0:
            work_path = getattr(self, "_export_work_path", "")
            output_path = getattr(self, "_export_output_path", "")
            try:
                os.replace(work_path, output_path)
                self.export_temp_paths.discard(work_path)
            except OSError as e:
                self._cleanup_export_temp_paths()
                _ = QMessageBox.critical(
                    self,
                    "Export Failed",
                    f"The video was encoded, but could not replace the selected output file.\n\nDetails: {e}",
                )
                return
            self._cleanup_export_temp_paths()
            _ = QMessageBox.information(self, "Export Complete", "Video exported successfully!")
        else:
            err = self.export_process.readAllStandardError().data().decode("utf-8", errors="replace")
            self._cleanup_export_temp_paths()
            _ = QMessageBox.critical(
                self,
                "Export Failed",
                f"An error occurred during video export.\n\nDetails:\n{err[:500]}"
            )

    def _handle_export_error(self, error):
        if getattr(self, "_closing", False):
            self._cleanup_export_temp_paths()
            return
        if hasattr(self, "export_dialog") and self.export_dialog.wasCanceled():
            return
        if hasattr(self, "export_dialog"):
            self.export_dialog.close()
        self._cleanup_export_temp_paths()

        error_msgs = {
            QProcess.ProcessError.FailedToStart: "FFmpeg executable not found. Make sure ffmpeg is in your system PATH.",
            QProcess.ProcessError.Crashed: "FFmpeg crashed during execution.",
            QProcess.ProcessError.Timedout: "FFmpeg operation timed out.",
            QProcess.ProcessError.WriteError: "An error occurred writing to FFmpeg.",
            QProcess.ProcessError.ReadError: "An error occurred reading from FFmpeg.",
            QProcess.ProcessError.UnknownError: "An unknown process error occurred."
        }
        msg = error_msgs.get(error, "An error occurred running FFmpeg.")
        self._export_error_shown = True
        _ = QMessageBox.critical(self, "Export Error", msg)
