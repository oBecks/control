"""The LAN listener behind Phone access, run for real on loopback addresses."""

import socket
import threading
import urllib.request
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from control.api import app as api
from control.api import lan


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def port_is_free(ip: str, port: int) -> bool:
    with socket.socket() as s:
        try:
            s.bind((ip, port))
        except OSError:
            return False
    return True


@pytest.fixture
def addresses(monkeypatch):
    """What lan_ips() reports; change the list to move this computer to other addresses."""
    ips = ["127.0.0.1"]
    monkeypatch.setattr(lan, "lan_ips", lambda: list(ips))
    return ips


@pytest.fixture
def listener(tmp_path, monkeypatch, addresses):
    monkeypatch.setenv("CONTROL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(lan, "WATCH_EVERY", 3600)  # the tests call refresh() themselves
    ll = lan.LanListener()
    ll.port = free_port()
    monkeypatch.setattr(lan, "listener", ll)  # the gate allows the Hosts it listens on
    yield ll
    ll.stop()


def get(url: str) -> int:
    with urllib.request.urlopen(f"{url}/api/access/phone", timeout=5) as resp:
        return resp.status


def test_start_listens_and_a_request_reaches_the_app(listener):
    listener.start()
    assert listener.running and listener.error is None
    assert listener.url == f"http://127.0.0.1:{listener.port}"
    assert get(listener.url) == 200


def test_stop_ends_the_thread_and_frees_the_port(listener):
    listener.start()
    thread = listener._thread
    listener.stop()
    assert not thread.is_alive() and not listener.running and listener.url is None
    assert port_is_free("127.0.0.1", listener.port)


def test_start_is_refused_while_the_old_listener_is_still_stopping(listener):
    done = threading.Event()
    slow = threading.Thread(target=done.wait, daemon=True)
    slow.start()
    listener._thread = slow  # a listener that was told to stop but hasn't ended yet
    try:
        listener.start()
        assert listener.error == "Phone access is still stopping. Try again in a moment."
        assert not listener.running
    finally:
        done.set()
        slow.join()
        listener._thread = None


def test_a_taken_port_is_an_error_and_leaves_nothing_running(listener):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", listener.port))
        taken.listen()
        listener.start()
        assert listener.error.startswith(f"Couldn't open 127.0.0.1:{listener.port}")
        assert not listener.running and listener._thread is None


def test_no_network_is_an_error(listener, addresses):
    addresses.clear()
    listener.start()
    assert listener.error == "This computer isn't connected to a network." and not listener.running


def test_listens_on_every_address(listener, addresses):
    addresses[:] = ["127.0.0.1", "127.0.0.2"]
    listener.start()
    assert listener.ips == ["127.0.0.1", "127.0.0.2"] and listener.url == f"http://127.0.0.1:{listener.port}"
    assert get(f"http://127.0.0.2:{listener.port}") == 200


def test_an_address_that_cannot_open_is_skipped(listener, addresses):
    addresses[:] = ["192.0.2.1", "127.0.0.1"]  # not this computer's, so it can't be bound
    listener.start()
    assert listener.ips == ["127.0.0.1"] and listener.error is None
    thread = listener._thread
    listener.refresh()
    assert listener._thread is thread  # the same addresses: not reopened


def test_follows_a_changed_address(listener, addresses):
    listener.start()
    old = listener.url
    listener.refresh()  # nothing changed
    assert listener.url == old and listener.moved_from is None

    addresses[:] = ["127.0.0.2"]
    listener.refresh()
    assert listener.url == f"http://127.0.0.2:{listener.port}" and listener.moved_from == old
    assert get(listener.url) == 200
    assert port_is_free("127.0.0.1", listener.port)

    listener.stop()
    assert listener.moved_from is None


def test_opens_once_the_computer_is_on_a_network_again(listener, addresses):
    addresses.clear()
    listener.start()
    assert listener.error
    addresses.append("127.0.0.1")
    listener.refresh()
    assert listener.running and listener.error is None and listener.moved_from is None


def test_refresh_does_nothing_while_phone_access_is_off(listener):
    listener.refresh()
    assert not listener.running and listener.error is None


def test_the_gate_accepts_every_listened_address(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(lan.listener, "ips", ["192.168.1.20", "10.0.0.5"])
    for host, status in (("192.168.1.20", 200), ("10.0.0.5", 200), ("evil.example", 400)):
        pc = TestClient(api.app, base_url=f"http://{host}:8321", client=("127.0.0.1", 50000))
        assert pc.get("/api/access/phone").status_code == status, host


def test_lan_ips_prefers_wifi_and_ethernet_and_skips_virtual_adapters(monkeypatch):
    def nic(*ips):
        return [SimpleNamespace(family=socket.AF_INET, address=ip) for ip in ips]

    adapters = {
        "vEthernet (WSL)": nic("172.24.16.1"),
        "OpenVPN TAP-Windows6": nic("10.8.0.2"),
        "Local Area Connection 2": nic("10.20.0.4"),
        "‏‏Wi-Fi": nic("192.168.1.20", "169.254.3.3"),
        "Ethernet 2": nic("192.168.1.21"),
        "Tailscale": nic("100.101.1.1"),
        "Unplugged Ethernet": nic("192.168.5.5"),
        "Loopback Pseudo-Interface 1": nic("127.0.0.1"),
    }
    up = {name: SimpleNamespace(isup=name != "Unplugged Ethernet") for name in adapters}
    monkeypatch.setattr(lan.psutil, "net_if_addrs", lambda: adapters)
    monkeypatch.setattr(lan.psutil, "net_if_stats", lambda: up)
    monkeypatch.setattr(lan, "_default_route_ip", lambda: "192.168.1.21")
    assert lan.lan_ips() == ["192.168.1.21", "192.168.1.20", "10.20.0.4"]
