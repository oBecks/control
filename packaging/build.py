"""Build dist/Control/Control.exe (PyInstaller) and dist/ControlSetup.exe (Inno Setup), ADR 0004.

Needs the `desktop` and `build` extras, a built web UI (npm --prefix web run build) and, for the
installer, Inno Setup 6 (https://jrsoftware.org/isinfo.php, or set ISCC to its ISCC.exe).
Usage: python packaging/build.py [--exe-only]"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"


def iscc() -> str | None:
    candidates = [
        os.environ.get("ISCC"),
        shutil.which("iscc"),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    ]
    return next((str(c) for c in candidates if c and Path(c).is_file()), None)


def main() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    import control

    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(DIST), "--workpath", str(ROOT / "build" / "pyinstaller"),
                    str(ROOT / "packaging" / "Control.spec")], check=True)
    print(f"Built {DIST / 'Control' / 'Control.exe'}")
    if "--exe-only" in sys.argv:
        return
    compiler = iscc()
    if compiler is None:
        sys.exit("Inno Setup 6 not found: install it, or set ISCC to its ISCC.exe")
    subprocess.run([compiler, f"/DAppVersion={control.__version__}", str(ROOT / "packaging" / "ControlSetup.iss")],
                   check=True)
    print(f"Built {DIST / 'ControlSetup.exe'}")


if __name__ == "__main__":
    main()
