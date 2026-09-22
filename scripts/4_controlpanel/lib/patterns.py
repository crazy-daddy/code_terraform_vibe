# Shared Library for Wildcard/Regex Component-ID Matching
# Small dependency-free helpers so callers (e.g. power load-shedding tiers)
# don't hand-roll wildcard matching against machine/component ids.

import re

REGEX_METACHARACTERS = ".^$+{}[]\\|()"


def escape_regex_literal(text):
    """
    Manual stand-in for re.escape(), which this sandbox's 're' module doesn't
    provide (only search/match/fullmatch/findall/sub/split are available).
    Leaves '*' and '?' unescaped so callers can still translate them into
    wildcard tokens afterward.
    """
    return "".join(f"\\{ch}" if ch in REGEX_METACHARACTERS else ch for ch in text)


def is_wildcard_pattern(pattern):
    """True if pattern contains glob-style wildcards ('*' or '?')."""
    return "*" in pattern or "?" in pattern


def wildcard_to_regex(pattern):
    """Compiles a glob-style pattern (e.g. 'smelter_*', 'o2gen_?') into an anchored regex string."""
    return "^" + escape_regex_literal(pattern).replace("*", ".*").replace("?", ".") + "$"


def match_wildcard(pattern, candidate):
    """True if candidate matches a glob-style pattern, or equals it exactly when pattern has no wildcards."""
    if not is_wildcard_pattern(pattern):
        return candidate == pattern
    return re.match(wildcard_to_regex(pattern), candidate) is not None


def filter_wildcard_matches(pattern, candidates):
    """Sorted subset of candidates matching a glob-style pattern."""
    regex_pat = wildcard_to_regex(pattern)
    return sorted(c for c in candidates if re.match(regex_pat, c))
