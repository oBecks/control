"""Android TV / Google TV over the Android TV Remote protocol (`androidtvremote2`, TCP 6466/6467).

The library is asyncio-based and keeps one connection per device that pushes power, the open app
and volume as they change. The Engine is threaded, so every connection lives on one background event
loop and the sync adapter below hands work to it.

A Link registers Control's client certificate with the device (the device shows a PIN). One
certificate serves every device; its private key is kept encrypted, with the password sealed by
`vault`, like a Local Key.
"""

import asyncio
import secrets
import ssl
import threading
from pathlib import Path

from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth
from androidtvremote2.certificate_generator import generate_selfsigned_cert
from cryptography.hazmat.primitives import serialization

from .. import vault
from ..errors import DeviceUnreachable
from ..registry import default_db_path
from ..streamer import StreamerState, key_code

CLIENT_NAME = "Control"  # shown on the TV while Linking
_CONNECT_TIMEOUT = 6.0
_CALL_TIMEOUT = 20.0


# --- Control's client identity --------------------------------------------------


def _identity_dir() -> Path:
    return default_db_path().parent / "androidtv"


def _identity() -> tuple[str, str, str]:
    """(certfile, keyfile, key password), created on first use."""
    folder = _identity_dir()
    cert, key, sealed = folder / "client.crt", folder / "client.key", folder / "client.pass"
    if not (cert.is_file() and key.is_file() and sealed.is_file()):
        folder.mkdir(parents=True, exist_ok=True)
        cert_pem, key_pem = generate_selfsigned_cert(CLIENT_NAME)
        password = secrets.token_urlsafe(32)
        private = serialization.load_pem_private_key(key_pem, password=None)
        encrypted = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(password.encode()),
        )
        cert.write_bytes(cert_pem)
        key.write_bytes(encrypted)
        sealed.write_text(vault.seal(password), encoding="utf-8")
    return str(cert), str(key), vault.unseal(sealed.read_text(encoding="utf-8"))


class _Remote(AndroidTVRemote):
    """Loads the client key with its password instead of from a plain key file."""

    def __init__(self, host: str, loop: asyncio.AbstractEventLoop):
        certfile, keyfile, self._password = _identity()
        super().__init__(CLIENT_NAME, certfile, keyfile, host, loop=loop)
        self.available = False
        self.add_is_available_updated_callback(self._set_available)

    def _set_available(self, available: bool) -> None:
        self.available = available

    async def _create_ssl_context(self) -> ssl.SSLContext:
        if self._ssl_context is None:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            ctx.load_cert_chain(self._certfile, self._keyfile, password=self._password)
            self._ssl_context = ctx
        return self._ssl_context


# --- The background event loop -----------------------------------------------------

_loop: asyncio.AbstractEventLoop | None = None
_loop_lock = threading.Lock()


def _run(coro, timeout: float = _CALL_TIMEOUT):
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="android-tv", daemon=True).start()
    return asyncio.run_coroutine_threadsafe(coro, _loop).result(timeout)


# --- Connections (touched only on the loop) ----------------------------------------

_remotes: dict[str, _Remote] = {}


async def _connected(uid: str, ip: str) -> _Remote:
    remote = _remotes.get(uid)
    if remote is not None and remote.host == ip and remote.available:
        return remote
    if remote is not None:
        remote.disconnect()  # moved, or lost: try now rather than wait for its backoff
        del _remotes[uid]
    remote = _Remote(ip, asyncio.get_running_loop())
    try:
        await asyncio.wait_for(remote.async_connect(), _CONNECT_TIMEOUT)
    except InvalidAuth:
        remote.disconnect()
        raise DeviceUnreachable(f"the device at {ip} no longer accepts Control: Link it again") from None
    except (CannotConnect, ConnectionClosed, asyncio.TimeoutError, OSError) as exc:
        remote.disconnect()
        raise DeviceUnreachable(f"Android TV at {ip}: {type(exc).__name__}") from None
    remote.available = True
    remote.keep_reconnecting()
    _remotes[uid] = remote
    return remote


def _state(remote: _Remote) -> StreamerState:
    volume = remote.volume_info
    if volume and not volume["max"]:
        volume = None  # e.g. a Shield whose TV handles volume over HDMI: level unknown
    return StreamerState(
        on=bool(remote.is_on),
        app=remote.current_app or None,
        volume=volume["level"] if volume else None,
        volume_max=volume["max"] if volume else None,
        muted=volume["muted"] if volume else None,
    )


class AndroidTVStreamer:
    def __init__(self, uid: str, ip: str):
        self._uid, self._ip = uid, ip
        _run(_connected(uid, ip))  # fail fast, like the other adapters

    def _do(self, action):
        async def go():
            remote = await _connected(self._uid, self._ip)
            try:
                return await action(remote)
            except ConnectionClosed:
                raise DeviceUnreachable(f"Android TV at {self._ip} dropped the connection") from None

        return _run(go())

    def get_state(self) -> StreamerState:
        async def read(remote):
            return _state(remote)

        return self._do(read)

    def set_power(self, on: bool) -> None:
        async def power(remote):
            if bool(remote.is_on) == on:
                return
            remote.send_key_command("POWER")
            for _ in range(30):  # the device reports the change a moment later
                await asyncio.sleep(0.1)
                if bool(remote.is_on) == on:
                    return

        self._do(power)

    def press(self, button: str) -> None:
        code = key_code(button)

        async def press(remote):
            remote.send_key_command(code)

        self._do(press)

    def open_app(self, app: str) -> None:
        """A link opens directly. A bare package goes through its Play Store page, whose focused
        button is Open when it's installed (ADR 0008): boxes refuse to open a package directly."""

        async def launch(remote):
            if "://" in app:
                remote.send_launch_app_command(app)
                return
            remote.send_launch_app_command(f"market://details?id={app}")
            if not await _until(lambda: remote.current_app == _PLAY_STORE):
                raise ValueError("the Play Store didn't open")
            await asyncio.sleep(1.5)  # let the page draw, so OK lands on its Open button
            remote.send_key_command("DPAD_CENTER")
            if not await _until(lambda: remote.current_app == app):
                raise ValueError(f"'{app}' didn't open from the Play Store; is it installed?")

        self._do(launch)


_PLAY_STORE = "com.android.vending"


async def _until(ok, seconds: float = 6.0) -> bool:
    for _ in range(int(seconds * 10)):
        if ok():
            return True
        await asyncio.sleep(0.1)
    return ok()


def forget(uid: str) -> None:
    """Close a forgotten Device's connection."""

    async def close():
        remote = _remotes.pop(uid, None)
        if remote is not None:
            remote.disconnect()

    if _loop is not None:
        _run(close())


# --- Linking --------------------------------------------------------------------------

_pairing: dict[str, _Remote] = {}  # uid -> a Link in progress


def start_link(uid: str, ip: str) -> None:
    """Ask the device to show a PIN on the TV."""

    async def start():
        old = _pairing.pop(uid, None)
        if old is not None:
            old.disconnect()
        remote = _Remote(ip, asyncio.get_running_loop())
        try:
            await asyncio.wait_for(remote.async_start_pairing(), _CONNECT_TIMEOUT)
        except (CannotConnect, ConnectionClosed, asyncio.TimeoutError, OSError) as exc:
            remote.disconnect()
            raise DeviceUnreachable(f"Android TV at {ip}: {type(exc).__name__}") from None
        _pairing[uid] = remote

    _run(start())


def finish_link(uid: str, ip: str, pin: str) -> dict:
    """Send the PIN. Returns what the device says about itself ({"manufacturer", "model"})."""

    async def finish():
        remote = _pairing.get(uid)
        if remote is None:
            raise LookupError("no Link in progress for this device; start again")
        try:
            await asyncio.wait_for(remote.async_finish_pairing(pin.strip().upper()), _CONNECT_TIMEOUT)
        except InvalidAuth:
            raise ValueError("that code didn't match; check the code on the TV and try again") from None
        except (ConnectionClosed, asyncio.TimeoutError):
            _pairing.pop(uid, None)
            remote.disconnect()
            raise ValueError("the TV closed the code; start again") from None
        _pairing.pop(uid, None)
        connected = await _connected(uid, ip)
        info = connected.device_info or {}
        return {"manufacturer": info.get("manufacturer", ""), "model": info.get("model", "")}

    return _run(finish(), timeout=_CALL_TIMEOUT * 2)


def cancel_link(uid: str) -> None:
    async def cancel():
        remote = _pairing.pop(uid, None)
        if remote is not None:
            remote.disconnect()

    if _loop is not None:
        _run(cancel())
