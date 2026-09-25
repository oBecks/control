import argparse
import json
import sys
from dataclasses import asdict

from .engine import signal_library
from .engine.climate import features_from_signals
from .engine.connect import connect_climate, connect_light, connect_plug, only_transmitter
from .engine.found_device import Category
from .engine.errors import DeviceUnreachable
from .engine.registry import Registry
from .engine.scan import DEFAULT_TIMEOUT, scan_and_remember


def _table(headers: tuple, rows: list[tuple]) -> None:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    for row in (headers, *rows):
        print("  ".join(str(x).ljust(w) for x, w in zip(row, widths)).rstrip())


def _print_devices(registry: Registry) -> None:
    devices, remotes = registry.all(), registry.remotes()
    if not devices and not remotes:
        print("No known devices. Run: control scan")
        return
    _table(
        ("", "CATEGORY", "NAME", "BRAND", "MODEL", "IP", "STATUS", "UID"),
        [
            (
                "NEW" if d.is_new else "",
                d.category.value,
                d.name,
                d.brand,
                d.model or "-",
                d.ip,
                d.readiness.value if d.online else "offline",
                d.uid,
            )
            for d in devices
        ]
        + [
            ("", r.category.value, r.name, "(remote)", r.source, "-", "assumed", r.uid)
            for r in remotes
        ],
    )


def _scan(registry: Registry, args) -> None:
    print(f"Scanning for {args.timeout:g}s...", file=sys.stderr, flush=True)
    result, report = scan_and_remember(registry, args.timeout)
    if args.json:
        print(json.dumps({"devices": [asdict(d) for d in result.devices], "errors": result.errors}, indent=2, default=str))
        return
    _print_devices(registry)
    print()
    print(f"{len(report.added)} new, {len(report.moved)} moved, {len(report.missing)} missing")
    for uid, (old, new) in report.moved.items():
        print(f"  moved: {registry.get(uid).name} {old} -> {new}")
    for brand, err in result.errors.items():
        print(f"! {brand} scan failed: {err}")


def _light(registry: Registry, args) -> None:
    if args.action in ("brightness", "color", "temp") and not args.value:
        sys.exit(f"'{args.action}' needs a value")
    try:
        device, light = connect_light(registry, args.device)
    except (LookupError, DeviceUnreachable) as exc:
        sys.exit(str(exc))

    if args.action == "on":
        light.turn_on()
    elif args.action == "off":
        light.turn_off()
    elif args.action == "brightness":
        light.set_brightness(int(args.value))
    elif args.action == "color":
        hex_ = args.value.lstrip("#")
        light.set_rgb(*(int(hex_[i : i + 2], 16) for i in (0, 2, 4)))
    elif args.action == "temp":
        light.set_kelvin(int(args.value))

    print(f"{device.name} ({device.ip})")
    print(light.features)
    print(light.get_state())


def _plug(registry: Registry, args) -> None:
    try:
        device, plug = connect_plug(registry, args.device)
        if args.action == "on":
            plug.turn_on()
        elif args.action == "off":
            plug.turn_off()
        state = plug.get_state()
    except (LookupError, DeviceUnreachable) as exc:
        sys.exit(str(exc))
    print(f"{device.name} ({device.ip}): {'on' if state.on else 'off'}")


def _ac_codes(args) -> None:
    sets = signal_library.search_climate(args.brand)
    if not sets:
        sys.exit(f"no Broadlink code sets for '{args.brand}'")
    _table(("CODE", "MANUFACTURER", "MODELS"), [(c.code, c.manufacturer, ", ".join(c.models)) for c in sets])


def _add_ac(registry: Registry, args) -> None:
    try:
        via = registry.resolve(args.via) if args.via else only_transmitter(registry)
        signals = signal_library.load_climate(args.code)
        uid = registry.add_remote(args.name, Category.CLIMATE, via.uid, f"smartir:climate:{args.code}", signals)
    except (LookupError, ValueError) as exc:
        sys.exit(str(exc))
    print(f"added '{args.name}' ({uid}) via {via.name}, code set {args.code}")
    print(features_from_signals(signals))


def _ac(registry: Registry, args) -> None:
    if args.action == "code":
        if not args.code:
            sys.exit("'code' needs a code set number")
        remote = registry.resolve_remote(args.device)
        registry.set_remote_signals(remote.uid, f"smartir:climate:{args.code}", signal_library.load_climate(args.code))
        print(f"'{remote.name}' now uses code set {args.code}")
        return
    try:
        remote, ac = connect_climate(registry, args.device)
    except (LookupError, DeviceUnreachable) as exc:
        sys.exit(str(exc))
    if args.action != "state":
        on = {"on": True, "off": False}.get(args.action)
        try:
            ac.apply(on=on, mode=args.mode, target_temp=args.temp, fan=args.fan, swing=args.swing)
        except ValueError as exc:
            sys.exit(str(exc))
        registry.set_assumed_state(remote.uid, ac.state_dict())
    print(f"{remote.name} ({remote.source})")
    print(ac.features)
    print(f"assumed: {ac.state}")


def _tuya_link(registry: Registry, args) -> None:
    import os

    import qrcode

    from .engine.links import tuya_link
    from .engine.registry import default_db_path

    print("In Smart Life: Me > Settings (gear) > Account and Security > User Code")
    user_code = args.user_code or input("User Code: ").strip()
    try:
        token, content = tuya_link.start(user_code)
    except tuya_link.LinkError as exc:
        sys.exit(str(exc))

    png = default_db_path().parent / "tuya-login-qr.png"
    qrcode.make(content).save(png)
    qr = qrcode.QRCode(border=1)
    qr.add_data(content)
    qr.print_ascii(invert=True)
    print(f"\nQR code also saved to {png}")
    if not args.no_open:
        os.startfile(png)
    print("Scan it in Smart Life (Home tab > scan icon, top right) and tap Confirm login.")
    print("Waiting up to 3 minutes...", flush=True)

    try:
        info = tuya_link.wait_for_login(token, user_code)
        linked = tuya_link.fetch_devices(info, user_code)
    except tuya_link.LinkError as exc:
        sys.exit(str(exc))
    finally:
        png.unlink(missing_ok=True)

    for d in linked:
        registry.save_link(d.uid, d.name, d.category, {"local_key": d.local_key},
                           {"tuya_category": d.tuya_category, "product_name": d.product_name, **d.extra})
    known = {k.uid for k in registry.all()}
    print(f"\nLinked {len(linked)} Tuya device(s):")
    _table(
        ("NAME", "CATEGORY", "TUYA KIND", "PRODUCT", "ON THIS NETWORK"),
        [(d.name, d.category.value, d.tuya_category, d.product_name, "yes" if d.uid in known else "not seen yet")
         for d in linked],
    )


def main() -> None:
    # Device names can be any language; the Windows console code page can't print all of them.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="control")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan the network and remember what's found")
    scan.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    scan.add_argument("--json", action="store_true", help="print this scan's raw results as JSON")

    sub.add_parser("devices", help="list remembered devices (no scan)")

    rename = sub.add_parser("rename", help="give a device a name (empty name resets it)")
    rename.add_argument("device", help="uid, current name or IP")
    rename.add_argument("name")

    seen = sub.add_parser("seen", help="clear the NEW flag")
    seen.add_argument("device", nargs="?", help="uid, name or IP (default: all)")

    forget = sub.add_parser("forget", help="remove a device from memory")
    forget.add_argument("device")

    light = sub.add_parser("light", help="control a light")
    light.add_argument("device", help="uid, name or IP")
    light.add_argument(
        "action",
        nargs="?",
        default="state",
        choices=["state", "on", "off", "brightness", "color", "temp"],
    )
    light.add_argument("value", nargs="?", help="brightness 1-100, color #RRGGBB, temp in kelvin")

    plug = sub.add_parser("plug", help="control a plug")
    plug.add_argument("device", help="uid, name or IP")
    plug.add_argument("action", nargs="?", default="state", choices=["state", "on", "off"])

    ac_codes = sub.add_parser("ac-codes", help="search the Signal Library for an AC brand")
    ac_codes.add_argument("brand")

    add_ac = sub.add_parser("add-ac", help="add an AC controlled through a transmitter")
    add_ac.add_argument("name")
    add_ac.add_argument("code", type=int, help="code set number from ac-codes")
    add_ac.add_argument("--via", help="transmitter (default: the only one)")

    ac = sub.add_parser("ac", help="control an AC")
    ac.add_argument("device", help="name or uid")
    ac.add_argument("action", nargs="?", default="state", choices=["state", "on", "off", "set", "code"])
    ac.add_argument("code", nargs="?", type=int, help="for 'code': switch to this code set")
    ac.add_argument("--mode")
    ac.add_argument("--temp", type=float)
    ac.add_argument("--fan")
    ac.add_argument("--swing")

    tuya = sub.add_parser("tuya-link", help="sign in with Smart Life (QR) to fetch Tuya Local Keys")
    tuya.add_argument("--user-code", help="Smart Life User Code (prompted if omitted)")
    tuya.add_argument("--no-open", action="store_true", help="don't open the QR image")

    serve = sub.add_parser("serve", help="run the Engine API")
    serve.add_argument("--port", type=int, default=8321)

    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        print(f"Engine API on http://127.0.0.1:{args.port}  (docs: /docs)")
        uvicorn.run("control.api.app:app", host="127.0.0.1", port=args.port)
        return
    registry = Registry()
    try:
        if args.command == "scan":
            _scan(registry, args)
        elif args.command == "devices":
            _print_devices(registry)
        elif args.command == "light":
            _light(registry, args)
        elif args.command == "plug":
            _plug(registry, args)
        elif args.command == "ac-codes":
            _ac_codes(args)
        elif args.command == "add-ac":
            _add_ac(registry, args)
        elif args.command == "ac":
            _ac(registry, args)
        elif args.command == "tuya-link":
            _tuya_link(registry, args)
        else:
            try:
                target = registry.resolve(args.device) if getattr(args, "device", None) else None
            except LookupError as exc:
                sys.exit(str(exc))
            if args.command == "rename":
                registry.rename(target.uid, args.name)
                print(f"renamed -> {registry.get(target.uid).name}")
            elif args.command == "seen":
                registry.mark_seen([target.uid] if target else None)
            elif args.command == "forget":
                registry.forget(target.uid)
                print(f"forgot {target.name}")
    finally:
        registry.close()


if __name__ == "__main__":
    main()
