// The last 7 days on one printable page: for yourself, or to show a teacher. "Print" opens the browser's print
// dialog, where "Save as PDF" makes a file.
import { eventText, lang, t, tc } from "../lib/i18n.js";
import { $, api, esc } from "../lib/ui.js";
import { catName, fmtHM } from "../lib/plan.js";

export async function mount(el) {
  const r = await api("/api/report/week");
  const day = iso => new Intl.DateTimeFormat(lang(), { weekday: "short", day: "numeric", month: "short" }).format(new Date(`${iso}T12:00`));
  const cats = new Map(r.categories.map(c => [c.id, c]));
  const pct = v => v == null ? "—" : `${Math.round(v)}%`;
  const max = Math.max(1, ...r.days.map(d => d.minutes));
  el.innerHTML = `
    <div class="report-page">
      <div class="row-between no-print"><a class="btn small" href="#/plan">← ${esc(t("nav.plan"))}</a>
        <button class="btn primary" id="printBtn">${esc(t("report_week.print"))}</button></div>
      <header class="gl-head"><h1>${esc(t("report_week.title"))}</h1>
        <p class="muted">${esc(t("report_week.range", { from: day(r.start), to: day(r.end) }))}</p></header>
      <div class="summary">
        <div class="stat"><div class="v">${esc(fmtHM(r.minutes))}</div><div class="l">${esc(t("report_week.total"))}</div></div>
        <div class="stat"><div class="v">${r.active_days}/7</div><div class="l">${esc(t("report_week.active_days"))}</div></div>
        <div class="stat"><div class="v">${r.streak}</div><div class="l">${esc(t("report_week.streak"))}</div></div>
        <div class="stat"><div class="v">${r.lessons}</div><div class="l">${esc(t("report_week.lessons"))}</div></div>
        <div class="stat"><div class="v">${r.xp}</div><div class="l">XP · ${esc(t("level.label", { n: r.level.level }))}</div></div>
      </div>
      <section><h2>${esc(t("report_week.per_day"))}</h2>
        <table class="report-table"><tr><th>${esc(t("report_week.day"))}</th><th>${esc(t("report_week.minutes"))}</th><th>${esc(t("report_week.what"))}</th></tr>
        ${r.days.map(d => `<tr><td>${esc(day(d.date))}</td>
          <td><span class="rbar"><i style="width:${Math.round(100 * d.minutes / max)}%"></i></span> ${esc(fmtHM(d.minutes))}</td>
          <td class="small">${esc(Object.entries(d.categories).map(([cid, m]) => `${cats.has(cid) ? catName(cats.get(cid)) : cid} ${fmtHM(m)}`).join(" · ") || "—")}</td></tr>`).join("")}</table></section>
      <section><h2>${esc(t("report_week.songs"))}</h2>
        ${r.songs.length ? `<table class="report-table"><tr><th>${esc(t("report_week.song"))}</th><th>${esc(t("report_week.sessions"))}</th><th>${esc(t("report_week.first_last"))}</th><th>${esc(t("report_week.best"))}</th></tr>
          ${r.songs.map(s => `<tr><td>${esc(s.name)}</td><td>${s.sessions}</td><td>${pct(s.first)} → ${pct(s.last)}</td><td><b>${pct(s.best)}</b></td></tr>`).join("")}</table>`
          : `<p class="muted">${esc(t("report_week.no_songs"))}</p>`}</section>
      <section><h2>${esc(t("report_week.earned"))}</h2>
        ${r.events.length ? `<ul class="report-events">${r.events.map(e => `<li>${esc((e.at || "").slice(0, 10))} · ${esc(eventText(e))}${e.xp ? ` <small class="muted">+${e.xp} XP</small>` : ""}</li>`).join("")}</ul>`
          : `<p class="muted">${esc(t("report_week.nothing"))}</p>`}
        ${r.events_capped ? `<p class="muted small">${esc(t("report_week.capped"))}</p>` : ""}</section>
      <section><h2>${esc(t("skills.title"))}</h2>
        <table class="report-table">${r.skills.map(s => `<tr><td>${esc(t(`skills.${s.area}`))}</td><td><b>${s.value}%</b></td>
          <td class="small muted">${s.total ? esc(t("skills.exercises", { passed: s.passed, total: s.total })) : ""}</td></tr>`).join("")}</table></section>
      <p class="muted small">${esc(t("report_week.generated", { at: r.generated.replace("T", " ") }))}</p>
    </div>`;
  $("#printBtn", el).onclick = () => window.print();
}
