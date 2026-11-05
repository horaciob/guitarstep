// Practice plan helpers shared by the plan page, Home and the sidebar.
import { lang, t } from "./i18n.js";
import { esc } from "./ui.js";

/** 95 → "1:35" (minutes as h:mm). */
export const fmtHM = min => `${Math.floor(min / 60)}:${String(Math.round(min % 60)).padStart(2, "0")}`;
/** 3725 → "1:02:05" (seconds as h:mm:ss, for running timers). */
export function fmtClock(sec) {
  const s = Math.max(0, Math.floor(sec));
  return `${Math.floor(s / 3600)}:${String(Math.floor(s / 60) % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
export const catName = c => (c.builtin ? t(`plan.cat_${c.id}`) : c.name);
export const fmtDay = (iso, opts = { day: "numeric", month: "short" }) =>
  new Intl.DateTimeFormat(lang(), opts).format(new Date(iso + "T12:00:00"));

/** Status → text, so a color is never the only signal. */
export const statusText = s => (s ? t(`plan.status_${s}`) : t("plan.status_none"));

/** Progress ring: the arc fills up to 100 % but the number shows the real percentage. */
export function ring(pct, status, size = 120) {
  const r = size / 2 - 7, c = 2 * Math.PI * r, fill = Math.max(0, Math.min(100, pct)) / 100;
  return `<svg class="ring ${status || "none"}" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img"
      aria-label="${esc(t("plan.ring_label", { pct: Math.round(pct), status: statusText(status) }))}">
    <circle class="ring-bg" cx="${size / 2}" cy="${size / 2}" r="${r}"/>
    <circle class="ring-fg" cx="${size / 2}" cy="${size / 2}" r="${r}" stroke-dasharray="${(c * fill).toFixed(1)} ${c.toFixed(1)}"
      transform="rotate(-90 ${size / 2} ${size / 2})"/>
    <text x="50%" y="50%" dominant-baseline="central" text-anchor="middle">${Math.round(pct)}%</text></svg>`;
}

/** The seven days of the week with their minutes and a color by how much of the goal they reached. */
export function weekStrip(days) {
  const wd = new Intl.DateTimeFormat(lang(), { weekday: "short" });
  return `<div class="days7">${days.map(d => {
    const label = wd.format(new Date(d.date + "T12:00:00"));
    const blank = d.state === "future" || d.state === "before";
    const value = blank ? "–" : fmtHM(d.minutes);
    const title = blank ? `${label} ${fmtDay(d.date)}` : `${label} ${fmtDay(d.date)} · ${fmtHM(d.minutes)} / ${fmtHM(d.goal)} · ${statusText(d.status)}`;
    return `<div class="d7 ${d.state} ${d.status || ""}" title="${esc(title)}"><small>${esc(label)}</small><b>${value}</b></div>`;
  }).join("")}</div>`;
}
