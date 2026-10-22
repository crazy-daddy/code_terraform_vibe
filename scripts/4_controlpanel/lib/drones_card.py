# Drones tab of the Control Room FLEET card (vehicles_panel.py): fleet-wide drone cruise throttle and
# auto-upgrade switch, the roster list and a detail pane for the selected
# drone.
#
# Pure intent publishes, as before the list layout: recall to the nearest
# Drone Depot (lib/drone_claims.py; couple()/uncouple() need a Depot, so not
# the nearest drone_service), retire (lib/fleet_decommission.py: recall home,
# unload, undeploy; parts stay in Inventory), default cruise throttle
# (lib/drone_energy.py) and the fleet upgrade switch (lib/drone_upgrade.py,
# run by builder_automation.py). Once Heli-Drones is researched: the
# "heli on unlock" switch (new chassis go heli) and a per-drone "-> heli"
# button (in-place conversion, the drone's own script swaps the modules at
# its next Depot unload; drone_upgrade.convert_to_heli_if_requested()).

import fleet_status
from archive import archive
from drone_claims import is_drone_recalled, set_drone_recalled
from drone_depots import heli_unlocked
from drone_energy import DEFAULT_CRUISE_THROTTLE_FALLBACK, DEFAULT_CRUISE_THROTTLE_KEY
from drone_navigation import NO_ROUTE_STATUS, STRANDED_STATUSES
from drone_upgrade import clear_heli_request, fleet_upgrade_state, heli_requested, request_heli, set_heli_on_unlock, set_upgrade_enabled
from fleet_card import BUTTON_H, RETIRE_BTN_W, cell, draw_detail_body, level_cell, roster, split, status_mark
from fleet_decommission import cancel_decommission, decommission_state, request_decommission

KIND_COLORS = {
    "drone_small": "text-muted",
    "drone_medium": "accent",
    "drone_large": "warning",
}
HELI_BTN_W = 80


def drone_id_of(drone):
    # id-first, matching DroneController.self.name (lib/drone.py) exactly --
    # that's the key each drone's own script checks recall under.
    return str(getattr(drone, "id", getattr(drone, "name", "drone")))


def dot_status(drone, raw_status, recalled):
    if getattr(drone, "is_being_rescued", False):
        return "being_rescued"
    if recalled:
        return "paused"
    if raw_status in STRANDED_STATUSES or raw_status == NO_ROUTE_STATUS:
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
    if heli_unlocked():
        heli_enabled = bool(upgrade_state.get("heli_on_unlock", False))
        heli_on = panel.switch("fleet_heli_on_unlock", status_x, y, heli_enabled, "heli on unlock")
        if heli_on != heli_enabled:
            set_heli_on_unlock(heli_on)
        status_x += 170
    panel.draw_text(status_x, y + 12, str(upgrade_state.get("status", "idle"))[: max(0, int((x + w - status_x) // 6))], 10, "text-secondary")
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

    flag = badge(drone, retire_state, recalled, did in upgrading)
    head = (dot_status(drone, raw_status, recalled), str(getattr(drone, "name", did)), kind.replace("drone_", "").upper(), KIND_COLORS.get(kind, "text-muted"))
    controls_y = draw_detail_body(panel, drone, entry, names, head, energy_level(drone), flag, x, y, w, h)

    switch_on = fleet_status.synced_switch(panel, "drone_recall", x, controls_y, recalled, "recall")
    if switch_on != recalled:
        set_drone_recalled(did, switch_on)
        if not switch_on and did in retiring:
            cancel_decommission(did)  # recall off = back to work
    # Hidden during a chassis swap: the upgrade owns the drone then.
    if did not in upgrading:
        draw_retire_buttons(panel, drone, did, retire_state, x + w, controls_y)


def badge(drone, retire_state, recalled, upgrading):
    """(text, colour) of the one status flag a drone shows, or None."""
    rescue = getattr(drone, "rescue_status", "none")
    if rescue != "none":
        return rescue, "warning"
    if retire_state == "blocked":
        return "retire blocked", "error"
    if retire_state:
        return "retiring", "warning"
    if recalled:
        return "recalled", "warning"
    if upgrading:
        return "upgrading", "accent"
    return None


def draw_retire_buttons(panel, drone, did, retire_state, right, y):
    """Retire/cancel button right-aligned at `right`, plus "-> heli" left of it for an electric drone once Heli-Drones is researched."""
    pending = retire_state in ("requested", "ready")
    if panel.button("drone_retire", right - RETIRE_BTN_W, y, RETIRE_BTN_W, BUTTON_H, "cancel" if pending else "retire"):
        if pending:
            cancel_decommission(did)
        else:
            request_decommission(did, "drone")
    if str(getattr(drone, "engine", "")) == "electric" and not retire_state and heli_unlocked():
        requested = heli_requested(did)
        if panel.button("drone_heli", right - RETIRE_BTN_W - HELI_BTN_W - 8, y, HELI_BTN_W, BUTTON_H, "cancel heli" if requested else "-> heli"):
            if requested:
                clear_heli_request(did)
            else:
                request_heli(did)
