from drone import DroneController

# Home: an outpost id (any free Drone Depot there, picked per trip) or a
# depot id/display name (hardwired to that one depot). None = auto: pinned in
# archive on first run as the outpost of the nearest depot at that time.
# Role is auto-detected from mounted modules; a hauler (Cargo Pods, no bio
# module) floats between jobs and only uses HOME_DEPOT as its recall target.
HOME_DEPOT = "${HOME_DEPOT:None}"

HOME_DEPOT = None if HOME_DEPOT in ("None", "") else HOME_DEPOT

controller = DroneController(self, home_depot=HOME_DEPOT)
controller.run()
