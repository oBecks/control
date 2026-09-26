"""The optional second step of an Android TV Link: adb over the network (ADR 0008).

With the box's developer mode on, and Control allowed once on the TV, Control can list the apps
actually installed and open any of them, including apps that declare no link (e.g. yes+), which the
Android TV Remote protocol can't open. Without it, Streamers work as before.

Control has one adb key for every box; its private half is sealed by `vault`, like a Local Key.
"""

import re
import tempfile
from pathlib import Path

from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.exceptions import AdbConnectionError, AdbTimeoutError, DeviceAuthError

from .. import vault
from ..errors import DeviceUnreachable
from ..registry import default_db_path

PORT = 5555
_LAUNCHER = "-a android.intent.action.MAIN -c android.intent.category.LEANBACK_LAUNCHER"
_PACKAGE = re.compile(r"^[A-Za-z][\w.]*$")


class NotAllowed(Exception):
    """Debugging is off on the box, or nobody pressed Allow on the TV."""


def _signer() -> PythonRSASigner:
    folder = default_db_path().parent / "androidtv"
    private, public = folder / "adbkey.sealed", folder / "adbkey.pub"
    if not (private.is_file() and public.is_file()):
        folder.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "adbkey"
            keygen(str(path))
            private.write_text(vault.seal(path.read_text()), encoding="utf-8")
            public.write_text(Path(str(path) + ".pub").read_text(), encoding="utf-8")
    return PythonRSASigner(public.read_text(encoding="utf-8"), vault.unseal(private.read_text(encoding="utf-8")))


def _connected(ip: str, wait_for_allow: float) -> AdbDeviceTcp:
    device = AdbDeviceTcp(ip, PORT, default_transport_timeout_s=5.0)
    try:
        device.connect(rsa_keys=[_signer()], auth_timeout_s=wait_for_allow)
    except (ConnectionRefusedError, AdbConnectionError) as exc:
        device.close()
        raise NotAllowed(f"debugging isn't on at {ip}: turn on Network debugging in its Developer options") from exc
    except (DeviceAuthError, AdbTimeoutError) as exc:
        device.close()
        raise NotAllowed("the TV didn't allow Control: choose Allow when it asks, then try again") from exc
    except OSError as exc:
        device.close()
        raise DeviceUnreachable(f"adb at {ip}: {type(exc).__name__}") from exc
    return device


def allow(ip: str) -> list[str]:
    """Connect, waiting for the user to press Allow on the TV. Returns the installed apps' packages."""
    device = _connected(ip, wait_for_allow=60.0)
    try:
        return _installed(device)
    finally:
        device.close()


def installed(ip: str) -> list[str]:
    device = _connected(ip, wait_for_allow=5.0)
    try:
        return _installed(device)
    finally:
        device.close()


def _installed(device: AdbDeviceTcp) -> list[str]:
    """Apps with a TV launcher entry, i.e. those a person can open, in the box's own order."""
    out = device.shell(f"cmd package query-activities --brief {_LAUNCHER}", read_timeout_s=10)
    packages = []
    for line in out.splitlines():
        line = line.strip()
        if "/" in line and not line.startswith(("priority", "Activity")):
            package = line.split("/", 1)[0]
            if _PACKAGE.match(package) and package not in packages:
                packages.append(package)
    return packages


def launch(ip: str, package: str) -> None:
    if not _PACKAGE.match(package):
        raise ValueError(f"'{package}' isn't a package name")
    device = _connected(ip, wait_for_allow=5.0)
    try:
        out = device.shell(f"monkey -p {package} -c android.intent.category.LEANBACK_LAUNCHER 1", read_timeout_s=10)
    finally:
        device.close()
    if "No activities found" in out or "monkey aborted" in out:
        raise ValueError(f"'{package}' isn't installed on this box")
