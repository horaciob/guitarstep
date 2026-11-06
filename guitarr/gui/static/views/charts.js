// Chord charts: built-in exercises + your own. Play them with listening, view or edit them.
import { t, tc } from "../lib/i18n.js";
import { $, $$, api, audioCtx, click, esc, strum } from "../lib/ui.js";

export function strumHtml(pattern) {
  if (!pattern) return "";
  const counts = ["1", "&", "2", "&", "3", "&", "4", "&", "5", "&", "6", "&"];
  return `<div class="strum" title="${esc(t("charts.strum_hint"))}">` + [...pattern].map((c, i) =>
    `<span class="${c === "D" ? "d" : c === "U" ? "u" : "r"}"><b>${c === "D" ? "↓" : c === "U" ? "↑" : "·"}</b><small>${counts[i] || ""}</small></span>`
  ).join("") + `</div>`;
}

export function barsHtml(chart) {
  let html = "", row = [], cell = [], acc = 0;
  const cellHtml = c => `<div class="bar-cell">${c.map(([i, x]) => `<span data-i="${i}">${esc(x)}</span>`).join("")}</div>`;
  const flushRow = () => { if (row.length) html += `<div class="bars">${row.map(cellHtml).join("")}</div>`; row = []; };
  for (const [i, b] of chart.bars.entries()) {
    if (b.section) {
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
const totalBeats = chart => chart.bars.reduce((s, b) => s + b.beats, 0);

/** A play-along guide for a chart: the current and next chord, the strum pattern and the bars, with a
 * playhead on the beat. `setClock(fn)`: fn() returns beats since the chart started (negative during
 * the count-in) or null; `setClock(null)` stops it. */
export function chartGuide(box, chart, { speed = 1, note = "" } = {}) {
  const bpb = chart.beats_per_bar, pat = chart.strum || "", total = totalBeats(chart), st = starts(chart);
  box.innerHTML = `
    ${note ? `<p class="small">${esc(note)}</p>` : ""}
    <div class="guide-now"><b class="g-chord">${esc(chart.bars[0]?.chord || "–")}</b>
      <span><span class="g-next"></span><small class="g-pos muted"></small></span></div>
    ${strumHtml(pat)}${barsHtml(chart)}
    <p class="muted small">${esc(t("lesson.guide_tempo", { bpm: Math.round(chart.bpm * speed), pct: Math.round(speed * 100) }))}</p>`;
  const slots = $$(".strum span", box), cells = $$(".bar-cell span[data-i]", box);
  const chordEl = $(".g-chord", box), nextEl = $(".g-next", box), posEl = $(".g-pos", box);
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
  };
  const frame = () => { show(clock ? clock() : null); raf = clock ? requestAnimationFrame(frame) : 0; };
  show(null);
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
    const c = pat[s % pat.length], beat = s * slot, bar = chart.bars[st.findLastIndex(x => x <= beat + 1e-6)];
    if ((c === "D" || c === "U") && bar?.frets) evs.push({ beat, frets: bar.frets, down: c === "D" });
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
        ${c.mine ? `<span class="pill">${esc(t("charts.yours"))}</span>` : ""}</header>
      <div class="chips">${c.chords.map(x => `<a class="chip" href="#/chords" title="${esc(t("charts.see_dictionary"))}">${esc(x)}</a>`).join("")}</div>
      ${strumHtml(c.strum)}
      ${c.note ? `<p class="muted small">${esc(note(c))}</p>` : ""}
      <div class="chart" hidden></div>
      <div class="row">
        <a class="btn small primary" href="#/practice?chart=${encodeURIComponent(c.id)}">${esc(t("charts.play"))}</a>
        <button class="btn small" data-act="view">${esc(t("charts.view"))}</button>
        <a class="btn small" href="#/chart/${encodeURIComponent(c.id)}">${esc(t(c.mine ? "charts.edit" : "charts.duplicate"))}</a>
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
