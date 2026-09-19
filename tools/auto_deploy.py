#!/usr/bin/env python3
r"""
Auto Deployer for Code: Terraform
Monitors in-game logs (logs/all.log) and workspace state (codeterraform-workspace.json)
to automatically deploy and launch scripts for newly constructed or deployed machines.

Usage:
    # Run once to scan and deploy any idle unscripted machines:
    python tools/auto_deploy.py --scan

    # Test run without writing files or starting scripts:
    python tools/auto_deploy.py --scan --dry-run

    # Continuous background daemon:
    python tools/auto_deploy.py --daemon

    # Manually deploy a specific machine with custom parameters:
    python tools/auto_deploy.py --deploy pioneer_5 --template pioneer_hauler \
        --param HOME_BASE=outpost_3 --param DESTINATION=outpost_home
"""

import os
import sys
import json
import time
import re
import argparse
from typing import Dict, Any, Optional, Tuple

# Import launch_script from sibling dap_client
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from dap_client import launch_script  # type: ignore
from early_game import find_latest_workspace  # type: ignore

STATE_FILE = os.path.join(SCRIPT_DIR, ".deployed_state.json")
TEMPLATES_DIR = os.path.join(SCRIPT_DIR, "templates")


def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"deployed": {}}


def save_state(state: Dict[str, Any]) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[AutoDeploy] Warning: failed to save state: {e}")


def parse_deploy_log_line(line: str) -> Optional[Tuple[str, Optional[str], Dict[str, str]]]:
    """
    Parses a log line for deployment markers and arbitrary parameter assignments.
    Supported patterns:
      [DEPLOY] machine_id=pioneer_5 template=pioneer_hauler HOME_BASE="outpost_3" DESTINATION="outpost_home"
      [DEPLOY] Deployed and equipped pioneer_5 with modules - use HOME_BASE="outpost_3", DESTINATION="outpost_home"
      [DEPLOY] {"machine_id": "solar_32", "template": "solar", "params": {...}}
    Returns (machine_id, template_name_or_None, params_dict) or None.
    """
    if "[DEPLOY]" not in line:
        return None

    content = line.split("[DEPLOY]", 1)[1].strip()

    # Case 1: JSON payload
    if content.startswith("{") and content.endswith("}"):
        try:
            data = json.loads(content)
            machine_id = data.get("machine_id")
            if machine_id:
                template = data.get("template")
                params = data.get("params", {})
                for k, v in data.items():
                    if k not in ("machine_id", "template", "params"):
                        params[k] = str(v)
                return str(machine_id), template, params
        except Exception:
            pass

    # Case 2: Token / assignment parsing
    # Match KEY="VAL", KEY='VAL', or KEY=VAL
    token_pattern = re.compile(r'([A-Za-z0-9_]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s,]+))')
    params: Dict[str, str] = {}
    for match in token_pattern.finditer(content):
        key = match.group(1)
        val = match.group(2) if match.group(2) is not None else (
            match.group(3) if match.group(3) is not None else match.group(4)
        )
        params[key] = val

    machine_id = params.pop("machine_id", None)
    template = params.pop("template", None)

    # If machine_id was not explicitly 'machine_id=...', infer from first '<type>_<number>' token
    if not machine_id:
        id_match = re.search(r'\b([a-zA-Z0-9_]+_\d+)\b', content)
        if id_match:
            machine_id = id_match.group(1)

    if machine_id:
        return machine_id, template, params

    return None


def substitute_placeholders(template_text: str, variables: Dict[str, Any]) -> str:
    """
    Substitutes variables into template text.
    Supports:
      ${VAR:default_value}
      ${VAR}
      {VAR:default_value}
      {VAR}
    """
    result = template_text

    # Pattern for ${VAR:default} or ${VAR}
    def replacer_dollar(match):
        var_name = match.group(1)
        default_val = match.group(2)
        if var_name in variables and variables[var_name] is not None:
            return str(variables[var_name])
        if default_val is not None:
            # Check if default_val itself contains a nested ${...}
            nested_sub = substitute_placeholders(default_val, variables)
            return nested_sub
        return f"${{{var_name}}}"

    pattern_dollar = re.compile(r'\$\{([A-Za-z0-9_]+)(?::([^}]*))?\}')
    # Loop to handle nested references like ${A:${B:default}}
    for _ in range(3):
        new_result = pattern_dollar.sub(replacer_dollar, result)
        if new_result == result:
            break
        result = new_result

    # Pattern for {VAR:default} or {VAR} (non-dollar bracket format)
    def replacer_brace(match):
        var_name = match.group(1)
        default_val = match.group(2)
        if var_name in variables and variables[var_name] is not None:
            return str(variables[var_name])
        if default_val is not None:
            return substitute_placeholders(default_val, variables)
        return match.group(0)

    pattern_brace = re.compile(r'\{([A-Za-z0-9_]+)(?::([^}]*))?\}')
    result = pattern_brace.sub(replacer_brace, result)
    return result


def find_template(template_name: Optional[str], machine_type: Optional[str], machine_id: str) -> Optional[str]:
    """
    Resolves the template file path in TEMPLATES_DIR.
    Tries:
      1. Explicit template_name.py
      2. machine_type.py
      3. Prefix of machine_id (e.g. 'solar' from 'solar_14')
    """
    candidates = []
    if template_name:
        candidates.append(f"{template_name}.py" if not template_name.endswith(".py") else template_name)
        if template_name.startswith("pioneer"):
            candidates.append("pioneer.py")
    if machine_type:
        candidates.append(f"{machine_type}.py")
    prefix = re.sub(r'_\d+$', '', machine_id)
    if prefix:
        candidates.append(f"{prefix}.py")

    for candidate in candidates:
        full_path = os.path.join(TEMPLATES_DIR, candidate)
        if os.path.isfile(full_path):
            return full_path

    return None


class AutoDeployer:
    def __init__(self, workspace: str, dry_run: bool = False, force: bool = False):
        self.workspace = os.path.abspath(workspace)
        self.dry_run = dry_run
        self.force = force
        self.state = load_state()
        self.pending_directives: Dict[str, Dict[str, Any]] = {}
        self.log_file_path = os.path.join(self.workspace, "logs", "all.log")
        self.log_offset = 0
        self.workspace_json_path = os.path.join(self.workspace, "codeterraform-workspace.json")

    def read_new_log_entries(self) -> None:
        """Reads new lines from logs/all.log and stores any deployment directives."""
        if not os.path.exists(self.log_file_path):
            return

        try:
            file_size = os.path.getsize(self.log_file_path)
            # If file rotated / shrunk, reset offset
            if file_size < self.log_offset:
                self.log_offset = 0

            with open(self.log_file_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(self.log_offset)
                lines = f.readlines()
                self.log_offset = f.tell()

            for line in lines:
                res = parse_deploy_log_line(line)
                if res:
                    m_id, template, params = res
                    print(f"[AutoDeploy] Log event detected: machine_id={m_id} template={template} params={params}")
                    self.pending_directives[m_id] = {
                        "template": template,
                        "params": params,
                        "timestamp": time.time(),
                    }
        except Exception as e:
            print(f"[AutoDeploy] Log read error: {e}")

    def read_workspace_state(self) -> Optional[Dict[str, Any]]:
        """Reads and parses codeterraform-workspace.json."""
        if not os.path.exists(self.workspace_json_path):
            return None
        try:
            with open(self.workspace_json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def deploy_machine(
        self,
        machine_id: str,
        machine_data: Optional[Dict[str, Any]] = None,
        template_override: Optional[str] = None,
        extra_params: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Generates script for machine_id and launches it."""
        deployed_record = self.state.get("deployed", {}).get(machine_id)
        if deployed_record and not self.force:
            return False

        machine_type = machine_data.get("typeId") if machine_data else None
        location_id = machine_data.get("locationId", "outpost_home") if machine_data else "outpost_home"

        # Check pending directives from logs
        directive = self.pending_directives.get(machine_id, {})
        template_name = template_override or directive.get("template")
        params = dict(directive.get("params", {}))
        if extra_params:
            params.update(extra_params)

        # Map aliases: SOURCE_OUTPOST_ID -> HOME_BASE, DESTINATION -> DESTINATION_OUTPOST_ID
        if "SOURCE_OUTPOST_ID" in params and "HOME_BASE" not in params:
            params["HOME_BASE"] = params["SOURCE_OUTPOST_ID"]
        if "DESTINATION" in params and "DESTINATION_OUTPOST_ID" not in params:
            params["DESTINATION_OUTPOST_ID"] = params["DESTINATION"]

        template_path = find_template(template_name, machine_type, machine_id)
        if not template_path:
            print(f"[AutoDeploy] No template found for machine '{machine_id}' (type='{machine_type}') in {TEMPLATES_DIR}")
            return False

        try:
            with open(template_path, "r", encoding="utf-8") as tf:
                raw_template = tf.read()
        except Exception as e:
            print(f"[AutoDeploy] Failed to read template {template_path}: {e}")
            return False

        # Build substitution dictionary
        sub_vars: Dict[str, Any] = {
            "MACHINE_ID": machine_id,
            "machine_id": machine_id,
            "TYPE_ID": machine_type or "",
            "type_id": machine_type or "",
            "LOCATION_ID": location_id,
            "OUTPOST": location_id,
        }
        sub_vars.update(params)

        final_code = substitute_placeholders(raw_template, sub_vars)
        target_script = os.path.join(self.workspace, f"{machine_id}.py")

        print(f"[AutoDeploy] === Deploying {machine_id} ===")
        print(f"[AutoDeploy] Target: {target_script}")
        print(f"[AutoDeploy] Template: {os.path.basename(template_path)}")
        print(f"[AutoDeploy] Parameters: {params}")

        if self.dry_run:
            print("[AutoDeploy] [DRY RUN] Generated script content:")
            print("--- START ---")
            print(final_code.strip())
            print("--- END ---")
            return True

        # Write code to file
        try:
            with open(target_script, "w", encoding="utf-8") as out_f:
                out_f.write(final_code)
            print(f"[AutoDeploy] Wrote script to {target_script}")
        except Exception as e:
            print(f"[AutoDeploy] Error writing {target_script}: {e}")
            return False

        # Give the game engine a brief moment to observe the file write
        time.sleep(0.5)

        # Launch script in running game via DAP
        print(f"[AutoDeploy] Launching {machine_id} in game via DAP...")
        launched = launch_script(self.workspace, target_script)
        if launched:
            print(f"[AutoDeploy] [SUCCESS] {machine_id} is now running in the game.")
            self.state.setdefault("deployed", {})[machine_id] = {
                "timestamp": time.time(),
                "template": os.path.basename(template_path),
                "script": f"{machine_id}.py",
                "params": params,
            }
            save_state(self.state)
            self.pending_directives.pop(machine_id, None)
            return True
        else:
            print(f"[AutoDeploy] [ERROR] Failed to launch {machine_id} via DAP. Script file remains on disk.")
            return False

    def scan_and_deploy(self) -> int:
        """
        Scans workspace JSON and log events for any unscripted/idle machines needing deployment.
        Returns count of successfully deployed machines.
        """
        self.read_new_log_entries()
        ws_data = self.read_workspace_state()
        if not ws_data:
            print("[AutoDeploy] Could not read codeterraform-workspace.json")
            return 0

        machines = ws_data.get("context", {}).get("machines", {})
        scripts = ws_data.get("context", {}).get("scripts", {})

        count = 0
        for m_id, m_data in machines.items():
            if m_id in self.state.get("deployed", {}) and not self.force:
                continue

            script_info = scripts.get(m_id)
            script_file = os.path.join(self.workspace, f"{m_id}.py")
            is_file_empty = not os.path.exists(script_file) or os.path.getsize(script_file) == 0

            # Eligible for deployment if:
            # 1. Script is idle and source is empty/missing
            # 2. Or a pending directive specifically requested this machine
            is_idle = script_info and script_info.get("status") == "idle"
            is_unscripted = not script_info or len(script_info.get("source", "").strip()) == 0 or is_file_empty
            has_directive = m_id in self.pending_directives

            if (is_idle and is_unscripted) or has_directive:
                ok = self.deploy_machine(m_id, m_data)
                if ok:
                    count += 1

        return count

    def run_daemon(self, interval: float = 2.0) -> None:
        """Continuous background monitoring loop."""
        print(f"[AutoDeploy] Daemon running for workspace: {self.workspace}")
        print(f"[AutoDeploy] Monitoring: {self.log_file_path} and {self.workspace_json_path}")
        print(f"[AutoDeploy] Templates: {TEMPLATES_DIR}")
        print("[AutoDeploy] Press Ctrl+C to stop.")

        # Seed initial log offset to end of current log to only watch new events
        if os.path.exists(self.log_file_path):
            self.log_offset = os.path.getsize(self.log_file_path)

        while True:
            try:
                self.scan_and_deploy()
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n[AutoDeploy] Daemon stopped.")
                break
            except Exception as e:
                print(f"[AutoDeploy] Unexpected error in daemon loop: {e}")
                time.sleep(interval)


def main():
    # 'tools' is distributed standalone; its install location says nothing
    # about where the workspace is. Resolve via early_game's discovery (cwd,
    # then the game's app-data save_*_scripts folders) instead.
    default_ws = find_latest_workspace()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workspace", default=default_ws, help=f"Workspace root (default: {default_ws or 'auto-detect'})")
    parser.add_argument("--scan", action="store_true", help="One-shot scan and deploy idle machines")
    parser.add_argument("--daemon", action="store_true", help="Continuous monitoring daemon")
    parser.add_argument("--deploy", dest="deploy_id", metavar="MACHINE_ID", help="Deploy a specific machine ID")
    parser.add_argument("--template", help="Template name to use (e.g. 'solar', 'pioneer_hauler')")
    parser.add_argument("--param", action="append", metavar="KEY=VALUE", help="Set template parameters (can be repeated)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without writing files or launching")
    parser.add_argument("--force", action="store_true", help="Deploy even if recorded in .deployed_state.json")
    args = parser.parse_args()

    if not args.workspace:
        print("[AutoDeploy] Error: No active save workspace found. Specify with --workspace <path>")
        sys.exit(1)

    deployer = AutoDeployer(workspace=args.workspace, dry_run=args.dry_run, force=args.force)

    if args.deploy_id:
        params: Dict[str, str] = {}
        if args.param:
            for p in args.param:
                if "=" in p:
                    k, v = p.split("=", 1)
                    params[k] = v
        ws_data = deployer.read_workspace_state() or {}
        machine_data = ws_data.get("context", {}).get("machines", {}).get(args.deploy_id)
        ok = deployer.deploy_machine(args.deploy_id, machine_data, template_override=args.template, extra_params=params)
        sys.exit(0 if ok else 1)

    if args.daemon:
        deployer.run_daemon()
        sys.exit(0)

    # Default to one-shot scan if not specified
    count = deployer.scan_and_deploy()
    print(f"[AutoDeploy] Scan complete. Deployed {count} machine(s).")


if __name__ == "__main__":
    main()

