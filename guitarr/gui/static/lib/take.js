// Listening back to a take: the guitar as recorded, with the metronome you heard mixed in when there was one.
import { t } from "./i18n.js";
import { esc } from "./ui.js";

const KEY = "guitarr.take.click";      // per browser: whether you like to hear the click on playback
const wantClick = () => { try { return localStorage.getItem(KEY) !== "0"; } catch { return true; } };

/** HTML for a take player. info = { click, bpm, final_bpm } from the server (may be missing for old takes). */
export function takePlayer(name, info) {
  const has = !!(info && info.click), on = has && wantClick();
  const src = n => `/takes/${encodeURIComponent(n)}`;
  const bpm = has && info.bpm ? (info.final_bpm && info.final_bpm !== info.bpm
    ? t("take.bpm_change", { from: info.bpm, to: info.final_bpm }) : t("take.bpm", { bpm: info.bpm })) : "";
  return `<div class="take-player" data-take="${esc(name)}">
    <audio controls preload="metadata" src="${src(name)}${on ? "?click=1" : ""}"></audio>
    ${has ? `<label class="check small"><input type="checkbox" data-take-click ${on ? "checked" : ""}> ${esc(t("take.with_click"))}</label>
      <span class="muted small">${esc(bpm)}</span>` : ""}
  </div>`;
}

/** Wires the "with the metronome" switches inside `root` (keeps the playback position when you flip it). */
export function bindTakePlayers(root) {
  root.querySelectorAll(".take-player").forEach(box => {
    const cb = box.querySelector("[data-take-click]"), audio = box.querySelector("audio");
    if (audio) audio.addEventListener("error", async () => {         // deleted from Settings → Your data?
      try {
        const r = await fetch(`/takes/${encodeURIComponent(box.dataset.take)}`, { method: "HEAD" });
        if (r.status === 404) box.innerHTML = `<span class="muted small">${esc(t("take.gone"))}</span>`;
      } catch { /* offline: leave the player */ }
    }, { once: true });
    if (!cb || !audio) return;
    cb.addEventListener("change", () => {
      try { localStorage.setItem(KEY, cb.checked ? "1" : "0"); } catch { /* private window */ }
      const at = audio.currentTime, playing = !audio.paused;
      audio.src = `/takes/${encodeURIComponent(box.dataset.take)}${cb.checked ? "?click=1" : ""}`;
      audio.addEventListener("loadedmetadata", () => { audio.currentTime = at; if (playing) audio.play().catch(() => {}); }, { once: true });
    });
  });
}

/** "Is it you or the system?": the server's reading of a take's timing, in words, with a way to fix it. */
export function timingVerdictHtml(v) {
  if (!v) return "";
  const p = { ...v.params, dir: t(`timing_v.dir_${v.params.dir}`) };
  const cls = v.code === "on_time" ? "ok" : v.code === "steady_system" ? "warn" : "";
  const link = v.code === "steady_system" ? ` <a href="#/settings">${esc(t("timing_v.fix_link"))}</a>` : "";
  return `<p class="callout small timing-verdict ${cls}">${esc(t(`timing_v.${v.code}`, p))}${link}</p>`;
}

/** Where in the beat the timing slips, and how even the attack is (the server's `summary.groove`). */
export function grooveHtml(g) {
  if (!g || (!g.timing.length && !g.dynamics)) return "";
  const signed = v => `${v > 0 ? "+" : ""}${v}`;
  const rows = g.timing.map(r => `<tr class="g-${r.tend}"><td>${esc(t(`groove.pos_${r.pos}`))}</td>
    <td class="mono">${esc(signed(r.mean_ms))} ms</td><td>${esc(t(`groove.tend_${r.tend}`))}</td>
    <td class="muted small">${esc(t("groove.notes", { n: r.n, std: r.std_ms }))}</td></tr>`).join("");
  const tip = g.tip ? `<p class="callout small">${esc(t("groove.tip", { pos: t(`groove.pos_${g.tip.pos}`), ms: g.tip.ms, tend: t(`groove.tend_${g.tip.tend}`) }))}</p>` : "";
  const d = g.dynamics;
  const dyn = d ? `<p class="small groove-dyn">${esc(t(`groove.dyn_${d.code}`, { spread: d.spread_pct, db: Math.abs(d.offbeat_db ?? 0) }))}</p>` : "";
  return `<div class="groove"><h3>${esc(t("groove.title"))}</h3>${rows ? `<table class="groove-table">${rows}</table>` : ""}${tip}${dyn}</div>`;
}
