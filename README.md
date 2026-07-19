# 🎬 Minimal Portable Media Player

저사양 노트북 및 미니 PC에서도 끊김 없이 동영상 및 음악을 재생할 수 있도록 설계된 **초경량 포터블 미디어 플레이어**입니다. `mpv` 엔진을 기반으로 하여 압도적인 퍼포먼스와 미니멀한 UI를 제공합니다.

## ✨ 주요 특징

- **🚀 초경량 & 고성능**: 저사양 환경에서도 4K 영상까지 부드럽게 재생.
- **🎵 오디오 파일 지원**: WAV, MP3, FLAC, AAC, OGG, M4A, OPUS, WMA, AIFF, APE 등 주요 오디오 포맷 재생 지원.
- **🎨 미니멀 다크 UI**: 영상 감상에 방해되지 않는 테두리 없는 세련된 다크 인터페이스.
- **📁 포터블 설계**: 별도의 설치 없이 실행 파일과 DLL만으로 어디서든 실행 가능.
- **🖱️ 직관적인 조작**: 
    - 하단 `📁` 버튼을 클릭하거나, 드래그 앤 드롭으로 즉시 파일 로드.
    - **Jump-to-Click**: 재생 바의 원하는 위치를 클릭하면 즉시 해당 시점으로 이동.
- **🗨️ 자막 자동 로드 & 다국어 지원**: 영상과 동일한 폴더의 자막 파일(`.srt`, `.ass`, `.vtt`, `.smi`)을 대소문자 구분 없이 자동으로 감지하여 로드합니다. 특히 다국어가 포함된 SMI 자막의 경우 한국어 자막(`KRCC`/`KORCC`)을 우선으로 자동 선별하여 표시하며, 인코딩 자동 복구 기능을 포함합니다.
- **🕘 최근 파일 및 이어보기**: 우클릭 메뉴에서 최근 파일을 다시 열 수 있고, 이전 재생 위치가 있으면 이어보기를 제안합니다.
- **🎬 오디오 동영상 내보내기**: 오디오 파일(WAV 등) 재생 중 우클릭 메뉴를 통해 해당 오디오 파일과 커버 이미지, 그리고 한국어 자막(SRT/SMI 등)을 하나로 병합한 MP4 동영상 파일 내보내기 기능을 제공합니다. (FFmpeg 도구 설치 및 시스템 PATH 환경 변수 등록이 필요합니다.)
- **🔐 안전한 MPV 다운로드**: 최초 실행 시 내려받는 `mpv-1.dll`은 SHA256으로 무결성을 확인한 뒤 사용합니다. (빌드 시 DLL이 프로젝트 폴더에 이미 존재하면 빌드 결과물에 자동으로 내장되며, 실행 시 추가 다운로드가 생략됩니다.)

## ⌨️ 단축키 및 제어 (Shortcuts)

| 기능 | 조작 방법 |
| :--- | :--- |
| **파일 열기** | 하단 `📁` 버튼 또는 영상 파일 드래그 앤 드롭 |
| **재생 / 일시정지** | `Space` 또는 하단 `▶` / `||` 버튼 |
| **건너뛰기 (5초)** | 키보드 `←` / `→` |
| **건너뛰기 (10초)** | 하단 `<<` / `>>` 버튼 |
| **볼륨 조절** | 키보드 `↑` / `↓` 또는 볼륨 슬라이더 (키보드 조절 시 화면 OSD 피드백 제공) |
| **자막 싱크 조정** | `Z` (0.1초 느리게) / `X` (0.1초 빠르게) (화면 OSD 피드백 제공) |
| **자막 크기 조절** | `[` (0.1x 작게) / `]` (0.1x 크게) (화면 OSD 피드백 제공) |
| **전체화면 토글** | `Enter` 키 (전체화면 모드 시 3초간 마우스 미이동 시 컨트롤 바가 부드럽게 페이드아웃되며 커서도 자동 숨김, 마우스 이동 시 다시 부드럽게 페이드인) |
| **프로그램 종료** | `ESC` 키 또는 `×` 버튼 |
| **창 이동** | 영상 화면 클릭 후 드래그 |
| **최소화** | 상단 타이틀 바 `-` 버튼 |
| **최근 파일 열기 및 비우기** | 우클릭 메뉴 → `Recent Files` (하단 `Clear Recent Files`로 비우기 가능) |
| **오디오 동영상 내보내기** | 오디오 파일 재생 중 우클릭 메뉴 → `Export to MP4 Video...` (FFmpeg 필수) |

> ⚠️ **동영상 내보내기(Export) 참고**:
> - 오디오 파일 재생 중에만 활성화되며, 자막이 자동 감지된 경우 자막을 영상에 하드번(Hardburn) 인코딩하여 하나로 구워냅니다.
> - 자동 감지된 커버 이미지가 없거나 자막이 없는 경우, 파일 선택창을 통해 원하는 이미지와 자막 파일을 수동으로 선택해 합성할 수 있습니다.
> - 본 기능은 시스템에 `ffmpeg`가 설치되어 있고 환경 변수(PATH)에 등록되어 있어야 작동합니다.

## 🚀 시작하기 (How to Use)

Python 3.10 이상이 필요합니다. Windows와 macOS 모두 64비트 Python 사용을 권장합니다.

### Windows

1. 프로젝트 클론: `git clone https://github.com/YuHyungmin1226/MinimalPlayer.git`
2. 폴더 이동: `cd MinimalPlayer`
3. 파이썬 가상환경 생성 및 활성화:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   ```
4. 의존성 설치: `pip install -r requirements.txt`
5. 실행: `python main.py` (최초 실행 시 `mpv-1.dll` 약 118MB 자동 다운로드)

### macOS / Linux

Windows와 달리 mpv 라이브러리를 자동 다운로드하지 않으며, 시스템에 `mpv`(libmpv)가 설치되어 있어야 합니다.

1. 프로젝트 클론 및 이동: `git clone https://github.com/YuHyungmin1226/MinimalPlayer.git && cd MinimalPlayer`
2. mpv 라이브러리 설치:
   - macOS: `brew install mpv` (자막을 포함한 MP4 내보내기도 사용하려면 `brew install ffmpeg-full` 추가)
   - Linux (Debian/Ubuntu): `sudo apt install libmpv2`
   - Linux (Fedora): `sudo dnf install mpv-libs`
3. 파이썬 가상환경 생성 및 활성화:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
4. 의존성 설치: `pip install -r requirements.txt`
5. 실행: `python main.py`

## 🛠 빌드 방법 (직접 실행 파일 만들기)

파이썬 환경에서 아래 명령어를 실행하면 `dist/` 폴더 내에 실행 파일(Windows) 또는 `.app` 번들(macOS)이 생성됩니다.
```bash
python build.py
```

> 💡 **Tip (포터블 패키징, Windows)**: 빌드를 실행하기 전에 프로젝트 루트 폴더에 `mpv-1.dll`이 이미 존재하면, PyInstaller가 이 DLL을 실행 파일 내부로 자동 번들링합니다. 이 경우, 사용자가 최초 실행 시 별도의 DLL 다운로드 팝업을 거치지 않는 완전한 오프라인 포터블 실행 파일이 생성됩니다.
>
> 💡 **Tip (macOS)**: 빌드 전 `brew install mpv`로 libmpv가 설치되어 있어야 하며, PyInstaller가 libmpv와 그 의존 라이브러리들을 `.app` 내부(`Contents/Frameworks`)에 자동으로 번들링하여 Homebrew가 없는 다른 Mac에서도 실행 가능한 자기완결형 앱을 만듭니다.

## 📜 라이선스
이 프로젝트는 MPV 미디어 엔진의 라이선스 정책을 따르며, 오픈 소스로 제공됩니다.
