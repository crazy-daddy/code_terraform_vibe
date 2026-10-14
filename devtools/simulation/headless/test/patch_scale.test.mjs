import { test } from "node:test";
import assert from "node:assert/strict";
import { patchScale, dataLocalBefore, patchInstantBuild } from "../anchors.mjs";

// Synthetic snippets in the worker's shape (never copied worker code: this
// repo is public). Locals are arbitrary one-letter names, as a minifier picks.
const O2 = `
    for (let a of q) {
      let i = a.data;
      let g = k * u * t;
      let _ = Math.min(g, r.co2);
      r.oxygen = add(r.oxygen, _);
    }
`;
const HEAT = `
    for (let r of q) {
      let i = r.data;
      let f = k * o * t;
      e.planet.temperature.heatUnits = add(e.planet.temperature.heatUnits, f);
    }
`;
const PRESSURE = `
    for (let a of q) {
      let i = a.data;
      if (a.scriptSlots.some(t => t && e.scripts[t]?.status === \`running\`)) {
          let d = k * (i.efficiency / 100) * l;
          r.pressure = add(r.pressure, d * t);
      }
    }
`;
const DRAIN = `
  let o = t * (24 / d.planet.dayCycleDuration);
  let s = \`\${a.portType}_level\`;
  let c = Math.max(0, e.data[s] ?? 0);
  let l = a.ratePerGameHour * o;
  let u = clamp(c, l);
`;
const DRAW = `
  } else if (!n.assumeScriptActive && !gate(e, t) || !on(e)) {
    return 0;
  } else {
    return a * tierFactor(e.data.tier ?? 1, e.data.tierUpgrade ?? 0);
  }
`;
const ALL = O2 + HEAT + PRESSURE + DRAIN + DRAW;

test("each scale pattern matches its synthetic site once and multiplies by the machine's data.scale", () => {
  const r = patchScale(ALL);
  assert.equal(r.why, null);
  assert.deepEqual(r.hits, { o2: 1, heat: 1, pressure: 1, drain: 1, draw: 1 });
  assert.match(r.src, /let _ = Math\.min\(g \* \(i\.scale \?\? 1\), r\.co2\);/);
  assert.match(r.src, /heatUnits = add\(e\.planet\.temperature\.heatUnits, f \* \(i\.scale \?\? 1\)\);/);
  assert.match(r.src, /r\.pressure = add\(r\.pressure, d \* t \* \(i\.scale \?\? 1\)\);/);
  assert.match(r.src, /let l = a\.ratePerGameHour \* o \* \(e\.data\.scale \?\? 1\);/);
  assert.match(r.src, /return a \* tierFactor\(e\.data\.tier \?\? 1, e\.data\.tierUpgrade \?\? 0\) \* \(e\.data\.scale \?\? 1\);/);
  // Only the five lines changed.
  assert.equal(r.src.split("\n").length, ALL.split("\n").length);
  assert.equal([...r.src.matchAll(/\.scale \?\? 1/g)].length, 5);
});

test("zero or several matches leave the source unchanged and name the site", () => {
  const twice = patchScale(ALL + DRAW);
  assert.equal(twice.src, ALL + DRAW);
  assert.equal(twice.hits.draw, 2);
  assert.match(twice.why, /power draw .* found 2x \(want 1\)/);
  const none = patchScale(ALL.replace("r.co2", "r.carbon"));
  assert.equal(none.src, ALL.replace("r.co2", "r.carbon"));
  assert.match(none.why, /O2 loop .* found 0x/);
  assert.equal(none.hits.o2, 0);
  assert.equal(none.hits.heat, 1, "the other sites still count");
});

test("the atmosphere data local comes from the enclosing loop only", () => {
  const src = O2.replace("      let i = a.data;\n", "");
  const r = patchScale(src + HEAT + PRESSURE + DRAIN + DRAW);
  assert.match(r.why, /O2 loop .*: no `let <data> = <machine>\.data;` in its loop/);
  // A data line in a previous loop does not count.
  const idx = (HEAT + O2.replace("      let i = a.data;\n", "")).indexOf("Math.min");
  assert.equal(dataLocalBefore(HEAT + O2.replace("      let i = a.data;\n", ""), idx), null);
  assert.equal(dataLocalBefore(ALL, ALL.indexOf("Math.min")), "i");
  // A data local in a closed sibling block is not the loop's.
  const sibling = O2.replace("      let i = a.data;\n", "      if (a.x) {\n        let j = a.data;\n      }\n");
  assert.equal(dataLocalBefore(sibling, sibling.indexOf("Math.min")), null);
  // One inside an open block above the anchor still counts.
  const open = O2.replace("      let g = k * u * t;\n", "      if (a.x) {\n      let g = k * u * t;\n");
  assert.equal(dataLocalBefore(open, open.indexOf("Math.min")), "i");
});

const WAIT = `
    return {
      kind: \`yield\`,
      action: {
        type: \`wait\`,
        ticks: toTicks(l),
        onResume: () => {
          let t = e.planet.clock.elapsedTime + 1 / d.game.tickRate;
          return M(\`ok\`);
        }
      }
    };
`;

test("the instant pattern guards the construction wait with the harness flag", () => {
  const r = patchInstantBuild(WAIT);
  assert.equal(r.why, null);
  assert.equal(r.hits, 1);
  assert.equal(r.src, WAIT.replace("ticks: toTicks(l)", "ticks: globalThis.__ctInstantBuild ? 2 : toTicks(l)"));
  const none = patchInstantBuild(WAIT.replace("type: `wait`", "type: `idle`"));
  assert.equal(none.src, WAIT.replace("type: `wait`", "type: `idle`"));
  assert.equal(none.hits, 0);
  assert.match(none.why, /found 0x/);
  const twice = patchInstantBuild(WAIT + WAIT);
  assert.equal(twice.src, WAIT + WAIT);
  assert.match(twice.why, /found 2x/);
});
