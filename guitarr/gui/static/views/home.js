// Home: your level, streak, what's next and what you did lately.
import { eventText, lang, t, tc } from "../lib/i18n.js";
import { $, $$, api, esc, toast } from "../lib/ui.js";
import { fmtHM, ring, weekStrip } from "../lib/plan.js";

function ago(iso) {
  const s = (Date.now() - new Date(iso)) / 1000;
  const rtf = new Intl.RelativeTimeFormat(lang(), { numeric: "auto" });
  if (s < 90) return t("home.just_now");
  if (s < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}

/** Title of a step of today's practice, from its kind and params. */
function stepTitle(s) {
  const p = s.params;
  switch (s.kind) {
    case "lesson": return t("today.step_lesson", { title: tc(`lessons.${p.lesson}.title`, p.title || p.lesson) });
    case "review_chord": return t("today.step_review_chord", { chord: p.chord });
    case "review_exercise": return t("today.step_review_exercise", { title: tc(`exercises.${p.lesson}/${p.exercise}`, p.title || p.exercise) });
    case "bars": return t("today.step_bars", { name: p.name, from: p.start, to: p.end });
    case "chart": return t("today.step_chart", { title: tc(`charts.${p.chart}.title`, p.title) });
    case "drill": return t("today.step_drill", { a: p.chords[0], b: p.chords[1] });
    default: return t(`today.step_${s.kind}`);
  }
}

function todayHtml(r) {
  const fmt = m => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
  const budgets = r.budgets || [15, 30, 60, 120];
  return `<div class="row-between"><h2>${esc(t("today.title"))}</h2>
      <span class="muted small">${esc(t("today.summary", { done: r.done, total: r.steps.length, minutes: fmt(r.minutes), goal: fmt(r.goal) }))}</span></div>
    <div class="budget-row"><span class="small muted">${esc(t("today.budget"))}</span>
      <div class="seg mini" role="group" aria-label="${esc(t("today.budget"))}">${[null, ...budgets].map(b =>
        `<button data-budget="${b ?? ""}" class="${(r.budget ?? null) === b ? "active" : ""}" aria-pressed="${(r.budget ?? null) === b}">${esc(b ? t("today.budget_n", { n: b }) : t("today.budget_auto"))}</button>`).join("")}</div></div>
    <ol class="today-steps">${r.steps.map(s => `<li class="${s.done ? "done" : ""}">
      <span class="tick" aria-hidden="true">${s.done ? "✓" : ""}</span>
      <span class="what"><b>${esc(stepTitle(s))}</b><small class="muted">${esc(t(`today.why_${s.kind}`))} · ${s.minutes} min</small></span>
      ${s.kind === "tune" ? `<button class="btn small${s.done ? "" : " ghost"}" data-tick="${esc(s.id)}" aria-pressed="${s.done}">${esc(t(s.done ? "today.ticked" : "today.tick"))}</button>` : ""}
      <a class="btn small${s.done ? "" : " primary"}" href="${esc(s.route)}">${esc(t(s.done ? "today.again" : "today.go"))}</a></li>`).join("")}</ol>
    ${r.done === r.steps.length ? `<p class="note ok">🎉 ${esc(t("today.all_done"))}</p>` : ""}`;
}

function bindToday(el) {
  $$("[data-budget]", el).forEach(b => b.onclick = async () => {
    try {
      const r = await api("/api/today/budget", { json: { minutes: b.dataset.budget ? +b.dataset.budget : null } });
      $("#todayPlan", el).innerHTML = todayHtml(r);
      bindToday(el);
    } catch (e) { toast(e.message); }
  });
  $$("[data-tick]", el).forEach(b => b.onclick = async () => {
    try {
      const r = await api("/api/today/check", { json: { step: b.dataset.tick, done: b.getAttribute("aria-pressed") !== "true" } });
      $("#todayPlan", el).innerHTML = todayHtml(r);
      bindToday(el);
    } catch (e) { toast(e.message); }
  });
}

export async function mount(el) {
  const [p, course, hist, plan, today] = await Promise.all([api("/api/progress"), api("/api/course"), api("/api/history").catch(() => []),
    api("/api/plan").catch(() => null), api("/api/today").catch(() => null)]);
  const lv = p.level;
  let weak = null;
  if (hist.length) {
    try {
      const h = await api(`/api/history/${encodeURIComponent(hist[0].id)}`);
      if (h.problem_bars.length && h.song) weak = { h, bars: h.problem_bars.slice(0, 2).map(b => b.bar) };
    } catch { /* no details */ }
  }
  const all = course.levels.flatMap(l => l.lessons);
  const dayFmt = new Intl.DateTimeFormat(lang(), { weekday: "narrow" });
  const week = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - (6 - i));
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { iso, on: p.days.includes(iso), label: dayFmt.format(d) };
  });
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t(p.practiced_today ? "home.title_done" : "home.title"))}</h1>
      <p class="muted">${esc(p.streak ? t("home.streak_line", { count: p.streak }) : t("home.no_streak"))}</p></div>
    ${today ? `<div class="panel today-plan" id="todayPlan">${todayHtml(today)}</div>` : ""}
    <div class="dash">
      <div class="panel level-card">
        <small class="muted">${esc(t("level.label", { n: lv.level }))}</small><h2>${esc(t(`level.title_${lv.level}`))}</h2>
        <div class="xpbar"><i style="width:${Math.round(lv.progress * 100)}%"></i></div>
        <div class="muted small">${esc(lv.next_xp ? t("home.xp_to_next", { xp: p.xp, left: lv.next_xp - p.xp, n: lv.level + 1 }) : t("home.xp_max", { xp: p.xp }))}</div>
      </div>
      ${plan ? `<a class="panel plan-card" href="#/plan">
        <div class="plan-card-top">${ring(plan.week.goal ? 100 * plan.week.minutes / plan.week.goal : 0, plan.week.estimate, 64)}
          <div><small class="muted">${esc(t("plan.this_week"))}</small><h2>${fmtHM(plan.week.minutes)} <span class="muted small">/ ${fmtHM(plan.week.goal)}</span></h2>
          <small class="muted">🔥 ${esc(t("plan.goal_streak_short", { count: plan.streak }))} · ${esc(plan.week.previous == null ? t("plan.no_data_prev") : t("plan.prev_short", { time: fmtHM(plan.week.previous) }))}</small></div></div>
        ${weekStrip(plan.week.days)}
      </a>` : `<div class="panel">
        <small class="muted">${esc(t("home.streak"))}</small><h2>🔥 ${esc(t("common.days", { count: p.streak }))}</h2>
        <div class="week">${week.map(d => `<span class="${d.on ? "on" : ""}" title="${d.iso}"><i></i>${esc(d.label)}</span>`).join("")}</div>
      </div>`}
      <div class="panel">
        <small class="muted">${esc(t("nav.course"))}</small><h2>${esc(t("home.lessons", { done: p.lessons.length, total: all.length }))}</h2>
        <div class="muted small">${esc(t("home.mastered", { chords: Object.keys(p.chords).length, records: Object.keys(p.drills).length }))}</div>
      </div>
    </div>
    <div class="dash two">
      <div class="stack">
        ${course.next ? `<a class="callout" href="#/lesson/${encodeURIComponent(course.next.id)}"><span>${t("home.next_lesson_html", { title: esc(tc(`lessons.${course.next.id}.title`, course.next.title)), interpolation: { escapeValue: false } })}</span><span class="btn small primary">${esc(t("home.go"))}</span></a>` : ""}
        ${weak ? `<a class="callout" href="#/history"><span>${t("home.weak_html", { song: esc(weak.h.reference.name || weak.h.id), bars: weak.bars.join(" & "), interpolation: { escapeValue: false } })}</span><span class="btn small">${esc(t("home.see"))}</span></a>` : ""}
        <div class="quick">
          <a class="panel" href="#/charts"><b>♫ ${esc(t("home.q_chart"))}</b><span class="muted small">${esc(t("home.q_chart_hint"))}</span></a>
          <a class="panel" href="#/tools?tab=drill"><b>⏱ ${esc(t("home.q_drill"))}</b><span class="muted small">${esc(t("home.q_drill_hint"))}</span></a>
          <a class="panel" href="#/chords"><b>▦ ${esc(t("home.q_chords"))}</b><span class="muted small">${esc(t("home.q_chords_hint"))}</span></a>
          <a class="panel" href="#/tuner"><b>◎ ${esc(t("home.q_tune"))}</b><span class="muted small">${esc(t("home.q_tune_hint"))}</span></a>
        </div>
      </div>
      <div class="panel"><h2>${esc(t("home.latest"))}</h2>
        ${p.events.length ? `<ul class="events">${p.events.slice(0, 8).map(e => `<li><span>${esc(eventText(e))}</span><span class="muted small">${e.xp ? `+${e.xp} XP · ` : ""}${esc(ago(e.at))}</span></li>`).join("")}</ul>`
          : `<p class="muted">${t("home.nothing_yet_html")}</p>`}
      </div>
    </div>`;
  bindToday(el);
}
