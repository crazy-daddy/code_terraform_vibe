"""Launch Code: Terraform with WebView2 remote debugging and toggle the sim speed with a hotkey.

Usage: python devtools/game_speed.py [--fast 10] [--exe PATH]

Starts the game with `--remote-debugging-port` (or reuses a running game that already has it),
attaches to the `simWorker` over the Chrome DevTools Protocol and sets a conditional breakpoint
in the sim's tick callback (docs/cheatsheet/dev_workflow.md §8a). The condition never pauses;
it re-arms the tick timer at `tick interval / factor` whenever the factor changed or the game
re-armed the timer itself (pause/resume, save barrier). F9 (global, works while the game has
focus) toggles the factor between 1 and `--fast`. The factor multiplies the in-game speed: at
in-game 3x, `--fast 10` gives 30x. Ctrl+C or closing the game ends the script; the timer keeps
its last rate until the game re-arms it.

Stdlib only. Nothing on disk changes.
"""

import argparse
import base64
import ctypes
import json
import os
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request

DEFAULT_EXE = r"C:\Steam\steamapps\common\CodeTerraform\code-terraform.exe"
PORT = 9222
VK_F9 = 0x78

# Breakpoint condition, evaluated in the tick callback's scope. {d}/{u}/{ms} are the minified
# names of the timer handle, the tick callback and the tick interval, read from the bundle.
# `n` counts tick callbacks (diagnostics).
CONDITION = """(globalThis.__ctSpeed ??= {{ factor: 1, d: void 0, f: 1, n: 0 }}, __ctSpeed.n++,
 ({d} !== __ctSpeed.d || __ctSpeed.f !== __ctSpeed.factor) && (
   ({d} === __ctSpeed.d || __ctSpeed.factor !== 1)
     && (clearInterval({d}), {d} = setInterval({u}, {ms} / __ctSpeed.factor)),
   __ctSpeed.d = {d}, __ctSpeed.f = __ctSpeed.factor),
 false)"""


class WebSocket:
    """Minimal RFC 6455 client: text frames out, text frames in. Enough for CDP."""

    def __init__(self, url: str):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET {u.path} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        ).encode())
        head = b""
        while b"\r\n\r\n" not in head:
            head += self.sock.recv(1)
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.decode(errors="replace"))

    def _frame(self, opcode: int, payload: bytes) -> None:
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 1 << 16:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(head + mask + body)

    def send(self, text: str) -> None:
        self._frame(0x1, text.encode())

    def _exact(self, n: int) -> bytes:
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(min(n - len(buf), 1 << 20))
            if not chunk:
                raise ConnectionError("socket closed")
            buf += chunk
        return bytes(buf)

    def recv(self) -> str:
        parts = b""
        while True:
            b0, b1 = self._exact(2)
            n = b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._exact(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._exact(8))[0]
            payload = self._exact(n)
            opcode = b0 & 0x0F
            if opcode == 0x8:
                raise ConnectionError("websocket closed")
            if opcode == 0x9:
                self._frame(0xA, payload)
                continue
            if opcode in (0x0, 0x1):
                parts += payload
                if b0 & 0x80:
                    return parts.decode()


class Cdp:
    def __init__(self, url: str):
        self.ws = WebSocket(url)
        self.next_id = 0
        self.events: list[dict] = []

    def call(self, method: str, params: dict | None = None) -> dict:
        """Send a command and return its result; events received meanwhile go to `events`."""
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.next_id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]
            self.events.append(msg)

    def eval(self, expr: str):
        return self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True})["result"].get("value")


def endpoint_up() -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1).close()
        return True
    except OSError:
        return False


def game_running(exe: str) -> bool:
    name = os.path.basename(exe)
    out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/NH"],
                         capture_output=True, text=True).stdout
    return name.lower() in out.lower()


def sim_worker_ws(game: subprocess.Popen | None) -> str:
    while game is None or game.poll() is None:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=1) as r:
                for t in json.load(r):
                    if t["type"] == "worker" and "/simWorker" in t["url"]:
                        return t["webSocketDebuggerUrl"]
        except OSError:
            pass
        time.sleep(0.5)
    raise SystemExit("game exited")


def ident_before(s: str, i: int) -> str:
    j = i
    while j > 0 and (s[j - 1].isalnum() or s[j - 1] in "_$"):
        j -= 1
    return s[j:i]


def install(cdp: Cdp) -> None:
    """Find the sim clock in the worker bundle and set the conditional breakpoint."""
    cdp.call("Debugger.enable")
    script = next(e["params"] for e in cdp.events
                  if e.get("method") == "Debugger.scriptParsed" and "/simWorker" in e["params"]["url"])
    cdp.events.clear()
    src = cdp.call("Debugger.getScriptSource", {"scriptId": script["scriptId"]})["scriptSource"]
    # Clock arming in the bundle: `(d=setInterval(u,WCe))`.
    i = src.find("=setInterval(")
    d = ident_before(src, i)
    u, ms = src[i + len("=setInterval("):src.find(")", i)].split(",")
    body = src.rfind(f",{u}=()=>{{", 0, i)
    if not d or body < 0:
        raise SystemExit("sim clock not found in simWorker bundle (game update?)")
    pos = body + len(f",{u}=()=>{{")
    line = src.count("\n", 0, pos)
    col = pos - (src.rfind("\n", 0, pos) + 1)
    cdp.call("Debugger.setBreakpoint", {
        "location": {"scriptId": script["scriptId"], "lineNumber": line, "columnNumber": col},
        "condition": CONDITION.format(d=d, u=u, ms=ms),
    })


def main() -> None:
    ap = argparse.ArgumentParser(description="Launch the game and toggle sim speed with F9.")
    ap.add_argument("--fast", type=float, default=10, help="timer factor for fast mode (default 10)")
    ap.add_argument("--exe", default=DEFAULT_EXE)
    args = ap.parse_args()

    game = None
    if endpoint_up():
        print("attaching to running game")
    elif game_running(args.exe):
        raise SystemExit(f"game is running without the debug port. Close it and rerun this script "
                         f"to relaunch it with --remote-debugging-port={PORT}.")
    else:
        env = dict(os.environ)
        extra = env.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        env["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"{extra} --remote-debugging-port={PORT}".strip()
        game = subprocess.Popen([args.exe], cwd=os.path.dirname(args.exe), env=env)

    cdp = Cdp(sim_worker_ws(game))
    install(cdp)
    print(f"sim clock hooked. F9 toggles 1x / {args.fast:g}x timer speed. Ctrl+C to quit.")

    get_key = ctypes.windll.user32.GetAsyncKeyState
    fast, was_down, next_check = False, False, 0.0
    try:
        while game is None or game.poll() is None:
            if game is None and time.time() > next_check:
                if not game_running(args.exe):
                    break
                next_check = time.time() + 1
            down = bool(get_key(VK_F9) & 0x8000)
            if down and not was_down:
                fast = not fast
                factor = args.fast if fast else 1
                cdp.eval(f"(globalThis.__ctSpeed ??= {{ factor: 1, d: void 0, f: 1, n: 0 }}).factor = {factor}")
                print(f"speed: {factor:g}x")
            was_down = down
            cdp.events.clear()
            time.sleep(0.03)
    except (KeyboardInterrupt, ConnectionError):
        pass


if __name__ == "__main__":
    main()
