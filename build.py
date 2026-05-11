import PyInstaller.__main__
import os
import shutil

# 빌드 설정
ENTRY_POINT = "main.py"
APP_NAME = "MinimalPlayer"
DLL_NAME = "mpv-1.dll"

def build():
    print(f"Starting build for {APP_NAME}...")
    
    # mpv-1.dll 존재 여부 확인
    if not os.path.exists(DLL_NAME):
        print(f"경고: {DLL_NAME} 파일이 루트 폴더에 없습니다.")
        print("포터블 실행 파일이 정상 작동하려면 mpv-1.dll이 필요합니다.")
        # 계속 진행은 하지만 경고 출력

    params = [
        ENTRY_POINT,
        "--name=" + APP_NAME,
        "--onefile", # 단일 실행 파일로 빌드
        "--windowed", # 콘솔 창 숨김
        "--noconfirm",
        "--clean",
        f"--add-binary={DLL_NAME};." if os.path.exists(DLL_NAME) else ""
    ]
    
    # 빈 문자열 제거
    params = [p for p in params if p]

    PyInstaller.__main__.run(params)
    print(f"\n빌드 완료! 'dist/{APP_NAME}.exe' 파일을 확인하세요.")

if __name__ == "__main__":
    build()
