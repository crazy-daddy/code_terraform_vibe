from archive import archive
from storage import best_unload_target
from version_guard import validate_game_version
from tree_console import TreeConsole, flush_all, reset_all
from swallow import swallowed

# Waste Processor base controller. The processor only destroys while the
# script that armed it keeps running (docs/components/waste_processor.md).
# Its only duty is water overflow (lib/water_sink.py
# WaterAwareWasteSinkController, "liquid" mode). No item is destroyed:
# life forms stay in storage for creature feed (Wildlife), and a full Drone
# Depot sheds its own surplus (lib/drone_depot.py flush_surplus()).
#
# Idle (no drain running): the processor is switched off, so it draws no
# power and can't destroy anything, and items staged in its input are
# ejected back to local storage.

STATUS_KEY = "waste_sink.status"   # {processor_id: telemetry}


class WasteSinkController:
    """Keeps a Waste Processor idle: disabled, input returned to local storage."""

    def __init__(self, processor):
        self.processor = processor
        self.name = getattr(processor, "id", "waste_processor")
        self.log = TreeConsole(module="waste_sink")

    def _outpost(self):
        return getattr(self.processor, "outpost", None)

    def idle(self):
        """Disable the processor, then eject whatever sits in its input bin."""
        try:
            if self.processor.is_enabled():
                self.processor.set_enabled(False)
                self.log.print(f"[{self.name}] Idle: destruction off.")
        except Exception as e:
            self.log.level("error").print(f"[{self.name}] disable failed: {e}")
            return
        self.return_input()

    def return_input(self):
        """Eject every staged stack to a local Warehouse. Returns units moved."""
        port = self.processor.input
        try:
            stacks = list(port.stacks()) if port.count() > 0 else []
        except Exception as error:
            swallowed("waste_sink.WasteSinkController.return_input: port.stacks", error)
            return 0
        if not stacks:
            return 0
        moved = 0
        self.log.start(f"[{self.name}] Returning {len(stacks)} staged stack(s) to storage")
        for stack in stacks:
            destination = best_unload_target(stack.id, stack.count, outpost=self._outpost())
            if destination is None:
                self.log.debug(f"no local room for {stack.count}x '{stack.id}'; left in the input.")
                continue
            try:
                res = port.eject(destination, stack.id, stack.count)
            except Exception as e:
                self.log.level("warn").print(f"[{self.name}] eject {stack.count}x '{stack.id}' -> '{destination}' failed: {e}")
                continue
            moved += getattr(res, "moved", 0) or 0
        self.log.end(f"returned {moved} unit(s)")
        return moved

    def publish_telemetry(self):
        try:
            status = self.processor.status()
            staged = self.processor.input.count()
        except Exception as error:
            swallowed("waste_sink.WasteSinkController.publish_telemetry: self.processor.status", error)
            status, staged = "unknown", 0
        archive.set_entry(STATUS_KEY, self.name, {
            "status": status,
            "staged": staged,
        })

    def step(self):
        self.idle()
        self.publish_telemetry()

    def run(self, poll_interval=10.0):
        self.log.print(f"Waste Sink Controller ({self.name}) online at '{getattr(self._outpost(), 'id', '?')}'.")
        validate_game_version()
        while True:
            reset_all()
            try:
                self.step()
            except Exception as error:
                self.log.level("error").print(f"[{self.name}] Waste sink exception: {error}")
            flush_all()
            sleep(poll_interval)
