// Seed Maker recipes of a world seed: port of the game's Bp(seed) (see
// devtools/seed_quality.py recipes()). PRNG mp(seed ^ 1347174734), partial
// Fisher-Yates over the 4060 lexicographic triples of 30 forms, a triple is skipped
// if one of its forms is already in 4 recipes; recipe s goes to species s.
// Allocation-free and early-exit: recipeForms(seed, n, out) stops after species n-1
// (crowncap = 9, grandbloom = 14). Verified against seed_quality.py by seedscan.mjs --verify.
export const N_FORMS = 30, N_SPECIES = 15, SPECIES_CROWNCAP = 9, SPECIES_GRANDBLOOM = 14;
const SALT = 1347174734, MAX_PER_FORM = 4;

const TRI = [];
for (let a = 0; a < N_FORMS; a++) for (let b = a + 1; b < N_FORMS; b++) for (let c = b + 1; c < N_FORMS; c++) TRI.push(a, b, c);
const TRIPLES = TRI.length / 3; // 4060
const TRI_FORMS = Uint8Array.from(TRI);

export function makeRecipeState() {
  const perm = new Int16Array(TRIPLES);
  for (let i = 0; i < TRIPLES; i++) perm[i] = i;
  return { perm, used: new Uint8Array(N_FORMS), touched: new Int16Array(1024) };
}

// Fills out[3 * s .. 3 * s + 2] (form indexes into FORMS, ascending) for s < n; false if the
// combination space ran out (never in practice). `st` from makeRecipeState(), reusable.
export function recipeForms(seed, n, out, st) {
  const { perm, used, touched } = st;
  used.fill(0);
  let t = (seed ^ SALT) | 0, o = 0, s = 0, nt = 0, ok = true;
  while (s < n) {
    if (o >= TRIPLES) { ok = false; break; }
    t = (t + 1831565813) | 0;
    let x = Math.imul(t ^ (t >>> 15), t | 1);
    x = (x + Math.imul(x ^ (x >>> 7), x | 61)) ^ x;
    const r = ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    const e = o + Math.floor(r * (TRIPLES - o));
    const pe = perm[e], po = perm[o];
    perm[e] = po; perm[o] = pe;
    if (nt + 2 > touched.length) throw new Error("touched overflow");
    touched[nt++] = e; touched[nt++] = o;
    o++;
    const i = pe * 3, a = TRI_FORMS[i], b = TRI_FORMS[i + 1], c = TRI_FORMS[i + 2];
    if (used[a] < MAX_PER_FORM && used[b] < MAX_PER_FORM && used[c] < MAX_PER_FORM) {
      used[a]++; used[b]++; used[c]++;
      out[3 * s] = a; out[3 * s + 1] = b; out[3 * s + 2] = c;
      s++;
    }
  }
  for (let k = nt - 1; k >= 0; k--) perm[touched[k]] = touched[k]; // identity again
  return ok;
}
