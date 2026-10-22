"""VehicleCargoMixin.unload_cargo(): each stack goes out through
storage_unload.send_stack(), busy retries, full stops, a raising send is swallowed."""

from types import SimpleNamespace
from unittest import mock

import harness
import vehicle_cargo
from tree_console import TreeConsole


class _Port:
    """Vehicle OutputSlot answering send() from a script of statuses ('raise' raises)."""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.connected = ""
        self.connects = 0
        self.sends = 0

    def connected_id(self):
        return self.connected

    def connect(self, target):
        self.connects += 1
        self.connected = target
        return SimpleNamespace(status="ok", message="")

    def send(self, item_id, count):
        self.sends += 1
        status = self.statuses.pop(0)
        if status == "raise":
            raise RuntimeError("port gone")
        return SimpleNamespace(status=status, moved=count if status == "ok" else 0, message="")


class _Host(vehicle_cargo.VehicleCargoMixin):
    name = "pioneer_7"
    home_outpost = "outpost_1"

    def __init__(self, statuses):
        self.log = TreeConsole()
        cargo = SimpleNamespace(count=lambda: 5, stacks=lambda: [SimpleNamespace(id="iron_ore", count=5)])
        self.vehicle = SimpleNamespace(cargo=cargo, output=_Port(statuses))

    def publish_telemetry(self, *_):
        pass


class UnloadTests(harness.StubTestCase):
    def unload(self, statuses, connected=""):
        host = _Host(statuses)
        host.vehicle.output.connected = connected
        with (
            mock.patch.object(vehicle_cargo, "top_up_bin", return_value=0),
            mock.patch.object(vehicle_cargo, "best_unload_target", return_value="warehouse_1"),
        ):
            return host.unload_cargo(), host.vehicle.output

    def test_busy_retries_then_sends(self):
        result, port = self.unload(["busy", "busy", "ok"])
        self.assertEqual((result, port.sends, port.connects, port.connected), (5, 3, 1, "warehouse_1"))

    def test_no_reconnect_when_already_on_target(self):
        result, port = self.unload(["ok"], connected="warehouse_1")
        self.assertEqual((result, port.connects), (5, 0))

    def test_full_target_reports_full(self):
        result, port = self.unload(["target_full"])
        self.assertEqual((result, port.sends), (-1, 1))

    def test_raising_send_is_swallowed(self):
        result, port = self.unload(["raise"])
        self.assertEqual((result, port.sends), (0, 1))

    def test_gives_up_after_ten_busy_answers(self):
        result, port = self.unload(["busy"] * 10)
        self.assertEqual((result, port.sends), (0, 10))
