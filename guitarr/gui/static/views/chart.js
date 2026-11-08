// Chart editor (plain-text format) with a live preview.
import { t, tc } from "../lib/i18n.js";
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

/** Your progress per section: each one moves through five states (a word, not just a color), with a target
 * tempo and a link to loop it in Practice. The song's mastery is the average, computed on the server. */
async function renderSections(box, id) {
  let r;
  try { r = await api(`/api/charts/${encodeURIComponent(id)}/sections`); } catch { box.hidden = true; return; }
  if (!r.sections.length) { box.hidden = true; return; }
  const name = s => tc(`sections.${s.name}`, s.name) + (s.key !== s.name ? s.key.slice(s.name.length) : "");
  box.innerHTML = `<div class="sec-progress-head"><h2 id="secTitle">${esc(t("sections.title"))}</h2>
      <span class="mastery"><b>${r.mastery}%</b> ${esc(t("sections.mastery"))}</span></div>
    <p class="muted small">${esc(t("sections.hint"))}</p>
    <div class="sec-rows">${r.sections.map(s => `
      <div class="sec-row" data-key="${esc(s.key)}">
        <div class="sec-name"><b>${esc(name(s))}</b><small class="muted">${esc(t("sections.bars", { from: s.from, to: s.to }))}</small></div>
        <div class="seg mini sec-states" role="group" aria-label="${esc(t("sections.state_of", { name: name(s) }))}">${r.states.map(st =>
          `<button data-st="${st}" class="st-${st}${st === s.state ? " active" : ""}" aria-pressed="${st === s.state}">${esc(t(`sections.${st}`))}</button>`).join("")}</div>
        <label class="field-inline small">${esc(t("sections.target"))}
          <input type="number" min="20" max="300" step="1" value="${s.bpm ?? ""}" placeholder="—" data-bpm aria-label="${esc(t("sections.target_of", { name: name(s) }))}"></label>
        <a class="btn small" href="#/practice?chart=${encodeURIComponent(id)}&from=${s.from}&to=${s.to}">${esc(t("flow.loop_it"))}</a>
        <small class="err" data-err hidden></small>
      </div>`).join("")}</div>`;
  box.querySelectorAll(".sec-row").forEach(row => {
    const save = async body => {
      const err = row.querySelector("[data-err]");
      try {
        await api(`/api/charts/${encodeURIComponent(id)}/sections`, { json: { key: row.dataset.key, ...body } });
        renderSections(box, id);
      } catch (e) { err.textContent = e.code === "bad_bpm" ? t("sections.bad_bpm") : e.message; err.hidden = false; }
    };
    row.querySelectorAll("[data-st]").forEach(b => b.onclick = () => save({ state: b.dataset.st }));
    const bpm = row.querySelector("[data-bpm]");
    bpm.onchange = () => bpm.value && save({ bpm: +bpm.value });
  });
}

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
    </div>
    ${id ? `<section class="panel sec-progress" id="secProgress" aria-labelledby="secTitle"></section>` : ""}`;
  if (id) renderSections($("#secProgress", el), id);
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
