// Scenario files for headless runs: which subsystem runs real, stands in, or is
// off, plus item flows and archive seeds. `run.mjs --scenario FILE`; the older
// flags (--only-scripts, --stock, --drain, --park) and --standin SUB=MODE[,k=v]
// merge over the file. Schema and examples: docs/headless/scenarios.md.

import { readFileSync } from "node:fs";
import { dirname, isAbsolute, join } from "node:path";
import { fileURLToPath } from "node:url";

export const SCHEMA = "headless-scenario-v1";
export const PROFILE_SCHEMA = "headless-profile-v1";
// The script-set profile loaded when neither the scenario file nor --script-set names one.
export const DEFAULT_PROFILE_PATH = join(dirname(fileURLToPath(import.meta.url)), "profiles", "code_terraform.json");
// Left-over sweep: record fields that name the writer (docs/headless/standins.md "Left-overs").
export const DEFAULT_SWEEP_FIELDS = Object.freeze(["by", "vehicle", "owner", "machine_id", "requester", "writer"]);

export function emptyScenario() {
  return { name: null, target: null, profile: undefined, default: "real", subsystems: {}, assign: {}, flows: [], archive: {}, ghosts: {}, keep: [], skipSystems: [], strict: false, sweep: {} };
}

// A script-set profile with nothing in it: no stubs, no budget refresh, no
// orchestrator marker, no request protocol (mover refused).
export function emptyProfile() {
  return { name: "none", orchestratorMarkers: [], stubs: {}, budget: null, requests: null, sweep: { fields: [...DEFAULT_SWEEP_FIELDS], skipKeys: [] } };
}

// Loads a script-set profile (docs/headless/standins.md "Profile"); `null` or
// "none" gives emptyProfile(). `_doc` members are comments and dropped.
export function loadProfile(path) {
  if (path === null || path === undefined || path === "none") return emptyProfile();
  const raw = JSON.parse(readFileSync(path, "utf8"));
  if (raw.$schema !== undefined && raw.$schema !== PROFILE_SCHEMA) throw new Error(`${path}: $schema is ${raw.$schema}, this run.mjs reads ${PROFILE_SCHEMA}`);
  // `_doc` is dropped at the top level and inside each section, never inside a stub value.
  const strip = (v, depth) => (depth > 0 && v && typeof v === "object" && !Array.isArray(v)) ? Object.fromEntries(Object.entries(v).filter(([k]) => k !== "_doc").map(([k, x]) => [k, strip(x, depth - 1)])) : v;
  const p = { ...strip(raw, 2), name: raw.name ?? path };
  delete p.$schema;
  return validateProfile(p, path);
}

const PROFILE_KEYS = ["name", "orchestratorMarkers", "stubs", "budget", "requests", "sweep"];

// Checks a profile and fills the omitted sections from emptyProfile().
export function validateProfile(raw, where = "profile") {
  const fail = msg => { throw new Error(`${where}: ${msg}`); };
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) fail("a profile is an object");
  for (const k of Object.keys(raw)) if (!PROFILE_KEYS.includes(k)) fail(`unknown field ${k}; valid: ${PROFILE_KEYS.join(", ")}`);
  const p = { ...emptyProfile(), ...raw };
  const strings = (v, what) => { if (!Array.isArray(v) || v.some(x => typeof x !== "string")) fail(`${what} must be a list of strings`); };
  strings(p.orchestratorMarkers, "orchestratorMarkers");
  for (const m of p.orchestratorMarkers) { try { new RegExp(m, "m"); } catch (e) { fail(`orchestratorMarkers ${JSON.stringify(m)}: ${e.message}`); } }
  if (!p.stubs || typeof p.stubs !== "object" || Array.isArray(p.stubs)) fail("stubs must be {group: {key: value}}");
  for (const [g, keys] of Object.entries(p.stubs)) if (!keys || typeof keys !== "object" || Array.isArray(keys)) fail(`stubs.${g} must be {key: value}`);
  if (p.budget !== null) {
    if (!p.budget || typeof p.budget !== "object" || typeof p.budget.key !== "string") fail("budget must be null or {key, floor, askStaleTicks, holdTicks}");
    for (const k of ["floor", "askStaleTicks", "holdTicks"]) if (!Number.isFinite(p.budget[k]) || p.budget[k] < 0) fail(`budget.${k} must be a number >= 0`);
  }
  if (p.requests !== null) {
    if (!p.requests || typeof p.requests !== "object" || typeof p.requests.key !== "string" || typeof p.requests.pickupsKey !== "string") fail("requests must be null or {key, pickupsKey, staleTicks, pickupStaleTicks}");
    for (const k of ["staleTicks", "pickupStaleTicks"]) if (!Number.isInteger(p.requests[k]) || p.requests[k] < 1) fail(`requests.${k} must be a positive integer`);
  }
  p.sweep = { ...emptyProfile().sweep, ...(p.sweep ?? {}) };
  for (const k of Object.keys(p.sweep)) if (!["fields", "skipKeys"].includes(k)) fail(`sweep: unknown field ${k}; valid: fields, skipKeys`);
  strings(p.sweep.fields, "sweep.fields");
  strings(p.sweep.skipKeys, "sweep.skipKeys");
  return p;
}

export function loadScenarioFile(path) {
  const raw = JSON.parse(readFileSync(path, "utf8"));
  if (raw.$schema !== undefined && raw.$schema !== SCHEMA) throw new Error(`${path}: $schema is ${raw.$schema}, this run.mjs reads ${SCHEMA}`);
  const sc = { ...emptyScenario(), ...raw, name: raw.name ?? path };
  delete sc.$schema;
  // `profile` is a path relative to the scenario file (or "none").
  if (typeof sc.profile === "string" && sc.profile !== "none" && !isAbsolute(sc.profile)) sc.profile = join(dirname(path), sc.profile);
  return sc;
}

// --standin SUB=MODE[,key=value,...]; numbers and booleans are parsed.
export function parseStandinFlag(spec) {
  const m = /^([\w-]+)=([\w-]+)((?:,[\w-]+=[^,]*)*)$/.exec(spec);
  if (!m) throw new Error(`--standin: expected SUB=MODE[,key=value,...], got ${spec}`);
  const entry = { mode: m[2] };
  for (const kv of m[3].split(",").filter(Boolean)) {
    const [k, v] = kv.split("=");
    entry[k] = v === "true" ? true : v === "false" ? false : v !== "" && !Number.isNaN(Number(v)) ? Number(v) : v;
  }
  return [m[1], entry];
}

// Old run.mjs flags become scenario entries; flags win over the file.
// `flags.scriptSet` (--script-set PATH|none) wins over the file's `profile`;
// the flag's path is relative to the working directory, the file's to the file.
export function mergeFlags(sc, flags = {}) {
  const out = structuredClone(sc);
  if (flags.scriptSet !== undefined) out.profile = flags.scriptSet;
  if (flags.onlyScripts) {
    out.default = "off";
    out.keep = [...new Set([...out.keep, ...flags.onlyScripts.split(",").filter(Boolean)])];
    out.name ??= "only-scripts";
  }
  for (const spec of flags.stock ?? []) {
    const [, item, n] = /^([^=]+)=(\d+)$/.exec(spec) ?? [];
    if (!item) throw new Error(`--stock: expected ITEM=N, got ${spec}`);
    out.flows.push({ item, keep: Number(n), at: "inventory" });
  }
  for (const spec of flags.drain ?? []) {
    const [, item, after] = /^([^:]+):(\d+)$/.exec(spec) ?? [];
    if (!item) throw new Error(`--drain: expected ITEM:TICKS, got ${spec}`);
    out.flows.push({ item, after: Number(after), at: "inventory" });
  }
  if (flags.park && !out.subsystems.terraforming) out.subsystems.terraforming = { mode: "park" };
  for (const spec of flags.standin ?? []) {
    const [sub, entry] = parseStandinFlag(spec);
    out.subsystems[sub] = { ...(out.subsystems[sub] ?? {}), ...entry };
  }
  return out;
}

// Checks names against the registry (standins.mjs GROUPS / MODES) and fills
// defaults. Resolves the script-set profile: `sc.profile` is a path, "none",
// an already loaded profile object, or undefined (DEFAULT_PROFILE_PATH).
// The scenario's `sweep` section (false, or {fields, skipKeys, extraKeys})
// merges over the profile's; `sc.sweep` ends up false or the merged object.
export function validateScenario(sc, registry) {
  const { GROUPS, MODES } = registry;
  const groups = Object.keys(GROUPS);
  const fail = msg => { throw new Error(`scenario ${sc.name ?? ""}: ${msg}`); };
  const modeNames = g => Object.keys(MODES[g] ?? {});
  sc.profile = sc.profile && typeof sc.profile === "object" ? validateProfile(sc.profile, `scenario ${sc.name ?? ""} profile`)
    : loadProfile(sc.profile === undefined ? DEFAULT_PROFILE_PATH : sc.profile);
  for (const g of Object.keys(sc.profile.stubs)) if (!groups.includes(g)) fail(`profile ${sc.profile.name}: stubs.${g} is not a subsystem; valid: ${groups.join(", ")}`);
  if (sc.sweep !== false) {
    if (!sc.sweep || typeof sc.sweep !== "object" || Array.isArray(sc.sweep)) fail("sweep must be false or {fields, skipKeys, extraKeys}");
    const merged = { fields: sc.sweep.fields ?? sc.profile.sweep.fields, skipKeys: [...sc.profile.sweep.skipKeys, ...(sc.sweep.skipKeys ?? [])], extraKeys: sc.sweep.extraKeys ?? [] };
    for (const k of ["fields", "skipKeys", "extraKeys"]) if (!Array.isArray(merged[k]) || merged[k].some(x => typeof x !== "string")) fail(`sweep.${k} must be a list of strings`);
    sc.sweep = merged;
  }
  if (!["real", "off"].includes(sc.default)) fail(`default must be "real" or "off", got ${JSON.stringify(sc.default)}`);
  for (const [g, entry] of Object.entries(sc.subsystems)) {
    if (!groups.includes(g)) fail(`unknown subsystem ${g}; valid: ${groups.join(", ")}`);
    if (!entry || typeof entry !== "object") fail(`subsystems.${g} must be an object with a mode`);
    const mode = entry.mode ?? sc.default;
    const def = MODES[g]?.[mode];
    if (!def) fail(`subsystem ${g} has no mode ${JSON.stringify(mode)}; valid: ${modeNames(g).join(", ")}`);
    if (def.planned) fail(`subsystem ${g} mode ${mode} is not implemented yet (${def.planned})`);
    if (def.needs === "requests" && !sc.profile.requests) fail(`subsystem ${g} mode ${mode} serves the script set's request protocol, and profile ${sc.profile.name} has no "requests" section (docs/headless/standins.md "Profile")`);
    for (const k of Object.keys(entry)) {
      if (k !== "mode" && !(k in (def.params ?? {}))) fail(`subsystem ${g} mode ${mode}: unknown parameter ${k}; valid: ${Object.keys(def.params ?? {}).join(", ") || "none"}`);
    }
    entry.mode = mode;
    for (const [k, v] of Object.entries(def.params ?? {})) entry[k] ??= v;
  }
  for (const [typeId, g] of Object.entries(sc.assign)) {
    if (!groups.includes(g)) fail(`assign.${typeId}: unknown subsystem ${g}; valid: ${groups.join(", ")}`);
  }
  for (const [g, n] of Object.entries(sc.ghosts)) {
    if (!groups.includes(g)) fail(`ghosts.${g}: unknown subsystem; valid: ${groups.join(", ")}`);
    if (!Number.isFinite(n) || n < 0) fail(`ghosts.${g} must be a number >= 0`);
  }
  for (const f of sc.flows) {
    if (!f.item) fail(`flows entry without item: ${JSON.stringify(f)}`);
    const kinds = ["keep", "rate_h", "after"].filter(k => f[k] !== undefined);
    if (kinds.length !== 1) fail(`flows entry ${f.item} needs exactly one of keep, rate_h, after`);
  }
  if (!Array.isArray(sc.keep)) fail("keep must be a list of slot ids");
  if (!Array.isArray(sc.skipSystems)) fail("skipSystems must be a list of system names");
  return sc;
}

// Effective mode of a group under the scenario.
export function modeOf(sc, group) {
  return sc.subsystems[group]?.mode ?? sc.default;
}
