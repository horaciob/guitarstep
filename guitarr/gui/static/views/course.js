// Course: levels → lessons. Every lesson is passed by playing its exercises.
import { t, tc } from "../lib/i18n.js";
import { $, $$, api, esc } from "../lib/ui.js";

export async function mount(el) {
  const r = await api("/api/course");
  const all = r.levels.flatMap(l => l.lessons);
  const done = all.filter(l => l.done).length;
  const title = (ls, lv) => ls.recap ? t("lesson.recap_title", { n: lv.badge || lv.number, level: tc(`levels.${lv.id}.title`, lv.title) }) : tc(`lessons.${ls.id}.title`, ls.title);
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("course.title"))}</h1>
      <p class="muted">${esc(t("course.subtitle", { done, total: all.length }))}</p></div>
    ${r.next ? `<a class="callout" href="#/lesson/${encodeURIComponent(r.next.id)}"><span>${t("course.continue_html", { title: esc(tc(`lessons.${r.next.id}.title`, r.next.title)), interpolation: { escapeValue: false } })}</span><span class="btn small primary">${esc(t("course.continue"))}</span></a>`
              : `<div class="callout"><span>${esc(t("course.finished"))}</span></div>`}
    <p class="placement-line small">${r.start_level ? `${esc(t("placement.starting_at", { level: levelName(r, r.start_level) }))}
      <button class="link-btn" id="plReset">${esc(t("placement.reset"))}</button> · ` : ""}<button class="link-btn" id="plOpen">${esc(t(r.start_level ? "placement.again" : "placement.open"))}</button></p>
    ${[...r.levels, ...(r.optional || [])].map((lv, k) => {
      const n = lv.lessons.length, d = lv.lessons.filter(l => l.done).length, full = d === n;
      const first = k === r.levels.length;                 // the optional courses start here
      return `${first ? `<div class="gl-head optional-head"><h2>${esc(t("course.optional_title"))}</h2><p class="muted">${esc(t("course.optional_hint"))}</p></div>` : ""}
      <section class="level${full ? " complete" : ""}${lv.track ? " optional" : ""}">
        <div class="level-head"><h2><span class="lvl-num">${full ? "✓" : esc(String(lv.badge || lv.number))}</span> ${esc(tc(`levels.${lv.id}.title`, lv.title))}</h2>
          <span class="lvl-prog"><span class="small">${esc(t(full ? "course.level_done" : "course.level_progress", { done: d, total: n }))}</span>
            <span class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${n}" aria-valuenow="${d}" aria-label="${esc(t("course.level_progress", { done: d, total: n }))}"><i style="width:${Math.round(100 * d / n)}%"></i></span></span></div>
        <p class="muted">${esc(tc(`levels.${lv.id}.subtitle`, lv.subtitle))}</p>
        <div class="lessons">
          ${lv.lessons.map(ls => {
            const passed = ls.exercises.filter(e => e.passed).length;
            const meta = [t("course.minutes", { n: ls.minutes }), t("course.n_exercises", { count: ls.exercises.length }),
                          (ls.chords || []).join(", ")].filter(Boolean).join(" · ");
            const exName = e => e.from ? tc(`exercises.${e.from}`, e.title) : tc(`exercises.${ls.id}/${e.id}`, e.title);
            return `<details class="lesson-row${ls.done ? " done" : ""}${r.next && r.next.id === ls.id ? " next" : ""}">
              <summary class="lesson${ls.done ? " done" : ""}${r.next && r.next.id === ls.id ? " next" : ""}">
                <span class="state">${ls.done ? "✓" : passed ? `${passed}/${ls.exercises.length}` : "○"}</span>
                <span><b>${esc(title(ls, lv))}</b><small class="muted">${esc(meta)}</small></span><span class="chev" aria-hidden="true">▸</span>
              </summary>
              <div class="lesson-peek">
                <ul class="peek-list">${ls.exercises.map(e => `<li class="${e.passed ? "ok" : ""}">${e.passed ? "✓" : "○"} ${esc(exName(e))}</li>`).join("")}</ul>
                <a class="btn small primary" href="#/lesson/${encodeURIComponent(ls.id)}">${esc(t("course.open_lesson"))}</a>
              </div>
            </details>`;
          }).join("")}
        </div>
      </section>`;
    }).join("")}`;
  $("#plOpen", el).onclick = () => placementDialog(el);
  const reset = $("#plReset", el);
  if (reset) reset.onclick = async () => { await api("/api/placement", { json: { reset: true } }); mount(el); };
}

const levelName = (r, id) => {
  const lv = r.levels.find(l => l.id === id);
  return lv ? `${lv.number} · ${tc(`levels.${lv.id}.title`, lv.title)}` : id;
};

/** One skill per level, yes or no: the first "no" is where you start. */
async function placementDialog(el) {
  const p = await api("/api/placement");
  const dlg = document.createElement("dialog");
  dlg.className = "placement";
  document.body.appendChild(dlg);
  const answers = [];
  const close = () => { dlg.close(); dlg.remove(); };
  const ask = () => {
    const k = answers.length, lv = p.levels[k];
    if (k === p.levels.length || answers.includes(false)) return finish();
    dlg.innerHTML = `<form method="dialog" class="dlg-head"><h2>${esc(t("placement.title"))}</h2><button class="btn ghost small" value="x" aria-label="${esc(t("placement.close"))}">✕</button></form>
      <p class="muted small">${esc(t("placement.step", { k: k + 1, n: p.levels.length }))}</p>
      <p class="placement-q">${esc(t(`placement.skill_${lv.id}`))}</p>
      <div class="row center"><button class="btn primary" data-a="1">${esc(t("placement.yes"))}</button>
        <button class="btn" data-a="0">${esc(t("placement.no"))}</button>
        ${k ? `<button class="btn ghost small" data-back>${esc(t("placement.back"))}</button>` : ""}</div>`;
    $$("[data-a]", dlg).forEach(b => b.onclick = () => { answers.push(b.dataset.a === "1"); ask(); });
    const back = $("[data-back]", dlg);
    if (back) back.onclick = () => { answers.pop(); ask(); };
    $("form", dlg).onsubmit = close;
    $("[data-a]", dlg).focus();
  };
  const finish = async () => {
    const r = await api("/api/placement", { json: { answers } });
    const lv = p.levels.find(l => l.id === r.start_level);
    dlg.innerHTML = `<form method="dialog" class="dlg-head"><h2>${esc(t("placement.title"))}</h2></form>
      <p class="placement-q">${esc(lv ? t("placement.result", { level: `${lv.number} · ${tc(`levels.${lv.id}.title`, lv.title)}` }) : t("placement.result_start"))}</p>
      <p class="muted small">${esc(t("placement.result_hint"))}</p>
      <div class="row center"><button class="btn primary" id="plDone">${esc(t("placement.done"))}</button></div>`;
    $("#plDone", dlg).onclick = () => { close(); mount(el); };
  };
  ask();
  dlg.showModal();
  dlg.addEventListener("cancel", close);
}
