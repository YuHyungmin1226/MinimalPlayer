import hashlib
import os
import subprocess
import sys
import urllib.request

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from constants import MPV_DLL_NAME, MPV_DLL_SHA256, MPV_DLL_URL


IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def verify_mpv_dll(path: str) -> bool:
    return os.path.exists(path) and sha256_file(path) == MPV_DLL_SHA256


def check_and_download_mpv():
    dll_path = os.path.join(BASE_DIR, MPV_DLL_NAME)
    if os.path.exists(dll_path):
        if verify_mpv_dll(dll_path):
            return
        _ = QMessageBox.critical(
            None,
            "Invalid mpv DLL",
            f"Existing {MPV_DLL_NAME} failed SHA256 verification.\n"
            "It will be removed, and a clean copy will be downloaded.",
        )
        os.remove(dll_path)

    if QApplication.instance() is None:
        QApplication(sys.argv)

    msg = QMessageBox()
    msg.setIcon(QMessageBox.Icon.Information)
    msg.setWindowTitle("Download Required")
    msg.setText(f"Download required file ({MPV_DLL_NAME}, ~118MB) for first run.\nDo you want to continue?")
    msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if msg.exec() != QMessageBox.StandardButton.Yes:
        sys.exit(0)

    progress = QProgressDialog(f"Downloading {MPV_DLL_NAME}...", "Cancel", 0, 100)
    progress.setWindowTitle("Download Progress")
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.resize(400, 100)
    progress.show()

    tmp_path = dll_path + ".tmp"

    def report(blocknum: int, blocksize: int, totalsize: int) -> None:
        read_so_far = blocknum * blocksize
        if totalsize > 0:
            progress.setValue(int(read_so_far * 100 / totalsize))
            QApplication.processEvents()
        if progress.wasCanceled():
            raise RuntimeError("Download canceled.")

    try:
        _ = urllib.request.urlretrieve(MPV_DLL_URL, tmp_path, report)
        if not verify_mpv_dll(tmp_path):
            raise RuntimeError("Downloaded file failed SHA256 verification.")
        os.replace(tmp_path, dll_path)
    except Exception as e:
        if str(e) != "Download canceled.":
            _ = QMessageBox.critical(
                None,
                "Download Failed",
                f"An error occurred during download:\n{e}\n\n"
                "Please try again, or download it manually from the GitHub Release page."
            )
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        sys.exit(1)

    progress.setValue(100)


def find_libmpv_dir() -> str | None:
    candidates: list[str] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(meipass)
        candidates.append(BASE_DIR)
        candidates.append(os.path.join(BASE_DIR, os.pardir, "Frameworks"))
    else:
        candidates.append(BASE_DIR)

    if IS_MAC:
        try:
            prefix = subprocess.check_output(["brew", "--prefix"], text=True, stderr=subprocess.DEVNULL).strip()
            if prefix:
                candidates.append(os.path.join(prefix, "lib"))
        except Exception:
            pass
        candidates += ["/opt/homebrew/lib", "/usr/local/lib"]
        libnames = ["libmpv.dylib", "libmpv.2.dylib", "libmpv.1.dylib"]
    else:
        candidates += ["/usr/lib", "/usr/local/lib", "/usr/lib/x86_64-linux-gnu", "/usr/lib64"]
        libnames = ["libmpv.so", "libmpv.so.2", "libmpv.so.1"]

    for directory in candidates:
        for name in libnames:
            if os.path.isfile(os.path.join(directory, name)):
                return os.path.abspath(directory)
    return None


def prepare_mpv_library():
    if IS_WINDOWS:
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.exists(os.path.join(meipass, MPV_DLL_NAME)):
            os.environ["PATH"] = meipass + os.pathsep + os.environ["PATH"]
            return
        os.environ["PATH"] = BASE_DIR + os.pathsep + os.environ["PATH"]
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(BASE_DIR)
            except Exception:
                pass
        check_and_download_mpv()
        return

    lib_dir = find_libmpv_dir()
    if lib_dir:
        env_key = "DYLD_FALLBACK_LIBRARY_PATH" if IS_MAC else "LD_LIBRARY_PATH"
        existing = os.environ.get(env_key, "")
        os.environ[env_key] = lib_dir + (os.pathsep + existing if existing else "")
