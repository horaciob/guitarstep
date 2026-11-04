// Chord charts: built-in exercises + your own. Play them with listening, view or edit them.
import { t, tc } from "../lib/i18n.js";
import { $, $$, api, esc } from "../lib/ui.js";

export function strumHtml(pattern) {
  if (!pattern) return "";
  const counts = ["1", "&", "2", "&", "3", "&", "4", "&", "5", "&", "6", "&"];
  return `<div class="strum" title="${esc(t("charts.strum_hint"))}">` + [...pattern].map((c, i) =>
    `<span class="${c === "D" ? "d" : c === "U" ? "u" : "r"}"><b>${c === "D" ? "↓" : c === "U" ? "↑" : "·"}</b><small>${counts[i] || ""}</small></span>`
  ).join("") + `</div>`;
}

export function barsHtml(chart) {
  let html = "", row = [], cell = [], acc = 0;
  const cellHtml = c => `<div class="bar-cell">${c.map(x => `<span>${esc(x)}</span>`).join("")}</div>`;
  const flushRow = () => { if (row.length) html += `<div class="bars">${row.map(cellHtml).join("")}</div>`; row = []; };
  for (const b of chart.bars) {
    if (b.section) {
      if (cell.length) { row.push(cell); cell = []; acc = 0; }
      flushRow();
      html += `<div class="bars-section">${esc(tc(`sections.${b.section}`, b.section))}</div>`;
    }
    cell.push(b.chord || "–");
    acc += b.beats;
    if (acc >= chart.beats_per_bar - 1e-6) { row.push(cell); cell = []; acc = 0; }
  }
  if (cell.length) row.push(cell);
  flushRow();
  return html;
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
    ${mine.length ? `<h3>${esc(t("charts.mine"))}</h3><div class="card-grid">${mine.map(card).join("")}</div>` : ""}
    <h3>${esc(t("charts.builtin"))}</h3><div class="card-grid">${builtin.map(card).join("")}</div>`;
  $$(".song-card", el).forEach(c => {
    $("[data-act=view]", c).onclick = async () => {
      const box = $(".chart", c);
      if (box.hidden && !box.innerHTML) box.innerHTML = barsHtml((await api(`/api/charts/${encodeURIComponent(c.dataset.id)}`)).chart);
      box.hidden = !box.hidden;
    };
  });
}
