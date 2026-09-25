"""Passive Tuya discovery: Tuya devices broadcast an announcement on UDP 6666/6667
roughly every 5 seconds. We listen and decode it; no Local Key is needed for that,
but one is needed (via a Link) before the device can be controlled."""

import json
import select
import socket
import time

from tinytuya.core.udp_helper import decrypt_udp

from ..found_device import Category, FoundDevice, Readiness

PORTS = (6666, 6667)


def _open(port: int) -> socket.socket | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind(("", port))
    except OSError:
        sock.close()
        return None
    return sock


def _decode(data: bytes) -> dict | None:
    try:
        payload = decrypt_udp(data)
        if isinstance(payload, bytes):
            payload = payload.decode()
        return json.loads(payload)
    except Exception:
        return None


def scan(timeout: float) -> list[FoundDevice]:
    socks = [s for s in (_open(p) for p in PORTS) if s]
    if not socks:
        raise OSError(f"could not listen on UDP {PORTS} (another Tuya app may be using them)")

    seen: dict[str, dict] = {}
    deadline = time.monotonic() + timeout
    try:
        while (remaining := deadline - time.monotonic()) > 0:
            readable, _, _ = select.select(socks, [], [], remaining)
            for sock in readable:
                data, addr = sock.recvfrom(4096)
                info = _decode(data)
                if info and "gwId" in info:
                    info.setdefault("ip", addr[0])
                    seen[info["gwId"]] = info
    finally:
        for s in socks:
            s.close()

    return [
        FoundDevice(
            brand="Tuya",
            ip=info["ip"],
            uid=f"tuya:{dev_id}",
            # The broadcast carries no device kind; Category is known only after a Link.
            category=Category.UNKNOWN,
            readiness=Readiness.NEEDS_LINK,
            note=f"product {info.get('productKey', '?')}, protocol v{info.get('version', '?')}",
            raw=info,
        )
        for dev_id, info in seen.items()
    ]
