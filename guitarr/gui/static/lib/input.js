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

/** The meter's zones, in dB (the same limits levelVerdict uses): green is where your playing should stay,
 *  yellow is a warning (a bit quiet, or getting hot) and red is where it should never get (it distorts). */
export const LEVEL_ZONES = [
  { kind: "warn", from: -42, to: -30 },
  { kind: "ok", from: -30, to: -10 },
  { kind: "warn", from: -10, to: -4 },
  { kind: "err", from: -4, to: 0 },
];
const zoneOf = d => (LEVEL_ZONES.find(z => d >= z.from && d < z.to) || (d >= 0 ? LEVEL_ZONES[LEVEL_ZONES.length - 1] : null));

/** Markup for a level meter: green / yellow / red zones, the noise-gate marker (`gateDb`) and a legend in words. */
export function meterHtml(id, gateDb = null) {
  const gate = gateDb == null ? "" : `<i class="lv-gate" style="left:${pctOf(gateDb)}%" title="${esc(t("settings.gate"))}"></i>`;
  const zones = [{ kind: "low", from: LEVEL_MIN, to: LEVEL_ZONES[0].from }, ...LEVEL_ZONES]
    .map(z => `<div class="lv-zone ${z.kind}" style="left:${pctOf(z.from)}%;width:${pctOf(z.to) - pctOf(z.from)}%"></div>`).join("");
  // the zones are always there, dim; what your signal reaches lights up in the color of each zone
  return `<div class="lv" id="${id}"><div class="lv-zones">${zones}</div><div class="lv-fill lv-zones lit" style="clip-path:inset(0 100% 0 0)">${zones}</div>
    <i class="lv-peak" hidden></i>${gate}</div>
    <div class="lv-legend small">
      <span><i class="sw ok"></i>${esc(t("meter.zone_ok"))}</span>
      <span><i class="sw warn"></i>${esc(t("meter.zone_warn"))}</span>
      <span><i class="sw err"></i>${esc(t("meter.zone_err"))}</span>
      <span class="muted" data-lv-now aria-live="off"></span>
    </div>`;
}

export const pctOf = d => Math.max(0, Math.min(100, (d - LEVEL_MIN) / -LEVEL_MIN * 100));

/** Moves the bar; its color and the word next to the legend say which zone you're in, and a thin mark holds the
 *  recent peak for a moment, so a hit that touched the red doesn't go unnoticed. */
export function setMeter(el, levelDb) {
  if (!el) return;
  const fill = el.querySelector(".lv-fill");
  if (fill.classList.contains("lit")) fill.style.clipPath = `inset(0 ${(100 - pctOf(levelDb)).toFixed(1)}% 0 0)`;
  else fill.style.width = pctOf(levelDb).toFixed(1) + "%";
  const z = levelDb > LEVEL_MIN ? zoneOf(levelDb) : null;
  el.classList.toggle("z-ok", z?.kind === "ok");
  el.classList.toggle("z-warn", z?.kind === "warn");
  el.classList.toggle("z-err", z?.kind === "err");
  const now = performance.now(), st = el._peak || (el._peak = { db: -120, at: 0 });
  if (levelDb >= st.db || now - st.at > 1500) { st.db = levelDb; st.at = now; }
  const pk = el.querySelector(".lv-peak");
  if (pk) {
    pk.hidden = st.db <= LEVEL_MIN;
    pk.style.left = pctOf(st.db) + "%";
    const pz = zoneOf(st.db);
    pk.className = `lv-peak ${pz ? pz.kind : ""}`;
  }
  const word = el.parentElement && el.parentElement.querySelector("[data-lv-now]");
  if (word) word.textContent = levelDb > LEVEL_MIN ? `${Math.round(levelDb)} dB` + (z ? ` · ${t(`meter.now_${z.kind}`)}` : ` · ${t("meter.now_low")}`) : "";
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
