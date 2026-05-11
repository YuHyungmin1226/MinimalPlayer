import sys
import os
import urllib.request
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                             QPushButton, QHBoxLayout, QSlider, QLabel, QFrame,
                             QFileDialog, QMessageBox, QProgressDialog)
from PySide6.QtCore import Qt, QTimer, QPoint, QSize
from PySide6.QtGui import QColor, QPalette, QIcon

# Portable path configuration
# mpv-1.dll이 실행 파일과 같은 경로에 있을 경우 이를 로드하도록 설정
os.environ["PATH"] = os.path.dirname(__file__) + os.pathsep + os.environ["PATH"]

def check_and_download_mpv():
    dll_path = os.path.join(os.path.dirname(__file__), "mpv-1.dll")
    if os.path.exists(dll_path):
        return

    app = QApplication.instance() or QApplication(sys.argv)
    
    msg = QMessageBox()
    msg.setIcon(QMessageBox.Information)
    msg.setWindowTitle("다운로드 필요")
    msg.setText("최초 실행을 위해 필수 파일(mpv-1.dll, 약 118MB)을 다운로드합니다.\n계속하시겠습니까?")
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    if msg.exec() != QMessageBox.Yes:
        sys.exit(0)

    progress = QProgressDialog("mpv-1.dll 다운로드 중...", "취소", 0, 100)
    progress.setWindowTitle("다운로드 진행 상태")
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
            raise Exception("다운로드가 취소되었습니다.")

    url = "https://github.com/YuHyungmin1226/MinimalPlayer/releases/download/v1.0/mpv-1.dll"
    try:
        urllib.request.urlretrieve(url, dll_path, report)
    except Exception as e:
        QMessageBox.critical(None, "다운로드 실패", f"다운로드 중 오류가 발생했습니다:\n{e}\n\nGitHub Release 페이지에서 직접 다운로드하여 실행 파일과 같은 폴더에 넣어주세요.")
        if os.path.exists(dll_path):
            os.remove(dll_path)
        sys.exit(1)
    
    progress.setValue(100)

check_and_download_mpv()

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
"""

# Custom Slider to support jump-to-click
class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 클릭한 위치로 슬라이더 핸들을 즉시 이동
            new_value = self.minimum() + (self.maximum() - self.minimum()) * event.position().x() / self.width()
            self.setValue(int(new_value))
            self.sliderMoved.emit(int(new_value))
        super().mousePressEvent(event)

class VideoPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        # 프레임리스 윈도우 설정 (미니멀리즘 디자인)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.resize(1000, 600)
        self.setStyleSheet(STYLE)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 커스텀 타이틀바
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
        
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(40, 35)
        self.close_btn.setFocusPolicy(Qt.NoFocus)
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setStyleSheet("QPushButton:hover { background-color: #e81123; color: white; }")

        self.title_bar_layout.addWidget(self.min_btn)
        self.title_bar_layout.addWidget(self.close_btn)
        
        self.main_layout.addWidget(self.title_bar)

        # 영상 출력 영역
        self.video_container = QWidget()
        self.video_container.setObjectName("VideoContainer")
        self.video_container.setAttribute(Qt.WA_NativeWindow)
        self.main_layout.addWidget(self.video_container, 1)

        # 하단 컨트롤 바
        self.control_bar = QFrame()
        self.control_bar.setObjectName("ControlBar")
        self.control_bar.setFixedHeight(70)
        self.control_layout = QVBoxLayout(self.control_bar)
        self.control_layout.setContentsMargins(15, 5, 15, 10)

        # 재생 바 (Seek Slider) - 커스텀 슬라이더 사용
        self.seek_slider = ClickableSlider(Qt.Horizontal)
        self.seek_slider.setCursor(Qt.PointingHandCursor)
        self.seek_slider.setFocusPolicy(Qt.NoFocus)
        self.seek_slider.sliderMoved.connect(self.seek)
        self.control_layout.addWidget(self.seek_slider)

        # 하단 버튼 레이아웃
        self.btns_layout = QHBoxLayout()
        self.btns_layout.setSpacing(10)
        self.btns_layout.setAlignment(Qt.AlignVCenter)
        
        # 파일 열기 버튼 추가
        self.open_btn = QPushButton("📁")
        self.open_btn.setFixedSize(45, 35)
        self.open_btn.setToolTip("Open File")
        self.open_btn.setFocusPolicy(Qt.NoFocus)
        self.open_btn.clicked.connect(self.open_file_dialog)
        self.btns_layout.addWidget(self.open_btn)

        # 건너띄기 버튼 추가 (뒤로 10초)
        self.back_btn = QPushButton("<<")
        self.back_btn.setFixedSize(45, 35)
        self.back_btn.setFocusPolicy(Qt.NoFocus)
        self.back_btn.clicked.connect(lambda: self.skip(-10))
        self.btns_layout.addWidget(self.back_btn)

        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(60, 35)
        self.play_btn.setFocusPolicy(Qt.NoFocus)
        self.play_btn.clicked.connect(self.toggle_pause)
        self.btns_layout.addWidget(self.play_btn)

        # 건너띄기 버튼 추가 (앞으로 10초)
        self.fwd_btn = QPushButton(">>")
        self.fwd_btn.setFixedSize(45, 35)
        self.fwd_btn.setFocusPolicy(Qt.NoFocus)
        self.fwd_btn.clicked.connect(lambda: self.skip(10))
        self.btns_layout.addWidget(self.fwd_btn)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setFixedHeight(35) # 버튼 높이와 동일하게 설정
        self.time_label.setAlignment(Qt.AlignCenter) # 텍스트 수직/수평 중앙 정렬
        self.btns_layout.addWidget(self.time_label)
        self.btns_layout.addStretch()

        # 볼륨 컨트롤
        self.vol_label = QLabel("Volume")
        self.vol_label.setFixedHeight(35)
        self.vol_label.setAlignment(Qt.AlignCenter)
        self.btns_layout.addWidget(self.vol_label)
        self.vol_slider = QSlider(Qt.Horizontal)
        self.vol_slider.setFixedHeight(35) # 높이 통일
        self.vol_slider.setFixedWidth(100)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(100)
        self.vol_slider.setCursor(Qt.PointingHandCursor)
        self.vol_slider.setFocusPolicy(Qt.NoFocus)
        self.vol_slider.valueChanged.connect(self.set_volume)
        self.btns_layout.addWidget(self.vol_slider)


        self.control_layout.addLayout(self.btns_layout)
        self.main_layout.addWidget(self.control_bar)

        # MPV 엔진 초기화
        try:
            self.player = mpv.MPV(wid=str(int(self.video_container.winId())),
                                  ytdl=True,
                                  input_default_bindings=True,
                                  input_vo_keyboard=True,
                                  osc=False) # 내장 UI 비활성화
        except Exception as e:
            QMessageBox.critical(
                self, "라이브러리 로드 오류",
                "mpv-1.dll 파일을 찾을 수 없거나 로드에 실패했습니다.\n\n"
                "GitHub 릴리즈 페이지에서 'mpv-1.dll'을 다운로드하여\n"
                "실행 파일과 같은 폴더에 넣어주세요."
            )
            print(f"MPV 초기화 오류: {e}")
            sys.exit(1)

        # UI 갱신 타이머 (5fps 정도로 갱신)
        self.timer = QTimer()
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.update_status)
        self.timer.start()

        self._drag_pos = None
        self.setFocus() # 초기 포커스 설정

    def toggle_pause(self):
        if self.player:
            self.player.pause = not self.player.pause
            # ⏸ 이모지 대신 텍스트 기호 || 를 사용하여 파란색 배경 제거
            self.play_btn.setText("▶" if self.player.pause else "||")

    def seek(self, position):
        if self.player:
            self.player.time_pos = position

    def set_volume(self, value):
        if self.player:
            # 볼륨 범위 제한 (0~100)
            new_vol = max(0, min(100, value))
            self.player.volume = new_vol
            # UI 슬라이더 위치 동기화
            self.vol_slider.setValue(new_vol)

    def skip(self, seconds):
        if self.player:
            # mpv의 seek 메서드 사용 (상대적 이동)
            self.player.seek(seconds, reference='relative')

    def adjust_sub_delay(self, delta):
        if self.player:
            # 자막 지연 시간 조정 (단위: 초)
            current = getattr(self.player, 'sub_delay', 0)
            self.player.sub_delay = current + delta
            # 간단한 상태 표시 (콘솔 출력 및 타이틀 바 임시 변경 가능)
            print(f"자막 싱크 조정: {self.player.sub_delay:.1f}s")

    def update_status(self):
        try:
            if self.player:
                # 재생 버튼 상태 동기화
                # 영상이 로드된 경우(time_pos가 None이 아님)에만 실제 pause 상태 반영
                # 그 외(시작 시, 영상 종료 시 등)에는 ▶ 버튼으로 표시
                if self.player.time_pos is not None:
                    play_text = "▶" if self.player.pause else "||"
                else:
                    play_text = "▶"
                
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
            # 플레이어가 이미 종료된 경우 타이머 정지
            if hasattr(self, 'timer'):
                self.timer.stop()

    def format_time(self, seconds):
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    def open_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "영상 파일 선택", "", 
            "Video Files (*.mp4 *.mkv *.avi *.mov *.wmv);;All Files (*)"
        )
        if file_path:
            self.load_video(file_path)

    def load_video(self, path):
        if not self.player: return
        self.player.play(path)
        self.title_label.setText(os.path.basename(path))
        
        # 자막 자동 로드 로직 (동일 파일명 감지)
        base = os.path.splitext(path)[0]
        # 주요 자막 확장자 체크
        for ext in ['.srt', '.ass', '.vtt', '.smi']:
            sub_path = base + ext
            if os.path.exists(sub_path):
                print(f"자막 발견 및 로드: {sub_path}")
                self.player.sub_add(sub_path)
                break

    # 키보드 이벤트 처리
    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Space:
            self.toggle_pause()
        elif key == Qt.Key_Left:
            self.skip(-5)
        elif key == Qt.Key_Right:
            self.skip(5)
        elif key == Qt.Key_Up:
            # 볼륨 5% 증가
            self.set_volume(self.player.volume + 5)
        elif key == Qt.Key_Down:
            # 볼륨 5% 감소
            self.set_volume(self.player.volume - 5)
        elif key == Qt.Key_Return or key == Qt.Key_Enter:
            # 전체화면 토글
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

    # 마우스 드래그 및 버튼 클릭 보장
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # 자식 위젯(버튼 등)이 이벤트를 처리하지 않은 경우에만 드래그 시작
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
        # 타이머 정지 및 mpv 리소스 해제
        if hasattr(self, 'timer'):
            self.timer.stop()
        if hasattr(self, 'player') and self.player:
            try:
                self.player.terminate()
            except:
                pass
        super().closeEvent(event)

    # 드래그 앤 드롭 파일 로드
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            self.load_video(files[0])

if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion") # QSS 호환성을 위해 Fusion 스타일 적용
    player = VideoPlayer()
    player.setAcceptDrops(True)
    player.show()
    sys.exit(app.exec())
