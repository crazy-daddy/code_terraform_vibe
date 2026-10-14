// Scenario files for headless runs: which subsystem runs real, stands in, or is
// off, plus item flows and archive seeds. `run.mjs --scenario FILE`; the older
// flags (--only-scripts, --stock, --drain, --park) and --standin SUB=MODE[,k=v]
// merge over the file. Schema and examples: docs/headless/scenarios.md.

import { readFileSync } from "node:fs";

export const SCHEMA = "headless-scenario-v1";

export function emptyScenario() {
  return { name: null, target: null, default: "real", subsystems: {}, assign: {}, flows: [], archive: {}, ghosts: {}, keep: [], skipSystems: [], strict: false };
}

export function loadScenarioFile(path) {
  const raw = JSON.parse(readFileSync(path, "utf8"));
  if (raw.$schema !== undefined && raw.$schema !== SCHEMA) throw new Error(`${path}: $schema is ${raw.$schema}, this run.mjs reads ${SCHEMA}`);
  const sc = { ...emptyScenario(), ...raw, name: raw.name ?? path };
  delete sc.$schema;
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
export function mergeFlags(sc, flags = {}) {
  const out = structuredClone(sc);
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

// Checks names against the registry (standins.mjs GROUPS / MODES) and fills defaults.
export function validateScenario(sc, registry) {
  const { GROUPS, MODES } = registry;
  const groups = Object.keys(GROUPS);
  const fail = msg => { throw new Error(`scenario ${sc.name ?? ""}: ${msg}`); };
  const modeNames = g => Object.keys(MODES[g] ?? {});
  if (!["real", "off"].includes(sc.default)) fail(`default must be "real" or "off", got ${JSON.stringify(sc.default)}`);
  for (const [g, entry] of Object.entries(sc.subsystems)) {
    if (!groups.includes(g)) fail(`unknown subsystem ${g}; valid: ${groups.join(", ")}`);
    if (!entry || typeof entry !== "object") fail(`subsystems.${g} must be an object with a mode`);
    const mode = entry.mode ?? sc.default;
    const def = MODES[g]?.[mode];
    if (!def) fail(`subsystem ${g} has no mode ${JSON.stringify(mode)}; valid: ${modeNames(g).join(", ")}`);
    if (def.planned) fail(`subsystem ${g} mode ${mode} is not implemented yet (${def.planned})`);
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
