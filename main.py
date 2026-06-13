import sys
import os
import urllib.request
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QPushButton, QHBoxLayout, QSlider, QLabel, QFrame,
                             QFileDialog, QMessageBox, QProgressDialog, QMenu)
from PySide6.QtCore import Qt, QTimer, QPoint, QSize
from PySide6.QtGui import QColor, QPalette, QIcon, QAction

# Portable path configuration
if getattr(sys, 'frozen', False):
    base_dir = os.path.dirname(sys.executable)
else:
    base_dir = os.path.dirname(os.path.abspath(__file__))

# Add executable directory to PATH so mpv-1.dll can be loaded if present
os.environ["PATH"] = base_dir + os.pathsep + os.environ["PATH"]

def check_and_download_mpv():
    dll_path = os.path.join(base_dir, "mpv-1.dll")
    if os.path.exists(dll_path):
        return

    app = QApplication.instance() or QApplication(sys.argv)
    
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("Download Required")
    msg.setText("Download required file (mpv-1.dll, ~118MB) for first run.\nDo you want to continue?")
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    if msg.exec() != QMessageBox.Yes:
        sys.exit(0)

    progress = QProgressDialog("Downloading mpv-1.dll...", "Cancel", 0, 100)
    progress.setWindowTitle("Download Progress")
    progress.setWindowModality(Qt.WindowModal)
    progress.resize(400, 100)
    progress.show()

    def report(blocknum, blocksize, totalsize):
        readsofar = blocknum * blocksize
        if totalsize > 0:
            percent = int(readsofar * 100 / totalsize)
            progress.setValue(percent)
            QApplication.processEvents()
        if progress.wasCanceled():
            raise Exception("Download canceled.")

    url = "https://github.com/YuHyungmin1226/MinimalPlayer/releases/download/v1.0/mpv-1.dll"
    try:
        urllib.request.urlretrieve(url, dll_path, report)
    except Exception as e:
        QMessageBox.critical(None, "Download Failed", f"An error occurred during download:\n{e}\n\nPlease download it manually from the GitHub Release page and place it in the same directory.")
        if os.path.exists(dll_path):
            os.remove(dll_path)
        sys.exit(1)
    
    progress.setValue(100)

check_and_download_mpv()

def register_file_associations(silent=False):
    """
    Register MinimalPlayer to Windows registry for file associations under HKCU.
    """
    if os.name != 'nt':
        return False

    import winreg
    import ctypes

    # 실행 경로 가져오기
    if getattr(sys, 'frozen', False):
        exe_path = os.path.abspath(sys.executable)
        cmd = f'"{exe_path}" "%1"'
    else:
        python_exe = os.path.abspath(sys.executable)
        script_path = os.path.abspath(sys.argv[0])
        cmd = f'"{python_exe}" "{script_path}" "%1"'
        exe_path = python_exe

    prog_id = "MinimalPlayer"
    app_name = "Minimal Portable Player"
    
    try:
        # 1. HKCU\Software\Classes\MinimalPlayer 등록
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, app_name)
            
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\shell\open\command") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, cmd)
            
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{prog_id}\DefaultIcon") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f"{exe_path},0")

        # 2. Capabilities 등록 (Default Apps 설정 페이지에 노출하기 위해 필요)
        capabilities_path = rf"Software\{prog_id}\Capabilities"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, capabilities_path) as key:
            winreg.SetValueEx(key, "ApplicationName", 0, winreg.REG_SZ, "MinimalPlayer")
            winreg.SetValueEx(key, "ApplicationDescription", 0, winreg.REG_SZ, "Lightweight Minimal Video Player")
            
        # 지원할 확장자 목록
        extensions = [
            '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', 
            '.3gp', '.mpeg', '.mpg', '.ts', '.tp', '.asf', '.m4v'
        ]
        
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{capabilities_path}\FileAssociations") as key:
            for ext in extensions:
                winreg.SetValueEx(key, ext, 0, winreg.REG_SZ, prog_id)
                
        # HKCU\Software\RegisteredApplications에 등록
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\RegisteredApplications") as key:
            winreg.SetValueEx(key, "MinimalPlayer", 0, winreg.REG_SZ, capabilities_path)
            
        # 3. 각 확장자의 OpenWithProgids에 MinimalPlayer를 빈 값으로 매핑
        for ext in extensions:
            assoc_path = rf"Software\Classes\{ext}\OpenWithProgids"
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, assoc_path) as key:
                winreg.SetValueEx(key, prog_id, 0, winreg.REG_NONE, b"")
                
        # Send Shell notification to update file associations immediately
        try:
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None) # SHCNE_ASSOCCHANGED
        except Exception as shell_err:
            if not silent:
                print(f"Failed to send Shell notification: {shell_err}")
                
        return True
    except Exception as e:
        if not silent:
            print(f"Registry registration failed: {e}")
        return False

import mpv

# Modern Dark Theme QSS
STYLE = """
QMainWindow {
    background-color: #121212;
}
#VideoContainer {
    background-color: #000000;
}
#TitleBar {
    background-color: #1e1e1e;
    border-bottom: 1px solid #333;
}
#ControlBar {
    background-color: rgba(30, 30, 30, 220);
    border-top: 1px solid #333;
}
QPushButton {
    background: transparent;
    color: #eee;
    border: none;
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 14px;
    padding: 5px;
    outline: none;
}
QPushButton:hover {
    background-color: rgba(255, 255, 255, 0.1);
}
QPushButton:pressed {
    background-color: rgba(255, 255, 255, 0.2);
}
QPushButton:focus {
    background: transparent;
}
QSlider::groove:horizontal {
    border: 1px solid #444;
    height: 4px;
    background: #222;
    margin: 2px 0;
}
QSlider::handle:horizontal {
    background: #888;
    border: 1px solid #888;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QLabel {
    color: #aaa;
    font-size: 12px;
}
#TitleLabel {
    color: #eee;
    font-weight: bold;
}
QMenu {
    background-color: #1e1e1e;
    color: #eee;
    border: 1px solid #333;
}
QMenu::item {
    background-color: transparent;
    padding: 6px 20px;
}
QMenu::item:selected {
    background-color: rgba(255, 255, 255, 0.1);
}
QMenu::separator {
    height: 1px;
    background: #333;
    margin: 4px 0;
}
"""

# Custom Slider to support jump-to-click
class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Move slider handle directly to clicked position
            new_value = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
            self.setValue(int(new_value))
            self.sliderMoved.emit(int(new_value))
        super().mousePressEvent(event)

class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        # Set frameless window for minimal design
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1000, 600)
        self.setStyleSheet(STYLE)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Custom titlebar
        self.title_bar = QFrame()
        self.title_bar.setObjectName("TitleBar")
        self.title_bar.setFixedHeight(35)
        self.title_bar_layout = QHBoxLayout(self.title_bar)
        self.title_bar_layout.setContentsMargins(15, 0, 0, 0)
        
        self.title_label = QLabel("Minimal Portable Player")
        self.title_label.setObjectName("TitleLabel")
        self.title_bar_layout.addWidget(self.title_label)
        self.title_bar_layout.addStretch()

        self.min_btn = QPushButton("-")
        self.min_btn.setFixedSize(40, 35)
        self.min_btn.setFocusPolicy(Qt.NoFocus)
        self.min_btn.clicked.connect(self.showMinimized)
        
        self.close_btn = QPushButton("x")
        self.close_btn.setFixedSize(40, 35)
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("QPushButton:hover { background-color: #e81123; color: white; }")

        self.title_bar_layout.addWidget(self.min_btn)
        self.title_bar_layout.addWidget(self.close_btn)
        
        self.main_layout.addWidget(self.title_bar)

        # Video output container
        self.video_container = QWidget()
        self.video_container.setObjectName("VideoContainer")
        self.video_container.setAttribute(Qt.WA_NativeWindow)
        self.main_layout.addWidget(self.video_container, 1)

        # Bottom control bar
        self.control_bar = QFrame()
        self.control_bar.setObjectName("ControlBar")
        self.control_bar.setFixedHeight(70)
        self.control_layout = QVBoxLayout(self.control_bar)
        self.control_layout.setContentsMargins(15, 5, 15, 10)

        # Seek Slider - Custom slider
        self.seek_slider = ClickableSlider(Qt.Horizontal)
        self.seek_slider.setCursor(Qt.PointingHandCursor)
        self.seek_slider.setFocusPolicy(Qt.NoFocus)
        self.seek_slider.sliderMoved.connect(self.seek)
        self.control_layout.addWidget(self.seek_slider)

        # Bottom buttons layout
        self.btns_layout = QHBoxLayout()
        self.btns_layout.setSpacing(10)
        self.btns_layout.setAlignment(Qt.AlignVCenter)
        
        # Add file open button
        self.open_btn = QPushButton("Open")
        self.open_btn.setFixedSize(45, 35)
        self.open_btn.setToolTip("Open File")
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.clicked.connect(self.open_file_dialog)
        self.btns_layout.addWidget(self.open_btn)

        # Seek back button (10s)
        self.back_btn = QPushButton("<<")
        self.back_btn.setFixedSize(45, 35)
        self.back_btn.setFocusPolicy(Qt.NoFocus)
        self.back_btn.clicked.connect(lambda: self.skip(-10))
        self.btns_layout.addWidget(self.back_btn)

        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedSize(60, 35)
        self.play_btn.setFocusPolicy(Qt.NoFocus)
        self.play_btn.clicked.connect(self.toggle_pause)
        self.btns_layout.addWidget(self.play_btn)

        # Seek forward button (10s)
        self.fwd_btn = QPushButton(">>")
        self.fwd_btn.setFixedSize(45, 35)
        self.fwd_btn.setFocusPolicy(Qt.NoFocus)
        self.fwd_btn.clicked.connect(lambda: self.skip(10))
        self.btns_layout.addWidget(self.fwd_btn)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedHeight(35) # Same height as buttons
        self.time_label.setAlignment(Qt.AlignCenter) # Align center
        self.btns_layout.addWidget(self.time_label)
        self.btns_layout.addStretch()

        # Volume control
        self.vol_label = QLabel("Volume")
        self.vol_label.setFixedHeight(35)
        self.vol_label.setAlignment(Qt.AlignCenter)
        self.btns_layout.addWidget(self.vol_label)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setFixedHeight(35) # Same height
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setCursor(Qt.PointingHandCursor)
        self.vol_slider.setFocusPolicy(Qt.NoFocus)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.btns_layout.addWidget(self.vol_slider)


        self.control_layout.addLayout(self.btns_layout)
        self.main_layout.addWidget(self.control_bar)

        # Initialize MPV Engine
        try:
            self.player = mpv.MPV(wid=str(int(self.video_container.winId())),
                                  ytdl=True,
                                  input_default_bindings=True,
                                  input_vo_keyboard=True,
                                  osc=False) # Disable default OSC
        except Exception as e:
            QMessageBox.critical(
                self, "Library Load Error",
                "Could not find or load mpv-1.dll.\n\n"
                "Please download 'mpv-1.dll' from the GitHub releases page\n"
                "and place it in the same directory as the executable."
            )
            print(f"MPV initialization error: {e}")
            sys.exit(1)

        # UI update timer (~5fps)
        self.timer = QTimer()
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.update_status)
        self.timer.start()

        self._drag_pos = None
        self.setFocus() # Set initial focus

    def toggle_pause(self):
        if self.player:
            self.player.pause = not self.player.pause
            # Toggle play/pause text
            self.play_btn.setText("Play" if self.player.pause else "Pause")

    def seek(self, position):
        if self.player:
            self.player.time_pos = position

    def set_volume(self, value):
        if self.player:
            # Limit volume range (0-100)
            new_vol = max(0, min(100, value))
            self.player.volume = new_vol
            # Sync UI slider position
            self.vol_slider.setValue(new_vol)

    def skip(self, seconds):
        if self.player:
            # Use mpv seek method (relative)
            self.player.seek(seconds, reference='relative')

    def adjust_sub_delay(self, delta):
        if self.player:
            # Adjust subtitle delay (seconds)
            current = getattr(self.player, 'sub_delay', 0)
            self.player.sub_delay = current + delta
            # Print status
            print(f"Subtitle sync delay: {self.player.sub_delay:.1f}s")

    def update_status(self):
        try:
            if self.player:
                # Sync play button status
                # Only sync status when video is loaded (time_pos is not None)
                if self.player.time_pos is not None:
                    play_text = "Play" if self.player.pause else "Pause"
                else:
                    play_text = "Play"
                
                if self.play_btn.text() != play_text:
                    self.play_btn.setText(play_text)

                if self.player.time_pos is not None:
                    curr = int(self.player.time_pos)
                    total = int(self.player.duration or 0)
                    self.seek_slider.setMaximum(total)
                    if not self.seek_slider.isSliderDown():
                        self.seek_slider.setValue(curr)
                    
                    self.time_label.setText(f"{self.format_time(curr)} / {self.format_time(total)}")
        except (mpv.ShutdownError, AttributeError):
            # Stop timer if player is already terminated
            if hasattr(self, 'timer'):
                self.timer.stop()

    def format_time(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "", 
            "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv);;All Files (*)"
        )
        if file_path:
            self.load_video(file_path)

    def load_video(self, path):
        if not self.player: return
        self.player.play(path)
        self.title_label.setText(os.path.basename(path))
        
        # Auto load subtitle (detect same filename)
        base = os.path.splitext(path)[0]
        # Check major subtitle extensions
        for ext in ['.srt', '.ass', '.vtt', '.smi']:
            sub_path = base + ext
            if os.path.exists(sub_path):
                print(f"Subtitle found and loaded: {sub_path}")
                self.player.sub_add(sub_path)
                break

    # Keyboard event handler
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Space:
            self.toggle_pause()
        elif key == Qt.Key_Left:
            self.skip(-5)
        elif key == Qt.Key_Right:
            self.skip(5)
        elif key == Qt.Key_Up:
            # Increase volume by 5%
            self.set_volume(self.player.volume + 5)
        elif key == Qt.Key_Down:
            # Decrease volume by 5%
            self.set_volume(self.player.volume - 5)
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            # Toggle full screen
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif key == Qt.Key_Z:
            self.adjust_sub_delay(0.1)
        elif key == Qt.Key_X:
            self.adjust_sub_delay(-0.1)
        elif key == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    # Handle window drag
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Start drag only if child widgets did not handle the event
            if self.childAt(event.position().toPoint()) is None or \
               self.childAt(event.position().toPoint()) in [self.video_container, self.title_bar, self.control_bar]:
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

    def closeEvent(self, event):
        # Stop timer and release mpv resources
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, 'player') and self.player:
            try:
                self.player.terminate()
            except:
                pass
        super().closeEvent(event)

    # Drag and drop file loading
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.load_video(files[0])

    # Right-click context menu
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        
        open_action = QAction("Open File...", self)
        open_action.triggered.connect(self.open_file_dialog)
        menu.addAction(open_action)
        
        menu.addSeparator()
        
        register_action = QAction("Set as Default App", self)
        register_action.triggered.connect(self.setup_default_program)
        menu.addAction(register_action)
        
        menu.addSeparator()
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)
        
        menu.exec(event.globalPos())

    # Register default app and redirect to Windows Settings
    def setup_default_program(self):
        success = register_file_associations(silent=True)
        if not success:
            QMessageBox.warning(
                self, "Error", 
                "An error occurred during registry write for default program registration.\n"
                "Please check if your antivirus software is blocking registry writes."
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
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.Yes)
        msg_box.setButtonText(QMessageBox.Yes, "OK (Open Settings)")
        msg_box.setButtonText(QMessageBox.No, "Cancel")
        
        if msg_box.exec() == QMessageBox.Yes:
            try:
                os.startfile("ms-settings:defaultapps?registeredApp=MinimalPlayer")
            except Exception:
                try:
                    os.startfile("ms-settings:defaultapps")
                except Exception as e:
                    QMessageBox.critical(
                        self, "Execution Failed", 
                        f"Failed to open Settings:\n{e}\n\n"
                        "Please search for 'Default apps' manually in the Windows Start menu."
                    )

if __name__ == "__main__":
    # Run in CLI mode if --register option is provided
    if len(sys.argv) > 1 and sys.argv[1] == "--register":
        success = register_file_associations(silent=False)
        if success:
            print("MinimalPlayer registered successfully to registry.")
            sys.exit(0)
        else:
            print("An error occurred during registry registration.")
            sys.exit(1)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion") # Apply Fusion style for QSS compatibility
    player = VideoPlayer()
    player.setAcceptDrops(True)
    player.show()

    # Play video if file path is provided as argument
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
        if os.path.exists(video_path):
            player.load_video(video_path)

    sys.exit(app.exec())
