// Read a save file as JSON text, plain or gzip-compressed (sample saves are stored as
// .json.gz; devtools/savefile.py is the Python twin). Detects gzip by its magic bytes.
import { readFileSync } from "node:fs";
import { gunzipSync } from "node:zlib";

export function readSaveText(path) {
  const buf = readFileSync(path);
  return (buf[0] === 0x1f && buf[1] === 0x8b ? gunzipSync(buf) : buf).toString("utf8");
}
