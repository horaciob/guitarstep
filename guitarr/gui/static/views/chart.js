// Chart editor (plain-text format) with a live preview.
import { t, tc } from "../lib/i18n.js";
import { $, api, esc, toast } from "../lib/ui.js";
import { barsHtml, strumHtml } from "./charts.js";
import { renderSections } from "../lib/sections.js";
import { chipsHtml } from "../lib/chips.js";

const TEMPLATE = `title: My chart
bpm: 80
time: 4/4
strum: D.DU.UDU
note: A tip for yourself.

[Verse]
G | D | Em | C
G | D | C G | D
`;

/** Sets (or adds) a header line in the chart text: `strum: …`, `time: …`. */
function setHeader(text, key, value) {
  const re = new RegExp(`^${key}\\s*:.*$`, "m");
  return re.test(text) ? text.replace(re, `${key}: ${value}`) : `${key}: ${value}\n${text}`;
}

export async function mount(el, { segs, params = {} }) {
  const id = segs[0] && segs[0] !== "new" ? decodeURIComponent(segs[0]) : null;
  let text = TEMPLATE, mine = false;
  if (id) {
    const c = await api(`/api/charts/${encodeURIComponent(id)}`);
    text = c.text; mine = c.mine;
  } else if (params.strum) {                         // "use in a chart" from the strumming library
    text = setHeader(setHeader(text, "strum", params.strum), "time", params.time || "4/4");
  }
  let patterns = [];
  try { patterns = (await api("/api/strums")).patterns; } catch { /* the editor works without it */ }
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t(id ? (mine ? "chart.edit_title" : "chart.duplicate_title") : "chart.new_title"))}</h1>
      <p class="muted">${t("chart.help_html")}</p></div>
    <div class="editor">
      <div class="panel">
        ${patterns.length ? `<label class="field-inline small strum-pick">${esc(t("strum.insert"))}
          <select id="strumPick"><option value="">—</option>${patterns.map(p => `<option value="${esc(p.id)}">${esc(tc(`strums.${p.id}.name`, p.name))} · ${esc(p.time)}</option>`).join("")}</select></label>` : ""}
        <details class="paste-sheet" id="pasteBox"><summary>${esc(t("chart.paste_title"))}</summary>
          <p class="muted small">${esc(t("chart.paste_hint"))}</p>
          <textarea id="sheet" rows="8" spellcheck="false" aria-label="${esc(t("chart.paste_title"))}" placeholder="${esc(t("chart.paste_placeholder"))}"></textarea>
          <p class="field-error" id="sheetErr" hidden></p>
          <button class="btn small" id="sheetGo" type="button">${esc(t("chart.paste_convert"))}</button></details>
        <textarea id="txt" spellcheck="false" rows="18" aria-label="${esc(t("chart.text_label"))}">${esc(text)}</textarea>
        <div class="row" style="margin-top:12px">
          <button class="btn primary" id="save">${esc(t("common.save"))}</button>
          ${mine ? `<button class="btn" id="del">${esc(t("chart.delete"))}</button>` : ""}
          <a class="btn" href="#/charts">${esc(t("common.back"))}</a>
        </div>
        <details class="muted small" style="margin-top:12px"><summary>${esc(t("chart.headers"))}</summary>
          <p>${t("chart.headers_html")}</p></details>
      </div>
      <div class="panel" id="preview"></div>
    </div>
    ${id ? `<section class="panel sec-progress" id="secProgress" aria-labelledby="secTitle"></section>` : ""}`;
  if (id) renderSections($("#secProgress", el), { base: `/api/charts/${encodeURIComponent(id)}`, practice: `#/practice?chart=${encodeURIComponent(id)}`, queue: `chart:${id}` });
  const txt = $("#txt", el), pv = $("#preview", el);
  let timer;
  const pickS = $("#strumPick", el);
  if (pickS) pickS.onchange = () => {
    const p = patterns.find(x => x.id === pickS.value);
    if (!p) return;
    txt.value = setHeader(setHeader(txt.value, "strum", p.strum), "time", p.time);
    pickS.value = "";
    validate();
  };
  const validate = async () => {
    const r = await api("/api/charts/validate", { json: { text: txt.value } });
    if (!r.chart) { pv.innerHTML = `<p class="err">⚠️ ${esc(r.error)}</p>`; return r; }
    const c = r.chart;
    pv.innerHTML = `<h2>${esc(c.title)}</h2>${chipsHtml({ tuning: c.tuning, bpm: c.bpm, time: `${c.beats_per_bar}/4`, capo: c.capo, swing: c.swing })}
      ${r.unknown && r.unknown.length ? `<p class="err">⚠️ ${t("chart.unknown_html", { chords: esc(r.unknown.join(", ")), interpolation: { escapeValue: false } })}</p>` : ""}
      ${strumHtml(c.strum)}${barsHtml(c)}`;
    return r;
  };
  txt.oninput = () => { clearTimeout(timer); timer = setTimeout(validate, 300); };
  $("#sheetGo", el).onclick = async () => {
    const err = $("#sheetErr", el);
    try {
      const r = await api("/api/charts/import-text", { json: { text: $("#sheet", el).value } });
      if (r.error) { err.textContent = t("chart.paste_none"); err.hidden = false; return; }
      txt.value = r.text; err.hidden = true;
      $("#pasteBox", el).open = false;
      toast(t("chart.paste_done", { count: r.bars }), true);
      validate();
    } catch (e) { err.textContent = e.message; err.hidden = false; }
  };
  validate();
  $("#save", el).onclick = async () => {
    try {
      const r = await api("/api/charts", { json: { text: txt.value, id: mine ? id : null } });
      toast(t("chart.saved", { title: r.title }), true);
      location.hash = "#/charts";
    } catch (e) { toast(e.message); }
  };
  const del = $("#del", el);
  if (del) del.onclick = async () => {
    if (!del.dataset.sure) {  // second click to confirm (no browser dialogs)
      del.dataset.sure = "1";
      del.textContent = t("chart.confirm_delete");
      setTimeout(() => { delete del.dataset.sure; del.textContent = t("chart.delete"); }, 4000);
      return;
    }
    try {
      await api(`/api/charts/${encodeURIComponent(id)}`, { method: "DELETE" });
      toast(t("chart.deleted"), true);
      location.hash = "#/charts";
    } catch (e) { toast(e.message); }
  };
}
