// Cifrados: ejercicios incluidos + los tuyos. Tocarlos con escucha, verlos o editarlos.
import { $, $$, api, esc } from "../lib/ui.js";

export function strumHtml(pattern) {
  if (!pattern) return "";
  const counts = ["1", "y", "2", "y", "3", "y", "4", "y", "5", "y", "6", "y"];
  return `<div class="strum" title="Rasgueo: D abajo, U arriba">` + [...pattern].map((c, i) =>
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
      html += `<div class="bars-section">${esc(b.section)}</div>`;
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
  const list = await api("/api/cifrados");
  const mine = list.filter(c => c.mine), builtin = list.filter(c => !c.mine);
  const card = c => c.error ? `<article class="card"><b>${esc(c.id)}</b><p class="err">⚠️ ${esc(c.error)}</p>
      <a class="btn small" href="#/cifrado/${encodeURIComponent(c.id)}">Corregir</a></article>` : `
    <article class="card song-card" data-id="${esc(c.id)}">
      <header><div><b>${esc(c.title)}</b>
        <div class="muted small">${c.level ? `Nivel ${c.level} · ` : ""}♩=${c.bpm} · ${c.beats_per_bar}/4${c.capo ? ` · capo ${c.capo}` : ""} · ${c.bars} acordes</div></div>
        ${c.mine ? `<span class="pill">tuyo</span>` : ""}</header>
      <div class="chips">${c.chords.map(x => `<a class="chip" href="#/acordes" title="Ver en el diccionario">${esc(x)}</a>`).join("")}</div>
      ${strumHtml(c.strum)}
      ${c.note ? `<p class="muted small">${esc(c.note)}</p>` : ""}
      <div class="chart" hidden></div>
      <div class="row">
        <a class="btn small primary" href="#/practicar?cifrado=${encodeURIComponent(c.id)}">▶ Tocar con escucha</a>
        <button class="btn small" data-act="ver">Ver cifrado</button>
        <a class="btn small" href="#/cifrado/${encodeURIComponent(c.id)}">${c.mine ? "Editar" : "Duplicar y editar"}</a>
      </div>
    </article>`;
  el.innerHTML = `
    <div class="gl-head"><h1>Cifrados</h1>
      <p class="muted">Acordes por compás para tocar con metrónomo: te escucha y te marca cada acorde que no entró o se fue de tiempo. Los rasguidos de relleno no cuentan como error.</p></div>
    <div class="row left" style="margin-bottom:16px"><a class="btn primary" href="#/cifrado/nuevo">＋ Escribir un cifrado</a></div>
    ${mine.length ? `<h3>Tuyos</h3><div class="card-grid">${mine.map(card).join("")}</div>` : ""}
    <h3>Ejercicios incluidos</h3><div class="card-grid">${builtin.map(card).join("")}</div>`;
  $$(".song-card", el).forEach(c => {
    $("[data-act=ver]", c).onclick = async () => {
      const box = $(".chart", c);
      if (box.hidden && !box.innerHTML) box.innerHTML = barsHtml((await api(`/api/cifrados/${encodeURIComponent(c.dataset.id)}`)).chart);
      box.hidden = !box.hidden;
    };
  });
}
