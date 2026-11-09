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
