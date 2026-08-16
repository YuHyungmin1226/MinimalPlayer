import PyInstaller.__main__
import hashlib
import os
import platform
import sys
import glob
import plistlib
import shutil
import subprocess
import urllib.request
import zipfile
from datetime import datetime

from constants import AUDIO_EXTENSIONS, MPV_DLL_NAME, MPV_DLL_SHA256, MPV_DLL_URL, VIDEO_EXTENSIONS

# Build configuration
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ENTRY_POINT = os.path.join(PROJECT_DIR, "main.py")
APP_NAME = "MinimalPlayer"
BUNDLE_IDENTIFIER = "com.yuhyungmin.minimalplayer"
SYSTEM_NAME = platform.system()

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

DEFAULT_DIST_DIR = os.path.join(PROJECT_DIR, "dist")
DEFAULT_WORK_DIR = os.path.join(PROJECT_DIR, "build")
RELEASE_DIR = os.path.join(PROJECT_DIR, "release")


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _verify_mpv_dll(path: str) -> bool:
    return os.path.exists(path) and _sha256_file(path) == MPV_DLL_SHA256


def _ensure_mpv_dll(dll_path: str) -> bool:
    """mpv-1.dll이 없거나 손상됐으면 다운로드해 완전 포터블 단일 exe로 내장할 수 있게 한다."""
    if _verify_mpv_dll(dll_path):
        return True

    if os.path.exists(dll_path):
        print(f"WARNING: {MPV_DLL_NAME} exists but failed SHA256 verification. Re-downloading...")
        os.remove(dll_path)

    print(f"Downloading {MPV_DLL_NAME} (~118MB) from {MPV_DLL_URL} ...")
    tmp_path = dll_path + ".tmp"
    try:
        urllib.request.urlretrieve(MPV_DLL_URL, tmp_path)
        if not _verify_mpv_dll(tmp_path):
            print("ERROR: Downloaded file failed SHA256 verification.")
            os.remove(tmp_path)
            return False
        os.replace(tmp_path, dll_path)
        print(f"Downloaded and verified {MPV_DLL_NAME}.")
        return True
    except Exception as e:
        print(f"ERROR: Failed to download {MPV_DLL_NAME}: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def _find_macos_libmpv():
    """Return the path to libmpv.dylib on macOS, or None if not found."""
    candidates = []
    try:
        prefix = subprocess.check_output(
            ["brew", "--prefix"], text=True, stderr=subprocess.DEVNULL).strip()
        if prefix:
            candidates.append(os.path.join(prefix, "lib"))
    except Exception:
        pass
    candidates += ["/opt/homebrew/lib", "/usr/local/lib", os.path.expanduser("~/.homebrew/lib")]
    for d in candidates:
        for pattern in ("libmpv.dylib", "libmpv.2.dylib", "libmpv.1.dylib"):
            matches = glob.glob(os.path.join(d, pattern))
            if matches:
                return matches[0]
    return None


def _verify_macos_bundle(app_path):
    """Confirm the .app is self-contained: no dependency points outside the bundle.

    PyInstaller recursively bundles libmpv's dependency chain (ffmpeg, libass, ...)
    and rewrites their load commands to @rpath. This checks that nothing still
    references a Homebrew/MacPorts path, which would break on a clean Mac.
    """
    fw = os.path.join(app_path, "Contents", "Frameworks")
    binaries = glob.glob(os.path.join(fw, "*.dylib")) + glob.glob(os.path.join(fw, "**", "*.dylib"), recursive=True)
    leaks = []
    for b in set(binaries):
        try:
            out = subprocess.check_output(["otool", "-L", b], text=True, stderr=subprocess.DEVNULL)
        except Exception:
            continue
        for line in out.splitlines()[1:]:
            ref = line.strip().split(" ")[0]
            if ref.startswith(("/opt/homebrew", "/opt/local", "/usr/local/Cellar", "/usr/local/opt")):
                leaks.append((os.path.basename(b), ref))
    print(f"Bundled dylibs checked: {len(set(binaries))}")
    if leaks:
        print(f"WARNING: {len(leaks)} external dependency reference(s) remain — "
              "the app may NOT run on a Mac without these libraries:")
        for name, ref in leaks[:20]:
            print(f"  {name} -> {ref}")
    else:
        print("OK: no external (Homebrew/MacPorts) dependencies — the .app is self-contained.")


def _configure_macos_file_associations(app_path):
    """Declare supported media types so Finder can route files to the app."""
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    with open(plist_path, "rb") as plist_file:
        info = plistlib.load(plist_file)

    info["CFBundleIdentifier"] = BUNDLE_IDENTIFIER
    info["CFBundleDocumentTypes"] = [
        {
            "CFBundleTypeName": "Video",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Owner",
            "LSItemContentTypes": ["public.movie"],
            "CFBundleTypeExtensions": sorted(ext.lstrip(".") for ext in VIDEO_EXTENSIONS),
        },
        {
            "CFBundleTypeName": "Audio",
            "CFBundleTypeRole": "Viewer",
            "LSHandlerRank": "Owner",
            "LSItemContentTypes": ["public.audio"],
            "CFBundleTypeExtensions": sorted(ext.lstrip(".") for ext in AUDIO_EXTENSIONS),
        },
    ]

    with open(plist_path, "wb") as plist_file:
        plistlib.dump(info, plist_file, sort_keys=False)

    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", app_path],
        check=True,
        stdout=subprocess.DEVNULL,
    )


def build(dist_dir: str | None = None, work_dir: str | None = None, spec_dir: str | None = None):
    dist_dir = dist_dir if dist_dir is not None else DEFAULT_DIST_DIR
    work_dir = work_dir if work_dir is not None else DEFAULT_WORK_DIR
    spec_dir = spec_dir if spec_dir is not None else PROJECT_DIR
    print(f"Starting build for {APP_NAME} on {sys.platform}...")

    for directory in (dist_dir, work_dir, spec_dir):
        os.makedirs(directory, exist_ok=True)

    params = [
        ENTRY_POINT,
        "--name=" + APP_NAME,
        "--windowed",   # hide console / build a .app bundle
        "--noconfirm",
        "--clean",
        "--hidden-import=mpv",
        "--distpath=" + dist_dir,
        "--workpath=" + work_dir,
        "--specpath=" + spec_dir,
    ]
    if IS_MAC:
        params.append("--osx-bundle-identifier=" + BUNDLE_IDENTIFIER)

    # PyInstaller uses ';' as the add-binary separator on Windows and ':' elsewhere.
    sep = ";" if IS_WINDOWS else ":"

    icon_png = os.path.join(PROJECT_DIR, "icon.png")
    icon_ico = os.path.join(PROJECT_DIR, "icon.ico")
    icon_icns = os.path.join(PROJECT_DIR, "icon.icns")
    if os.path.exists(icon_png):
        params.append(f"--add-data={icon_png}{sep}.")

    if IS_WINDOWS and os.path.exists(icon_ico):
        params.append("--icon=" + icon_ico)
    elif IS_MAC and os.path.exists(icon_icns):
        params.append("--icon=" + icon_icns)

    if IS_WINDOWS:
        # Single-file portable executable for Windows.
        params.append("--onefile")
        dll_path = os.path.join(PROJECT_DIR, MPV_DLL_NAME)
        if not _ensure_mpv_dll(dll_path):
            print(f"ERROR: could not obtain a verified {MPV_DLL_NAME}. Aborting build.")
            sys.exit(1)
        # Embed the DLL inside the onefile executable so the app runs standalone,
        # with no first-run download required.
        params.append(f"--add-binary={dll_path}{sep}.")
    elif IS_MAC:
        # Use onedir (default) so PyInstaller produces a proper self-contained .app
        # with all of libmpv's dependencies under Contents/Frameworks. --onefile is
        # avoided on macOS: it extracts to a temp dir at runtime and complicates
        # code-signing/notarization.
        lib = _find_macos_libmpv()
        if lib:
            params.append(f"--add-binary={lib}{sep}.")
            print(f"Bundling libmpv (and its dependencies) from: {lib}")
        else:
            print("ERROR: libmpv not found. Install it first with 'brew install mpv'.")
            print("A self-contained macOS app cannot be built without it.")
            sys.exit(1)
    else:  # Linux
        params.append("--onefile")
        print("Note: libmpv is expected to be installed system-wide on the target machine.")

    PyInstaller.__main__.run(params)

    if IS_MAC:
        app_path = os.path.join(dist_dir, f"{APP_NAME}.app")
        _configure_macos_file_associations(app_path)
        print()
        _verify_macos_bundle(app_path)
        print(f"\nBuild complete! Check '{app_path}'.")
    else:
        out = os.path.join(dist_dir, APP_NAME)
        if IS_WINDOWS:
            out += ".exe"
        print(f"\nBuild complete! Check '{out}'.")


def clean_build_dirs() -> None:
    """빌드 중간 산출물(build/, dist/, __pycache__, .spec)을 정리한다."""
    for directory in (DEFAULT_WORK_DIR, DEFAULT_DIST_DIR, os.path.join(PROJECT_DIR, "__pycache__")):
        if os.path.exists(directory):
            shutil.rmtree(directory, ignore_errors=True)
    for spec_file in glob.glob(os.path.join(PROJECT_DIR, "*.spec")):
        os.remove(spec_file)


def get_build_artifact():
    if IS_MAC:
        artifact = os.path.join(DEFAULT_DIST_DIR, f"{APP_NAME}.app")
    elif IS_WINDOWS:
        artifact = os.path.join(DEFAULT_DIST_DIR, f"{APP_NAME}.exe")
    else:
        artifact = os.path.join(DEFAULT_DIST_DIR, APP_NAME)
    return artifact if os.path.exists(artifact) else None


def get_path_size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            file_path = os.path.join(root, name)
            if not os.path.islink(file_path):
                total += os.path.getsize(file_path)
    return total


def copy_to_release():
    """빌드된 파일을 release 디렉토리로 복사한다."""
    artifact = get_build_artifact()
    if not artifact:
        print("빌드된 실행 파일을 찾을 수 없습니다.")
        return None

    os.makedirs(RELEASE_DIR, exist_ok=True)
    release_artifact = os.path.join(RELEASE_DIR, os.path.basename(artifact))
    if os.path.exists(release_artifact):
        print(f"기존 산출물 교체: {release_artifact}")
        if os.path.isdir(release_artifact):
            shutil.rmtree(release_artifact)
        else:
            os.remove(release_artifact)

    print("release 디렉토리로 복사 중...")
    if os.path.isdir(artifact):
        shutil.copytree(artifact, release_artifact, symlinks=True)
    else:
        shutil.copy2(artifact, release_artifact)

    file_size = get_path_size(release_artifact) / (1024 * 1024)
    print(f"복사 완료! 파일 크기: {file_size:.1f} MB")
    return release_artifact


def sync_release_docs() -> None:
    os.makedirs(RELEASE_DIR, exist_ok=True)
    for file_name in ("README.md", "requirements.txt"):
        source = os.path.join(PROJECT_DIR, file_name)
        if os.path.exists(source):
            shutil.copy2(source, os.path.join(RELEASE_DIR, file_name))


def create_zip_package(release_artifact: str):
    """배포용 ZIP 패키지를 생성한다."""
    print("ZIP 패키지 생성 중...")

    version = datetime.now().strftime("%Y.%m.%d")
    platform_label = {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(
        SYSTEM_NAME, SYSTEM_NAME or "Unknown"
    )
    zip_path = os.path.join(RELEASE_DIR, f"{APP_NAME}_v{version}_{platform_label}.zip")

    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            if os.path.isdir(release_artifact):
                for root, _dirs, files in os.walk(release_artifact):
                    for name in files:
                        file_path = os.path.join(root, name)
                        arcname = os.path.relpath(file_path, RELEASE_DIR)
                        zipf.write(file_path, arcname)
            else:
                zipf.write(release_artifact, os.path.basename(release_artifact))

            for file_name in ("README.md", "requirements.txt"):
                source = os.path.join(PROJECT_DIR, file_name)
                if os.path.exists(source):
                    zipf.write(source, file_name)

        zip_size = os.path.getsize(zip_path) / (1024 * 1024)
        print(f"ZIP 패키지 생성 완료: {zip_path} ({zip_size:.1f} MB)")
        return zip_path
    except Exception as e:
        print(f"ZIP 패키지 생성 실패: {e}")
        return None


def main() -> bool:
    """빌드 후 release/ 로 결과물을 옮기고, 중간 산출물은 모두 정리한다."""
    clean_build_dirs()

    build()

    release_artifact = copy_to_release()
    if not release_artifact:
        clean_build_dirs()
        return False

    sync_release_docs()
    zip_path = create_zip_package(release_artifact)

    print("최종 정리 중 (빌드 임시 파일 제거)...")
    clean_build_dirs()

    print("=== 빌드 프로세스 완료! ===")
    print(f"결과물: {release_artifact}")
    if zip_path:
        print(f"배포 패키지: {zip_path}")

    return True


if __name__ == "__main__":
    if not main():
        sys.exit(1)
