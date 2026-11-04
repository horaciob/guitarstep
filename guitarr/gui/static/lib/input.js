// Live input check: opens the tuner socket (optionally on a device/channel that is not saved
// yet) and reports level + detected pitch. Used by the setup wizard and the settings page.
import { errorText, t } from "./i18n.js";
import { esc } from "./ui.js";

export const LEVEL_MIN = -70;   // dB shown at the left edge of a level meter

export function openInput({ device = null, channel = null, onReading, onSource, onError } = {}) {
  const qs = new URLSearchParams();
  if (device !== null && device !== "") qs.set("device", device);
  if (channel) qs.set("channel", channel);
  const ws = new WebSocket(`ws://${location.host}/ws/tuner${qs.toString() ? "?" + qs : ""}`);
  let closed = false;
  ws.onmessage = ev => {
    const r = JSON.parse(ev.data);
    if (r.error) { onError && onError(errorText(r.error)); return; }
    if (r.source) { onSource && onSource(r.source); return; }
    onReading && onReading(r);
  };
  ws.onerror = () => { if (!closed) onError && onError(t("setup.no_connection")); };
  return { close() { closed = true; try { ws.close(); } catch { /* already closed */ } } };
}

/** Markup for a level meter; `gateDb` draws the noise-gate marker. */
export function meterHtml(id, gateDb = null) {
  const gate = gateDb == null ? "" : `<i class="lv-gate" style="left:${pctOf(gateDb)}%" title="${esc(t("settings.gate"))}"></i>`;
  return `<div class="lv" id="${id}"><div class="lv-fill"></div>${gate}
    <div class="lv-zone" style="left:${pctOf(-30)}%;width:${pctOf(-10) - pctOf(-30)}%"></div></div>`;
}

export const pctOf = d => Math.max(0, Math.min(100, (d - LEVEL_MIN) / -LEVEL_MIN * 100));

export function setMeter(el, levelDb) {
  if (!el) return;
  const fill = el.querySelector(".lv-fill");
  fill.style.width = pctOf(levelDb).toFixed(1) + "%";
  el.classList.toggle("hot", levelDb > -6);
}

export function setGate(el, gateDb) {
  const g = el && el.querySelector(".lv-gate");
  if (g) g.style.left = pctOf(gateDb) + "%";
}

/** Plain-language verdict for a reading: {cls, text}. Tracks recent peaks to avoid flicker. */
export function levelVerdict(state, r) {
  const now = performance.now();
  state.since = state.since || now;
  if (r.level_db > (state.peak ?? -120) || now - (state.peakAt || 0) > 1500) { state.peak = r.level_db; state.peakAt = now; }
  if (r.level_db > -80) state.alive = now;
  if (r.note) { state.heard = r.note; state.heardAt = now; state.heardDb = r.level_db; }
  const recent = state.heardAt && now - state.heardAt < 2000;
  if (state.peak > -4) return { cls: "err", text: t("setup.too_loud") };
  if (recent && state.heardDb < -42) return { cls: "warn", text: t("setup.too_quiet") };
  if (recent) return { cls: "ok", text: t("setup.heard", { note: state.heard }) };
  if (state.peak > -40) return { cls: "", text: t("setup.hearing") };
  if (now - (state.alive || state.since) > 6000) return { cls: "warn", text: t("setup.silence") };
  return { cls: "muted", text: t("setup.play_string") };
}
