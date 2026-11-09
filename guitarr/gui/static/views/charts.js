// Chord charts: built-in exercises + your own. Play them with listening, view or edit them.
import { t, tc } from "../lib/i18n.js";
import { $, $$, api, audioCtx, chordSvg, click, esc, strum } from "../lib/ui.js";
import { readinessRing } from "../lib/chips.js";

export function strumHtml(pattern) {
  if (!pattern) return "";
  const counts = ["1", "&", "2", "&", "3", "&", "4", "&", "5", "&", "6", "&"];
  const sym = { D: ["d", "↓"], U: ["u", "↑"], "^": ["a", "↓»"], "_": ["r", "‿"] };
  return `<div class="strum" title="${esc(t("charts.strum_hint"))}">` + [...pattern].map((c, i) => {
    const [cls, mark] = sym[c] || ["r", "·"];
    return `<span class="${cls}"><b>${mark}</b><small>${counts[i] || ""}</small></span>`;
  }).join("") + `</div>`;
}

export function barsHtml(chart) {
  let html = "", row = [], cell = [], acc = 0;
  const single = chart.bars.filter(b => b.section).length <= 1 && !chart.bars.slice(1).some(b => b.section);   // one section: no label
  const cellHtml = c => `<div class="bar-cell">${c.map(([i, x]) => `<span data-i="${i}">${esc(x)}</span>`).join("")}</div>`;
  const flushRow = () => { if (row.length) html += `<div class="bars">${row.map(cellHtml).join("")}</div>`; row = []; };
  for (const [i, b] of chart.bars.entries()) {
    if (b.section && !single) {
      if (cell.length) { row.push(cell); cell = []; acc = 0; }
      flushRow();
      html += `<div class="bars-section">${esc(tc(`sections.${b.section}`, b.section))}</div>`;
    }
    cell.push([i, b.chord || "–"]);
    acc += b.beats;
    if (acc >= chart.beats_per_bar - 1e-6) { row.push(cell); cell = []; acc = 0; }
  }
  if (cell.length) row.push(cell);
  flushRow();
  return html;
}

const starts = chart => { let acc = 0; return chart.bars.map(b => (acc += b.beats) - b.beats); };
/** With swing, an offbeat eighth (x.5 beats) comes later: at x + ratio. */
const swung = (chart, beat) => chart.swing && Math.abs(beat % 1 - 0.5) < 1e-6 ? Math.floor(beat) + chart.swing : beat;
const totalBeats = chart => chart.bars.reduce((s, b) => s + b.beats, 0);

/** A play-along guide for a chart: the current and next chord, the strum pattern and the bars, with a
 * playhead on the beat. `setClock(fn)`: fn() returns beats since the chart started (negative during
 * the count-in) or null; `setClock(null)` stops it. */
const SHAPES_KEY = "guitarr.guide.shapes";
let chordDb = null;

/** Diagrams of the chords a chart uses, in order of appearance (the dictionary's, with fingers;
 * otherwise drawn from the chart's own frets). */
async function chartShapesHtml(chart) {
  if (!chordDb) chordDb = api("/api/chords").then(r => new Map(r.chords.map(c => [c.id, c]))).catch(() => new Map());
  const db = await chordDb, seen = new Map();
  for (const b of chart.bars) if (b.chord && !seen.has(b.chord) && (db.get(b.chord) || b.frets))
    seen.set(b.chord, db.get(b.chord) || { id: b.chord, frets: b.frets });
  return [...seen.values()].map(c => `<div class="mini-chord" data-chord="${esc(c.id)}"><b>${esc(c.id)}</b>${chordSvg(c, { size: 76, label: false })}</div>`).join("");
}

export function chartGuide(box, chart, { speed = 1, note = "" } = {}) {
  const bpb = chart.beats_per_bar, pat = chart.strum || "", total = totalBeats(chart), st = starts(chart);
  box.innerHTML = `
    ${note ? `<p class="small">${esc(note)}</p>` : ""}
    <div class="guide-now"><b class="g-chord">${esc(chart.bars[0]?.chord || "–")}</b>
      <span><span class="g-next"></span><small class="g-pos muted"></small></span>
      ${strumHtml(pat)}
      <button type="button" class="btn small g-shapes-btn" aria-expanded="false">${esc(t("lesson.show_shapes"))}</button>
      <div class="g-shapes mini-chords" hidden></div></div>
    ${barsHtml(chart)}
    <p class="muted small">${esc(t("lesson.guide_tempo", { bpm: Math.round(chart.bpm * speed), pct: Math.round(speed * 100) }))}${chart.swing ? ` ${esc(t("lesson.guide_swing"))}` : ""}${(chart.strum || "").includes("^") ? ` ${esc(t("lesson.guide_anticipation"))}` : ""}</p>`;
  const slots = $$(".strum span", box), cells = $$(".bar-cell span[data-i]", box);
  const chordEl = $(".g-chord", box), nextEl = $(".g-next", box), posEl = $(".g-pos", box);
  const shapesEl = $(".g-shapes", box), shapesBtn = $(".g-shapes-btn", box);
  const openShapes = async open => {
    shapesEl.hidden = !open;
    shapesBtn.setAttribute("aria-expanded", String(open));
    shapesBtn.textContent = t(open ? "lesson.hide_shapes" : "lesson.show_shapes");
    try { localStorage.setItem(SHAPES_KEY, open ? "1" : "0"); } catch {}
    if (open && !shapesEl.innerHTML) {
      shapesEl.innerHTML = await chartShapesHtml(chart);
      shown = "";                                     // re-mark the current chord
      show(clock ? clock() : null);
    }
  };
  shapesBtn.onclick = () => openShapes(shapesEl.hidden);
  let clock = null, raf = 0, shown = "";
  const show = beat => {
    let i = -1, slot = -1, chord = chart.bars[0]?.chord || "–", next = "", pos = "";
    if (beat != null && beat < 0) {
      pos = t("lesson.count_in", { n: Math.ceil(-beat) });
    } else if (beat != null && beat < total) {
      i = st.findLastIndex(s => s <= beat + 1e-6);
      const inBar = beat - Math.floor(beat / bpb) * bpb;
      slot = pat.length ? Math.floor(inBar / (bpb / pat.length)) : -1;
      chord = chart.bars[i].chord || "–";
      const j = chart.bars.findIndex((b, k) => k > i && b.chord !== chart.bars[i].chord);
      next = j < 0 ? t("lesson.guide_last") : t("lesson.guide_next", { chord: chart.bars[j].chord || "–", count: Math.ceil(st[j] - beat - 1e-6) });
      pos = t("lesson.guide_pos", { bar: Math.floor(beat / bpb) + 1, bars: Math.ceil(total / bpb), beat: Math.floor(inBar) + 1 });
    }
    const key = [i, slot, chord, next, pos].join("|");
    if (key === shown) return;
    shown = key;
    chordEl.textContent = chord;
    nextEl.textContent = next;
    posEl.textContent = pos;
    slots.forEach((s, k) => s.classList.toggle("on", k === slot));
    cells.forEach(c => c.classList.toggle("on", +c.dataset.i === i));
    $$(".mini-chord", shapesEl).forEach(m => m.classList.toggle("on", i >= 0 && m.dataset.chord === chord));
  };
  const frame = () => { show(clock ? clock() : null); raf = clock ? requestAnimationFrame(frame) : 0; };
  show(null);
  let remembered = false;
  try { remembered = localStorage.getItem(SHAPES_KEY) === "1"; } catch {}
  if (remembered) openShapes(true);
  return {
    setClock(fn) { clock = fn; cancelAnimationFrame(raf); frame(); },
  };
}

/** Plays a chart (count-in clicks, metronome and the strum pattern) at `speed`. Returns
 * `{ clock, stop, done }`; clock() is in beats since the chart started, as chartGuide expects. */
export function playChart(chart, { speed = 1 } = {}) {
  const ac = audioCtx(), bpb = chart.beats_per_bar, pat = chart.strum || "D".repeat(bpb);
  const total = totalBeats(chart), st = starts(chart), rate = chart.bpm * speed / 60;
  const t0 = ac.currentTime + 0.15, at = beat => t0 + (beat + bpb) / rate;
  const evs = [];
  for (let b = -bpb; b < total; b++) evs.push({ beat: b, click: true, accent: ((b % bpb) + bpb) % bpb === 0 });
  const slot = bpb / pat.length;
  for (let s = 0; s * slot < total - 1e-6; s++) {
    const c = pat[s % pat.length], beat = swung(chart, s * slot), at = s * slot;
    // "^" anticipates: it strums the chord of the next slot's bar
    const bar = chart.bars[st.findLastIndex(x => x <= (c === "^" ? at + slot : at) + 1e-6)];
    if ((c === "D" || c === "U" || c === "^") && bar?.frets) evs.push({ beat, frets: bar.frets, down: c !== "U" });
  }
  evs.sort((a, b) => a.beat - b.beat);
  let next = 0, timer = 0, finish;
  const done = new Promise(r => { finish = r; });
  const stop = () => { clearInterval(timer); finish(); };
  const pump = () => {     // schedules a little ahead, so stop() cuts the sound right away
    while (next < evs.length && at(evs[next].beat) < ac.currentTime + 0.2) {
      const e = evs[next++], when = at(e.beat);
      if (e.click) click(when, e.accent);
      else strum({ frets: e.frets }, { down: e.down, capo: chart.capo || 0, when: Math.max(0, when - ac.currentTime) });
    }
    if (ac.currentTime > at(total)) stop();
  };
  timer = setInterval(pump, 40);
  pump();
  return { clock: () => (ac.currentTime - t0) * rate - bpb, stop, done };
}

export async function mount(el) {
  const list = await api("/api/charts");
  const mine = list.filter(c => c.mine), builtin = list.filter(c => !c.mine);
  const title = c => c.mine ? c.title : tc(`charts.${c.id}.title`, c.title);
  const note = c => c.mine ? c.note : tc(`charts.${c.id}.note`, c.note);
  const card = c => c.error ? `<article class="card"><b>${esc(c.id)}</b><p class="err">⚠️ ${esc(c.error)}</p>
      <a class="btn small" href="#/chart/${encodeURIComponent(c.id)}">${esc(t("charts.fix"))}</a></article>` : `
    <article class="card song-card" data-id="${esc(c.id)}">
      <header><div><b>${esc(title(c))}</b>
        <div class="muted small">${esc([c.level ? t("charts.level", { n: c.level }) : "", `♩=${c.bpm}`, `${c.beats_per_bar}/4`,
          c.capo ? t("charts.capo", { n: c.capo }) : "", t("charts.n_chords", { count: c.bars })].filter(Boolean).join(" · "))}</div></div>
        ${c.mine ? `<span class="pill">${esc(t("charts.yours"))}</span>` : ""}${readinessRing(c.readiness, 44)}</header>
      <div class="chips">${c.chords.map(x => `<a class="chip" href="#/chords" title="${esc(t("charts.see_dictionary"))}">${esc(x)}</a>`).join("")}</div>
      ${strumHtml(c.strum)}
      ${c.note ? `<p class="muted small">${esc(note(c))}</p>` : ""}
      <div class="chart" hidden></div>
      <div class="row">
        <a class="btn small primary" href="#/practice?chart=${encodeURIComponent(c.id)}">${esc(t("charts.play"))}</a>
        <button class="btn small" data-act="view">${esc(t("charts.view"))}</button>
        <a class="btn small" href="#/chart/${encodeURIComponent(c.id)}">${esc(t(c.mine ? "charts.edit" : "charts.duplicate"))}</a>
        <a class="btn small ghost" href="#/stage?chart=${encodeURIComponent(c.id)}">${esc(t("stage.open"))}</a>
      </div>
    </article>`;
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("charts.title"))}</h1>
      <p class="muted">${esc(t("charts.subtitle"))}</p></div>
    <div class="row left" style="margin-bottom:16px"><a class="btn primary" href="#/chart/new">${esc(t("charts.new"))}</a></div>
    ${mine.length ? `<h2 class="sub">${esc(t("charts.mine"))}</h2><div class="card-grid">${mine.map(card).join("")}</div>` : ""}
    <h2 class="sub">${esc(t("charts.builtin"))}</h2><div class="card-grid">${builtin.map(card).join("")}</div>`;
  $$(".song-card", el).forEach(c => {
    $("[data-act=view]", c).onclick = async () => {
      const box = $(".chart", c);
      if (box.hidden && !box.innerHTML) box.innerHTML = barsHtml((await api(`/api/charts/${encodeURIComponent(c.dataset.id)}`)).chart);
      box.hidden = !box.hidden;
    };
  });
}
