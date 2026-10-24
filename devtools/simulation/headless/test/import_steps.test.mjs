import { test } from "node:test";
import assert from "node:assert/strict";
import { patchImportSteps } from "../simhost.mjs";

// Synthetic snippet in the worker's shape (never copied worker code: this repo is public).
const RESOLVE = `
    try {
      this.executeModuleBodySync(c.body);
      u.status = \`ready\`;
    } catch (n) {
`;

test("the module body run goes through __ctImportStep", () => {
  const { src, why } = patchImportSteps(RESOLVE);
  assert.equal(why, undefined);
  assert.match(src, /__ctImportStep\(this, \(\) => this\.executeModuleBodySync\(c\.body\)\);/);
  assert.match(src, /u\.status = `ready`;/);
});

test("a missing or doubled module body run leaves the source alone", () => {
  assert.match(patchImportSteps("nothing here").why, /found 0x/);
  const twice = RESOLVE + RESOLVE;
  const r = patchImportSteps(twice);
  assert.match(r.why, /found 2x/);
  assert.equal(r.src, twice);
});
