"""Phone access (ADR 0003): a second listener on this machine's LAN address, running only while the
user has Phone access turned on. The main listener always stays on 127.0.0.1, so Windows only asks
to allow Control on the network once the user opts in."""

import socket
import threading
import time

import uvicorn


def lan_ip() -> str | None:
    """The address other devices on the home network reach this machine at."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))  # UDP connect sends nothing; it only picks the outgoing interface
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") else ip


class LanListener:
    def __init__(self):
        # Set by `control serve`. None means there is no real server to open (e.g. tests), so start()
        # and stop() only have the setting to follow.
        self.port: int | None = None
        self.ip: str | None = None
        self.error: str | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._server and self._server.started)

    @property
    def url(self) -> str | None:
        return f"http://{self.ip}:{self.port}" if self.running else None

    def start(self) -> None:
        with self._lock:
            if self.port is None or self.running:
                return
            if self._thread and self._thread.is_alive():
                # A listener that was told to stop is still shutting down; a second one would clash with it.
                self.error = "Phone access is still stopping. Try again in a moment."
                return
            self.error = None
            ip = lan_ip()
            if ip is None:
                self.error = "This computer isn't connected to a network."
                return
            from .app import app  # the same app as on 127.0.0.1

            config = uvicorn.Config(app, host=ip, port=self.port, lifespan="off", log_level="warning")
            server = uvicorn.Server(config)
            # Its own thread and event loop: uvicorn only installs signal handlers on the main thread,
            # so Ctrl+C still stops the main listener, and this daemon thread goes with it.
            thread = threading.Thread(target=server.run, name="lan-listener", daemon=True)
            thread.start()
            deadline = time.monotonic() + 5
            while thread.is_alive() and not server.started and time.monotonic() < deadline:
                time.sleep(0.05)
            self.ip, self._server, self._thread = ip, server, thread
            if not server.started:
                self.error = f"Couldn't open {ip}:{self.port}. Is another program using that port?"
                self._shut_down()

    def stop(self) -> None:
        with self._lock:
            self.error = None
            self._shut_down()

    def _shut_down(self) -> None:
        """Ask the listener to exit. Its references are kept until the thread has really ended, so a
        slow shutdown (or a slow start that came up late) can't leave an untracked server behind."""
        if self._server:
            self._server.should_exit = True
        if self._thread:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                return
        self._server = self._thread = None


listener = LanListener()
