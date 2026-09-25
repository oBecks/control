import pytest

from control.api import desktop as desktop_api
from control.desktop import autostart, updates

from .test_access import approve, pc, phone, turn_on  # noqa: F401 (pc is a fixture)


def release(tag, **extra):
    return {"tag_name": tag, "html_url": f"https://github.com/oBecks/control/releases/tag/{tag}",
            "assets": [{"name": "ControlSetup.exe", "browser_download_url": f"https://example.test/{tag}/ControlSetup.exe"}],
            **extra}


def test_a_newer_release_links_to_its_installer():
    assert updates.newer(release("v0.2.0"), current="0.1.0") == updates.Update(
        "0.2.0", "https://example.test/v0.2.0/ControlSetup.exe")


@pytest.mark.parametrize("rel", [
    release("v0.1.0"),  # the one running
    release("v0.0.9"),
    release("v0.2.0", prerelease=True),
    release("nightly"),
])
def test_no_update_unless_a_newer_final_release(rel):
    assert updates.newer(rel, current="0.1.0") is None


def test_version_compares_numbers_not_text():
    assert updates.newer(release("v0.10.0"), current="0.9.0").version == "0.10.0"


def test_a_release_without_the_installer_links_to_its_page():
    rel = release("v1.0.0", assets=[])
    assert updates.newer(rel, current="0.1.0").url == rel["html_url"]


@pytest.fixture
def in_app(monkeypatch):
    """The Engine running inside the Desktop App, with the Run key faked."""
    state = {"on": False}
    monkeypatch.setattr(autostart, "is_on", lambda: state["on"])
    monkeypatch.setattr(autostart, "set_on", lambda on: state.update(on=on))
    monkeypatch.setattr(desktop_api, "state", desktop_api.DesktopApp(running=True))
    return state


def test_outside_the_desktop_app_there_is_no_start_with_windows(pc):
    body = pc.get("/api/desktop").json()
    assert body["app"] is False and body["start_with_windows"] is None
    assert pc.put("/api/desktop/start-with-windows", json={"on": True}).status_code == 409


def test_start_with_windows_switch(pc, in_app):
    assert pc.get("/api/desktop").json()["start_with_windows"] is False
    assert pc.put("/api/desktop/start-with-windows", json={"on": True}).json()["start_with_windows"] is True
    assert in_app["on"] is True


def test_phones_cant_change_start_with_windows(pc, in_app):
    turn_on(pc)
    p = phone()
    approve(pc, p)
    assert p.get("/api/desktop").json()["can_change"] is False
    assert p.put("/api/desktop/start-with-windows", json={"on": True}).status_code == 403
    assert in_app["on"] is False


def test_settings_show_a_found_update(pc, in_app):
    desktop_api.state.update = updates.Update("0.2.0", "https://example.test/ControlSetup.exe")
    assert pc.get("/api/desktop").json()["update"] == {"version": "0.2.0", "url": "https://example.test/ControlSetup.exe"}


def test_phone_access_names_the_program_windows_asks_about(pc, monkeypatch):
    assert pc.get("/api/access/phone").json()["program"] == "Python"  # from source
    monkeypatch.setattr("sys.frozen", True, raising=False)  # Control.exe
    assert pc.get("/api/access/phone").json()["program"] == "Control"


def test_sign_in_starts_the_app_hidden():
    assert autostart.command().endswith("--hidden")
