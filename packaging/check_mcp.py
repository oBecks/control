"""Start a packaged Control.exe with --mcp, the way Claude does, and check that it lists its tools.
The release workflow runs it so a Control.exe missing a module is never published (ADR 0005)."""

import json
import subprocess
import sys
from pathlib import Path

TOOLS = {"list_devices", "get_device", "set_power", "set_light", "set_climate", "press_button"}


def main(exe: str) -> None:
    exe = str(Path(exe).resolve())
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "check", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    stdin = "".join(json.dumps(r) + "\n" for r in requests)
    # The server exits when stdin closes, after answering what it was sent.
    done = subprocess.run([exe, "--mcp"], input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=60)
    replies = [json.loads(line) for line in done.stdout.splitlines() if line.strip()]
    tools = {t["name"] for r in replies if r.get("id") == 2 for t in r["result"]["tools"]}
    if tools != TOOLS:
        sys.exit(f"{exe} --mcp listed {sorted(tools)}, expected {sorted(TOOLS)}\n{done.stderr}")
    print(f"{exe} --mcp lists its {len(tools)} tools")


if __name__ == "__main__":
    main(sys.argv[1])
