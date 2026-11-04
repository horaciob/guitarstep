// Chart editor (plain-text format) with a live preview.
import { t } from "../lib/i18n.js";
import { $, api, esc, toast } from "../lib/ui.js";
import { barsHtml, strumHtml } from "./charts.js";

const TEMPLATE = `title: My chart
bpm: 80
time: 4/4
strum: D.DU.UDU
note: A tip for yourself.

[Verse]
G | D | Em | C
G | D | C G | D
`;

export async function mount(el, { segs }) {
  const id = segs[0] && segs[0] !== "new" ? decodeURIComponent(segs[0]) : null;
  let text = TEMPLATE, mine = false;
  if (id) {
    const c = await api(`/api/charts/${encodeURIComponent(id)}`);
    text = c.text; mine = c.mine;
  }
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t(id ? (mine ? "chart.edit_title" : "chart.duplicate_title") : "chart.new_title"))}</h1>
      <p class="muted">${t("chart.help_html")}</p></div>
    <div class="editor">
      <div class="panel">
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
    </div>`;
  const txt = $("#txt", el), pv = $("#preview", el);
  let timer;
  const validate = async () => {
    const r = await api("/api/charts/validate", { json: { text: txt.value } });
    if (!r.chart) { pv.innerHTML = `<p class="err">⚠️ ${esc(r.error)}</p>`; return r; }
    const c = r.chart;
    pv.innerHTML = `<h2>${esc(c.title)}</h2><p class="muted small">♩=${c.bpm} · ${c.beats_per_bar}/4${c.capo ? ` · ${esc(t("charts.capo", { n: c.capo }))}` : ""}</p>
      ${r.unknown && r.unknown.length ? `<p class="err">⚠️ ${t("chart.unknown_html", { chords: esc(r.unknown.join(", ")), interpolation: { escapeValue: false } })}</p>` : ""}
      ${strumHtml(c.strum)}${barsHtml(c)}`;
    return r;
  };
  txt.oninput = () => { clearTimeout(timer); timer = setTimeout(validate, 300); };
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
