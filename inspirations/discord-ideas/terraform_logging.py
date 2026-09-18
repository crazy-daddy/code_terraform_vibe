# terraform_logging.py VERSION: 1.0.2
"""
Shared Code: Terraform logging service.

Central controls live here so controller scripts do not each carry their own
formatting, timestamp, throttling, and severity logic.

Levels:
    ERROR = 0
    WARN  = 1
    INFO  = 2
    DEBUG = 3
    TRACE = 4

Set DEFAULT_LEVEL below to change the base logging level for every importing
module.  CATEGORY_LEVELS can selectively raise/lower one subsystem.

Console timestamps use the developer-recommended console.now() prefix format.
Python time is used only for elapsed/rate-limit calculations when available.
"""

try:
    import time as _time
except Exception:
    _time = None

SCRIPT_VERSION = "1.0.2"

ERROR = 0
WARN = 1
INFO = 2
DEBUG = 3
TRACE = 4

# -----------------------------------------------------------------------------
# BASE-LEVEL CONFIGURATION
# -----------------------------------------------------------------------------
# Change this one value to alter the normal logging level system-wide.
DEFAULT_LEVEL = INFO

# Optional subsystem overrides.  Longest matching prefix wins, so a future
# "fleet.resource_transfer" override can be more specific than "fleet".
CATEGORY_LEVELS = {
    "fleet": DEBUG,
    "fleet.resource_transfer": DEBUG,
    "fleet.resources": DEBUG,
}

TIMESTAMPS = True
SHOW_LEVEL = True
HEARTBEAT_SECONDS = 60.0
RATE_LIMIT_SECONDS = 30.0

_last_emit = {}
_last_state = {}
_start_time = None

try:
    if _time is not None:
        _start_time = _time.time()
except Exception:
    _start_time = None


def _now_seconds():
    try:
        if _time is not None:
            return float(_time.time())
    except Exception:
        pass
    return None


def _timestamp():
    # Timestamp rendering is delegated to the game console.
    return ""


def _console_emit(message, level):
    """Emit through the game console using the developer-recommended timestamp format.

    Timestamp rendering uses console.now() and prefixes the message explicitly:
        console.print(console.now() + " " + str(message), level=level_name)

    Falls back to built-in print if the console component is unavailable in a
    particular script/runtime context.
    """
    level_name = _level_name(level).lower()

    try:
        console = get_component("console")
        output = str(message)
        if TIMESTAMPS:
            output = console.now() + " " + output
        console.print(output, level=level_name)
        return True
    except Exception:
        print(str(message))
        return False

def _level_name(level):
    value = int(level)
    if value <= ERROR:
        return "ERROR"
    if value == WARN:
        return "WARN"
    if value == INFO:
        return "INFO"
    if value == DEBUG:
        return "DEBUG"
    return "TRACE"


def _effective_level(category):
    category = str(category)
    best_level = DEFAULT_LEVEL
    best_length = -1

    for prefix in CATEGORY_LEVELS:
        prefix_text = str(prefix)
        if (
            category == prefix_text
            or category.startswith(prefix_text + ".")
        ):
            if len(prefix_text) > best_length:
                best_level = int(CATEGORY_LEVELS[prefix])
                best_length = len(prefix_text)

    return best_level


def enabled(level, category="system"):
    return int(level) <= _effective_level(category)


def _format(level, category, message, actor=""):
    parts = []

    if SHOW_LEVEL:
        parts.append("[" + _level_name(level) + "]")

    if str(actor) != "":
        parts.append("[" + str(actor) + "]")

    if str(category) != "":
        parts.append("[" + str(category) + "]")

    parts.append(str(message))
    return " ".join(parts)


def log(level, category, message, actor=""):
    if not enabled(level, category):
        return False

    _console_emit(_format(level, category, message, actor), level)
    return True


def error(category, message, actor=""):
    return log(ERROR, category, message, actor)


def warn(category, message, actor=""):
    return log(WARN, category, message, actor)


def info(category, message, actor=""):
    return log(INFO, category, message, actor)


def debug(category, message, actor=""):
    return log(DEBUG, category, message, actor)


def trace(category, message, actor=""):
    return log(TRACE, category, message, actor)


def exception(category, error_value, actor="", message="Exception"):
    return error(
        category,
        str(message) + ": " + str(error_value),
        actor
    )


def log_once(key, level, category, message, actor=""):
    key = "once:" + str(key)
    if key in _last_emit:
        return False

    _last_emit[key] = _now_seconds()
    return log(level, category, message, actor)


def rate_limited(
    key,
    level,
    category,
    message,
    actor="",
    seconds=None
):
    if not enabled(level, category):
        return False

    if seconds is None:
        seconds = RATE_LIMIT_SECONDS

    now = _now_seconds()
    cache_key = "rate:" + str(key)

    if now is not None:
        previous = _last_emit.get(cache_key)
        if previous is not None and now - float(previous) < float(seconds):
            return False
        _last_emit[cache_key] = now
    else:
        # Without a runtime clock, avoid suppressing potentially useful output.
        _last_emit[cache_key] = None

    return log(level, category, message, actor)


def heartbeat(key, category, message, actor="", seconds=None):
    if seconds is None:
        seconds = HEARTBEAT_SECONDS

    return rate_limited(
        "heartbeat:" + str(key),
        DEBUG,
        category,
        message,
        actor,
        seconds
    )


def state_change(key, category, state, actor="", level=INFO, detail=""):
    cache_key = str(key)
    state_text = str(state)
    previous = _last_state.get(cache_key)

    if previous == state_text:
        return False

    _last_state[cache_key] = state_text

    message = "state=" + state_text
    if previous is not None:
        message = "state=" + str(previous) + " -> " + state_text

    if str(detail) != "":
        message += " " + str(detail)

    return log(level, category, message, actor)


def elapsed_since_start():
    now = _now_seconds()
    if now is None or _start_time is None:
        return None
    return max(0.0, now - _start_time)


info(
    "logging",
    "Shared logger online. VERSION " + SCRIPT_VERSION
    + " base_level=" + _level_name(DEFAULT_LEVEL)
)
