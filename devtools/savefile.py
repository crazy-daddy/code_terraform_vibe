"""Read a save file, plain or gzip-compressed (sample saves are stored as .json.gz;
devtools/headless/savefile.mjs is the JS twin). Detects gzip by its magic bytes."""
import gzip
import json
from pathlib import Path

GZIP_MAGIC = b"\x1f\x8b"


def read_save_text(path) -> str:
    raw = Path(path).read_bytes()
    if raw[:2] == GZIP_MAGIC:
        raw = gzip.decompress(raw)
    return raw.decode("utf-8")


def load_save(path) -> dict:
    return json.loads(read_save_text(path))
