import pytest

from control.engine import connect
from control.engine.errors import DeviceUnreachable
from control.engine.found_device import Category, FoundDevice, Readiness
from control.engine.registry import Registry
from control.engine.scan import ScanResult


def bulb(ip: str, uid: str = "yeelight:1", name: str = "") -> FoundDevice:
    return FoundDevice("Yeelight", ip, uid, Category.LIGHT, Readiness.READY, name=name, model="color")


def tuya(ip: str) -> FoundDevice:
    return FoundDevice("Tuya", ip, "tuya:abc", Category.UNKNOWN, Readiness.NEEDS_LINK)


@pytest.fixture
def registry(tmp_path):
    r = Registry(tmp_path / "test.db")
    yield r
    r.close()


def test_first_scan_adds_devices_as_new(registry):
    report = registry.merge_scan([bulb("10.0.0.2"), tuya("10.0.0.3")])
    assert sorted(report.added) == ["tuya:abc", "yeelight:1"]
    assert all(d.is_new and d.online for d in registry.all())


def test_ip_change_keeps_identity_and_user_name(registry):
    registry.merge_scan([bulb("10.0.0.2")])
    registry.rename("yeelight:1", "Desk lamp")
    report = registry.merge_scan([bulb("10.0.0.9")])
    assert report.added == []
    assert report.moved == {"yeelight:1": ("10.0.0.2", "10.0.0.9")}
    d = registry.get("yeelight:1")
    assert (d.ip, d.name) == ("10.0.0.9", "Desk lamp")


def test_missing_device_goes_offline_and_comes_back(registry):
    registry.merge_scan([bulb("10.0.0.2")])
    assert registry.merge_scan([]).missing == ["yeelight:1"]
    assert not registry.get("yeelight:1").online
    registry.merge_scan([bulb("10.0.0.2")])
    assert registry.get("yeelight:1").online


def test_partial_scan_leaves_other_brands_alone(registry):
    registry.merge_scan([bulb("10.0.0.2"), tuya("10.0.0.3")])
    report = registry.merge_scan([bulb("10.0.0.2")], brands={"Yeelight"})
    assert report.missing == []
    assert registry.get("tuya:abc").online


def test_name_falls_back_to_brand_name_then_model(registry):
    registry.merge_scan([bulb("10.0.0.2", name="Bedroom")])
    assert registry.get("yeelight:1").name == "Bedroom"
    registry.rename("yeelight:1", "")
    registry.merge_scan([bulb("10.0.0.2")])
    assert registry.get("yeelight:1").name == "Yeelight color"


def test_resolve_by_uid_name_or_ip(registry):
    registry.merge_scan([bulb("10.0.0.2")])
    registry.rename("yeelight:1", "Desk lamp")
    for ref in ("yeelight:1", "desk LAMP", "10.0.0.2"):
        assert registry.resolve(ref).uid == "yeelight:1"
    with pytest.raises(LookupError):
        registry.resolve("nope")


def test_link_makes_device_ready_and_survives_rescan(registry):
    registry.merge_scan([tuya("10.0.0.3")])
    registry.save_link("tuya:abc", "Kettle", Category.PLUG, {"local_key": "k"})
    d = registry.get("tuya:abc")
    assert (d.name, d.category, d.readiness) == ("Kettle", Category.PLUG, Readiness.READY)
    registry.merge_scan([tuya("10.0.0.4")])  # scanner still reports UNKNOWN / NEEDS_LINK
    d = registry.get("tuya:abc")
    assert (d.ip, d.category, d.readiness) == ("10.0.0.4", Category.PLUG, Readiness.READY)
    assert registry.get_link("tuya:abc")["secret"] == {"local_key": "k"}


def test_link_before_device_is_seen_applies_on_first_scan(registry):
    registry.save_link("tuya:abc", "Kettle", Category.PLUG, {"local_key": "k"})
    registry.merge_scan([tuya("10.0.0.3")])
    assert registry.get("tuya:abc").readiness is Readiness.READY


def test_user_name_beats_link_name(registry):
    registry.merge_scan([tuya("10.0.0.3")])
    registry.rename("tuya:abc", "Kitchen kettle")
    registry.save_link("tuya:abc", "Kettle", Category.PLUG, {"local_key": "k"})
    assert registry.get("tuya:abc").name == "Kitchen kettle"


def test_connect_refinds_light_after_ip_change(registry, monkeypatch):
    registry.merge_scan([bulb("10.0.0.2")])

    class FakeLight:
        def __init__(self, ip):
            if ip != "10.0.0.9":
                raise DeviceUnreachable(ip)
            self.ip = ip

    def fake_scan(reg, timeout, brands):
        reg.merge_scan([bulb("10.0.0.9")], brands=brands)
        return ScanResult(), None

    monkeypatch.setitem(connect._LIGHT_ADAPTERS, "Yeelight", FakeLight)
    monkeypatch.setattr(connect, "scan_and_remember", fake_scan)

    device, light = connect.connect_light(registry, "yeelight:1")
    assert device.ip == light.ip == "10.0.0.9"


def test_yeelight_reads_fresh_state_after_a_command(monkeypatch):
    from control.engine.adapters import yeelight_light

    calls = []

    class FakeBulb:
        bulb_type = yeelight_light.yeelight.BulbType.Color

        def __init__(self, ip, **kw):
            self.power = "off"

        def get_properties(self):
            calls.append("get")
            return {"power": self.power, "bright": "50", "color_mode": "2", "ct": "4000"}

        def get_model_specs(self):
            return {"color_temp": {"min": 1700, "max": 6500}}

        def turn_on(self):
            self.power = "on"

    monkeypatch.setattr(yeelight_light.yeelight, "Bulb", FakeBulb)
    light = yeelight_light.YeelightLight("10.0.0.2")
    assert light.get_state().on is False and calls == ["get"]  # first read reuses the connect-time answer
    light.turn_on()
    assert light.get_state().on is True and calls == ["get", "get"]  # after a command: asks the bulb again


def test_answering_device_is_marked_online_again(registry, monkeypatch):
    registry.merge_scan([bulb("10.0.0.2")])
    registry.merge_scan([])  # a Scan missed its reply
    assert not registry.get("yeelight:1").online

    monkeypatch.setitem(connect._LIGHT_ADAPTERS, "Yeelight", lambda ip: object())
    connect.connect_light(registry, "yeelight:1")
    assert registry.get("yeelight:1").online
