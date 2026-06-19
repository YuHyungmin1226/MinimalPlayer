import PyInstaller.__main__
import os
import sys
import glob
import subprocess

# Build configuration
ENTRY_POINT = "main.py"
APP_NAME = "MinimalPlayer"

IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


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
    candidates += ["/opt/homebrew/lib", "/usr/local/lib"]
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


def build():
    print(f"Starting build for {APP_NAME} on {sys.platform}...")

    params = [
        ENTRY_POINT,
        "--name=" + APP_NAME,
        "--windowed",   # hide console / build a .app bundle
        "--noconfirm",
        "--clean",
        "--hidden-import=mpv",
    ]

    # PyInstaller uses ';' as the add-binary separator on Windows and ':' elsewhere.
    sep = ";" if IS_WINDOWS else ":"

    if IS_WINDOWS:
        # Single-file portable executable for Windows.
        params.append("--onefile")
        dll_name = "mpv-1.dll"
        if os.path.exists(dll_name):
            params.append(f"--add-binary={dll_name}{sep}.")
        else:
            print(f"Warning: {dll_name} not found in the project root.")
            print("It will be downloaded on first run of the built executable.")
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
        app_path = os.path.join("dist", f"{APP_NAME}.app")
        print()
        _verify_macos_bundle(app_path)
        print(f"\nBuild complete! Check '{app_path}'.")
    else:
        out = f"dist/{APP_NAME}"
        if IS_WINDOWS:
            out += ".exe"
        print(f"\nBuild complete! Check '{out}'.")


if __name__ == "__main__":
    build()
