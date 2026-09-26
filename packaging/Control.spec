# PyInstaller spec for Control.exe (ADR 0004). Run through `python packaging/build.py`.
# One folder, not one file: it starts faster (nothing to unpack on each launch), the installer ships
# the folder anyway, and one-file exes trip antivirus heuristics more often.
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                 VarFileInfo, VarStruct, VSVersionInfo)

import control

root = Path(SPECPATH).parent
icon = root / "src" / "control" / "desktop" / "control.ico"
ui = root / "web" / "build"
if not (ui / "index.html").is_file():
    raise SystemExit("Build the web UI first: npm --prefix web run build")

numbers = tuple(int(n) for n in control.__version__.split(".")) + (0,)
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "Control"),
            StringStruct("FileDescription", "Control"),  # the name Task Manager shows
            StringStruct("FileVersion", control.__version__),
            StringStruct("ProductName", "Control"),
            StringStruct("ProductVersion", control.__version__),
            StringStruct("OriginalFilename", "Control.exe"),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

a = Analysis(
    [str(root / "packaging" / "control_app.py")],
    pathex=[str(root / "src")],
    datas=[(str(ui), "web"), (str(icon), "control/desktop")],
    # uvicorn picks its loop and protocol implementations at run time; zeroconf imports its compiled
    # parts by name.
    hiddenimports=collect_submodules("uvicorn") + collect_submodules("zeroconf"),
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Control", icon=str(icon), version=version,
    console=False, upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Control", upx=False)
