"""Tuya Link: sign in once with the Smart Life app (QR code) to fetch each device's
Local Key, name and kind. After that, control is local; the cloud isn't needed.

Uses Tuya's official device-sharing SDK. NOTE: it identifies as Home Assistant's
registered app (client id below), the only place Control does so. Fine for personal
use; blocks a public release. See docs/adr/0002-tuya-link-borrows-home-assistant-identity.md.
"""

import time
from dataclasses import dataclass, field

from tuya_sharing import LoginControl, Manager

from ..found_device import Category

CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
SCHEMA = "haauthorize"

# Tuya product category codes -> our Categories. Unlisted codes stay UNKNOWN.
_CATEGORIES = {
    **dict.fromkeys(["dj", "dd", "dc", "fwd", "xdd", "fsd", "tgq", "tgkg", "sxd", "gyd"], Category.LIGHT),
    **dict.fromkeys(["cz", "pc", "kg", "tdq", "znjdq"], Category.PLUG),
    **dict.fromkeys(["kt", "ktkzq", "wk", "wkf", "qn", "fs", "cs", "jsq"], Category.CLIMATE),
    **dict.fromkeys(["infrared_tv", "tv", "sp"], Category.MEDIA),
}


@dataclass
class LinkedDevice:
    device_id: str
    name: str
    local_key: str
    category: Category
    tuya_category: str
    product_name: str
    extra: dict = field(default_factory=dict)

    @property
    def uid(self) -> str:
        return f"tuya:{self.device_id}"


class LinkError(Exception):
    pass


def start(user_code: str) -> tuple[str, str]:
    """Ask Tuya for a login QR. Returns (token, qr_content)."""
    resp = LoginControl().qr_code(CLIENT_ID, SCHEMA, user_code)
    if not resp.get("success"):
        raise LinkError(f"Tuya refused the User Code: {resp.get('msg') or resp}")
    token = resp["result"]["qrcode"]
    return token, f"tuyaSmart--qrLogin?token={token}"


def check_login(token: str, user_code: str) -> dict | None:
    """One non-blocking check: the login info once the QR is confirmed, else None."""
    ok, info = LoginControl().login_result(token, CLIENT_ID, user_code)
    return info if ok else None


def wait_for_login(token: str, user_code: str, timeout: float = 180, poll: float = 2) -> dict:
    """Block until the user confirms the login in Smart Life, or `timeout` passes."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if info := check_login(token, user_code):
            return info
        time.sleep(poll)
    raise LinkError("timed out waiting for the QR code to be confirmed in Smart Life")


def fetch_devices(login_info: dict, user_code: str) -> list[LinkedDevice]:
    token_response = {
        "t": login_info["t"],
        "uid": login_info["uid"],
        "expire_time": login_info["expire_time"],
        "access_token": login_info["access_token"],
        "refresh_token": login_info["refresh_token"],
    }
    manager = Manager(CLIENT_ID, user_code, login_info["terminal_id"], login_info["endpoint"], token_response)
    manager.update_device_cache()
    return [
        LinkedDevice(
            device_id=d.id,
            name=d.name,
            local_key=d.local_key,
            category=_CATEGORIES.get(d.category, Category.UNKNOWN),
            tuya_category=d.category,
            product_name=d.product_name,
            # Data points (what the device can do); the Tuya adapter will need these.
            extra={"status": dict(d.status), "sub": d.sub, "product_id": d.product_id},
        )
        for d in manager.device_map.values()
    ]
