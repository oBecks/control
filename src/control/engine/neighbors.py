"""Who answers on the home network right now, for Presence (ADR 0014).

A sleeping phone doesn't answer ARP until something wakes it, so `nudge` sends each address a UDP
packet to port 5353 (mDNS, which a sleeping iPhone wakes for) and Windows asks for its MAC on the
way. A few seconds later `table` reads Windows' neighbour table, where only a *Reachable* entry means
the device answered just now: `arp -a` also lists *Stale* entries for devices that left minutes ago.
Nothing here needs admin rights.
"""

import ctypes
import ipaddress
import socket
import sys
from dataclasses import dataclass

NUDGE_PORT = 5353
SETTLE = 7  # seconds from a nudge until Windows knows: it waits 5 s (Delay), then asks (Probe)
MAX_SWEEP = 1024  # addresses: a sweep covers a home's subnet, never a big office network

# Windows' NL_NEIGHBOR_STATE
UNREACHABLE, INCOMPLETE, PROBE, DELAY, STALE, REACHABLE, PERMANENT = range(7)


@dataclass(frozen=True)
class Neighbor:
    ip: str
    mac: str  # "4a:84:cf:32:5e:d9"
    reachable: bool  # answered just now


def normal_mac(mac: str) -> str:
    """"4A-84-CF-32-5E-D9" -> "4a:84:cf:32:5e:d9"; ValueError when it isn't a MAC."""
    parts = mac.strip().lower().replace("-", ":").split(":")
    if len(parts) != 6 or any(len(p) != 2 or any(c not in "0123456789abcdef" for c in p) for p in parts):
        raise ValueError(f"'{mac}' isn't a Wi-Fi (MAC) address")
    return ":".join(parts)


def is_private(mac: str) -> bool:
    """A locally administered MAC: what phones make up per network instead of their real one."""
    return bool(int(mac[:2], 16) & 0x02)


def nudge(ips) -> None:
    """Wake each address with one small UDP packet; any answer (or ARP reply) lands in the table."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        for ip in ips:
            try:
                s.sendto(b"\0", (ip, NUDGE_PORT))
            except OSError:
                pass  # e.g. no route: nothing to wake there


def subnet_hosts(own_ips) -> list[str]:
    """Every other address on this PC's home subnets (assumed /24, as home routers hand out)."""
    hosts: list[str] = []
    for own in own_ips:
        net = ipaddress.ip_network(f"{own}/24", strict=False)
        hosts += [str(h) for h in net.hosts() if str(h) != own]
    return list(dict.fromkeys(hosts))[:MAX_SWEEP]


class _Row(ctypes.Structure):  # MIB_IPNET_ROW2
    _fields_ = [("address", ctypes.c_ubyte * 28), ("if_index", ctypes.c_ulong), ("if_luid", ctypes.c_ulonglong),
                ("mac", ctypes.c_ubyte * 32), ("mac_length", ctypes.c_ulong), ("state", ctypes.c_int),
                ("flags", ctypes.c_ubyte), ("reachability", ctypes.c_ulong)]


def table() -> list[Neighbor]:
    """Windows' IPv4 neighbour table, leaving out entries without a MAC. Empty elsewhere."""
    if sys.platform != "win32":
        return []
    iphlpapi = ctypes.windll.iphlpapi
    pointer = ctypes.c_void_p()
    if iphlpapi.GetIpNetTable2(socket.AF_INET, ctypes.byref(pointer)) != 0:
        return []
    try:
        count = ctypes.c_ulong.from_address(pointer.value).value
        rows = (_Row * count).from_address(pointer.value + 8)  # the rows start 8-aligned after the count
        out = []
        for row in rows:
            mac = bytes(row.mac[:row.mac_length])
            if len(mac) != 6 or not any(mac) or mac == b"\xff" * 6 or mac[0] & 0x01:  # none, broadcast, multicast
                continue
            out.append(Neighbor(socket.inet_ntoa(bytes(row.address[4:8])), ":".join(f"{b:02x}" for b in mac),
                                row.state == REACHABLE))
        return out
    finally:
        iphlpapi.FreeMibTable(pointer)
