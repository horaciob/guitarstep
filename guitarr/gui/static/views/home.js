// Home: your level, streak, what's next and what you did lately.
import { eventText, lang, t, tc } from "../lib/i18n.js";
import { api, esc } from "../lib/ui.js";

function ago(iso) {
  const s = (Date.now() - new Date(iso)) / 1000;
  const rtf = new Intl.RelativeTimeFormat(lang(), { numeric: "auto" });
  if (s < 90) return t("home.just_now");
  if (s < 3600) return rtf.format(-Math.round(s / 60), "minute");
  if (s < 86400) return rtf.format(-Math.round(s / 3600), "hour");
  return rtf.format(-Math.round(s / 86400), "day");
}

export async function mount(el) {
  const [p, course, hist] = await Promise.all([api("/api/progress"), api("/api/course"), api("/api/history").catch(() => [])]);
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
    <div class="dash">
      <div class="panel level-card">
        <small class="muted">${esc(t("level.label", { n: lv.level }))}</small><h2>${esc(t(`level.title_${lv.level}`))}</h2>
        <div class="xpbar"><i style="width:${Math.round(lv.progress * 100)}%"></i></div>
        <div class="muted small">${esc(lv.next_xp ? t("home.xp_to_next", { xp: p.xp, left: lv.next_xp - p.xp, n: lv.level + 1 }) : t("home.xp_max", { xp: p.xp }))}</div>
      </div>
      <div class="panel">
        <small class="muted">${esc(t("home.streak"))}</small><h2>🔥 ${esc(t("common.days", { count: p.streak }))}</h2>
        <div class="week">${week.map(d => `<span class="${d.on ? "on" : ""}" title="${d.iso}"><i></i>${esc(d.label)}</span>`).join("")}</div>
      </div>
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
}
