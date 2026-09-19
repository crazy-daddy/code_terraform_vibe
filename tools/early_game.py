#!/usr/bin/env python3
r"""
Early Game Speedrun Orchestrator for Code: Terraform
=====================================================
Automates the early-game bootstrapping flow for fresh saves:
  1. Boot-up / First Contact onboarding (boot -> power -> sensors -> uplink -> calibrations).
  2. Earth contract puzzle solvers (relay_hack, xenogenetics, corrupted_archive).
  3. Standalone machine deployment (<20k TP before Shared Library unlocks).
  4. Real-time background watcher for newly placed machines.

Usage:
    # Auto-detect newest save folder and run First Contact onboarding:
    python tools/early_game.py --onboarding

    # Solve the 3 intro Earth contracts for +3,750 starter credits:
    python tools/early_game.py --contracts

    # Scan and deploy early-game scripts to all idle machines:
    python tools/early_game.py --scan

    # All-in-one run (onboarding + contracts + deploy idle machines):
    python tools/early_game.py --all

    # All-in-one AND stay running in background daemon:
    python tools/early_game.py --all --daemon
    # (or use the shortcut alias):
    python tools/early_game.py --auto

    # Target an explicit save workspace:
    python tools/early_game.py --workspace "C:\...\save_mu86b3z3_y90qbv_scripts" --auto
"""

import os
import sys
import re
import glob
import json
import time
import uuid
import argparse
import functools
import shutil
from typing import Dict, Any, Optional, List

# Unbuffered stdout for live progress in console and pipes
print = functools.partial(print, flush=True)

# Ensure dap_client is importable from tools/
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from dap_client import launch_script  # type: ignore
except ImportError as e:
    print(f"[EarlyGame] Warning: dap_client could not be imported ({e}). In-game launches will be disabled.")
    def launch_script(workspace: str, script_path: str, timeout: int = 15) -> bool:
        return False

APPDATA_GAME_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
TEMPLATES_EARLY_DIR = os.path.join(SCRIPT_DIR, "templates", "early")
TEMPLATES_LATE_DIR = os.path.join(SCRIPT_DIR, "templates")

# ==============================================================================
# SCRIPT REPOSITORIES: ONBOARDING & CONTRACTS
# ==============================================================================

ONBOARDING_DIR = os.path.join(SCRIPT_DIR, "onboarding")
CONTRACTS_DIR = os.path.join(SCRIPT_DIR, "contracts")

def get_onboarding_script(filename: str) -> str:
    """Reads onboarding script content from tools/onboarding/."""
    path = os.path.join(ONBOARDING_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def get_contract_script(filename: str) -> str:
    """Reads contract solver script content from tools/contracts/."""
    path = os.path.join(CONTRACTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ==============================================================================
# WORKSPACE & SAVE DETECTION
# ==============================================================================

def find_latest_workspace() -> Optional[str]:
    """Finds the most recently modified save_*_scripts directory in the app-data folder."""
    candidates = glob.glob(os.path.join(APPDATA_GAME_DIR, "save_*_scripts"))
    if not candidates:
        # Fallback to current working directory if within a scripts folder
        cwd = os.getcwd()
        if "save_" in cwd and "_scripts" in cwd:
            return cwd
        return None
    # Sort by modification time descending
    candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return candidates[0]


def resolve_save_json(workspace: str) -> Optional[str]:
    """Finds the matching save_*.json file beside the scripts folder."""
    base_dir = os.path.dirname(os.path.abspath(workspace))
    folder_name = os.path.basename(os.path.abspath(workspace))
    if folder_name.endswith("_scripts"):
        save_id = folder_name[:-8]  # Strip '_scripts'
        save_file = os.path.join(base_dir, f"{save_id}.json")
        if os.path.exists(save_file):
            return save_file
    return None


def check_workspace_ready(workspace: str) -> bool:
    """Checks if codeterraform-workspace.json exists."""
    ws_file = os.path.join(workspace, "codeterraform-workspace.json")
    if not os.path.exists(ws_file):
        print("\n" + "=" * 70)
        print("[!]  EXTERNAL SCRIPTS FOLDER NOT READY")
        print(f"Target directory: {workspace}")
        print("Missing: codeterraform-workspace.json")
        print("\nHow to fix in-game:")
        print("  1. In Code: Terraform, open Settings (from menu or top bar)")
        print("  2. Navigate to: Editor -> External Editor")
        print("  3. Click: 'Open Scripts Folder' (or 'Set Up VS Code')")
        print("=" * 70 + "\n")
        return False
    return True


def read_save_state(workspace: str) -> Dict[str, Any]:
    """Reads the complete live simulation state from the active save_*.json file."""
    save_json = resolve_save_json(workspace)
    if save_json and os.path.exists(save_json):
        try:
            with open(save_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("state", {})
        except Exception as e:
            print(f"[EarlyGame] Warning: Failed to read {save_json} with Exception: {e}")
    return {}


def read_workspace_context(workspace: str) -> Dict[str, Any]:
    """Reads full state, ensuring real-time machine and script definitions from codeterraform-workspace.json take priority."""
    state = read_save_state(workspace)

    ws_file = os.path.join(workspace, "codeterraform-workspace.json")
    if os.path.exists(ws_file):
        try:
            with open(ws_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                ctx = data.get("context", {})

                # Merge any missing top-level keys
                for k, v in ctx.items():
                    if k not in state or state[k] is None or state[k] == {}:
                        state[k] = v

                # Machines & scripts are exported immediately in real-time to workspace.json!
                ws_machines = ctx.get("machines", {})
                if ws_machines:
                    state_machines = dict(state.get("machines", {}))
                    state_machines.update(ws_machines)
                    state["machines"] = state_machines

                ws_scripts = ctx.get("scripts", {})
                if ws_scripts:
                    state_scripts = dict(state.get("scripts", {}))
                    state_scripts.update(ws_scripts)
                    state["scripts"] = state_scripts

                ws_tech = ctx.get("unlockedTech", [])
                if ws_tech:
                    state["unlockedTech"] = ws_tech

        except Exception as e:
            print(f"[EarlyGame] Warning: Failed to read codeterraform-workspace.json with Exception: {e}")

    return state


# ==============================================================================
# SCRIPT EXECUTION & REGISTRATION HELPERS
# ==============================================================================

def get_registered_documents(workspace: str) -> set:
    """Returns set of registered document paths and IDs from codeterraform-workspace.json."""
    ws_json = os.path.join(workspace, "codeterraform-workspace.json")
    if os.path.exists(ws_json):
        try:
            with open(ws_json, "r", encoding="utf-8") as f:
                data = json.load(f)
                docs = data.get("documents", [])
                registered = set()
                for d in docs:
                    if "path" in d:
                        registered.add(d["path"])
                        registered.add(os.path.basename(d["path"]))
                    if "id" in d:
                        registered.add(d["id"])
                return registered
        except Exception as e:
            print(f"[EarlyGame] Warning: Failed to parse documents from {ws_json} with Exception: {e}")
    return set()


def is_script_registered(workspace: str, filename: str) -> bool:
    """Checks whether filename or script ID is listed in codeterraform-workspace.json documents."""
    registered = get_registered_documents(workspace)
    base = os.path.basename(filename)
    return base in registered or filename in registered


def wait_for_script_registration(workspace: str, filename: str, prompt_message: str = "", timeout: float = 60.0) -> bool:
    """Waits for a script to be registered in codeterraform-workspace.json documents, prompting user if needed."""
    if is_script_registered(workspace, filename):
        return True

    if prompt_message:
        print(f"\n[EarlyGame] [WAIT] {prompt_message}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        if is_script_registered(workspace, filename):
            print(f"[EarlyGame] [OK] Detected '{filename}' registered in workspace documents!")
            return True

    print(f"[EarlyGame] [!] Timeout waiting for '{filename}' to appear in documents.")
    return False


def get_log_offset(workspace: str) -> int:
    """Returns current byte size of logs/all.log to allow tailing only new entries."""
    log_file = os.path.join(workspace, "logs", "all.log")
    if os.path.exists(log_file):
        return os.path.getsize(log_file)
    return 0


def read_full_log(workspace: str) -> str:
    """Reads entire content of logs/all.log."""
    log_file = os.path.join(workspace, "logs", "all.log")
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        except Exception as e:
            print(f"[EarlyGame] Warning: Failed to read {log_file} with Exception: {e}")
    return ""


def wait_for_log_pattern(workspace: str, pattern: str, start_offset: int = 0, timeout: float = 60.0) -> bool:
    """Waits until pattern appears in logs/all.log."""
    log_file = os.path.join(workspace, "logs", "all.log")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(log_file):
            try:
                with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                    full_text = f.read()
                    if re.search(pattern, full_text, re.IGNORECASE):
                        return True
            except Exception as e:
                print(f"[EarlyGame] Warning: Error checking log {log_file} with Exception: {e}")
        time.sleep(0.5)
    return False


def wait_for_sensor_repair(workspace: str, sensor_id: str, timeout: float = 30.0) -> bool:
    """Waits until sensor is marked repaired in codeterraform-workspace.json."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ctx = read_workspace_context(workspace)
        sensor_data = ctx.get("machines", {}).get(sensor_id, {}).get("data", {})
        if sensor_data.get("repaired") == 1:
            return True
        time.sleep(0.5)
    return False


def wait_for_contract_completion(workspace: str, contract_id: str, timeout: float = 30.0) -> bool:
    """Waits until contract status is 'completed' in codeterraform-workspace.json."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ctx = read_workspace_context(workspace)
        if ctx.get("contractStatus", {}).get(contract_id) == "completed":
            return True
        time.sleep(0.5)
    return False


def restart_game_script(workspace: str, script_name: str, source: str = "") -> bool:
    """Restarts a script in-game using the game's official .codeterraform command bridge."""
    try:
        ws_json_path = os.path.join(workspace, "codeterraform-workspace.json")
        if not os.path.exists(ws_json_path):
            return False
        with open(ws_json_path, "r", encoding="utf-8") as f:
            ws = json.load(f)
        session = ws.get("session")
        if not session:
            return False

        # Resolve document path and script ID from workspace documents
        target_name = os.path.basename(script_name)
        target_base = os.path.splitext(target_name)[0]
        actual_script_id = target_base
        actual_file_name = f"{target_base}.py"

        for doc in ws.get("documents", []):
            d_path = doc.get("path", "")
            d_id = doc.get("id", "")
            if target_name in (d_path, d_id) or target_base in (d_path, d_id, os.path.splitext(d_path)[0]):
                actual_script_id = d_id
                actual_file_name = d_path
                break

        script_path = os.path.join(workspace, actual_file_name)
        if os.path.exists(script_path):
            with open(script_path, "r", encoding="utf-8", newline="") as f:
                source = f.read()

        dot_ct = os.path.join(workspace, ".codeterraform")
        os.makedirs(dot_ct, exist_ok=True)

        req_id = str(uuid.uuid4())
        cmd_data = {
            "version": 1,
            "requestId": req_id,
            "issuedAt": int(time.time() * 1000),
            "session": session,
            "action": "run",
            "scriptId": actual_script_id,
            "source": source
        }

        lock_path = os.path.join(dot_ct, "command.lock")
        cmd_path = os.path.join(dot_ct, "command.json")
        tmp_path = os.path.join(dot_ct, f"command.json.{req_id}.tmp")
        result_path = os.path.join(dot_ct, "command-result.json")

        if os.path.exists(lock_path):
            if time.time() - os.path.getmtime(lock_path) > 30:
                try:
                    os.remove(lock_path)
                except Exception:
                    pass

        try:
            with open(lock_path, "x") as f:
                f.write(req_id)
        except Exception:
            return False

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(cmd_data, f)
            os.replace(tmp_path, cmd_path)

            deadline = time.time() + 10.0
            while time.time() < deadline:
                if os.path.exists(result_path):
                    try:
                        with open(result_path, "r", encoding="utf-8") as f:
                            res = json.load(f)
                        if res.get("requestId") == req_id:
                            return res.get("ok", False)
                    except Exception:
                        pass
                time.sleep(0.1)
        finally:
            if os.path.exists(lock_path):
                try:
                    os.remove(lock_path)
                except Exception:
                    pass
    except Exception as e:
        print(f"[EarlyGame] Warning: restart_game_script failed with Exception: {e}")
    return False


def write_and_launch(workspace: str, filename: str, content: str, dry_run: bool = False, prompt_message: str = "") -> bool:
    """Writes a script file into the workspace, ensures document registration, and restarts/launches it."""
    script_path = os.path.join(workspace, filename)

    if not dry_run:
        if not is_script_registered(workspace, filename):
            if prompt_message:
                ok = wait_for_script_registration(workspace, filename, prompt_message, timeout=60.0)
                if not ok:
                    print(f"[EarlyGame] [!] Skipping launch of {filename} (unregistered).")
                    return False
            else:
                time.sleep(0.5)

        with open(script_path, "w", encoding="utf-8") as f:
            f.write(content)
        time.sleep(0.3)  # Give file watcher a moment

        # Try in-game command bridge first (instant hot-restart)
        if restart_game_script(workspace, filename):
            return True

        # Fallback to DAP launch
        success = launch_script(workspace, script_path)
        if not success:
            print(f"[EarlyGame] [!] {filename} launch returned False (check in-game console / registration).")
        return success
    else:
        print(f"[EarlyGame] [DRY RUN] Would write and launch {filename}.")
        return True


# ==============================================================================
# ONBOARDING AUTOMATION (FIRST CONTACT)
# ==============================================================================

def run_onboarding(workspace: str, dry_run: bool = False) -> None:
    """Executes the First Contact sequence step by step, synchronizing with all.log and workspace state."""
    print("\n--- Running First Contact Onboarding Sequence ---")
    if not check_workspace_ready(workspace):
        return

    full_log = read_full_log(workspace)
    ctx = read_workspace_context(workspace)
    machines = ctx.get("machines", {})

    # 1. Boot sequence (~5.7s simworker delay total)
    if "Turn On Power: online" in full_log or "power system can be activated" in full_log:
        print("[EarlyGame] [OK] Boot sequence already completed.")
    else:
        print("[EarlyGame] Step 1: Running boot.py...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "boot.py", get_onboarding_script("boot.py"), dry_run) and not dry_run:
            print("[EarlyGame] Waiting for boot diagnostics to complete (sim delay ~5.7s)...")
            ok = wait_for_log_pattern(workspace, r"power system can be activated|use:\s*activate_power", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Boot diagnostics complete.")
            else:
                print("[EarlyGame] [!] Timeout waiting for boot diagnostics; continuing.")

    # 2. Planet Power (~20s online transition)
    full_log = read_full_log(workspace)
    if "Turn On Power: online" in full_log:
        print("[EarlyGame] [OK] Power already turned online.")
    else:
        print("[EarlyGame] Step 2: Running planet_power.py (activate_power)...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "planet_power.py", get_onboarding_script("planet_power.py"), dry_run) and not dry_run:
            ok = wait_for_log_pattern(workspace, r"Turn On Power:\s*online", offset, timeout=35.0)
            if ok:
                print("[EarlyGame] [OK] Power system online.")
            else:
                print("[EarlyGame] [!] Timeout waiting for 'Turn On Power: online'.")

    # 3. Planet Sensors (~16s online transition)
    full_log = read_full_log(workspace)
    if "Read Sensor Data: online" in full_log:
        print("[EarlyGame] [OK] Sensor data already read.")
    else:
        print("[EarlyGame] Step 3: Running planet_sensors.py (activate_sensors)...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "planet_sensors.py", get_onboarding_script("planet_sensors.py"), dry_run) and not dry_run:
            ok = wait_for_log_pattern(workspace, r"Read Sensor Data:\s*online", offset, timeout=35.0)
            if ok:
                print("[EarlyGame] [OK] Sensors active.")
            else:
                print("[EarlyGame] [!] Timeout waiting for 'Read Sensor Data: online'.")

    # 4. Uplink (~16s online transition)
    full_log = read_full_log(workspace)
    if "Establish Uplink: online" in full_log:
        print("[EarlyGame] [OK] Uplink already established.")
    else:
        print("[EarlyGame] Step 4: Running uplink.py (transmitting temperature to Earth)...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "uplink.py", get_onboarding_script("uplink.py"), dry_run) and not dry_run:
            ok = wait_for_log_pattern(workspace, r"Establish Uplink:\s*online", offset, timeout=35.0)
            if ok:
                print("[EarlyGame] [OK] Uplink established! First Contact completed.")
            else:
                print("[EarlyGame] [!] Timeout waiting for 'Establish Uplink: online'.")

    # Refresh context after First Contact
    ctx = read_workspace_context(workspace)
    machines = ctx.get("machines", {})

    # 5. Pressure Sensor Stabilization (5 tests * 1.5s = 7.5s sim delay)
    ps_data = machines.get("pressure_sensor", {}).get("data", {})
    if ps_data.get("repaired") == 1 or "Pressure sensor stabilize result: ok" in read_full_log(workspace):
        print("[EarlyGame] [OK] Pressure sensor already stabilized.")
    else:
        print("[EarlyGame] Step 5: Stabilizing pressure_sensor.py...")
        offset = get_log_offset(workspace)
        prompt_ps = "Please click on 'Pressure Sensor' in the in-game UI to create its script slot..."
        if write_and_launch(workspace, "pressure_sensor.py", get_onboarding_script("pressure_sensor.py"), dry_run, prompt_message=prompt_ps) and not dry_run:
            print("[EarlyGame] Running pressure sensor stabilization suite (5 tests, ~7.5s)...")
            ok = wait_for_sensor_repair(workspace, "pressure_sensor", timeout=30.0) or wait_for_log_pattern(workspace, r"Pressure sensor stabilize result:\s*ok", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Pressure sensor stabilized! Contracts and Harvesting unlocked.")
            else:
                print("[EarlyGame] [!] Waiting for pressure sensor stabilization confirmation...")

    # 6. Oxygen Sensor Calibration (5 tests * 1.5s = 7.5s sim delay)
    ox_data = machines.get("oxygen_sensor", {}).get("data", {})
    if ox_data.get("repaired") == 1 or "Oxygen sensor calibrate result: ok" in read_full_log(workspace):
        print("[EarlyGame] [OK] Oxygen sensor already calibrated.")
    else:
        print("[EarlyGame] Step 6: Calibrating oxygen_sensor.py...")
        offset = get_log_offset(workspace)
        prompt_ox = "Please click on 'Oxygen Sensor' in the in-game UI to create its script slot..."
        if write_and_launch(workspace, "oxygen_sensor.py", get_onboarding_script("oxygen_sensor.py"), dry_run, prompt_message=prompt_ox) and not dry_run:
            print("[EarlyGame] Running oxygen sensor calibration suite (5 tests, ~7.5s)...")
            ok = wait_for_sensor_repair(workspace, "oxygen_sensor", timeout=30.0) or wait_for_log_pattern(workspace, r"Oxygen sensor calibrate result:\s*ok", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Oxygen sensor calibrated! Atmosphere unlocked.")
            else:
                print("[EarlyGame] [!] Waiting for oxygen sensor calibration confirmation...")

    print("[EarlyGame] Onboarding and calibration phase finished.")


# ==============================================================================
# INTRO CONTRACTS AUTOMATION
# ==============================================================================

def run_contracts(workspace: str, dry_run: bool = False) -> None:
    """Solves the early Earth contracts across Intro and Earth Clearance tiers."""
    print("\n--- Running Earth Contract Solvers (~26,250 total credits) ---")
    if not check_workspace_ready(workspace):
        return

    ctx = read_workspace_context(workspace)
    contract_status = ctx.get("contractStatus", {})
    prompt_contracts = "Please click on the 'Contracts' tab in-game to initialize Earth contracts..."

    # Check if contracts are registered, if not prompt
    if not is_script_registered(workspace, "relay_hack.py") and not is_script_registered(workspace, "contract_relay_hack"):
        wait_for_script_registration(workspace, "relay_hack.py", prompt_contracts, timeout=60.0)

    # 1. Relay Hack
    if contract_status.get("relay_hack") == "completed":
        print("[EarlyGame] [OK] Relay Hack contract already completed.")
    else:
        print("[EarlyGame] Solving Orbital Relay Hack...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "relay_hack.py", get_contract_script("relay_hack.py"), dry_run, prompt_message=prompt_contracts) and not dry_run:
            ok = wait_for_contract_completion(workspace, "relay_hack", timeout=30.0) or wait_for_log_pattern(workspace, r"Relay Hack result:\s*(accepted|ok|already_completed)", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Orbital Relay Hack completed (+1,250 cr).")
            else:
                print("[EarlyGame] [!] Relay Hack transmitted; check logs/workspace.")

    # 2. Xenogenetics Survey
    if contract_status.get("xenogenetics") == "completed":
        print("[EarlyGame] [OK] Xenogenetics Survey contract already completed.")
    else:
        print("[EarlyGame] Solving Xenogenetics Survey...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "xenogenetics.py", get_contract_script("xenogenetics.py"), dry_run, prompt_message=prompt_contracts) and not dry_run:
            ok = wait_for_contract_completion(workspace, "xenogenetics", timeout=30.0) or wait_for_log_pattern(workspace, r"Xenogenetics result:\s*(accepted|ok|already_completed)", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Xenogenetics Survey completed (+1,250 cr).")
            else:
                print("[EarlyGame] [!] Xenogenetics transmitted; check logs/workspace.")

    # 3. Corrupted Archive
    if contract_status.get("corrupted_archive") == "completed":
        print("[EarlyGame] [OK] Corrupted Archive contract already completed.")
    else:
        print("[EarlyGame] Solving Corrupted Archive...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "corrupted_archive.py", get_contract_script("corrupted_archive.py"), dry_run, prompt_message=prompt_contracts) and not dry_run:
            ok = wait_for_contract_completion(workspace, "corrupted_archive", timeout=30.0) or wait_for_log_pattern(workspace, r"Corrupted Archive result:\s*(accepted|ok|already_completed)", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Corrupted Archive completed (+1,250 cr).")
            else:
                print("[EarlyGame] [!] Corrupted Archive transmitted; check logs/workspace.")

    # 4. Sealed Vault (Earth Clearance @ 3.0 ppt O2)
    if contract_status.get("sealed_vault") == "completed":
        print("[EarlyGame] [OK] Sealed Vault contract already completed.")
    elif is_script_registered(workspace, "sealed_vault.py"):
        print("[EarlyGame] Solving Sealed Vault (Earth Clearance @ 3.0 ppt O2)...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "sealed_vault.py", get_contract_script("sealed_vault.py"), dry_run, prompt_message=prompt_contracts) and not dry_run:
            ok = wait_for_contract_completion(workspace, "sealed_vault", timeout=30.0) or wait_for_log_pattern(workspace, r"Sealed Vault result:\s*(accepted|ok|already_completed)", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Sealed Vault completed (+10,000 cr).")
            else:
                print("[EarlyGame] [!] Sealed Vault transmitted; check logs/workspace.")

    # 5. Terminal Breach (Earth Clearance @ 3.0 ppt O2)
    if contract_status.get("terminal_breach") == "completed":
        print("[EarlyGame] [OK] Terminal Breach contract already completed.")
    elif is_script_registered(workspace, "terminal_breach.py"):
        print("[EarlyGame] Solving Alien Terminal Breach (Earth Clearance @ 3.0 ppt O2)...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "terminal_breach.py", get_contract_script("terminal_breach.py"), dry_run, prompt_message=prompt_contracts) and not dry_run:
            ok = wait_for_contract_completion(workspace, "terminal_breach", timeout=30.0) or wait_for_log_pattern(workspace, r"Terminal Breach result:\s*(accepted|ok|already_completed)", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Terminal Breach completed (+7,500 cr).")
            else:
                print("[EarlyGame] [!] Terminal Breach transmitted; check logs/workspace.")

    # 6. Underground Data Tablet (Earth Clearance @ 3.0 ppt O2)
    if contract_status.get("data_tablet") == "completed":
        print("[EarlyGame] [OK] Data Tablet contract already completed.")
    elif is_script_registered(workspace, "data_tablet.py"):
        print("[EarlyGame] Solving Underground Data Tablet (Earth Clearance @ 3.0 ppt O2)...")
        offset = get_log_offset(workspace)
        if write_and_launch(workspace, "data_tablet.py", get_contract_script("data_tablet.py"), dry_run, prompt_message=prompt_contracts) and not dry_run:
            ok = wait_for_contract_completion(workspace, "data_tablet", timeout=30.0) or wait_for_log_pattern(workspace, r"Data Tablet result:\s*(accepted|ok|already_completed)", offset, timeout=30.0)
            if ok:
                print("[EarlyGame] [OK] Data Tablet completed (+5,000 cr).")
            else:
                print("[EarlyGame] [!] Data Tablet transmitted; check logs/workspace.")

    print("[EarlyGame] Contract solving complete. Capital unlocked for base expansion.")


# ==============================================================================
# STANDALONE MACHINE TEMPLATES & DEPLOYMENT (<20k TP)
# ==============================================================================

def get_template_content(machine_type: str, use_early: bool = True) -> Optional[str]:
    """Retrieves template content from tools/templates/early/ or tools/templates/."""
    template_dir = TEMPLATES_EARLY_DIR if use_early else TEMPLATES_LATE_DIR
    template_path = os.path.join(template_dir, f"{machine_type}.py")

    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return f.read()

    # Fallback to late template if early not available
    fallback_path = os.path.join(TEMPLATES_LATE_DIR, f"{machine_type}.py")
    if os.path.exists(fallback_path):
        with open(fallback_path, "r", encoding="utf-8") as f:
            return f.read()

    return None


def resolve_machine_template_type(type_id: str) -> Optional[str]:
    """Maps game machine typeId to a template name."""
    mapping = {
        "solar_generator": "solar",
        "pressure_generator": "pressure",
        "oxygen_generator": "o2gen",
        "heat_generator": "heater",
        "temp_heater": "heater",
        "harvester": "harvester",
        "scanner": "scanner",
        "smelter": "smelter",
        "charging_station": "charging_station",
        "vehicle_charging_station": "charging_station",
        "rover": "rover",
        "pioneer": "pioneer",
    }
    return mapping.get(type_id)


def trigger_midgame_migration(workspace: str) -> bool:
    """Migrates workspace to the modular mid-game architecture (~150k TP).
    Copies lib/ from reference workspace if not already present."""
    ref_lib = os.path.join(SCRIPT_DIR, "..", "lib")
    target_lib = os.path.join(workspace, "lib")
    if not os.path.exists(ref_lib):
        return False

    migrated = False
    if not os.path.exists(target_lib) or not os.path.exists(os.path.join(target_lib, "version_guard.py")):
        print("\n" + "=" * 76)
        print(" [EarlyGame] *** 150,000 TP REACHED: MID-GAME ARCHITECTURE ACTIVATION ***")
        print("=" * 76)
        print(f"[EarlyGame] Deploying shared library (lib/) to {workspace}...")
        os.makedirs(target_lib, exist_ok=True)
        for item in os.listdir(ref_lib):
            s = os.path.join(ref_lib, item)
            d = os.path.join(target_lib, item)
            if os.path.isfile(s):
                shutil.copy2(s, d)
            elif os.path.isdir(s) and item != "__pycache__":
                shutil.copytree(s, d, dirs_exist_ok=True)
        print("[EarlyGame] [OK] Shared lib/ deployed successfully. Signal Bus & Data Archive ready.")
        migrated = True
    return migrated


# In-memory tracking of machines deployed and vehicles mounted
_DEPLOYED_IN_SESSION = set()
_VEHICLE_MOUNTED = set()

def scan_and_deploy_machines(workspace: str, dry_run: bool = False) -> int:
    """Finds idle, errored, or unscripted deployed machines and assigns early templates."""
    if not check_workspace_ready(workspace):
        return 0

    state = read_workspace_context(workspace)

    machines = state.get("machines", {})
    scripts = state.get("scripts", {})
    unlocked_tech = set(state.get("unlockedTech", []))

    # Early templates remain active until the 150k TP mid-game architecture migration
    research_rates = state.get("researchRates", {})
    total_tp = int(research_rates.get("terraform", {}).get("lastValue", 0))
    if total_tp >= 150_000:
        trigger_midgame_migration(workspace)
        use_early = False
    else:
        use_early = True

    deployed_count = 0

    for m_id, m_data in machines.items():
        type_id = m_data.get("typeId") or m_data.get("type")
        template_name = resolve_machine_template_type(type_id)
        if not template_name:
            continue

        script_name = f"{m_id}.py"
        script_file_path = os.path.join(workspace, script_name)

        # Check in-game script state
        script_state = scripts.get(m_id, {})
        status = script_state.get("status")
        is_idle = status in (None, "idle")
        is_error = status == "error"
        has_source = bool(script_state.get("source", "").strip())
        file_exists = os.path.exists(script_file_path) and os.path.getsize(script_file_path) > 0

        # Check if file has incompatible imports when in early mode
        needs_repair = False
        if file_exists and use_early:
            try:
                with open(script_file_path, "r", encoding="utf-8") as sf:
                    content_head = sf.read(250)
                    if "from terraforming import" in content_head or "from pressure import" in content_head or "from smelter import" in content_head:
                        needs_repair = True
            except Exception:
                pass

        # If vehicle needs hardware mounting first, stage and run mount_vehicle
        if template_name in ("rover", "pioneer") and m_id not in _VEHICLE_MOUNTED:
            mounted_modules = set(m_data.get("mountedModules", []))
            target_mods = {"nav_module", "sonar_module", "drill_module"} if template_name == "rover" else {"nav_module", "battery_holder_small", "cargo_rack_small"}
            if not target_mods.issubset(mounted_modules):
                mount_content = get_template_content("mount_vehicle", use_early=True)
                if mount_content:
                    print(f"[EarlyGame] Vehicle {m_id} detected! Executing module mounting routine...")
                    write_and_launch(workspace, script_name, mount_content, dry_run=dry_run)
                    time.sleep(2.0)
                    _VEHICLE_MOUNTED.add(m_id)
            else:
                _VEHICLE_MOUNTED.add(m_id)

        # Determine if machine needs operational template
        should_deploy = False
        if not file_exists or (is_idle and not has_source) or is_error or needs_repair:
            should_deploy = True
        elif template_name in ("rover", "pioneer") and m_id in _VEHICLE_MOUNTED and status != "running":
            should_deploy = True

        if should_deploy:
            content = get_template_content(template_name, use_early=use_early)
            if content:
                print(f"[EarlyGame] Deploying operational {template_name} template to {m_id} ({script_name})...")
                ok = write_and_launch(workspace, script_name, content, dry_run=dry_run)
                if not dry_run:
                    # Send hot-restart via command.json
                    restart_game_script(workspace, m_id, content)
                _DEPLOYED_IN_SESSION.add(m_id)
                deployed_count += 1
                time.sleep(0.3)
        elif status == "running" and m_id in _DEPLOYED_IN_SESSION:
            pass
        elif (is_error or needs_repair) and m_id in _DEPLOYED_IN_SESSION:
            _DEPLOYED_IN_SESSION.discard(m_id)

    if deployed_count > 0:
        print(f"[EarlyGame] Machine scan complete. Deployed/repaired: {deployed_count}")
    return deployed_count


# ==============================================================================
# SPEEDRUN ADVISOR & LIVE MONITOR
# ==============================================================================

def get_live_metrics(workspace: str) -> Dict[str, Any]:
    """Extracts live player, planet, power, and terraforming metrics from save."""
    state = read_workspace_context(workspace)

    planet = state.get("planet", {})
    player = state.get("player", {})
    atmos = planet.get("atmosphere", {})
    temp = planet.get("temperature", {})
    biomass = planet.get("biomass", {})
    power = planet.get("power", {})
    clock = planet.get("clock", {})
    research = state.get("researchRates", {})
    machines = state.get("machines", {})
    unlocked_tech = set(state.get("unlockedTech", []))

    # Terraforming points
    tf_rate = research.get("terraform", {})
    total_tp = int(tf_rate.get("lastValue", 0))
    tp_rate = float(tf_rate.get("ratePerGh", 0.0))

    # Atmosphere & rates
    o2_rate = research.get("oxygen", {})
    o2_val = float(atmos.get("oxygen", o2_rate.get("lastValue", 0.0)))
    o2_delta = float(o2_rate.get("ratePerGh", 0.0))

    p_rate = research.get("pressure", {})
    p_val = float(atmos.get("pressure", p_rate.get("lastValue", 0.0)))
    p_delta = float(p_rate.get("ratePerGh", 0.0))

    t_rate = research.get("temperature", {})
    heat_units = float(temp.get("heatUnits", t_rate.get("lastValue", 0.0)))
    heat_delta = float(t_rate.get("ratePerGh", 0.0))
    surface_temp = float(temp.get("surface", -63.0))

    bio_val = float(biomass.get("totalTons", 0.0))

    credits = int(player.get("credits", 0))
    total_credits = int(player.get("totalCreditsEarned", 0))

    # Machine counts by category
    counts = {
        "solar": 0,
        "battery": 0,
        "o2gen": 0,
        "pressure": 0,
        "heater": 0,
        "smelter": 0,
        "harvester": 0,
        "scanner": 0,
        "bio": 0,
        "rover": 0,
    }
    for m_id, m in machines.items():
        t = m.get("typeId") or m.get("type", "")
        if t == "solar_generator":
            counts["solar"] += 1
        elif "battery" in t:
            counts["battery"] += 1
        elif t == "oxygen_generator":
            counts["o2gen"] += 1
        elif t == "pressure_generator":
            counts["pressure"] += 1
        elif t in ("temp_heater", "heat_generator"):
            counts["heater"] += 1
        elif t == "smelter":
            counts["smelter"] += 1
        elif t == "harvester":
            counts["harvester"] += 1
        elif t == "scanner":
            counts["scanner"] += 1
        elif "bio" in t:
            counts["bio"] += 1
        elif t == "rover":
            counts["rover"] += 1

    # Base building slots (only buildings at outpost_home consume building slots)
    base_buildings = [m for m in machines.values() if m.get("locationId") == "outpost_home"]
    slots_used = len(base_buildings)
    slots_max = 30 if "outpost_expansion_unlock" in unlocked_tech else 25
    slots_free = max(0, slots_max - slots_used)

    return {
        "credits": credits,
        "total_credits": total_credits,
        "total_tp": total_tp,
        "tp_rate": tp_rate,
        "o2": o2_val,
        "o2_rate": o2_delta,
        "pressure": p_val,
        "pressure_rate": p_delta,
        "heat_units": heat_units,
        "heat_rate": heat_delta,
        "surface_temp": surface_temp,
        "biomass": bio_val,
        "day": clock.get("dayNumber", 1),
        "time_of_day": clock.get("timeOfDay", "day"),
        "solar_eff": float(clock.get("solarEfficiency", 0.0)) * 100.0,
        "power_gen": power.get("generated", 0),
        "power_con": power.get("consumed", 0),
        "power_stored": power.get("stored", 0),
        "machine_counts": counts,
        "slots_used": slots_used,
        "slots_max": slots_max,
        "slots_free": slots_free,
        "total_machines": len(machines),
        "machines": machines,
        "unlocked_tech": unlocked_tech,
        "contracts": state.get("contractStatus", {}),
    }


def get_speedrun_advisory(metrics: Dict[str, Any]) -> Tuple[str, List[str], List[str]]:
    """
    Evaluates current state against Section 7 Optimized Speedrun Strategy (0 -> 100k TP Pioneer Rush).
    Returns (phase_title, next_milestones_list, recommendations_list).
    """
    tp = metrics["total_tp"]
    o2 = metrics["o2"]
    pressure = metrics["pressure"]
    heat = metrics["heat_units"]
    counts = metrics["machine_counts"]
    credits = metrics["credits"]
    tech = metrics["unlocked_tech"]

    milestones = []
    recs = []

    # Milestone tracking aligned with Section 7 speedrun targets
    if pressure < 0.20:
        if pressure < 0.10:
            milestones.append(f"0.100 kPa Pressure (currently {pressure:.3f}) -> Unlocks Mining Operations")
        if pressure < 0.11:
            milestones.append(f"0.110 kPa Pressure (currently {pressure:.3f}) -> Unlocks Rover Chassis")
        milestones.append(f"0.200 kPa Pressure (currently {pressure:.3f}) -> [!] Target: Atmospheric Density for Surface Rover")

    if o2 < 5.0:
        if o2 < 1.0:
            milestones.append(f"1.000 ppt O2 (currently {o2:.3f}) -> Unlocks Auto Feeders (feeder_unlock)")
        if o2 < 3.0:
            milestones.append(f"3.000 ppt O2 (currently {o2:.3f}) -> Unlocks Earth Clearance contracts")
        milestones.append(f"5.000 ppt O2 (currently {o2:.3f}) -> [!] Target: Ore Refinement & Smelter Unlock")

    if heat < 12.0:
        if heat < 10.0:
            milestones.append(f"10.0 HU Heat (currently {heat:.1f}) -> Unlocks Constructor Module")
        milestones.append(f"12.0 HU Heat (currently {heat:.1f}) -> [!] Target: Small Battery Holder & 100k TP Tri-Pillar")

    if tp < 20000:
        milestones.append(f"20,000 TP (currently {tp:,d}) -> Unlocks Shared Library (lib/ modular code)")
    if tp < 100000:
        milestones.append(f"100,000 TP (currently {tp:,d}) -> [!] PIONEER CHASSIS BREAKOUT (~98.6k TP at 0.2P + 5.0 O2 + 12.0 HU)")

    # Section 7 Speedrun Phase Progression
    if pressure < 0.20:
        # Phase 0 (Power Anchor) or Phase 1 (Pressure Rush)
        if counts["solar"] < 4 or counts["battery"] < 2:
            phase_title = "Phase 0: Boot & Power Anchor (Sec. 7.3 Step 1)"
            if counts["solar"] < 4:
                needed = 4 - counts["solar"]
                recs.append(f"POWER ANCHOR: Buy {needed}x Solar Generator (500 cr ea, currently {counts['solar']}/4) -> Needs 4 Solar (~78W avg).")
            if counts["battery"] < 2:
                needed = 2 - counts["battery"]
                recs.append(f"POWER ANCHOR: Buy {needed}x Small Battery (500 cr ea, currently {counts['battery']}/2) -> Needs 1,000 Wh night reserve.")
            if counts["bio"] < 3:
                recs.append("BIO-LOOP: Ensure bio_collector_1, bio_lab_1, bio_exchange_1 are connected to grid (18W continuous).")
            recs.append(f"PRESSURE RUSH PREP: Currently {counts['pressure']}/10 Pressure Gens. Once power is anchored, rush 10 Pressure Gens!")
        else:
            phase_title = "Phase 1: Pressure Rush to 0.20 kPa (Sec. 7.3 Step 2)"
            if counts["pressure"] < 10:
                needed = 10 - counts["pressure"]
                recs.append(f"PRESSURE RUSH: Buy {needed}x Pressure Generator (1,200 cr ea, currently {counts['pressure']}/10).")
                recs.append("  -> 10 Pressure Gens draw 70W; hits 0.20 kPa in ~1.5 - 2 planetary days!")
            else:
                recs.append("PRESSURE RUSH ACTIVE: All 10 Pressure Generators running at resonance sync! Rushing 0.200 kPa for Mining & Rover.")
            if counts["solar"] < 4:
                recs.append(f"Scale solar to 4 panels (currently {counts['solar']}/4) to support 88W total load (18W Bio + 70W Pressure).")
            recs.append("NEXT SWAP: When Pressure hits 0.20 kPa, recycle 9 Pressure Gens down to 1, and build 9x Oxygen Gens for Phase 2!")

    elif o2 < 9.0:
        phase_title = "Phase 2: Oxygen Rush to 9.0 ppt & Mining Setup (Sec. 7.3 Step 3)"
        if counts["o2gen"] < 11:
            needed = 11 - counts["o2gen"]
            recs.append(f"OXYGEN RUSH: Scale to 11x Oxygen Generator (currently {counts['o2gen']}/11, 8W ea = 88W load).")
            recs.append("  -> Rushes 9.0 ppt O2 in ~3-4 days (Auto Feeders @ 1.0, Earth Clearance @ 3.0, Smelter @ 5.0, Charging Station @ 9.0).")
        if o2 >= 5.0 and counts["smelter"] < 1:
            recs.append("DEPLOY SMELTER: Oxygen >= 5.0 ppt unlocked! Deploy Smelter 1 to refine iron ore & silicon.")
        if o2 < 9.0:
            recs.append(f"CHARGING STATION LOCKED: Vehicle Charging Station requires 9.0 ppt O2 (currently {o2:.2f}/9.0 ppt). Keep running 11 O2 gens!")
        else:
            recs.append("CHARGING STATION UNLOCKED: Deploy Vehicle Charging Station 1 + Rover 1 chassis and mount Nav/Sonar/Drill modules!")
        recs.append("NEXT SWAP: At 9.0 ppt O2 with Rover active, recycle 10 O2 gens down to 1, scale to 7 Solar + 4 Batteries for Phase 3 Heat Rush!")

    elif heat < 12.0:
        phase_title = "Phase 3: The Heat Rush to 12.0 Temp (Sec. 7.3 Step 4)"
        if counts["solar"] < 7 or counts["battery"] < 4:
            if counts["solar"] < 7:
                recs.append(f"SCALE POWER: Buy {7 - counts['solar']}x Solar Generator (currently {counts['solar']}/7) for 10-Heater continuous load.")
            if counts["battery"] < 4:
                recs.append(f"SCALE BATTERIES: Buy {4 - counts['battery']}x Small Battery (currently {counts['battery']}/4) for 2,000 Wh night reserve.")
        if counts["heater"] < 10:
            needed = 10 - counts["heater"]
            recs.append(f"HEAT RUSH: Deploy {needed}x Heat Generator (currently {counts['heater']}/10, auto-calibrated to 100% efficiency).")
            recs.append("  -> Sweet spot: 10 Heaters + 4 Fixed gives +18.5W surplus (leaves 30W margin for Rover charging with ZERO brownouts!).")
            recs.append(f"  -> Reaches 12.0 Temp in ~4.8 days ({heat:.1f}/12.0 HU).")
        recs.append("NEXT STEP: At 12.0 Temp, Tri-Pillar hits ~98,579 TP + Bio-Loop -> 100,000 TP Pioneer Breakout!")

    elif tp < 100000:
        phase_title = "Phase 4: 100k TP Breakout & Pioneer Transition (Sec. 7.3 Step 5)"
        recs.append("PIONEER THRESHOLD REACHED: Tri-Pillar complete (0.20 kPa + 5.0 ppt + 12.0 HU = ~98.6k TP).")
        recs.append("COMMISSION PIONEER: Fabricate Pioneer Chassis + Modular Small Cargo Racks + Nav + Battery + Constructor.")
        recs.append("Transition Nocturna Base into multi-outpost deep-field hub!")

    else:
        phase_title = "Phase 5+: Planetary Expansion & Outpost Network (100,000+ TP)"
        recs.append("PIONEER ERA ACTIVE: Deep mining, Geothermal Power at thermal vents, Water Pump & Hydrology, Drone fleet.")

    return phase_title, milestones, recs


def print_speedrun_dashboard(metrics: Dict[str, Any]) -> None:
    """Renders clean ASCII dashboard of live metrics, progression phase, and recommendations."""
    phase_title, milestones, recs = get_speedrun_advisory(metrics)

    print("\n" + "=" * 76)
    print(" CODE: TERRAFORM SPEEDRUN MONITOR & ADVISOR")
    print("=" * 76)
    print(f" [Time] Day {metrics['day']} ({metrics['time_of_day']}) | Solar Eff: {metrics['solar_eff']:.1f}% | Cash: {metrics['credits']:,} cr (Total: {metrics['total_credits']:,} cr)")
    print(f" [Power] Gen: {metrics['power_gen']} W | Con: {metrics['power_con']} W | Stored: {metrics['power_stored']} Wh")
    print("-" * 76)
    print(" TERRAFORMING METRICS:")
    print(f"   * Total TP    : {metrics['total_tp']:>9,d} TP  (+{metrics['tp_rate']:.1f} TP/h)")
    print(f"   * Oxygen      : {metrics['o2']:>9.3f} ppt (+{metrics['o2_rate']:.3f} ppt/h)")
    print(f"   * Pressure    : {metrics['pressure']:>9.3f} kPa (+{metrics['pressure_rate']:.3f} kPa/h)")
    print(f"   * Heat Units  : {metrics['heat_units']:>9.1f} HU  (+{metrics['heat_rate']:.1f} HU/h | Surface: {metrics['surface_temp']:.1f} C)")
    print(f"   * Biomass     : {metrics['biomass']:>9.1f} tons")
    print("-" * 76)
    print(f" CURRENT PHASE: {phase_title}")
    if milestones:
        print(" NEXT MILESTONES:")
        for m in milestones:
            print(f"   -> {m}")
    if recs:
        print(" ACTIONABLE RECOMMENDATIONS:")
        for r in recs:
            print(f"   [!] {r}")
    c = metrics["machine_counts"]
    print("-" * 76)
    print(f" BASE BUILDING SLOTS (Nocturna Base): {metrics['slots_used']}/{metrics['slots_max']} used ({metrics['slots_free']} slots free)")
    print(f"   * Power     : {c['solar']} Solar | {c['battery']} Battery")
    print(f"   * Atmosphere: {c['pressure']} Pressure | {c['o2gen']} O2 | {c['heater']} Heat")
    print(f"   * Biology   : {c['bio']} Bio-Loop | Smelter: {c['smelter']}")
    print(f" MOBILE / FIELD UNITS (0 slots): Harvester: {c['harvester']} | Scanner: {c['scanner']} | Rover: {c['rover']}")
    print("=" * 76 + "\n")


def run_daemon(workspace: str, dry_run: bool = False, interval: float = 5.0) -> None:
    """Continuous background loop displaying live dashboard and auto-deploying new machines."""
    print(f"\n[EarlyGame] Starting Speedrun Advisor daemon (refresh interval: {interval}s)...")
    print("[EarlyGame] Press Ctrl+C at any time to stop.")

    last_metrics_time = 0.0

    while True:
        try:
            now = time.time()
            if now - last_metrics_time >= interval:
                metrics = get_live_metrics(workspace)
                print_speedrun_dashboard(metrics)
                last_metrics_time = now

            # Check for newly placed machines to auto-deploy
            scan_and_deploy_machines(workspace, dry_run=dry_run)

            time.sleep(min(1.0, interval))
        except KeyboardInterrupt:
            print("\n[EarlyGame] Speedrun Advisor daemon stopped.")
            break
        except Exception as e:
            print(f"[EarlyGame] Warning in daemon loop: {e}")
            time.sleep(2.0)


# ==============================================================================
# MAIN ENTRYPOINT
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Early Game Speedrun Orchestrator & Advisor for Code: Terraform")
    parser.add_argument("--workspace", help="Path to <save_id>_scripts workspace directory")
    parser.add_argument("--onboarding", action="store_true", help="Run First Contact boot & calibration sequence")
    parser.add_argument("--contracts", action="store_true", help="Run the 3 intro Earth contract solvers")
    parser.add_argument("--scan", action="store_true", help="Scan and deploy scripts to unscripted/idle machines")
    parser.add_argument("--advisor", action="store_true", help="Print live speedrun dashboard and recommendations once")
    parser.add_argument("--all", action="store_true", help="Run onboarding, solve contracts, and deploy all machines")
    parser.add_argument("--daemon", action="store_true", help="Run continuous watcher loop to monitor metrics and auto-deploy new machines")
    parser.add_argument("--auto", action="store_true", help="Run --all and then continue running in --daemon mode")
    parser.add_argument("--interval", type=float, default=5.0, help="Dashboard refresh interval in seconds (default: 5.0)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate actions without writing files or launching DAP")
    args = parser.parse_args()

    workspace = args.workspace or find_latest_workspace()
    if not workspace:
        print("[EarlyGame] Error: No active save workspace found. Specify with --workspace <path>")
        sys.exit(1)

    print(f"[EarlyGame] Target workspace: {workspace}")

    do_onboarding = args.onboarding or args.all or args.auto
    do_contracts = args.contracts or args.all or args.auto
    do_scan = args.scan or args.all or args.auto
    do_advisor = args.advisor
    do_daemon = args.daemon or args.auto

    if do_onboarding:
        run_onboarding(workspace, dry_run=args.dry_run)

    if do_contracts:
        run_contracts(workspace, dry_run=args.dry_run)

    if do_scan:
        scan_and_deploy_machines(workspace, dry_run=args.dry_run)

    if do_advisor and not do_daemon:
        metrics = get_live_metrics(workspace)
        print_speedrun_dashboard(metrics)

    if do_daemon:
        run_daemon(workspace, dry_run=args.dry_run, interval=args.interval)


if __name__ == "__main__":
    main()


