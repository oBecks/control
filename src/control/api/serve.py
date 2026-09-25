"""Starting the Engine's listeners, shared by `control serve` and the Desktop App."""

import logging

from ..engine.registry import Registry
from . import access, lan


class QuietReads(logging.Filter):
    """Access log: keep changes and errors, drop successful reads. The UI polls every few seconds,
    so logging every read would bury what matters."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            _client, method, _path, _http, status = record.args
            return not (method in ("GET", "HEAD") and int(status) < 400)
        except (TypeError, ValueError):
            return True


def prepare(port: int) -> None:
    """Call before the main listener starts: quiet the access log, and reopen Phone access if the
    user left it on."""
    logging.getLogger("uvicorn.access").addFilter(QuietReads())
    lan.listener.port = port
    r = Registry()
    try:
        phone_access = r.setting(access.PHONE_ACCESS, False)
    finally:
        r.close()
    if phone_access:
        lan.listener.start()
