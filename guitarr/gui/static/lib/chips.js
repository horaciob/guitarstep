// Small shared pieces: status chips (tuning · key · BPM · time, each with its label) and the readiness ring.
import { t } from "./i18n.js";
import { esc } from "./ui.js";

/** Chips with a label each (never color alone). Missing values are left out. */
export function chipsHtml({ tuning, key, bpm, time, capo, swing } = {}) {
  const c = [];
  if (tuning) c.push([t("chips.tuning"), t(`instrument.t_${tuning}`, { defaultValue: tuning })]);
  if (key) c.push([t("chips.key"), key]);
  if (bpm) c.push([t("chips.bpm"), Math.round(bpm)]);
  if (time) c.push([t("chips.time"), time]);
  if (capo) c.push([t("chips.capo"), capo]);
  if (swing) c.push([t("chips.feel"), t("chips.swing")]);
  return c.length ? `<div class="status-chips">${c.map(([l, v]) => `<span class="status-chip"><small>${esc(l)}</small> <b>${esc(String(v))}</b></span>`).join("")}</div>` : "";
}

/** A ring with the number inside: how ready a song is (the average of its sections). */
export function readinessRing(pct, size = 64) {
  if (pct == null) return "";
  const r = 26, len = 2 * Math.PI * r;
  return `<span class="ready-ring" role="img" aria-label="${esc(t("chips.readiness", { pct }))}">
    <svg viewBox="0 0 60 60" width="${size}" height="${size}" aria-hidden="true"><circle cx="30" cy="30" r="${r}" class="rr-track"/>
      <circle cx="30" cy="30" r="${r}" class="rr-val" stroke-dasharray="${len}" stroke-dashoffset="${(len * (1 - pct / 100)).toFixed(1)}" transform="rotate(-90 30 30)"/></svg>
    <b>${pct}%</b></span>`;
}
