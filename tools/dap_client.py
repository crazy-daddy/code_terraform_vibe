r"""
Minimal Debug Adapter Protocol (DAP) client for Code: Terraform's external
debug adapter (external-ide/server/debug-adapter.cjs), for driving a debug
session from a plain script instead of VS Code. See
docs/AI_CHEATSHEET.md Section 8 for the full writeup, capabilities, and the
attach-vs-launch gotcha this file's docstrings reference below.

SAFETY: a session opened with this tool runs against the real, live game
save -- pausing a script at a breakpoint pauses real gameplay for that
machine/vehicle until resumed. Per CLAUDE.md, always confirm with the user
before starting a session (attach/launch) or before anything that resumes
world time indefinitely. This module itself takes no such confirmation --
that's the caller's responsibility.

Usage as a library:
    from dap_client import DapClient, run_session

    def on_stopped(client, stopped_event):
        thread_id = stopped_event["body"]["threadId"]
        frames = client.request("stackTrace", {"threadId": thread_id})
        print(frames)
        # return True to resume (continue) and disconnect automatically,
        # False to leave it paused and handle continue/disconnect yourself.
        return True

    run_session(
        workspace=r"C:\...\save_..._scripts",
        script=r"C:\...\save_..._scripts\rover_1.py",
        breakpoints=[(r"C:\...\save_..._scripts\lib\vehicle.py", 136)],
        mode="attach",          # "attach" for an already-running script,
                                 # "launch" for an idle one -- see the
                                 # attach-vs-launch note on run_session().
        on_stopped=on_stopped,
        wait_timeout=20,
    )

Usage from the command line:
    python dap_client.py --workspace <dir> --script <path> \
        --break <file.py>:<line> [--break ...] [--mode attach|launch] \
        [--timeout 20]
Prints the stack trace and top-frame locals at the first breakpoint hit,
then resumes and disconnects (non-terminating).
"""
import json
import os
import shutil
import subprocess
import threading
import queue
import sys
import time
import argparse


def _default_node() -> str:
    """Resolves 'node' from PATH; falls back to the bare command name so a
    missing PATH entry surfaces as a clear FileNotFoundError from Popen
    rather than a silently wrong hardcoded location."""
    return shutil.which("node") or "node"


def _default_adapter() -> str:
    """Locates debug-adapter.cjs under the game's per-user data directory
    (%APPDATA%/io.codeterraform.game on Windows; XDG_CONFIG_HOME or
    ~/.config on other platforms), independent of machine or username."""
    app_data = (
        os.environ.get("APPDATA")
        or os.environ.get("XDG_CONFIG_HOME")
        or os.path.join(os.path.expanduser("~"), ".config")
    )
    return os.path.join(app_data, "io.codeterraform.game", "external-ide", "server", "debug-adapter.cjs")


NODE = _default_node()
ADAPTER = _default_adapter()


class DapClient:
    """Low-level stdio DAP transport: Content-Length-framed JSON messages, a background reader thread, and helpers to send requests and wait for matching responses/events."""

    def __init__(self, node=NODE, adapter=ADAPTER):
        self.proc = subprocess.Popen(
            [node, adapter],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.seq = 0
        self.inbox = queue.Queue()
        self._stop = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._stderr_loop, daemon=True)
        self._stderr_reader.start()

    def _stderr_loop(self):
        for line in iter(self.proc.stderr.readline, b""):
            sys.stderr.write("[adapter stderr] " + line.decode(errors="replace"))

    def _read_loop(self):
        f = self.proc.stdout
        while not self._stop:
            line = f.readline()
            if not line:
                break
            if line.strip() == b"":
                continue
            if line.startswith(b"Content-Length:"):
                length = int(line.decode().split(":")[1].strip())
                f.readline()  # blank line separator
                body = f.read(length)
                try:
                    msg = json.loads(body.decode("utf-8"))
                except Exception as e:
                    self.inbox.put({"_error": str(e), "_raw": body})
                    continue
                self.inbox.put(msg)

    def send(self, msg_type, command=None, arguments=None, **extra):
        self.seq += 1
        msg = {"seq": self.seq, "type": msg_type}
        if command:
            msg["command"] = command
        if arguments is not None:
            msg["arguments"] = arguments
        msg.update(extra)
        body = json.dumps(msg).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
        self.proc.stdin.write(header + body)
        self.proc.stdin.flush()
        return msg["seq"]

    def request(self, command, arguments=None, timeout=10):
        """Sends a request and blocks for its matching response (matched by request_seq)."""
        seq = self.send("request", command, arguments)
        return self.wait_for(lambda m: m.get("type") == "response" and m.get("request_seq") == seq, timeout)

    def wait_for(self, predicate, timeout=10):
        """Blocks until a message satisfying predicate arrives, or timeout. Non-matching messages seen along the way are requeued, so this can be called repeatedly without losing events."""
        deadline = time.time() + timeout
        pending = []
        while time.time() < deadline:
            try:
                msg = self.inbox.get(timeout=0.2)
            except queue.Empty:
                continue
            if predicate(msg):
                for p in pending:
                    self.inbox.put(p)
                return msg
            pending.append(msg)
        for p in pending:
            self.inbox.put(p)
        return None

    def drain_events(self, duration=1.0):
        """Collects whatever arrives over duration seconds -- handy for sweeping up output events after a request completes."""
        events = []
        deadline = time.time() + duration
        while time.time() < deadline:
            try:
                events.append(self.inbox.get(timeout=0.1))
            except queue.Empty:
                continue
        return events

    def close(self):
        """Terminates the adapter process. Per the adapter's own capabilities (supportTerminateDebuggee: false), this never stops the game script itself -- only detaches, same as VS Code's Shift+F5. Use 'disconnect' first for a clean handshake; close() is the final cleanup either way."""
        self._stop = True
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        self.proc.terminate()


def run_session(workspace, script, breakpoints, mode="attach", on_stopped=None, wait_timeout=20, init_timeout=15):
    """
    Full one-shot session: initialize -> attach/launch -> setBreakpoints ->
    configurationDone -> wait for a 'stopped' event -> on_stopped(client, event)
    -> continue (unless on_stopped returned False) -> disconnect (non-
    terminating) -> close. Returns the 'stopped' event (or None if the
    breakpoint never hit within wait_timeout).

    mode: "attach" for a script the game is already running (does NOT
    restart it -- attaching just starts watching it, so a breakpoint at
    e.g. __init__ that already ran won't re-fire; pick a line reached by
    the ongoing loop instead). "launch" starts an *idle* script fresh. There
    is no confirmed way to force a genuine restart of an already-running
    script through this raw DAP interface -- a bare launch on a running
    script just attaches without restarting (matches the external-ide
    README), and a guessed launch arguments["restart"]=True had no effect
    (no such capability is advertised by 'initialize'). VS Code's own
    "Run Script in Game" command may do this via extension-specific
    plumbing outside debug-adapter.cjs's plain surface; not reproduced here.

    breakpoints: list of (absolute_source_path, line) tuples. Grouped by
    file and one setBreakpoints request sent per file (the protocol sets
    all breakpoints for a source in one call, replacing any prior set for
    that file in this session).
    """
    client = DapClient()
    try:
        r = client.request("initialize", {
            "clientID": "dap_client.py", "adapterID": "codeterraform",
            "pathFormat": "path", "linesStartAt1": True, "columnsStartAt1": True,
        }, timeout=init_timeout)
        if not r or not r.get("success"):
            raise RuntimeError(f"initialize failed: {r}")

        client.send("request", mode, {"workspace": workspace, "script": script})
        ev = client.wait_for(lambda m: m.get("type") == "event" and m.get("event") == "initialized", timeout=init_timeout)
        if not ev:
            raise RuntimeError(f"never received 'initialized' event after {mode}")

        by_file = {}
        for path, line in breakpoints:
            by_file.setdefault(path, []).append(line)
        for path, lines in by_file.items():
            r = client.request("setBreakpoints", {
                "source": {"path": path},
                "breakpoints": [{"line": ln} for ln in lines],
            }, timeout=init_timeout)
            if not r or not r.get("success"):
                raise RuntimeError(f"setBreakpoints failed for {path}: {r}")

        r = client.request("configurationDone", {}, timeout=init_timeout)
        if not r or not r.get("success"):
            raise RuntimeError(f"configurationDone failed: {r}")

        client.wait_for(lambda m: m.get("type") == "response" and m.get("command") == mode, timeout=init_timeout)

        stopped = client.wait_for(lambda m: m.get("type") == "event" and m.get("event") == "stopped", timeout=wait_timeout)
        if stopped:
            resume = True
            if on_stopped:
                resume = on_stopped(client, stopped) is not False
            if resume:
                thread_id = stopped["body"]["threadId"]
                client.request("continue", {"threadId": thread_id}, timeout=init_timeout)
        client.request("disconnect", {"terminateDebuggee": False}, timeout=init_timeout)
        return stopped
    finally:
        client.close()


def launch_script(workspace, script, timeout=15):
    """
    Launches an idle game script via DAP without breakpoints,
    starts its execution in the game (runIfIdle=True), and disconnects cleanly.
    Returns True on success, False on failure.
    """
    client = DapClient()
    try:
        r = client.request("initialize", {
            "clientID": "dap_client.py", "adapterID": "codeterraform",
            "pathFormat": "path", "linesStartAt1": True, "columnsStartAt1": True,
        }, timeout=timeout)
        if not r or not r.get("success"):
            msg = r.get("message") if r else "no response"
            print(f"[DAP] initialize failed: {msg}", file=sys.stderr)
            return False

        client.send("request", "launch", {"workspace": workspace, "script": script})
        ev = client.wait_for(
            lambda m: (m.get("type") == "event" and m.get("event") == "initialized") or
                      (m.get("type") == "response" and m.get("command") == "launch" and not m.get("success")),
            timeout=timeout
        )
        if not ev:
            print(f"[DAP] Timeout waiting for 'initialized' event for {script}", file=sys.stderr)
            return False
        if ev.get("type") == "response" and not ev.get("success"):
            print(f"[DAP] Launch rejected by game adapter: {ev.get('message', 'unknown error')}", file=sys.stderr)
            return False

        r = client.request("configurationDone", {}, timeout=timeout)
        if not r or not r.get("success"):
            msg = r.get("message") if r else "no response"
            print(f"[DAP] configurationDone failed for {script}: {msg}", file=sys.stderr)
            return False

        client.wait_for(lambda m: m.get("type") == "response" and m.get("command") == "launch", timeout=timeout)
        client.request("disconnect", {"terminateDebuggee": False}, timeout=timeout)
        return True
    except Exception as e:
        print(f"[DAP] Exception during launch_script({script}): {e}", file=sys.stderr)
        return False
    finally:
        client.close()


def _print_stopped_state(client, stopped_event):
    thread_id = stopped_event["body"]["threadId"]
    frames = client.request("stackTrace", {"threadId": thread_id})
    print("=== stack trace ===")
    print(json.dumps(frames, indent=2))
    if frames and frames.get("body", {}).get("stackFrames"):
        frame_id = frames["body"]["stackFrames"][0]["id"]
        scopes = client.request("scopes", {"frameId": frame_id})
        for scope in scopes.get("body", {}).get("scopes", []):
            variables = client.request("variables", {"variablesReference": scope["variablesReference"]})
            print(f"=== {scope['name']} ===")
            print(json.dumps(variables, indent=2))
    return True  # resume after printing


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--launch", action="store_true", help="Launch an idle script in the running game without breakpoints")
    parser.add_argument("--break", dest="breaks", action="append", metavar="FILE:LINE", help="Breakpoint for debug session")
    parser.add_argument("--mode", choices=["attach", "launch"], default="attach")
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()

    if args.launch:
        ok = launch_script(args.workspace, args.script, timeout=args.timeout)
        if ok:
            print(f"Successfully launched {args.script} in game.")
            sys.exit(0)
        else:
            print(f"Failed to launch {args.script}.")
            sys.exit(1)

    if not args.breaks:
        parser.error("Either --launch or at least one --break must be specified.")

    breakpoints = []
    for spec in args.breaks:
        path, line = spec.rsplit(":", 1)
        breakpoints.append((path, int(line)))

    result = run_session(
        args.workspace, args.script, breakpoints,
        mode=args.mode, on_stopped=_print_stopped_state, wait_timeout=args.timeout,
    )
    if not result:
        print(f"Breakpoint never hit within {args.timeout}s.")
        sys.exit(1)
