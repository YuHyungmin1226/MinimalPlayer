# 저사양 최적화 포터블 플레이어 프로젝트 지침

## 1. 개요
본 프로젝트는 저사양 PC에서도 원활하게 동작하는 동영상 플레이어를 목표로 합니다. `mpv` 엔진을 기반으로 하며, `PySide6`를 통해 미니멀한 UI를 제공합니다.

## 2. 포터블 환경 설정 방법
1. **Python 가상환경 생성**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **MPV 라이브러리 설치**:
   - `mpv-1.dll` 파일이 `main.py`와 같은 위치에 있어야 합니다.
   - [mpv-player-windows](https://sourceforge.net/projects/mpv-player-windows/files/libmpv/)에서 최신 `64-bit` libmpv를 다운로드하여 압축을 풀고 `mpv-1.dll`을 프로젝트 루트에 복사하세요.

## 3. UI/UX 원칙
- **미니멀리즘**: 불필요한 테두리와 메뉴바를 제거하고, 영상 콘텐츠에 집중합니다.
- **다크 모드**: 모든 UI 요소는 어두운 톤으로 일관성을 유지합니다.
- **반응형**: 창 크기 조절 시 영상 비율을 유지하며 컨트롤 패널이 유연하게 배치됩니다.

## 4. 자막 자동 인식
- 영상 파일과 **동일한 폴더**, **동일한 파일명**을 가진 자막 파일(`.srt`, `.ass`, `.vtt`, `.smi`)을 자동으로 감지하여 출력합니다.
