# =============================================================================
#  PIONEER SCOUT  —  temporary standalone role for the 100k-150k TP window
#  Explore every "?" contact with the (basic) sonar. No mining, no
#  construction, no cargo hauling — those need lib/pioneer.py's full
#  PioneerController, which cannot run until the real 150k TP Control Room
#  migration stages lib/ (see tools/early_game.py's trigger_midgame_migration
#  docstring — staging it earlier would leave Solar/Smelter grid supervision,
#  now centralized in panel_1.py, with no Control Room process to drive it).
#
#  Without this, a Pioneer commissioned at the 100k TP breakout just sits idle
#  at base for however long it takes to reach 150k TP — wasted time when it
#  could already be mapping the surrounding mineral/POI field so the real
#  PioneerController has a head start once it takes over.
#
#  Loadout (mount_vehicle.py's TARGET_MODULES_PIONEER): nav + basic sonar_module
#  + 6x Battery Holder (max range). Deliberately NOT Wide Sonar or Constructor
#  Module — confirmed live those aren't unlocked yet at the 100k TP breakout
#  under this speedrun's Pressure/Heat Rush targets (Wide Sonar needs Pressure
#  6.0 kPa, Constructor Module needs Heat 10 HU — see docs/database/
#  research_catalog.md; the strategy only reaches 0.200 kPa / 12.0 HU). No
#  Cargo Rack either: a pure Scout has nothing to haul.
#
#  Adapted from tools/templates/early/rover.py's explore loop: same
#  nocturna.points_of_interest() / journal survey persistence model, same
#  drive-and-block pattern, but with mining/unloading stripped out since this
#  Pioneer has no Drill Module mounted.
# =============================================================================

CRUISE = 0.6               # throttle; lower = more meters per Wh
ARRIVE_M = 2                # "close enough" — brake happens after this
RESERVE_WH = 20             # keep this much after the estimated trip home
LEVEL_FLOOR = 0.2           # never let the battery go below this away from home
CHARGE_TO = 0.95            # leave home once charged to this
WH_PER_M_GUESS = 0.08       # movement cost before any is measured (heavier than a Rover)
SAFETY = 1.4                # multiplier on the estimated trip-home cost

TICK = 1                    # seconds between drive-loop checks
STUCK_TICKS = 20            # zero speed for this long mid-drive = stuck
RESCAN_IDLE_SECONDS = 120   # once fully explored, re-check this often for new POIs

nocturna = get_component("nocturna")
journal = get_component("journal")
network = get_component("outpost_network")
comms = get_component("comms")

print(f"[scout] Pioneer {self.id} starting temporary Scout role (100k-150k TP window)...")

home = network.home()
home_x = home.x
home_y = home.y

station_pos = None
for building in home.buildings("charging_station"):
    station_pos = building.position
    break
if station_pos is not None:
    home_x = station_pos[0]
    home_y = station_pos[1]
    print(f"[scout] home = charging station at {home_x}, {home_y}")
else:
    print("[scout] no charging station at home — parking at the outpost; battery will not refill")

if not self.sonar:
    print("[scout] no Sonar Module mounted yet — waiting for mount_vehicle.py to finish...")

skipped = []


def key_of(x, y):
    return str(x) + ":" + str(y)


def publish(state, detail):
    if comms is None:
        return
    status = {}
    status["state"] = state
    status["detail"] = detail
    status["battery"] = round(self.battery.level(), 2)
    comms.broadcast("pioneer_scout.status", status)


cost = {}
cost["wh_per_m"] = WH_PER_M_GUESS
cost["last_wh"] = self.battery.wh()
cost["last_pos"] = self.nav.get_position()


def learn_cost():
    pos = self.nav.get_position()
    last = cost["last_pos"]
    moved = self.nav.get_distance_to(last.x, last.y)
    spent = cost["last_wh"] - self.battery.wh()
    if moved > 1 and spent > 0:
        sample = spent / moved
        cost["wh_per_m"] = cost["wh_per_m"] * 0.8 + sample * 0.2
    cost["last_wh"] = self.battery.wh()
    cost["last_pos"] = pos


def wh_to_reach(x, y):
    return self.nav.get_distance_to(x, y) * cost["wh_per_m"] * SAFETY


def can_afford_to_be_here():
    if self.battery.level() < LEVEL_FLOOR:
        return False
    return self.battery.wh() > wh_to_reach(home_x, home_y) + RESERVE_WH


def nocturna_distance(x1, y1, x2, y2):
    dx = x1 - x2
    dy = y1 - y2
    return sqrt(dx * dx + dy * dy)


def can_afford_trip(x, y):
    there = wh_to_reach(x, y)
    back = nocturna_distance(x, y, home_x, home_y) * cost["wh_per_m"] * SAFETY
    return self.battery.wh() > there + back + RESERVE_WH


def at_home():
    return self.nav.get_distance_to(home_x, home_y) <= ARRIVE_M


def drive_to(x, y, heading_home):
    self.nav.set_target(x, y)
    self.nav.set_throttle(CRUISE)
    still = 0
    while self.nav.get_distance_to(x, y) > ARRIVE_M:
        sleep(TICK)
        learn_cost()

        if self.is_being_rescued():
            self.nav.brake()
            return "rescued"
        if not heading_home and not can_afford_to_be_here():
            self.nav.brake()
            return "low_battery"

        if self.nav.get_speed() == 0:
            still = still + 1
            if still >= STUCK_TICKS:
                self.nav.brake()
                return "stuck"
        else:
            still = 0

    self.nav.brake()
    return "ok"


def go_home():
    publish("returning", "")
    result = drive_to(home_x, home_y, True)
    if result != "ok":
        print(f"[scout] return home: {result}")
    return result


def next_contact():
    best = None
    best_d = 0
    for p in nocturna.points_of_interest():
        if p.scanned:
            continue
        if key_of(p.x, p.y) in skipped:
            continue
        d = self.nav.get_distance_to(p.x, p.y)
        if best is None or d < best_d:
            best = p
            best_d = d
    return best


def explore(p):
    publish("exploring", key_of(p.x, p.y))
    result = drive_to(p.x, p.y, False)
    if result != "ok":
        return result

    sweep = self.sonar.scan()
    if sweep.status != "ok":
        print(f"[scout] scan: {sweep.message}")
        skipped.append(key_of(p.x, p.y))
        return "scan_failed"

    resolved = 0
    for site in sweep.sites:
        if site.surveyed:
            resolved = resolved + 1
            continue
        survey = self.sonar.survey(site)
        if survey.status == "ok":
            resolved = resolved + 1
            found = survey.site
            if found.kind() == "mineral":
                print(f"[scout] surveyed {found.name} - {found.item_id} hardness {found.hardness} purity {found.purity}")
            else:
                print(f"[scout] surveyed {found.name} - {found.kind()}")
        else:
            print(f"[scout] survey {site.name} - {survey.message}")

    still_open = False
    for q in nocturna.points_of_interest():
        if q.x == p.x and q.y == p.y and not q.scanned:
            still_open = True
    if still_open:
        skipped.append(key_of(p.x, p.y))
        print(f"[scout] contact at {p.x}, {p.y} needs a different scanner — skipping")

    return "ok"


idle_note = ""

while True:
    learn_cost()

    if not self.sonar or not self.nav:
        sleep(5)
        continue

    if self.is_being_rescued():
        publish("rescued", self.rescue_status())
        sleep(5)
        continue

    if at_home() and self.battery.level() < CHARGE_TO:
        publish("charging", str(round(self.battery.level(), 2)))
        sleep(5 if station_pos is not None else 60)
        continue

    if not at_home() and not can_afford_to_be_here():
        go_home()
        continue

    contact = next_contact()
    if contact is not None and can_afford_trip(contact.x, contact.y):
        idle_note = ""
        result = explore(contact)
        if result in ("low_battery", "stuck"):
            go_home()
        continue

    if not at_home():
        go_home()
        continue

    if idle_note != "idle":
        if contact is not None:
            print("[scout] contacts remain but none are within battery range — idle at home")
        else:
            print("[scout] every reachable contact scanned — idle at home, watching for new POIs and the 150k TP migration")
        idle_note = "idle"
    publish("idle", "")
    sleep(RESCAN_IDLE_SECONDS)
