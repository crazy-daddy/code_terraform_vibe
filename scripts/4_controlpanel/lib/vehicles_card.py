# Ground vehicle view of the Control Room FLEET card (vehicles_panel.py):
# fleet-wide cruise throttle and drone-yield controls, headline counts per
# activity, the roster list and a detail pane for the selected vehicle.
#
# Every control is a pure intent publish (archive writes), same as before the
# list layout: recall (lib/vehicle_claims.py), retire (lib/fleet_decommission.py,
# Pioneers and Rovers), the one-shot Sport Nav request (lib/pioneer_upgrade.py,
# Pioneers only; the Pioneer mounts it next time it is idle at base), the
# fleet-wide default cruise throttle (lib/vehicle_energy.py) and drone yield
# (lib/logistics_requests.py). Each vehicle's own script acts on them.

from archive import archive
from vehicle_claims import is_vehicle_recalled, set_vehicle_recalled
from vehicle_energy import DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK, nav_speed_multiplier_for
from pioneer_upgrade import is_sport_nav_requested, request_sport_nav, sport_nav_unlocked
from logistics_requests import drone_yield_enabled, set_drone_yield_enabled
from fleet_decommission import decommission_state, request_decommission, cancel_decommission
from fleet_card import roster, split, cell, level_cell, status_mark, draw_wrapped, counters, COMPACT_H
import fleet_status

BUTTON_H = 22
RETIRE_BTN_W = 70
SPORT_BTN_W = 96

# Headline buckets: charging first, then idle, then the published job role.
# Rovers without a published role count as miners.
ROLE_BUCKETS = {"miner": "MINE", "hauler": "HAUL", "constructor": "BUILD", "scout": "SCOUT", "rover": "MINE"}
BUCKETS = ("IDLE", "CHARGE", "MINE", "HAUL", "BUILD", "SCOUT")


def vehicle_role(vehicle):
    """Role pill from VehicleRef.kind ("rover"/"pioneer"), so renamed vehicles keep theirs."""
    kind = str(getattr(vehicle, "kind", "") or "").lower()
    if kind == "rover":
        return "ROVER", "accent"
    if kind == "pioneer":
        return "PIONEER", "warning"
    return "VEHICLE", "text-muted"


def dot_status(vehicle, raw_status, recalled):
    if getattr(vehicle, "is_being_rescued", False):
        return "being_rescued"
    if recalled:
        return "paused"
    if raw_status in ["stranded", "stalled_no_battery"]:
        return "error"
    if raw_status in ["moving", "scanning", "surveying", "drilling"]:
        return "running"
    if raw_status in ["charging", "queued"]:
        return "paused"
    return "idle"


def bucket(vehicle, raw_status, entry):
    if raw_status in ["charging", "queued"]:
        return "CHARGE"
    if raw_status == "idle":
        return "IDLE"
    role = str(entry.get("role") or getattr(vehicle, "kind", "") or "").lower()
    return ROLE_BUCKETS.get(role, "IDLE")


def badge(vehicle, retire_state, recalled, sport_pending):
    """(text, colour) of the one status flag a vehicle shows, or None. Same precedence as the old row pill."""
    rescue = getattr(vehicle, "rescue_status", "none")
    if rescue != "none":
        return rescue, "warning"
    if retire_state == "blocked":
        return "retire blocked", "error"
    if retire_state:
        return "retiring", "warning"
    if recalled:
        return "recalled", "warning"
    if sport_pending:
        return "sport nav pending", "warning"
    return None


def vehicle_id_of(vehicle):
    # id-first, matching VehicleController.self.name (lib/vehicle.py) exactly --
    # that's the key the vehicle's own script checks recall under.
    return str(getattr(vehicle, "id", getattr(vehicle, "name", "vehicle")))


def has_sport_nav(vehicle_id):
    """True when the live vehicle already mounts a Sport Nav (fleet refs carry no module data)."""
    live = get_component(vehicle_id)
    return live is not None and nav_speed_multiplier_for(live) > 1.0


def draw_ground(panel, x, y, w, h):
    """Ground view in the content box (x, y, w, h)."""
    right = x + w

    # Top row: cruise throttle (label carries the value: slider() draws its
    # own label where this script can't place a second text), drone yield
    # switch, headline counts.
    current_throttle = archive.get(DEFAULT_CRUISE_THROTTLE_KEY, DEFAULT_CRUISE_THROTTLE_FALLBACK)
    slider_value = panel.slider("default_cruise_throttle", x, y + 4, 160, current_throttle, f"cruise {current_throttle * 100:.0f}%")
    if slider_value != current_throttle:
        archive.set(DEFAULT_CRUISE_THROTTLE_KEY, slider_value)
    drone_yield = drone_yield_enabled()
    yield_on = panel.switch("drone_yield", x + 270, y, drone_yield, "leave to drones")
    if yield_on != drone_yield:
        set_drone_yield_enabled(yield_on)

    fleet = get_component("fleet")
    vehicles = fleet.vehicles() if fleet and hasattr(fleet, "vehicles") else []
    telemetry = fleet_status.get_all()
    names = fleet_status.outpost_names()
    retiring = decommission_state()

    counts = {b: 0 for b in BUCKETS}
    rows = []
    for vehicle in vehicles:
        vid = vehicle_id_of(vehicle)
        raw_status = str(getattr(vehicle, "status", "unknown"))
        entry = telemetry.get(vid) or {}
        recalled = is_vehicle_recalled(vid)
        counts[bucket(vehicle, raw_status, entry)] += 1
        status_text = f"{raw_status}-docked" if getattr(vehicle, "is_docked", False) else raw_status
        role = entry.get("role") or ""
        home = entry.get("home")
        where = f"{role} @ {names.get(home, home)}" if home else str(role)
        name = str(getattr(vehicle, "name", vid))
        level = getattr(vehicle, "battery_level", 0.0) or 0.0
        rows.append(f"{status_mark(dot_status(vehicle, raw_status, recalled))} {cell(name, 11)} {level_cell(level)} {cell(status_text, 13)} {where}")
    if right - (x + 470) >= 6 * 70:
        counters(panel, x + 470, y + 12, [(b, counts[b]) for b in BUCKETS], (right - (x + 470)) // 6)

    list_y = y + 36
    list_h = y + h - list_y
    if not vehicles:
        panel.label(x, list_y + 12, "No ground vehicles owned", "muted")
        return
    list_w, dx, dw = split(x, w)
    index = roster(panel, "ground_list", x, list_y, list_w, list_h, rows)
    if index is None:
        return
    draw_detail(panel, vehicles[index], telemetry.get(vehicle_id_of(vehicles[index])) or {}, names, retiring, dx, list_y, dw, list_h)


def draw_detail(panel, vehicle, entry, names, retiring, x, y, w, h):
    vid = vehicle_id_of(vehicle)
    name = str(getattr(vehicle, "name", vid))
    role_label, role_color = vehicle_role(vehicle)
    raw_status = str(getattr(vehicle, "status", "unknown"))
    recalled = is_vehicle_recalled(vid)
    pioneer = role_label == "PIONEER"
    sport_pending = pioneer and is_sport_nav_requested(vid)
    retire_entry = retiring.get(vid)
    retire_state = retire_entry.get("state") if isinstance(retire_entry, dict) else None
    compact = h < COMPACT_H
    controls_y = y + h - BUTTON_H

    panel.status_dot(x + 6, y + 8, 5, dot_status(vehicle, raw_status, recalled))
    panel.draw_text(x + 18, y + 8, name[:16], 13, "text-bright")
    panel.pill(x + w - 80, y, role_label, role_color)

    level = getattr(vehicle, "battery_level", 0.0) or 0.0
    panel.progress_bar(x, y + 22, w - 48, 10, level, "error" if level < 0.2 else "success")
    panel.draw_text(x + w - 40, y + 27, f"{level * 100:.0f}%", 10, "text-value")

    status_text = f"{raw_status} - docked" if getattr(vehicle, "is_docked", False) else raw_status
    cy = y + 46
    flag = badge(vehicle, retire_state, recalled, sport_pending)
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

    # Controls on the selected vehicle. Fixed keys: synced_switch() re-seeds
    # the recall switch from the archive when the selection changes.
    switch_on = fleet_status.synced_switch(panel, "ground_recall", x, controls_y, recalled, "recall")
    if switch_on != recalled:
        set_vehicle_recalled(vid, switch_on)
        if not switch_on and vid in retiring:
            cancel_decommission(vid)  # recall off = back to work
    bx = x + w - RETIRE_BTN_W
    if role_label in ("PIONEER", "ROVER"):
        pending = retire_state in ("requested", "ready")
        if panel.button("ground_retire", bx, controls_y, RETIRE_BTN_W, BUTTON_H, "cancel" if pending else "retire"):
            if pending:
                cancel_decommission(vid)
            else:
                request_decommission(vid, role_label.lower())
    # Hidden until researched, and once a Sport Nav is mounted: a second one
    # rarely pays for its slot.
    if pioneer and sport_nav_unlocked() and not has_sport_nav(vid):
        label = "requested" if sport_pending else "+ Sport Nav"
        if panel.button("ground_sport_nav", bx - SPORT_BTN_W - 8, controls_y, SPORT_BTN_W, BUTTON_H, label) and not sport_pending:
            request_sport_nav(vid)
