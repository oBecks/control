"""Seals Link secrets (e.g. Tuya Local Keys) before they reach the Registry's database.

On Windows this is DPAPI: only the same Windows user on the same PC can unseal, so a copied
control.db (backup, cloud sync, another account, a stolen disk) leaks nothing. It doesn't stop
code already running as that user. Elsewhere (CI, a future always-on box) text passes through
unchanged until that platform gets its own store."""

import base64
import sys

PREFIX = "dpapi:"
_ENTROPY = b"Control Link secret"  # ties sealed blobs to this app, not to any DPAPI caller


def seal(text: str) -> str:
    if sys.platform != "win32":
        return text
    return PREFIX + base64.b64encode(_dpapi(text.encode(), protect=True)).decode()


def unseal(stored: str) -> str:
    """Also accepts unsealed text, which is what databases from before sealing hold."""
    if not stored.startswith(PREFIX):
        return stored
    return _dpapi(base64.b64decode(stored[len(PREFIX):]), protect=False).decode()


def is_sealed(stored: str) -> bool:
    return stored.startswith(PREFIX)


def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    data_buf, entropy_buf = ctypes.create_string_buffer(data, len(data)), ctypes.create_string_buffer(_ENTROPY)
    source = Blob(len(data), ctypes.cast(data_buf, ctypes.POINTER(ctypes.c_char)))
    entropy = Blob(len(_ENTROPY), ctypes.cast(entropy_buf, ctypes.POINTER(ctypes.c_char)))
    out = Blob()
    UI_FORBIDDEN = 0x1
    if not fn(ctypes.byref(source), None, ctypes.byref(entropy), None, None, UI_FORBIDDEN, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "DPAPI " + ("seal" if protect else "unseal") + " failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)
