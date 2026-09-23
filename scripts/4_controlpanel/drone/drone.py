from drone import DroneController

# Home: an outpost id (any free Drone Depot there, picked per trip) or a
# depot id/display name (hardwired to that one depot). None = auto: pinned in
# archive on first run as the outpost of the nearest depot at that time.
HOME_DEPOT = "${HOME_DEPOT:None}"
CRUISE_THROTTLE = "${CRUISE_THROTTLE:None}"

HOME_DEPOT = None if HOME_DEPOT in ("None", "") else HOME_DEPOT
CRUISE_THROTTLE = float(CRUISE_THROTTLE) if CRUISE_THROTTLE not in ("None", "") else None

controller = DroneController(self, home_depot=HOME_DEPOT, cruise_throttle=CRUISE_THROTTLE)
controller.run()
