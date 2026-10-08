// Evaluator half of devtools/extract_game_spec.py: reads the decompiled
// simworker, evaluates only the data tables and API method literals it is
// asked for, and prints one JSON object on stdout.
//
//   node devtools/extract_game_spec.js <deobfuscated.js>
//
// Never runs the whole file. A top-level `const NAME = ...;`, `function NAME`
// or `class NAME` is sliced out and evaluated only when an evaluated literal
// reads NAME (lazily, cached, in a vm sandbox). An identifier with no
// top-level definition, or whose definition fails to evaluate, becomes a
// marker; markers and getter fields serialize as null and are listed in
// `unresolved`.
"use strict";
const fs = require("fs");
const vm = require("vm");

const SRC = fs.readFileSync(process.argv[2], "utf8");

// ------------------------------------------------------------ source scanning

// Index just past the bracket that closes the one at `open`. Skips strings,
// template literals (with ${} nesting) and comments.
function matchBracket(open) {
  const pairs = { "(": ")", "[": "]", "{": "}" };
  const stack = [];
  let i = open;
  while (i < SRC.length) {
    const c = SRC[i];
    if (c === "/" && SRC[i + 1] === "/") {
      i = SRC.indexOf("\n", i);
      if (i < 0) break;
      continue;
    }
    if (c === "/" && SRC[i + 1] === "*") {
      i = SRC.indexOf("*/", i) + 2;
      continue;
    }
    if (c === "'" || c === '"') {
      i++;
      while (SRC[i] !== c) i += SRC[i] === "\\" ? 2 : 1;
      i++;
      continue;
    }
    if (c === "`") {
      stack.push("`");
      i++;
      // inside a template: scan to ` or ${
      while (true) {
        const d = SRC[i];
        if (d === "\\") { i += 2; continue; }
        if (d === "`") { stack.pop(); i++; break; }
        if (d === "$" && SRC[i + 1] === "{") { stack.push("${"); i += 2; break; }
        i++;
      }
      continue;
    }
    if (c in pairs) {
      stack.push(pairs[c]);
    } else if (c === ")" || c === "]" || c === "}") {
      const top = stack.pop();
      if (top === "${") {
        // back inside the enclosing template literal
        i++;
        while (true) {
          const d = SRC[i];
          if (d === "\\") { i += 2; continue; }
          if (d === "`") { stack.pop(); i++; break; }
          if (d === "$" && SRC[i + 1] === "{") { stack.push("${"); i += 2; break; }
          i++;
        }
        if (stack.length === 0) return i;
        continue;
      }
      if (stack.length === 0) return i + 1;
    }
    i++;
  }
  throw new Error("unbalanced bracket at " + open);
}

// End of the expression starting at `start`: the first `;` or newline at
// bracket depth 0.
function expressionEnd(start) {
  let i = start;
  while (i < SRC.length) {
    const c = SRC[i];
    if (c === ";" || c === "\n") return i;
    if (c === "(" || c === "[" || c === "{" || c === "`" || c === "'" || c === '"') {
      i = c === "(" || c === "[" || c === "{" ? matchBracket(i) : skipString(i);
      continue;
    }
    i++;
  }
  return i;
}

function skipString(i) {
  if (SRC[i] === "`") return matchTemplate(i);
  const q = SRC[i];
  i++;
  while (SRC[i] !== q) i += SRC[i] === "\\" ? 2 : 1;
  return i + 1;
}

function matchTemplate(i) {
  // wrap in a bracket scan: a template literal is balanced like a bracket
  i++;
  while (true) {
    const d = SRC[i];
    if (d === "\\") { i += 2; continue; }
    if (d === "`") return i + 1;
    if (d === "$" && SRC[i + 1] === "{") { i = matchBracket(i + 1); continue; }
    i++;
  }
}

// Top-level definitions (column 0): name -> {kind, at}
const DEFS = new Map();
{
  const re = /^(?:(const|let|var) ([\w$]+) = |(?:async )?(function)\*? ?([\w$]+)\(|(class) ([\w$]+)[ {])/gm;
  let m;
  while ((m = re.exec(SRC))) {
    const name = m[2] || m[4] || m[6];
    if (DEFS.has(name)) continue;
    if (m[1]) DEFS.set(name, { kind: "value", at: m.index + m[0].length });
    else DEFS.set(name, { kind: m[3] ? "function" : "class", at: m.index });
  }
}

function definitionSource(name) {
  const d = DEFS.get(name);
  if (d.kind === "value") return SRC.slice(d.at, expressionEnd(d.at));
  // function NAME(params) {body} / class NAME ... {body}
  let i = d.at;
  if (d.kind === "function") i = matchBracket(SRC.indexOf("(", i));
  return SRC.slice(d.at, matchBracket(SRC.indexOf("{", i)));
}

// ------------------------------------------------------------------ sandbox

const MARK = Symbol("unresolved");
const unresolved = new Set();

function marker(name) {
  const fn = function () {};
  return new Proxy(fn, {
    get(_, k) {
      if (k === MARK) return name;
      if (k === Symbol.toPrimitive) return () => "<" + name + ">";
      if (typeof k === "symbol" || k === "then") return undefined;
      return marker(name + "." + k);
    },
    apply() { return marker(name + "()"); },
    construct() { return marker("new " + name); },
  });
}

const ctx = vm.createContext({});
const GLOBALS = new Set(vm.runInContext("Object.getOwnPropertyNames(globalThis)", ctx));
const cache = new Map();
const resolving = new Set();

const scope = new Proxy(Object.create(null), {
  has(_, k) { return typeof k === "string" && !GLOBALS.has(k) && k !== "__scope"; },
  get(_, k) { return typeof k === "string" ? resolve(k) : undefined; },
  set() { return true; },
});
ctx.__scope = scope;

function resolve(name) {
  if (cache.has(name)) return cache.get(name);
  if (!DEFS.has(name) || resolving.has(name)) return marker(name);
  resolving.add(name);
  let value;
  try {
    value = evaluate(definitionSource(name));
  } catch (e) {
    value = marker(name);
  }
  resolving.delete(name);
  cache.set(name, value);
  return value;
}

function evaluate(expr) {
  return vm.runInContext("with (__scope) { (" + expr + "\n) }", ctx, { timeout: 5000 });
}

// ------------------------------------------------------------- serializing

function isMarker(v) {
  return (typeof v === "function" || typeof v === "object") && v !== null && v[MARK] !== undefined;
}

// JSON-safe copy. Getters and markers become null and their path is listed
// in `unresolved`; functions are dropped.
function plain(v, path) {
  if (isMarker(v)) {
    unresolved.add(path + " = " + v[MARK]);
    return null;
  }
  if (v === null || typeof v === "string" || typeof v === "boolean") return v;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  if (typeof v === "undefined" || typeof v === "function") return undefined;
  if (v instanceof Set || Array.isArray(v)) {
    return Array.from(v, (x, i) => {
      const y = plain(x, path + "[" + i + "]");
      return y === undefined ? null : y;
    });
  }
  if (v instanceof Map) v = Object.fromEntries(v);
  const out = {};
  for (const key of Object.keys(v)) {
    const desc = Object.getOwnPropertyDescriptor(v, key);
    if (desc.get) {
      unresolved.add(path + "." + key + " (getter)");
      out[key] = null;
      continue;
    }
    const y = plain(desc.value, path + "." + key);
    if (y !== undefined) out[key] = y;
  }
  return out;
}

// ------------------------------------------------------------------ tables

// The top-level const whose definition contains the first match of `anchor`.
// Minified names change with every build; the anchors are stable strings.
function table(label, anchor) {
  const m = anchor.exec(SRC);
  if (!m) throw new Error(label + " table not found: " + anchor);
  let best = null;
  for (const [name, d] of DEFS) {
    if (d.kind === "value" && d.at <= m.index && (!best || d.at > best.at)) best = { name, at: d.at };
  }
  if (!best || expressionEnd(best.at) < m.index) throw new Error(label + " table not found: " + anchor);
  return resolve(best.name);
}

const machines = {};
for (const [i, m] of table("machine", /nameKey: `machines\.battery\.name`/).entries()) {
  const row = plain(m, "machines[" + i + "]");
  machines[row.id === null ? "#" + i : row.id] = row;
}

const recipes = table("recipe", /nameKey: `recipes\.craft_battery_cell\.name`/)
  .map((r, i) => plain(r, "recipes[" + i + "]"));
const storage = plain(table("storage", /\{\s*slotCount: \d+,\s*slotCapacity: /), "storage");

// -------------------------------------------------------------------- API

// One registry method object -> spec entry. `outcomes` is the status list of
// a result contract; an `optional` contract (returns None) sets contract_kind.
function methodEntry(obj, path) {
  const params = (obj.params || []).map((p, i) => {
    const out = {};
    for (const k of Object.keys(p)) {
      const desc = Object.getOwnPropertyDescriptor(p, k);
      if (desc.get || k === "dynamicSuggestions") continue; // i18n text, editor hints
      const y = plain(desc.value, path + ".params[" + i + "]." + k);
      if (y !== undefined) out[k] = y;
    }
    return out;
  });
  const entry = {
    params,
    returns: obj.returnType === undefined ? null : plain(obj.returnType, path + ".returnType"),
    readonly: obj.readonly === true,
    signature: obj.signature,
  };
  if (obj.isProperty === true) entry.property = true;
  const contract = obj.outcomeContract;
  if (contract === undefined) return entry;
  if (!isMarker(contract) && contract.kind !== "result") {
    entry.contract_kind = contract.kind;
  } else if (isMarker(contract) || !Array.isArray(contract.outcomes)) {
    unresolved.add(path + ".outcomeContract");
    entry.outcomes = null;
  } else {
    entry.outcomes = contract.outcomes.map((o) => o.code);
    entry.result_type = contract.resultType;
    entry.payload_fields = plain(contract.payloadFields, path + ".payloadFields");
  }
  return entry;
}

const duplicates = [];

function addEntry(section, owner, method, entry, path) {
  section[owner] = section[owner] || Object.create(null);
  if (Object.hasOwn(section[owner], method)) {
    if (JSON.stringify(section[owner][method]) !== JSON.stringify(entry)) duplicates.push(path);
    return;
  }
  section[owner][method] = entry;
}

// Component methods, first from the component registry (each entry {id,
// methods: [...]}; covers methods built by helpers and shared method objects),
const api = Object.create(null);
for (const [i, comp] of table("component", /nameKey: `components\.pioneer\.name`/).entries()) {
  if (typeof comp.id !== "string" || !Array.isArray(comp.methods)) {
    unresolved.add("api registry[" + i + "]");
    continue;
  }
  for (const obj of comp.methods) {
    const path = "api." + comp.id + "." + obj.name;
    addEntry(api, comp.id, obj.name, methodEntry(obj, path), path);
  }
}
// then from method literals whose descriptionKey is components.<comp>.<method>
// (owners the registry lacks: building, drone, power_grid, ...).
{
  const re = /\{\s*name: `([\w]+)`,\s*signature: `/g;
  let m;
  while ((m = re.exec(SRC))) {
    const end = matchBracket(m.index);
    re.lastIndex = end;
    const body = SRC.slice(m.index, end);
    const key = /descriptionKey: `components\.([\w]+)\.([\w]+)`/.exec(body);
    if (!key || key[2] !== m[1]) continue; // panel API, object types
    const path = "api." + key[1] + "." + key[2];
    let obj;
    try {
      obj = evaluate(body);
    } catch (e) {
      unresolved.add(path + " (" + e.message + ")");
      continue;
    }
    addEntry(api, key[1], key[2], methodEntry(obj, path), path);
  }
}

// Object types returned by component calls (InputSlot, ItemStack, NavModule, ...):
// top-level `typeName: `X`` entries with a `methods: [...]` list.
const types = Object.create(null);
{
  const re = /^  typeName: `(\w+)`,$/gm;
  let m;
  while ((m = re.exec(SRC))) {
    const typeName = m[1];
    const close = SRC.indexOf("\n}", m.index);
    const at = SRC.indexOf("\n  methods: [", m.index);
    if (at < 0 || at > close) continue;
    const open = SRC.indexOf("[", at);
    let methods;
    try {
      methods = evaluate(SRC.slice(open, matchBracket(open)));
    } catch (e) {
      unresolved.add("types." + typeName + " (" + e.message + ")");
      continue;
    }
    for (const obj of methods) {
      const path = "types." + typeName + "." + obj.name;
      addEntry(types, typeName, obj.name, methodEntry(obj, path), path);
    }
  }
}

const version = /get_game_version: \w+\(`get_game_version`, \(\) => \w+\(`(\w+)`\)\)/.exec(SRC);

process.stdout.write(JSON.stringify({
  game_version: version ? version[1] : null,
  api,
  types,
  machines,
  recipes,
  storage,
  unresolved: Array.from(unresolved).sort(),
  duplicate_methods: duplicates.sort(),
}));
