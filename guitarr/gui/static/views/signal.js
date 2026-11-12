// Signal check: a guided pass over your guitar's input — noise and hum, guitar knobs,
// interface gain, how your attacks are heard — with a big meter, sounds that tell you when
// the level is right, and playback of what guitarr heard. It ends by saving the settings.
import { t } from "../lib/i18n.js";
import { $, $$, api, audioCtx, esc, instrument, noteName, toast } from "../lib/ui.js";
import { icon } from "../lib/icons.js";
import { inputSocket, sourceName } from "../lib/browser-input.js";

const STEPS = ["silence", "guitar", "gain", "notes", "listen", "done"];
const RANGE = [-70, 0];                 // dB shown by the meter
const ZONE = [-18, -6];                 // strumming hard should peak here
let root = null, ws = null, st = null, timer = 0, beepT = 0;

const pct = d => Math.max(0, Math.min(100, (d - RANGE[0]) / (RANGE[1] - RANGE[0]) * 100));

let simulate = null;
export async function mount(el, { params } = {}) {
  root = el;
  simulate = params && params.simulate;
  st = { step: "silence", reading: null, peaks: [], results: {}, hum: null, zoneSince: 0, inZone: false, recording: null };
  el.innerHTML = `<div class="gl-head head-row"><div><h1>${esc(t("signal.title"))}</h1><p class="muted">${esc(t("signal.subtitle"))}</p></div></div>
    <ol class="steps" id="sgSteps"></ol>
    <div class="panel sg-meter">
      <div class="listen-head"><b id="sgSource" class="muted">${esc(t("setup.connecting"))}</b><span class="mono" id="sgDb">— dB</span></div>
      <div class="big-meter" id="sgMeter" aria-hidden="true">
        <div class="bm-zone" style="left:${pct(ZONE[0])}%;width:${pct(ZONE[1]) - pct(ZONE[0])}%"></div>
        <div class="bm-gate" id="sgGate" hidden></div>
        <div class="bm-fill" id="sgFill"></div><div class="bm-peak" id="sgPeak"></div><span class="bm-clip" id="sgClip">CLIP</span>
      </div>
      <div class="bm-scale"><span>${RANGE[0]}</span><span>−50</span><span>−40</span><span>−30</span><span>−20</span><span>−10</span><span>0 dB</span></div>
    </div>
    <div class="panel sg-card" id="sgCard"></div>`;
  connect();
  render();
}

export function unmount() {
  clearInterval(timer); clearTimeout(beepT);
  if (ws) { try { ws.close(); } catch { /* closed */ } ws = null; }
  root = null;
}

// ------------------------------------------------------------------ live input
function connect() {
  ws = inputSocket("/ws/signal", { simulate });
  ws.onmessage = ev => {
    const r = JSON.parse(ev.data);
    if (r.error) {
      $("#sgSource", root).textContent = t(`errors.${r.error.code}`, { defaultValue: r.error.message });
      $("#sgSource", root).className = "err";
      return;
    }
    if (r.source) { $("#sgSource", root).textContent = t("signal.listening_to", { name: sourceName(r.source) }); return; }
    onReading(r);
  };
  ws.onclose = () => { if (root) $("#sgSource", root).textContent = t("signal.disconnected"); };
}

function onReading(r) {
  if (!root) return;
  st.reading = r;
  const now = performance.now();
  st.peaks.push([now, r.peak_db]);
  while (st.peaks.length && now - st.peaks[0][0] > 1500) st.peaks.shift();
  const recentPeak = Math.max(...st.peaks.map(p => p[1]));
  $("#sgFill", root).style.width = pct(r.level_db) + "%";
  $("#sgPeak", root).style.left = pct(recentPeak) + "%";
  $("#sgClip", root).classList.toggle("on", r.clip);
  $("#sgDb", root).textContent = `${Math.round(r.level_db)} dB · ${t("signal.peak")} ${Math.round(recentPeak)} dB`;
  if (st.step === "gain") gainCoach(recentPeak, r.clip);
}

// ------------------------------------------------------------------ sounds (what you hear)
function tone(freq, dur = 0.15, type = "sine", gain = 0.15) {
  const ac = audioCtx(), o = ac.createOscillator(), g = ac.createGain(), t0 = ac.currentTime;
  o.type = type; o.frequency.value = freq;
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  o.connect(g).connect(ac.destination);
  o.start(t0); o.stop(t0 + dur + 0.02);
}
const chime = () => { tone(880, 0.25); setTimeout(() => tone(1320, 0.35), 120); };
const buzz = () => tone(110, 0.25, "sawtooth", 0.08);

/** Plays what guitarr recorded for a step; `humOnly` keeps just the low hum region, louder. */
async function play(step, humOnly = false) {
  const ac = audioCtx();
  try {
    const data = await (await fetch(`/api/signal/clip/${step}`)).arrayBuffer();
    const buf = await ac.decodeAudioData(data);
    const src = ac.createBufferSource(), g = ac.createGain();
    src.buffer = buf;
    if (humOnly) {
      const lp = ac.createBiquadFilter(); lp.type = "lowpass"; lp.frequency.value = 260; lp.Q.value = 0.7;
      g.gain.value = 6;
      src.connect(lp).connect(g);
    } else { g.gain.value = 1; src.connect(g); }
    const lim = ac.createDynamicsCompressor(); lim.threshold.value = -6; lim.ratio.value = 20;
    g.connect(lim).connect(ac.destination);
    src.start();
  } catch { toast(t("signal.nothing_recorded")); }
}

// ------------------------------------------------------------------ steps
function frame(body) {
  const i = STEPS.indexOf(st.step);
  $("#sgSteps", root).innerHTML = STEPS.map((s, k) => `<li class="${k < i ? "done" : k === i ? "on" : ""}"><span>${k < i ? icon("check", 14) : k + 1}</span>${esc(t(`signal.step_${s}`))}</li>`).join("");
  $("#sgCard", root).innerHTML = body;
  $$("[data-go]", root).forEach(b => b.onclick = () => go(b.dataset.go));
  $$("[data-play]", root).forEach(b => b.onclick = () => play(b.dataset.play, b.dataset.hum === "1"));
}
function go(step) { st.step = step; render(); }
function nav(prev, next, nextLabel = t("setup.continue"), primary = true) {
  return `<div class="setup-actions">${prev ? `<button class="btn ghost" data-go="${prev}">← ${esc(t("common.back"))}</button>` : "<span></span>"}
    ${next ? `<button class="btn${primary ? " primary" : ""}" data-go="${next}">${esc(nextLabel)} →</button>` : ""}</div>`;
}

/** Records the last `seconds` with a countdown, then asks the server to analyze them. */
function measure(step, seconds, extra = {}) {
  const btn = $("#sgRec", root), bar = $("#sgRecBar", root);
  btn.disabled = true;
  const t0 = performance.now();
  clearInterval(timer);
  timer = setInterval(async () => {
    const left = seconds - (performance.now() - t0) / 1000;
    bar.style.width = Math.min(100, 100 * (1 - left / seconds)) + "%";
    btn.textContent = left > 0 ? t("signal.recording", { s: Math.ceil(left) }) : t("signal.analyzing");
    if (left > 0) return;
    clearInterval(timer);
    try {
      st.results[step] = await api("/api/signal/measure", { json: { step, seconds, ...extra } });
      render();
    } catch (e) { toast(e.message); btn.disabled = false; btn.textContent = t("signal.try_again"); }
  }, 100);
}
const recorder = (label) => `<div class="sg-rec"><button class="btn primary" id="sgRec">${esc(label)}</button><div class="pbar"><i id="sgRecBar"></i></div></div>`;

function render() {
  if (!root) return;
  const R = st.results;
  if (st.step === "silence") {
    const r = R.silence;
    if (r) { st.hum = r.hum_hz; $("#sgGate", root).hidden = true; }
    frame(`<h2>${esc(t("signal.silence_title"))}</h2><p class="lead">${esc(t("signal.silence_lead"))}</p>
      ${recorder(r ? t("signal.measure_again") : t("signal.measure", { s: 4 }))}
      ${r ? `<div class="sg-result ${r.verdict === "quiet" && !r.hum_hz ? "ok" : "warn"}">
          <b>${esc(t(`signal.noise_${r.verdict}`, { db: Math.round(r.floor_db) }))}</b>
          ${r.hum_hz ? `<p>${esc(t("signal.hum_found", { hz: r.hum_hz }))}</p><ul class="tips">${["hum_tip_charger", "hum_tip_touch", "hum_tip_pickup", "hum_tip_cable"].map(k => `<li>${esc(t(`signal.${k}`))}</li>`).join("")}</ul>
            <div class="row left wrap"><button class="btn small" data-play="silence" data-hum="1">🔊 ${esc(t("signal.hear_hum"))}</button>
            <label class="check"><input type="checkbox" id="sgHum" ${st.hum ? "checked" : ""}> ${esc(t("signal.filter_hum", { hz: r.hum_hz }))}</label></div>`
          : `<p class="muted">${esc(t("signal.no_hum"))}</p>`}
          ${r.verdict !== "quiet" ? `<ul class="tips"><li>${esc(t("signal.noise_tip_gain"))}</li><li>${esc(t("signal.noise_tip_mute"))}</li></ul>` : ""}
        </div>` : ""}
      ${nav(null, r ? "guitar" : null)}`);
    $("#sgRec", root).onclick = () => measure("silence", 4);
    const h = $("#sgHum", root);
    if (h) h.onchange = () => { st.hum = h.checked ? r.hum_hz : null; };
    return;
  }
  if (st.step === "guitar") {
    const items = ["volume", "tone", "pickup", "inst", "autogain", "direct"];
    frame(`<h2>${esc(t("signal.guitar_title"))}</h2><p class="lead">${esc(t("signal.guitar_lead"))}</p>
      <ul class="checklist">${items.map(k => `<li><label class="check"><input type="checkbox"> <span><b>${esc(t(`signal.chk_${k}`))}</b><small class="muted">${esc(t(`signal.chk_${k}_why`))}</small></span></label></li>`).join("")}</ul>
      ${nav("silence", "gain")}`);
    return;
  }
  if (st.step === "gain") {
    const r = R.strum;
    frame(`<h2>${esc(t("signal.gain_title"))}</h2><p class="lead">${esc(t("signal.gain_lead"))}</p>
      <div class="coach" id="sgCoach" aria-live="polite"><span class="arrow" id="sgArrow">…</span><b id="sgCoachText">${esc(t("signal.strum_now"))}</b></div>
      ${recorder(r ? t("signal.check_again") : t("signal.check_level", { s: 5 }))}
      ${r ? `<div class="sg-result ${r.verdict === "good" ? "ok" : "warn"}"><b>${esc(t(`signal.level_${r.verdict}`, { db: Math.round(r.peak_db), change: Math.abs(Math.round(r.change_db)) }))}</b>
          <p class="muted small">${esc(t("signal.level_detail", { peak: r.peak_db, crest: r.crest_db }))}</p>
          ${r.verdict === "limited" ? `<ul class="tips"><li>${esc(t("signal.limited_tip_1"))}</li><li>${esc(t("signal.limited_tip_2"))}</li><li>${esc(t("signal.limited_tip_3"))}</li></ul>` : ""}
          <button class="btn small" data-play="strum">🔊 ${esc(t("signal.hear_it"))}</button></div>` : ""}
      ${nav("guitar", r ? "notes" : null, r && r.verdict !== "good" ? t("signal.continue_anyway") : t("setup.continue"), !r || r.verdict === "good")}`);
    $("#sgRec", root).onclick = () => measure("strum", 5);
    return;
  }
  if (st.step === "notes") {
    const r = R.notes, n = instrument.strings.length;
    const lowFirst = instrument.strings.map((m, i) => [m, i + 1]).reverse();
    frame(`<h2>${esc(t("signal.notes_title"))}</h2><p class="lead">${esc(t("signal.notes_lead", { n }))}</p>
      <div class="strings">${lowFirst.map(([m, s]) => {
        const hit = r && r.notes.find(x => x.string === s);
        const cls = !r ? "" : !hit ? "miss" : Math.abs(hit.cents) <= 10 ? "ok" : "on";
        return `<div class="${cls}"><b>${noteName(m)}</b><small>${hit ? `${hit.cents > 0 ? "+" : ""}${hit.cents}¢` : esc(t("tuner.string_n", { n: s }))}</small></div>`;
      }).join("")}</div>
      ${recorder(r ? t("signal.record_again") : t("signal.record_notes", { s: 2 * n + 2 }))}
      ${r ? `<div class="sg-result ${r.exact ? "ok" : "warn"}"><b>${esc(r.exact ? t("signal.notes_ok", { n: r.detected }) : t("signal.notes_off", { got: r.detected, n: r.expected }))}</b>
          <p class="muted small">${esc(t("signal.found_settings", { gate: Math.round(r.gate_db), sens: r.sensitivity.toFixed(1) }))}</p>
          ${r.notes.some(x => x.cents != null && Math.abs(x.cents) > 10) ? `<p>${esc(t("signal.needs_tuning"))} <a href="#/tuner">${esc(t("nav.tuner"))} →</a></p>` : ""}
          ${!r.exact ? `<p class="muted small">${esc(t(r.detected > r.expected ? "signal.too_many" : "signal.too_few"))}</p>` : ""}
          <button class="btn small" data-play="notes">🔊 ${esc(t("signal.hear_it"))}</button></div>` : ""}
      ${nav("gain", r ? "listen" : null)}`);
    $("#sgRec", root).onclick = () => measure("notes", 2 * n + 2, { expected: n });
    if (r) { const g = $("#sgGate", root); g.hidden = false; g.style.left = pct(r.gate_db) + "%"; }
    return;
  }
  if (st.step === "listen") {
    frame(`<h2>${esc(t("signal.listen_title"))}</h2><p class="lead">${esc(t("signal.listen_lead"))}</p>
      <div class="choice-grid">
        ${R.silence ? `<button class="choice" data-play="silence">${icon("mic", 22)}<b>${esc(t("signal.clip_silence"))}</b><small>${esc(t("signal.clip_silence_hint"))}</small></button>` : ""}
        ${R.silence && R.silence.hum_hz ? `<button class="choice" data-play="silence" data-hum="1">${icon("analyze", 22)}<b>${esc(t("signal.clip_hum"))}</b><small>${esc(t("signal.clip_hum_hint"))}</small></button>` : ""}
        ${R.strum ? `<button class="choice" data-play="strum">${icon("practice", 22)}<b>${esc(t("signal.clip_strum"))}</b><small>${esc(t("signal.clip_strum_hint"))}</small></button>` : ""}
        ${R.notes ? `<button class="choice" data-play="notes">${icon("tuner", 22)}<b>${esc(t("signal.clip_notes"))}</b><small>${esc(t("signal.clip_notes_hint"))}</small></button>` : ""}
      </div>
      ${nav("notes", "done")}`);
    return;
  }
  // done: what will be saved
  const n = R.notes;
  frame(`<div class="done-mark">${icon("check", 34)}</div><h2>${esc(t("signal.done_title"))}</h2><p class="lead">${esc(t("signal.done_lead"))}</p>
    <dl class="facts sg-facts">
      ${n ? `<div><dt>${esc(t("settings.gate"))}</dt><dd>${Math.round(n.gate_db)} dB</dd></div><div><dt>${esc(t("settings.sensitivity"))}</dt><dd>${n.sensitivity.toFixed(1)}</dd></div>` : ""}
      <div><dt>${esc(t("signal.hum_filter"))}</dt><dd>${st.hum ? `${st.hum} Hz` : esc(t("signal.off"))}</dd></div>
      ${R.strum ? `<div><dt>${esc(t("signal.level"))}</dt><dd>${esc(t(`signal.short_${R.strum.verdict}`))}</dd></div>` : ""}
    </dl>
    <div class="setup-actions"><button class="btn ghost" data-go="listen">← ${esc(t("common.back"))}</button>
      <button class="btn primary" id="sgSave">${esc(t("signal.save"))}</button></div>`);
  $("#sgSave", root).onclick = async () => {
    try {
      await api("/api/signal/apply", { json: { gate_db: n ? n.gate_db : null, sensitivity: n ? n.sensitivity : null, hum_hz: st.hum || null } });
      toast(t("signal.saved"), true);
      location.hash = "#/practice";
    } catch (e) { toast(e.message); }
  };
}

// live coaching while you set the interface gain: arrow + words + sounds
function gainCoach(peak, clip) {
  const arrow = $("#sgArrow", root), text = $("#sgCoachText", root), box = $("#sgCoach", root);
  if (!arrow) return;
  let state;
  if (clip || peak > -1) state = "clip";
  else if (peak < -45) state = "silent";
  else if (peak < ZONE[0]) state = "up";
  else if (peak > ZONE[1]) state = "down";
  else state = "ok";
  arrow.textContent = { clip: "⚠", silent: "…", up: "↑", down: "↓", ok: "✓" }[state];
  text.textContent = t(`signal.coach_${state}`);
  box.className = "coach " + state;
  const now = performance.now();
  if (state === "ok" && !st.inZone) { st.inZone = true; chime(); }
  if (state !== "ok" && state !== "silent") st.inZone = false;
  if (state === "clip" && now - st.zoneSince > 1200) { st.zoneSince = now; buzz(); }
}
