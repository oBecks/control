"""Start a packaged Control.exe with --mcp, the way Claude does, and check that it lists its tools.
The release workflow runs it so a Control.exe missing a module is never published (ADR 0005).

Like Claude, it keeps the server's stdin open until it has its answers: closing it right after the
requests let the server exit before answering tools/list on a slow machine (the v0.8.0 build)."""

import json
import queue
import re
import subprocess
import sys
import threading
from pathlib import Path

# Every tool the source defines, so this check never needs updating when a tool is added.
SERVER = Path(__file__).resolve().parents[1] / "src" / "control" / "assistant" / "server.py"
TOOLS = set(re.findall(r"@server\.tool\([^)]*\)\s*def (\w+)", SERVER.read_text(encoding="utf-8")))
TIMEOUT = 60  # seconds for each answer: the first start of a packaged exe can be slow


def main(exe: str) -> None:
    exe = str(Path(exe).resolve())
    server = subprocess.Popen([exe, "--mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True, encoding="utf-8")
    lines: queue.Queue = queue.Queue()

    def read() -> None:
        for line in server.stdout:
            lines.put(line)
        lines.put(None)  # it exited

    threading.Thread(target=read, daemon=True).start()

    def send(message: dict) -> None:
        server.stdin.write(json.dumps(message) + "\n")
        server.stdin.flush()

    def fail(why: str) -> None:
        server.kill()
        sys.exit(f"{exe} --mcp: {why}\n{server.stderr.read()}")

    def answer(request_id: int) -> dict:
        while True:
            try:
                line = lines.get(timeout=TIMEOUT)
            except queue.Empty:
                fail(f"no answer to request {request_id} within {TIMEOUT} s")
            if line is None:
                fail(f"it exited before answering request {request_id}")
            reply = json.loads(line)
            if reply.get("id") == request_id:
                return reply

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                         "clientInfo": {"name": "check", "version": "0"}}})
        answer(1)
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = {t["name"] for t in answer(2)["result"]["tools"]}
    finally:
        server.stdin.close()  # the server exits when stdin closes
    server.wait(timeout=TIMEOUT)
    if tools != TOOLS:
        sys.exit(f"{exe} --mcp listed {sorted(tools)}, expected {sorted(TOOLS)}")
    print(f"{exe} --mcp lists its {len(tools)} tools")


if __name__ == "__main__":
    main(sys.argv[1])
