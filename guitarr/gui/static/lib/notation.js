// Rhythm notation: one bar of 4/4 on a one-line staff, drawn as SVG from the compact notation of
// guitarr/rhythm.py ("q e e rq", "e. s", "te te te"). Also plays a bar and records taps against it.
// Grades are shown with a word or a number next to each note, never by color alone.
import { audioCtx, click, esc, pluck } from "./ui.js";
import { t } from "./i18n.js";

const BEATS = { w: 4, h: 2, q: 1, e: 0.5, s: 0.25 };

/** "q. e rq" → [{ fig, rest, dotted, triplet, beats, at }] */
export function parseRhythm(pattern) {
  let at = 0;
  return String(pattern).trim().split(/\s+/).map(tok => {
    const m = /^(r?)(t?)([whqes])(\.?)$/.exec(tok);
    if (!m) throw new Error(`rhythm token ${tok}`);
    const [, r, tr, fig, dot] = m;
    const beats = BEATS[fig] * (dot ? 1.5 : 1) * (tr ? 2 / 3 : 1);
    const ev = { fig, rest: !!r, dotted: !!dot, triplet: !!tr, beats, at };
    at += beats;
    return ev;
  });
}

/** Onsets of the notes (not rests), in beats. */
export const onsetsOf = pattern => parseRhythm(pattern).filter(e => !e.rest).map(e => e.at);

const EPS = 1e-6;

/**
 * The SVG for one bar. opts: { width, label, beatNumbers } — every note is a <g class="nt" data-k>
 * (k = index among notes) so a take can mark it later with markHits().
 */
export function rhythmSvg(pattern, { width = 520, label = "", beatNumbers = true, timeSig = true } = {}) {
  const evs = parseRhythm(pattern);
  const H = 120, mid = 70, left = timeSig ? 58 : 22, right = 18;
  const span = width - left - right;
  const x = at => left + 14 + (span - 28) * at / 4;
  const stemTop = mid - 40;
  let s = `<svg class="rhythm-svg" viewBox="0 0 ${width} ${H}" role="img" aria-label="${esc(label || t("rhythm.notation_label"))}">`;
  s += `<line x1="${left - 8}" x2="${width - right}" y1="${mid}" y2="${mid}" class="rs-line"/>`;
  s += `<line x1="${left - 8}" x2="${left - 8}" y1="${mid - 16}" y2="${mid + 16}" class="rs-bar"/>`;
  s += `<line x1="${width - right}" x2="${width - right}" y1="${mid - 16}" y2="${mid + 16}" class="rs-bar"/>`;
  if (timeSig) s += `<text x="${left - 32}" y="${mid - 3}" class="rs-ts">4</text><text x="${left - 32}" y="${mid + 21}" class="rs-ts">4</text>`;
  if (beatNumbers) for (let b = 0; b < 4; b++) s += `<text x="${x(b)}" y="${H - 6}" class="rs-count">${b + 1}</text>`;

  // beam groups: consecutive eighths/sixteenths (notes, not rests) inside the same beat
  const beamable = e => !e.rest && (e.fig === "e" || e.fig === "s");
  const groups = [];
  let cur = [];
  evs.forEach((e, i) => {
    const beat = Math.floor(e.at + EPS);
    if (beamable(e) && cur.length && Math.floor(evs[cur[0]].at + EPS) === beat && cur[cur.length - 1] === i - 1) cur.push(i);
    else { if (cur.length) groups.push(cur); cur = beamable(e) ? [i] : []; }
  });
  if (cur.length) groups.push(cur);
  const inBeam = new Set(groups.filter(g => g.length > 1).flat());

  let k = 0;
  evs.forEach((e, i) => {
    const cx = x(e.at);
    if (e.rest) { s += restGlyph(e, cx, mid); return; }
    const hollow = e.fig === "w" || e.fig === "h";
    s += `<g class="nt" data-k="${k}"><ellipse cx="${cx}" cy="${mid}" rx="8.5" ry="6" transform="rotate(-20 ${cx} ${mid})" class="${hollow ? "rs-hollow" : "rs-head"}"/>`;
    if (e.fig !== "w") s += `<line x1="${cx + 7.6}" x2="${cx + 7.6}" y1="${mid - 2}" y2="${stemTop}" class="rs-stem"/>`;
    if (!inBeam.has(i) && (e.fig === "e" || e.fig === "s")) {
      s += flag(cx + 7.6, stemTop);
      if (e.fig === "s") s += flag(cx + 7.6, stemTop + 9);
    }
    if (e.dotted) s += `<circle cx="${cx + 16}" cy="${mid - 3}" r="2.6" class="rs-dot"/>`;
    s += `<text x="${cx}" y="${mid + 30}" class="rs-mark"></text></g>`;
    k++;
  });
  // beams: a full one over the group, a second one between neighbouring sixteenths (or a stub for a lone one)
  groups.filter(g => g.length > 1).forEach(g => {
    const xs = g.map(i => x(evs[i].at) + 7.6);
    s += `<rect x="${xs[0]}" y="${stemTop}" width="${xs[xs.length - 1] - xs[0]}" height="5" class="rs-beam"/>`;
    g.forEach((i, j) => {
      if (evs[i].fig !== "s") return;
      const nb = g[j + 1] != null && evs[g[j + 1]].fig === "s";
      const pb = g[j - 1] != null && evs[g[j - 1]].fig === "s";
      if (nb) s += `<rect x="${xs[j]}" y="${stemTop + 9}" width="${xs[j + 1] - xs[j]}" height="5" class="rs-beam"/>`;
      else if (!pb) {
        const dir = j === g.length - 1 ? -1 : 1;
        const w = 10;
        s += `<rect x="${dir > 0 ? xs[j] : xs[j] - w}" y="${stemTop + 9}" width="${w}" height="5" class="rs-beam"/>`;
      }
    });
  });
  // triplet brackets: every run of triplet events, cut each time it adds up to a whole group
  let run = [];
  const flush = () => {
    if (!run.length) return;
    const a = x(run[0].at) - 4, b = x(run[run.length - 1].at) + 12, y = stemTop - 12;
    s += `<path d="M${a} ${y + 5} V${y} H${b} V${y + 5}" class="rs-tuplet"/><text x="${(a + b) / 2}" y="${y - 3}" class="rs-tnum">3</text>`;
    run = [];
  };
  evs.forEach(e => {
    if (!e.triplet) return flush();
    run.push(e);
    const sum = run.reduce((acc, r) => acc + r.beats, 0);
    if (Math.abs(sum - BEATS[run[0].fig] * 2) < 1e-3) flush();
  });
  flush();
  return s + `</svg>`;
}

function flag(x, y) {
  return `<path d="M${x} ${y} c 2 8 13 10 9 22 c 1 -8 -5 -12 -9 -13 z" class="rs-flag"/>`;
}

function restGlyph(e, cx, mid) {
  let g = "";
  if (e.fig === "w") g = `<rect x="${cx - 8}" y="${mid - 12}" width="16" height="6" class="rs-rest"/><line x1="${cx - 13}" x2="${cx + 13}" y1="${mid - 12}" y2="${mid - 12}" class="rs-stem"/>`;
  else if (e.fig === "h") g = `<rect x="${cx - 8}" y="${mid - 6}" width="16" height="6" class="rs-rest"/>`;
  else if (e.fig === "q") g = `<path d="M${cx - 3} ${mid - 22} l 7 9 l -6 7 l 7 9 c -6 -2 -10 1 -5 7 c -9 -4 -7 -11 0 -9 l -7 -8 l 6 -7 z" class="rs-rest"/>`;
  else {
    const two = e.fig === "s";
    g = `<line x1="${cx + 5}" y1="${mid - 12}" x2="${cx - 2}" y2="${mid + (two ? 16 : 8)}" class="rs-stem"/><circle cx="${cx - 1}" cy="${mid - 10}" r="3.2" class="rs-rest"/>`
      + (two ? `<circle cx="${cx - 4}" cy="${mid - 1}" r="3.2" class="rs-rest"/>` : "");
  }
  if (e.dotted) g += `<circle cx="${cx + 14}" cy="${mid - 5}" r="2.6" class="rs-dot"/>`;
  return `<g class="rs-r">${g}</g>`;
}

/** Marks each note with how it went: ✓ / a number of ms (early −, late +) / ✕ for a miss. */
export function markHits(svgBox, hits) {
  hits.forEach((h, k) => {
    const g = svgBox.querySelector(`.nt[data-k="${k}"]`);
    if (!g) return;
    g.classList.add(`g-${h.grade}`);
    const txt = g.querySelector(".rs-mark");
    txt.textContent = h.grade === "miss" ? "✕" : h.grade === "perfect" ? "✓" : `${h.offset > 0 ? "+" : "−"}${Math.abs(h.offset)}`;
  });
}

/** Lights the note being played (k) during a playback or a take. */
export function lightNote(svgBox, k) {
  svgBox.querySelectorAll(".nt").forEach(g => g.classList.toggle("on", +g.dataset.k === k));
}

/**
 * Plays onsets (beats) at a tempo after a count-in of `countIn` clicks, with a click on every beat.
 * → { start: AudioContext time of beat 1, startMs: performance.now() of beat 1, end }
 */
export function playBar(onsets, bpm, { countIn = 4, beats = 4, notes = true, pitch = 52, clicks = true } = {}) {
  const ac = audioCtx(), spb = 60 / bpm, t0 = ac.currentTime + 0.15, start = t0 + countIn * spb;
  for (let b = 0; b < countIn; b++) click(t0 + b * spb, b === 0, 0.9);
  if (clicks) for (let b = 0; b < beats; b++) click(start + b * spb, b === 0, 0.55);
  if (notes) onsets.forEach(o => pluck(pitch, start + o * spb - ac.currentTime, 0.4));
  const startMs = performance.now() + (start - ac.currentTime) * 1000 + (ac.outputLatency || 0) * 1000;
  return { start, startMs, end: start + beats * spb, spb };
}

/** Plays a bar and lights each note of its drawing in time. */
export function hearBar(svgBox, pattern, bpm, opts = {}) {
  const ons = onsetsOf(pattern), b = playBar(ons, bpm, opts), in0 = b.startMs - performance.now();
  ons.forEach((o, k) => setTimeout(() => lightNote(svgBox, k), in0 + o * b.spb * 1000));
  setTimeout(() => lightNote(svgBox, -1), in0 + 4 * b.spb * 1000);
  return b;
}
