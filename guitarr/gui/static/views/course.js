// Course: levels → lessons. Every lesson is passed by playing its exercises.
import { t, tc } from "../lib/i18n.js";
import { api, esc } from "../lib/ui.js";

export async function mount(el) {
  const r = await api("/api/course");
  const all = r.levels.flatMap(l => l.lessons);
  const done = all.filter(l => l.done).length;
  const title = ls => tc(`lessons.${ls.id}.title`, ls.title);
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("course.title"))}</h1>
      <p class="muted">${esc(t("course.subtitle", { done, total: all.length }))}</p></div>
    ${r.next ? `<a class="callout" href="#/lesson/${encodeURIComponent(r.next.id)}"><span>${t("course.continue_html", { title: esc(tc(`lessons.${r.next.id}.title`, r.next.title)), interpolation: { escapeValue: false } })}</span><span class="btn small primary">${esc(t("course.continue"))}</span></a>`
              : `<div class="callout"><span>${esc(t("course.finished"))}</span></div>`}
    ${r.levels.map(lv => {
      const n = lv.lessons.length, d = lv.lessons.filter(l => l.done).length, full = d === n;
      return `
      <section class="level${full ? " complete" : ""}">
        <div class="level-head"><h2><span class="lvl-num">${full ? "✓" : lv.number}</span> ${esc(tc(`levels.${lv.id}.title`, lv.title))}</h2>
          <span class="lvl-prog"><span class="small">${esc(t(full ? "course.level_done" : "course.level_progress", { done: d, total: n }))}</span>
            <span class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${n}" aria-valuenow="${d}" aria-label="${esc(t("course.level_progress", { done: d, total: n }))}"><i style="width:${Math.round(100 * d / n)}%"></i></span></span></div>
        <p class="muted">${esc(tc(`levels.${lv.id}.subtitle`, lv.subtitle))}</p>
        <div class="lessons">
          ${lv.lessons.map(ls => {
            const passed = ls.exercises.filter(e => e.passed).length;
            const meta = [t("course.minutes", { n: ls.minutes }), t("course.n_exercises", { count: ls.exercises.length }),
                          (ls.chords || []).join(", ")].filter(Boolean).join(" · ");
            return `<a class="lesson${ls.done ? " done" : ""}${r.next && r.next.id === ls.id ? " next" : ""}" href="#/lesson/${encodeURIComponent(ls.id)}">
              <span class="state">${ls.done ? "✓" : passed ? `${passed}/${ls.exercises.length}` : "○"}</span>
              <span><b>${esc(title(ls))}</b><small class="muted">${esc(meta)}</small></span>
            </a>`;
          }).join("")}
        </div>
      </section>`;
    }).join("")}`;
}
