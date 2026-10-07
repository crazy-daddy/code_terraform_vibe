# Drones tab of the Control Room FLEET card (vehicles_panel.py): fleet-wide drone cruise throttle and
# auto-upgrade switch, the roster list and a detail pane for the selected
# drone.
#
# Pure intent publishes, as before the list layout: recall to the nearest
# Drone Depot (lib/drone_claims.py; couple()/uncouple() need a Depot, so not
# the nearest drone_service), retire (lib/fleet_decommission.py: recall home,
# unload, undeploy; parts stay in Inventory), default cruise throttle
# (lib/drone_energy.py) and the fleet upgrade switch (lib/drone_upgrade.py,
# run by control_room_automation.py). No Sport Nav equivalent: that is a
# Pioneer-only mechanism.

from archive import archive
from drone_claims import is_drone_recalled, set_drone_recalled
from drone_energy import DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK
from drone_upgrade import fleet_upgrade_state, set_upgrade_enabled
from fleet_decommission import decommission_state, request_decommission, cancel_decommission
from fleet_card import roster, split, cell, level_cell, status_mark, draw_wrapped, COMPACT_H
import fleet_status

KIND_COLORS = {
    "drone_small": "text-muted",
    "drone_medium": "accent",
    "drone_large": "warning",
}
BUTTON_H = 22
RETIRE_BTN_W = 70


def drone_id_of(drone):
    # id-first, matching DroneController.self.name (lib/drone.py) exactly --
    # that's the key each drone's own script checks recall under.
    return str(getattr(drone, "id", getattr(drone, "name", "drone")))


def dot_status(drone, raw_status, recalled):
    if getattr(drone, "is_being_rescued", False):
        return "being_rescued"
    if recalled:
        return "paused"
    if raw_status in ["stalled_no_battery", "stalled_no_oil", "stalled_no_route", "scrambled"]:
        return "error"
    if raw_status in ["traveling", "holding_weather"]:
        return "running"
    if raw_status in ["charging", "refueling", "waiting_service", "waiting_oil", "waiting_bay"]:
        return "paused"
    return "idle"


def energy_level(drone):
    # Electric drones report battery_level, heli drones oil_level --
    # .battery/.oil_tank raise ReferenceError across the wrong engine type
    # (drone.md), so read the ref's own pre-branched fields.
    if str(getattr(drone, "engine", "")) == "heli":
        return getattr(drone, "oil_level", None) or 0.0
    return getattr(drone, "battery_level", None) or 0.0


def upgrading_ids(upgrade_state):
    drones = upgrade_state.get("drones") or {}
    ids = {k for k, e in drones.items() if isinstance(e, dict) and e.get("state") != "blocked"}
    return ids | {e.get("new_id") for e in drones.values() if isinstance(e, dict) and e.get("new_id")}


def draw_drones(panel, x, y, w, h):
    """Drone view in the content box (x, y, w, h)."""
    current_throttle = archive.get(DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK)
    slider_value = panel.slider("drone_default_cruise_throttle", x, y + 4, 160, current_throttle, f"cruise {current_throttle * 100:.0f}%")
    if slider_value != current_throttle:
        archive.set(DEFAULT_CRUISE_THROTTLE_KEY, slider_value)
    upgrade_state = fleet_upgrade_state()
    upgrade_enabled = bool(upgrade_state.get("enabled", True))
    upgrade_on = panel.switch("fleet_upgrade_enabled", x + 270, y, upgrade_enabled, "auto-upgrade")
    if upgrade_on != upgrade_enabled:
        set_upgrade_enabled(upgrade_on)
    status_x = x + 430
    panel.draw_text(status_x, y + 12, str(upgrade_state.get("status", "idle"))[:max(0, int((x + w - status_x) // 6))], 10, "text-secondary")
    upgrading = upgrading_ids(upgrade_state)

    fleet = get_component("fleet")
    drones = fleet.drones() if fleet and hasattr(fleet, "drones") else []
    telemetry = fleet_status.get_all()
    names = fleet_status.outpost_names()
    retiring = decommission_state()

    list_y = y + 36
    list_h = y + h - list_y
    if not drones:
        panel.label(x, list_y + 12, "No drones owned", "muted")
        return
    rows = []
    for drone in drones:
        did = drone_id_of(drone)
        raw_status = str(getattr(drone, "status", "unknown"))
        entry = telemetry.get(did) or {}
        status_text = f"{raw_status}-docked" if getattr(drone, "is_docked", False) else raw_status
        kind = str(getattr(drone, "kind", "drone_small")).replace("drone_", "")[:1].upper()
        role = entry.get("role") or ""
        home = entry.get("home")
        where = f"{role} @ {names.get(home, home)}" if home else str(role)
        mark = status_mark(dot_status(drone, raw_status, is_drone_recalled(did)))
        name = str(getattr(drone, "name", did))
        rows.append(f"{mark} {cell(name, 11)} {kind} {level_cell(energy_level(drone))} {cell(status_text, 15)} {where}")
    list_w, dx, dw = split(x, w)
    index = roster(panel, "drone_list", x, list_y, list_w, list_h, rows)
    if index is None:
        return
    drone = drones[index]
    draw_detail(panel, drone, telemetry.get(drone_id_of(drone)) or {}, names, retiring, upgrading, dx, list_y, dw, list_h)


def draw_detail(panel, drone, entry, names, retiring, upgrading, x, y, w, h):
    did = drone_id_of(drone)
    raw_status = str(getattr(drone, "status", "unknown"))
    recalled = is_drone_recalled(did)
    kind = str(getattr(drone, "kind", "drone_small"))
    retire_entry = retiring.get(did)
    retire_state = retire_entry.get("state") if isinstance(retire_entry, dict) else None
    compact = h < COMPACT_H
    controls_y = y + h - BUTTON_H

    panel.status_dot(x + 6, y + 8, 5, dot_status(drone, raw_status, recalled))
    panel.draw_text(x + 18, y + 8, str(getattr(drone, "name", did))[:16], 13, "text-bright")
    panel.pill(x + w - 80, y, kind.replace("drone_", "").upper(), KIND_COLORS.get(kind, "text-muted"))

    level = energy_level(drone)
    panel.progress_bar(x, y + 22, w - 48, 10, level, "error" if level < 0.2 else "success")
    panel.draw_text(x + w - 40, y + 27, f"{level * 100:.0f}%", 10, "text-value")

    rescue = getattr(drone, "rescue_status", "none")
    if rescue != "none":
        flag = (rescue, "warning")
    elif retire_state == "blocked":
        flag = ("retire blocked", "error")
    elif retire_state:
        flag = ("retiring", "warning")
    elif recalled:
        flag = ("recalled", "warning")
    elif did in upgrading:
        flag = ("upgrading", "accent")
    else:
        flag = None
    cy = y + 46
    status_text = f"{raw_status} - docked" if getattr(drone, "is_docked", False) else raw_status
    panel.draw_text(x, cy, status_text[:24], 10, "text-secondary")
    if flag:
        panel.pill(x + w - 8 - len(flag[0]) * 7, cy - 8, flag[0], flag[1])
    cy += 16
    if not compact and cy + 26 < controls_y:
        fleet_status.draw_assignment(panel, x, cy, entry, names, w)
        cy += 30
    intent = str(entry.get("intent") or "")
    lines = int((controls_y - 6 - cy) // 13)
    if intent and lines > 0:
        draw_wrapped(panel, x, cy, intent, w, min(lines, 4))

    switch_on = fleet_status.synced_switch(panel, "drone_recall", x, controls_y, recalled, "recall")
    if switch_on != recalled:
        set_drone_recalled(did, switch_on)
        if not switch_on and did in retiring:
            cancel_decommission(did)  # recall off = back to work
    # Hidden during a chassis swap: the upgrade owns the drone then.
    if did not in upgrading:
        pending = retire_state in ("requested", "ready")
        if panel.button("drone_retire", x + w - RETIRE_BTN_W, controls_y, RETIRE_BTN_W, BUTTON_H, "cancel" if pending else "retire"):
            if pending:
                cancel_decommission(did)
            else:
                request_decommission(did, "drone")
