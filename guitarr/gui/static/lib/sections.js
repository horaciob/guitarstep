// Progress per section of a chart or a song: five states (a word, not just a color), a target tempo, a link
// to loop it in Practice, and "+" to put it in today's plan. The mastery is computed on the server.
import { t, tc } from "./i18n.js";
import { api, esc, toast } from "./ui.js";

/** base: "/api/charts/<id>" or "/api/songs/<name>" · practice: the Practice link without from/to · queue: the
 * id used to put a section in today's queue ("chart:<id>" or "song:<name>"). onChange(mastery) after a save. */
export async function renderSections(box, { base, practice, queue, onChange = null }) {
  let r;
  try { r = await api(`${base}/sections`); } catch { box.hidden = true; return; }
  if (!r.sections.length) { box.hidden = true; return; }
  const name = s => tc(`sections.${s.name}`, s.name) + (s.key !== s.name ? s.key.slice(s.name.length) : "");
  box.innerHTML = `<div class="sec-progress-head"><h2 id="secTitle">${esc(t("sections.title"))}</h2>
      <span class="mastery"><b>${r.mastery}%</b> ${esc(t("sections.mastery"))}</span></div>
    <p class="muted small">${esc(t("sections.hint"))}</p>
    <div class="sec-rows">${r.sections.map(s => `
      <div class="sec-row" data-key="${esc(s.key)}">
        <div class="sec-name"><b>${esc(name(s))}</b><small class="muted">${esc(s.to ? t("sections.bars", { from: s.from, to: s.to }) : t("sections.whole"))}</small></div>
        <div class="seg mini sec-states" role="group" aria-label="${esc(t("sections.state_of", { name: name(s) }))}">${r.states.map(st =>
          `<button data-st="${st}" class="st-${st}${st === s.state ? " active" : ""}" aria-pressed="${st === s.state}">${esc(t(`sections.${st}`))}</button>`).join("")}</div>
        <label class="field-inline small">${esc(t("sections.target"))}
          <input type="number" min="20" max="300" step="1" value="${s.bpm ?? ""}" placeholder="—" data-bpm aria-label="${esc(t("sections.target_of", { name: name(s) }))}"></label>
        <a class="btn small" href="${esc(practice)}${s.to ? `&from=${s.from}&to=${s.to}` : ""}">${esc(t("flow.loop_it"))}</a>
        ${queue ? `<button class="btn small" data-queue aria-label="${esc(t("sections.queue_of", { name: name(s) }))}">＋ ${esc(t("sections.queue"))}</button>` : ""}
        <small class="err" data-err hidden></small>
      </div>`).join("")}</div>`;
  onChange && onChange(r.mastery);
  box.querySelectorAll(".sec-row").forEach(row => {
    const save = async body => {
      const err = row.querySelector("[data-err]");
      try {
        await api(`${base}/sections`, { json: { key: row.dataset.key, ...body } });
        renderSections(box, { base, practice, queue, onChange });
      } catch (e) { err.textContent = e.code === "bad_bpm" ? t("sections.bad_bpm") : e.message; err.hidden = false; }
    };
    row.querySelectorAll("[data-st]").forEach(b => b.onclick = () => save({ state: b.dataset.st }));
    const bpm = row.querySelector("[data-bpm]");
    bpm.onchange = () => bpm.value && save({ bpm: +bpm.value });
    const q = row.querySelector("[data-queue]");
    if (q) q.onclick = async () => {
      try {
        await api("/api/today/queue", { json: { ref: queue, section: row.dataset.key } });
        toast(t("sections.queued", { name: row.querySelector(".sec-name b").textContent }), true);
      } catch (e) { toast(e.message); }
    };
  });
}
