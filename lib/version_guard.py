# Shared Library for the Game Version Safety Gate
# Halts a controller at startup when the running game build no longer
# matches the last operator-confirmed "good" build, since a build change can
# carry breaking API changes that would otherwise make automation act on
# assumptions that no longer hold. Called once, right before each
# controller's run() loop starts (see docs/AI_CHEATSHEET.md) rather than
# duplicated into every root entry script -- new entry scripts get the gate
# for free since they just call controller.run(). Not re-checked every tick:
# a build change only takes effect on the next script (re)start, same as the
# game itself.
#
# Resumes as soon as the operator clicks "Confirm New Version" on panel_1
# (see panel_1.py), which records the new build as good and broadcasts on
# VERSION_CONFIRMED_CHANNEL so every waiting script wakes immediately
# instead of polling. Falls back to polling archive directly if the Signal
# Bus ("comms") is unavailable or not yet researched.

from archive import archive
from tree_console import TreeConsole

GOOD_VERSION_KEY = "system.good_version"
VERSION_CONFIRMED_CHANNEL = "system.version_confirmed"
POLL_FALLBACK_SECONDS = 5.0


def good_version():
    """Last operator-confirmed build hash, seeded from the current build on first run
    (a fresh save/script install should never immediately halt itself)."""
    if not archive.has(GOOD_VERSION_KEY):
        archive.set(GOOD_VERSION_KEY, get_game_version())
    return archive.get(GOOD_VERSION_KEY, get_game_version())


def version_mismatch():
    """True while the running build differs from the last confirmed-good build.
    Build hashes only support equality checks (docs/guide/builtins_and_commands.md),
    so this can't and doesn't try to tell "older" from "newer"."""
    return get_game_version() != good_version()


def confirm_new_version():
    """Operator-triggered (panel_1's "Confirm New Version" button): records the
    running build as good and wakes every script blocked in validate_game_version()."""
    current = get_game_version()
    archive.set(GOOD_VERSION_KEY, current)
    comms = get_component("comms")
    if comms:
        comms.broadcast(VERSION_CONFIRMED_CHANNEL, current)
    return current


def validate_game_version():
    """
    Call once at controller startup, immediately before entering its run()
    loop -- not on every tick. Blocks (without busy-looping) while the
    running game build no longer matches the last confirmed-good version.
    Resumes as soon as the operator confirms on panel_1, or returns
    immediately if there is no mismatch.
    """
    if not version_mismatch():
        return

    log = TreeConsole(module="version_guard")
    log.debug(f"validate_game_version: mismatch confirmed, current={get_game_version()!r} last_good={good_version()!r} match={get_game_version() == good_version()}")
    log.level("warn").print(
        f"Game version changed ({good_version()} -> {get_game_version()}); "
        f"halted until confirmed on panel_1's AUTOMATION card."
    )
    comms = get_component("comms")
    while version_mismatch():
        if comms:
            comms.wait_broadcast(VERSION_CONFIRMED_CHANNEL)
        else:
            sleep(POLL_FALLBACK_SECONDS)
    log.print(f"Version confirmed ({get_game_version()}); resuming.")
