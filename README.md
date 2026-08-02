# 🎬 Minimal Portable Media Player

저사양 노트북 및 미니 PC에서도 끊김 없이 동영상 및 음악을 재생할 수 있도록 설계된 **초경량 포터블 미디어 플레이어**입니다. `mpv` 엔진을 기반으로 하여 압도적인 퍼포먼스와 미니멀한 UI를 제공합니다.

## ✨ 주요 특징

- **🚀 초경량 & 고성능**: 저사양 환경에서도 4K 영상까지 부드럽게 재생.
- **🎵 오디오 파일 지원**: WAV, MP3, FLAC, AAC, OGG, M4A, OPUS, WMA, AIFF, APE 등 주요 오디오 포맷 재생 지원.
- **🎨 미니멀 다크 UI**: 플랫폼 표준 창과 메뉴를 사용해 기본 조작과 접근성을 유지하면서 영상 감상에 집중하는 다크 인터페이스.
- **📁 포터블 설계**: 별도의 설치 없이 실행 파일과 DLL만으로 어디서든 실행 가능.
- **🖱️ 직관적인 조작**: 
    - 하단 `📁` 버튼을 클릭하거나, 드래그 앤 드롭으로 즉시 파일 로드.
    - **Jump-to-Click**: 재생 바의 원하는 위치를 클릭하면 즉시 해당 시점으로 이동.
- **🗨️ 자막 자동 로드 & 다국어 지원**: 영상과 동일한 폴더의 자막 파일(`.srt`, `.ass`, `.vtt`, `.smi`)을 대소문자 구분 없이 자동으로 감지하여 로드합니다. 특히 다국어가 포함된 SMI 자막의 경우 한국어 자막(`KRCC`/`KORCC`)을 우선으로 자동 선별하여 표시하며, 인코딩 자동 복구 기능을 포함합니다.
- **🕘 최근 파일 및 이어보기**: `File → Open Recent` 또는 우클릭 메뉴에서 최근 파일을 다시 열 수 있고, 이전 재생 위치가 있으면 이어보기를 제안합니다. 단, 폴더 순차 이동(자동 넘김, `|<` / `>|`)으로 넘어간 파일은 연속 재생이 끊기지 않도록 묻지 않고 처음부터 재생합니다.
- **⏭️ 폴더 연속 재생 및 곡 이동**: 재생이 끝나면 같은 폴더의 다음 파일을 파일명 순서로 자동 재생하고, 하단 `|<` / `>|` 버튼(또는 `PageUp` / `PageDown`)으로 언제든 이전·다음 파일로 건너뛸 수 있습니다. 정렬은 탐색기·Finder와 동일한 자연 정렬(`ep2` → `ep10`)이며, 영상과 오디오를 함께 이름 순으로 이어갑니다. 폴더의 처음/마지막에서는 순환하지 않고 해당 버튼이 비활성화됩니다. 자동 넘김은 `Playback → Autoplay Next in Folder` 또는 우클릭 메뉴에서 끄고 켤 수 있으며 설정은 저장됩니다(이전·다음 버튼은 이 설정과 무관하게 항상 동작).
- **🎬 오디오 동영상 내보내기**: 오디오 파일(WAV 등) 재생 중 `File → Export to MP4 Video...` 또는 우클릭 메뉴를 통해 해당 오디오 파일과 커버 이미지, 그리고 한국어 자막(SRT/SMI 등)을 하나로 병합한 MP4 동영상 파일 내보내기 기능을 제공합니다. (FFmpeg 도구 설치 및 시스템 PATH 환경 변수 등록이 필요합니다.)
- **🔐 안전한 MPV 다운로드**: 최초 실행 시 내려받는 `mpv-1.dll`은 SHA256으로 무결성을 확인한 뒤 사용합니다. (빌드 시 DLL이 프로젝트 폴더에 이미 존재하면 빌드 결과물에 자동으로 내장되며, 실행 시 추가 다운로드가 생략됩니다.)

## ⌨️ 단축키 및 제어 (Shortcuts)

| 기능 | 조작 방법 |
| :--- | :--- |
| **파일 열기** | 하단 `📁` 버튼 또는 영상 파일 드래그 앤 드롭 |
| **재생 / 일시정지** | `Space` 또는 하단 `▶` / `||` 버튼 |
| **건너뛰기 (5초)** | 키보드 `←` / `→` |
| **건너뛰기 (10초)** | 하단 `<<` / `>>` 버튼 |
| **이전 / 다음 파일** | 하단 `\|<` / `>\|` 버튼 또는 `PageUp` / `PageDown` (같은 폴더, 파일명 순) |
| **볼륨 조절** | 키보드 `↑` / `↓` 또는 볼륨 슬라이더 (키보드 조절 시 화면 OSD 피드백 제공) |
| **자막 싱크 조정** | `Z` (0.1초 느리게) / `X` (0.1초 빠르게) (화면 OSD 피드백 제공) |
| **자막 크기 조절** | `[` (0.1x 작게) / `]` (0.1x 크게) (화면 OSD 피드백 제공) |
| **전체화면 토글** | `Enter`, 영상 화면 두 번 클릭, 또는 `View → Full Screen` (플랫폼 표준 단축키 포함). `ESC`는 전체화면에서만 창 모드로 복귀합니다. |
| **프로그램 종료** | 플랫폼 표준 창 닫기 버튼 또는 `File → Quit` |
| **창 이동·최소화·최대화** | 운영체제의 표준 타이틀 바와 창 제어 |
| **최근 파일 열기 및 비우기** | `File → Open Recent` 또는 우클릭 메뉴 → `Recent Files` |
| **폴더 자동 연속 재생 켜기/끄기** | `Playback → Autoplay Next in Folder` 또는 우클릭 메뉴 (기본값 켜짐, 설정 저장됨) |
| **오디오 동영상 내보내기** | 오디오 파일 재생 중 `File → Export to MP4 Video...` 또는 우클릭 메뉴 (FFmpeg 필수) |

> ⚠️ **동영상 내보내기(Export) 참고**:
> - 오디오 파일 재생 중에만 활성화되며, 자막이 자동 감지된 경우 자막을 영상에 하드번(Hardburn) 인코딩하여 하나로 구워냅니다.
> - 자동 감지된 커버 이미지가 없거나 자막이 없는 경우, 파일 선택창을 통해 원하는 이미지와 자막 파일을 수동으로 선택해 합성할 수 있습니다.
> - 본 기능은 시스템에 `ffmpeg`가 설치되어 있고 환경 변수(PATH)에 등록되어 있어야 작동합니다.

## 🚀 시작하기 (How to Use)

Python 3.10 이상이 필요합니다. Windows와 macOS 모두 64비트 Python 사용을 권장합니다.

### 지원 범위

| 환경 | 지원 범위 | 자동 검증 |
| :--- | :--- | :--- |
| Python | 3.10~3.14 | Ubuntu에서 3.10 / 3.12 / 3.14 단위 테스트 |
| Windows | Windows 10 1809 이상, x64 | Windows Server 2022 x64에서 테스트·빌드·스모크 실행 |
| macOS | macOS 14 이상, Apple Silicon | macOS 14 arm64에서 테스트·빌드·스모크 실행 |
| Linux | Ubuntu 22.04 이상, x64 | Ubuntu 22.04 x64에서 테스트·빌드·스모크 실행 |

macOS Intel, Windows ARM64, Linux ARM64 및 기타 배포판은 기반 라이브러리에서 동작할 수 있지만 현재 CI 검증 범위에는 포함되지 않습니다. 배포 산출물은 각 플랫폼에서 개별적으로 빌드하며, 교차 컴파일은 지원하지 않습니다.

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

## 기본 미디어 플레이어로 설정

### Windows

1. MinimalPlayer를 실행한 뒤 `File → Set as Default App`(또는 우클릭 메뉴)을 선택합니다.
2. 열리는 Windows `기본 앱` 설정에서 `MinimalPlayer`를 찾아 원하는 영상·오디오 확장자의 기본 앱으로 지정합니다.

Windows 보안 정책상 애플리케이션이 사용자 확인 없이 기본 앱을 강제로 변경할 수는 없습니다.

### macOS

1. 빌드된 `MinimalPlayer.app`을 `응용 프로그램` 폴더로 이동하고 한 번 실행합니다.
2. Finder에서 미디어 파일을 선택하고 `정보 가져오기`를 엽니다.
3. `다음으로 열기`에서 `MinimalPlayer`를 선택한 뒤 `모두 변경…`을 누릅니다.

앱이 실행 중인 상태에서 다른 미디어 파일을 더블 클릭해도 해당 파일로 재생이 전환됩니다.

## 🛠 빌드 방법 (직접 실행 파일 만들기)

파이썬 환경에서 아래 명령어를 실행하면 `dist/` 폴더 내에 실행 파일(Windows) 또는 `.app` 번들(macOS)이 생성됩니다.
```bash
python build.py
```

> 💡 **Tip (포터블 패키징, Windows)**: 빌드를 실행하기 전에 프로젝트 루트 폴더에 `mpv-1.dll`이 이미 존재하면, PyInstaller가 이 DLL을 실행 파일 내부로 자동 번들링합니다. 이 경우, 사용자가 최초 실행 시 별도의 DLL 다운로드 팝업을 거치지 않는 완전한 오프라인 포터블 실행 파일이 생성됩니다.
>
> 💡 **Tip (macOS)**: 빌드 전 `brew install mpv`로 libmpv가 설치되어 있어야 하며, PyInstaller가 libmpv와 그 의존 라이브러리들을 `.app` 내부(`Contents/Frameworks`)에 자동으로 번들링하여 Homebrew가 없는 다른 Mac에서도 실행 가능한 자기완결형 앱을 만듭니다.

> ⚠️ **macOS 배포 시 주의**: 생성된 앱의 CPU 아키텍처와 최소 macOS 버전은 빌드한 Mac과 Homebrew 라이브러리의 호환 범위를 따릅니다. 배포 대상 중 가장 오래된 macOS/아키텍처 환경에서 빌드와 실행을 검증하세요. `build.py`는 로컬 실행을 위한 ad-hoc 서명만 적용하므로, 다른 사용자에게 배포할 때는 Apple Developer ID 서명과 notarization/stapling을 별도로 완료해야 Gatekeeper 차단을 피할 수 있습니다.

## 테스트

의존성이 설치된 가상환경에서 다음을 실행합니다.

```bash
python -m unittest discover -v
```

패키징 산출물의 Qt·libmpv 초기화까지 비대화식으로 확인하려면 다음을 실행합니다. 이 검사는 OpenGL 프레임 렌더링까지 검증하지는 않습니다.

```bash
QT_QPA_PLATFORM=offscreen python main.py --smoke-test
```

GitHub Actions의 `.github/workflows/ci.yml`은 위 Python 호환성 테스트와 Windows/macOS/Linux 패키징 스모크를 자동으로 실행합니다.

## 📜 라이선스
현재 저장소에는 프로젝트 자체의 `LICENSE` 파일과 번들된 제3자 구성 요소의 고지 문서가 없습니다. 실행 파일을 공개 배포하기 전에 프로젝트 라이선스를 명시하고 PySide6, python-mpv, mpv 및 번들된 미디어 라이브러리의 재배포 조건과 고지 의무를 확인하세요.
