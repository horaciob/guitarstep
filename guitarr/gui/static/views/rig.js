// Tone rig: guitar voicing, pedalboard, amp, cabinet + mic, effects and a looper.
// The audio engine (lib/rig/engine.js) keeps running when you leave this page.
import { t } from "../lib/i18n.js";
import { $, $$, api, esc, toast } from "../lib/ui.js";
import { icon } from "../lib/icons.js";
import { rig } from "../lib/rig/engine.js";
import { AMP_KNOBS, AMPS, CABS, EFFECT_GROUPS, EFFECTS, GUITARS, MICS } from "../lib/rig/effects.js";
import { ARTIST_INFO, ARTIST_STYLE, ARTIST_STYLES, ARTISTS, FACTORY, factory, makeEffect } from "../lib/rig/presets.js";
import { knob } from "../lib/rig/knob.js";
import { RIFFS, VOICES } from "../lib/rig/synth.js";
import { clipPlot, comparePlots, isDrive, stackCurve } from "../lib/rig/visuals.js";

const HP_KEY = "guitarr.rig.headphones";
let root = null, raf = 0, onChange = null, onLoop = null, onParam = null, onMidi = null, onRec = null, confirmDelete = false;
const knobsByTarget = new Map();      // "uid:param" or "master" → knob element (to follow an expression pedal)

const fmt = (unit, v) => {
  if (unit === "dB") return `${v > 0 ? "+" : ""}${(+v).toFixed(Math.abs(v) < 10 && v % 1 ? 1 : 0)} dB`;
  if (unit === "ms") return `${Math.round(v)} ms`;
  if (unit === "Hz") return `${(+v).toFixed(v < 1 ? 2 : 1)} Hz`;
  if (unit === "st") return `${v > 0 ? "+" : ""}${Math.round(v)} st`;
  if (unit === "¢") return `${v > 0 ? "+" : ""}${Math.round(v)}¢`;
  if (unit === "s") return `${(+v).toFixed(1)} s`;
  return (+v).toFixed(1);
};
const paramLabel = id => /^[bc]\d+$/.test(id) ? (+id.slice(1) >= 1000 ? `${+id.slice(1) / 1000}k` : id.slice(1)) : t(`rig.param.${id}`);
const ackHeadphones = () => { try { return localStorage.getItem(HP_KEY) === "1"; } catch { return false; } };

export async function mount(el) {
  root = el;
  await rig.load();
  el.innerHTML = `
    <div class="gl-head head-row"><div><h1>${esc(t("rig.title"))}</h1><p class="muted">${esc(t("rig.subtitle"))}</p></div></div>
    <div class="rig-bar panel" id="rigBar"></div>
    <div class="rig-hp callout" id="rigHp" hidden></div>
    <section class="rig-quick" id="rigQuick" aria-labelledby="quickTitle"></section>
    <div class="panel rig-source" id="rigSource"></div>
    <div class="panel rig-tools" id="rigTools"></div>
    <nav class="flow" id="rigFlow" aria-label="${esc(t("rig.flow"))}"></nav>
    <section class="rig-sec" id="sec-guitar"></section>
    <section class="rig-sec" id="sec-pedals"></section>
    <section class="rig-sec" id="sec-amp"></section>
    <section class="rig-sec" id="sec-cab"></section>
    <section class="rig-sec" id="sec-capture"></section>
    <section class="rig-sec" id="sec-post"></section>
    <section class="rig-sec" id="sec-looper"></section>
    <dialog class="rig-dialog" id="fxDialog"></dialog>
    <p class="muted small center">${esc(t("rig.clean_note"))}</p>`;
  renderAll();
  let toolsKey = "";
  onChange = () => {
    updateBar(); renderFlow();
    const k = JSON.stringify([rig.running, !!rig.tuning, !!rig.midiAccess, rig.midiLearning, rig.midiTargets().length]);
    if (k !== toolsKey) { toolsKey = k; renderTools(); }
  };
  onLoop = () => renderLooper();
  onRec = () => { const sec = root && $("#sec-looper", root); if (sec) renderRecorder(sec); };
  rig.addEventListener("change", onRec);
  rig.addEventListener("change", onChange);
  rig.addEventListener("looper", onLoop);
  onParam = e => { const k = knobsByTarget.get(e.detail.target); if (k && k.isConnected) k.setValue(e.detail.value); };
  onMidi = () => renderTools();
  rig.addEventListener("param", onParam);
  rig.addEventListener("midi", onMidi);
  const tick = () => { meters(); tunerTick(); raf = requestAnimationFrame(tick); };
  raf = requestAnimationFrame(tick);
}

export function unmount() {
  cancelAnimationFrame(raf);
  if (onChange) rig.removeEventListener("change", onChange);
  if (onLoop) rig.removeEventListener("looper", onLoop);
  if (onParam) rig.removeEventListener("param", onParam);
  if (onMidi) rig.removeEventListener("midi", onMidi);
  if (onRec) rig.removeEventListener("change", onRec);
  clearInterval(recTick);
  if (rig.tuning) rig.setTuning(false);
  knobsByTarget.clear();
  root = null;
}

function renderAll() {
  renderBar(); renderQuick(); renderSource(); renderTools(); renderFlow(); renderGuitar(); renderBoard("pedals"); renderAmp(); renderCab(); renderCapture(); renderBoard("post"); renderLooper();
}

// ------------------------------------------------------------------ quick sounds: the factory presets, one click each
const STYLE_KEY = "guitarr.rig.artistStyle";
let artistStyle = (() => { try { return localStorage.getItem(STYLE_KEY) || "all"; } catch { return "all"; } })();

/** Lowercase, no accents, no punctuation: "Keb' Mo'" matches "keb mo", "Andrés" matches "andres". */
const fold = x => String(x || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
let presetQuery = "";

/** What a card can be found by: its name, and for artist tones the player, bands, genres and style. */
function searchText(id, kind) {
  if (kind === "user") return fold(id);
  const parts = [t(`rig.preset.${id}`)];
  const info = ARTIST_INFO[id];
  if (info) {
    parts.push(info.artist, ...info.bands, ...info.genres.map(g => `${t(`rig.genre.${g}`)} ${g.replace(/_/g, " ")}`));
    if (ARTIST_STYLE[id]) parts.push(t(`rig.artist_style.${ARTIST_STYLE[id]}`));
  }
  return fold(parts.join(" "));
}

/** Edit distance (with swapped letters as one edit), stopping early past `max`. */
function editDistance(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev2 = [], prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) cur[j] = Math.min(cur[j], prev2[j - 2] + 1);
      best = Math.min(best, cur[j]);
    }
    if (best > max) return max + 1;
    prev2 = prev; prev = cur;
  }
  return prev[b.length];
}

/** A typo still finds it: "henrix" → Hendrix, "ricotta" → Ricota, "stever" → Stevie (short words must be exact). */
function closeTo(word, text) {
  if (word.length >= 4 && text.replace(/ /g, "").includes(word)) return true;     // "pinkfloyd", "acdc"
  const max = word.length >= 5 ? 2 : word.length === 4 ? 1 : 0;
  if (!max) return false;
  return text.split(" ").some(tok => tok.length >= 3 && (editDistance(word, tok, max) <= max
    || (tok.length > word.length && editDistance(word, tok.slice(0, word.length), max - 1 || 1) <= (max - 1 || 1))));
}

/** Shows the cards that match the search (and, with no search, the chosen artist style). */
function applySearch() {
  const box = $("#rigQuick", root);
  if (!box) return;
  const words = fold(presetQuery).split(" ").filter(Boolean);
  const cards = $$(".quick[data-q]", box);
  // matched as typed first; only when that finds nothing, close spellings count too
  const exact = q => words.every(w => q.includes(w));
  const loose = words.length && !cards.some(c => exact(c.dataset.q));
  const has = (q, w) => q.includes(w) || (loose && closeTo(w, q));
  let shown = 0;
  cards.forEach(c => {
    const byStyle = words.length || !c.dataset.style || artistStyle === "all" || c.dataset.style === artistStyle;
    const ok = byStyle && words.every(w => has(c.dataset.q, w));
    c.hidden = !ok;
    if (ok) shown++;
  });
  $$(".quick-group", box).forEach(g => { g.hidden = !!words.length && !$$(".quick[data-q]:not([hidden])", g).length; });
  const add = $("#mySave", box);
  if (add) add.hidden = !!words.length;
  const styles = $(".artist-styles", box);
  if (styles) styles.hidden = !!words.length;                 // a search looks through every style
  const none = $("#searchNone", box), count = $("#searchCount", box);
  none.hidden = !words.length || shown > 0;
  none.textContent = t("rig.search_none", { q: presetQuery.trim() });
  count.textContent = words.length ? t("rig.search_count", { count: shown }) + (loose && shown ? ` · ${t("rig.search_close")}` : "") : "";
}

function renderQuick() {
  const outer = $("#rigQuick", root);
  if (!outer) return;
  if (!$("#presetSearch", outer)) {
    outer.innerHTML = `<div class="rig-search"><label class="sr-only" for="presetSearch">${esc(t("rig.search_label"))}</label>
        <input type="search" id="presetSearch" placeholder="${esc(t("rig.search_placeholder"))}" autocomplete="off">
        <small class="muted" id="searchCount" aria-live="polite"></small></div>
      <p class="muted" id="searchNone" hidden></p><div id="quickBody"></div>`;
    const input = $("#presetSearch", outer);
    input.value = presetQuery;
    input.oninput = () => { presetQuery = input.value; applySearch(); };
  }
  const box = $("#quickBody", outer);
  const cur = rig.preset && rig.preset.kind === "factory" ? rig.preset.id : "";
  const card = id => {
    const s = factory(id), n = [...s.pedals, ...s.post].filter(e => e.on).length;
    return `<button class="quick${id === cur ? " on" : ""}" data-id="${id}" data-q="${esc(searchText(id))}"${ARTIST_STYLE[id] ? ` data-style="${ARTIST_STYLE[id]}"` : ""} aria-pressed="${id === cur}">${ampThumb(s.amp.type)}
        <b>${esc(t(`rig.preset.${id}`))}</b>
        <small>${esc(t(`rig.amp_${s.amp.type}`))} · ${esc(t("rig.quick_fx", { count: n }))}</small>
        ${id === cur ? `<span class="quick-on">✓ ${esc(t("rig.quick_active"))}</span>` : ""}</button>`;
  };
  const mineId = rig.preset && rig.preset.kind === "user" ? rig.preset.id : "";
  const fxCount = s => [...(s.pedals || []), ...(s.post || [])].filter(e => e.on).length;
  box.innerHTML = `<div class="quick-group"><h2 class="sub">${esc(t("rig.my_sounds"))}</h2>
    <div class="quick-row" id="mySounds">
      <button class="quick quick-add" id="mySave">${icon("plus", 22)}<b>${esc(t("rig.save_current"))}</b><small>${esc(t("rig.save_current_hint"))}</small></button>
      ${(rig.userPresets || []).map(p => {
        const on = p.id === mineId, amp = p.rig && p.rig.amp ? p.rig.amp.type : "";
        return `<button class="quick${on ? " on" : ""}" data-user="${esc(p.id)}" data-q="${esc(searchText(p.name, "user"))}" aria-pressed="${on}">${amp ? ampThumb(amp) : ""}
          <b>${esc(p.name)}</b>
          <small>${amp ? `${esc(t(`rig.amp_${amp}`))} · ` : ""}${esc(t("rig.quick_fx", { count: fxCount(p.rig || {}) }))}</small>
          ${on ? `<span class="quick-on">✓ ${esc(t("rig.quick_active"))}</span>` : ""}</button>`;
      }).join("")}
    </div></div>
    <div class="quick-group"><h2 id="quickTitle" class="sub">${esc(t("rig.quick_title"))}</h2>
    <div class="quick-row">${Object.keys(FACTORY).map(card).join("")}</div></div>
    <div class="quick-group"><h2 class="sub">${esc(t("rig.artists_title"))}</h2>
    <p class="muted small artists-hint">${esc(t("rig.artists_hint"))}</p>
    <div class="seg mini artist-styles" role="group" aria-label="${esc(t("rig.artist_filter"))}">${["all", ...ARTIST_STYLES].map(st =>
      `<button data-style="${st}" class="${st === artistStyle ? "active" : ""}" aria-pressed="${st === artistStyle}">${esc(t(`rig.artist_style.${st}`))}</button>`).join("")}</div>
    <div class="quick-row" id="artistSounds">${Object.keys(ARTISTS).map(card).join("")}</div></div>`;
  $$(".quick[data-id]", box).forEach(b => b.onclick = () => loadPreset(`factory:${b.dataset.id}`));
  $$(".artist-styles button", box).forEach(b => b.onclick = () => {
    artistStyle = b.dataset.style;
    try { localStorage.setItem(STYLE_KEY, artistStyle); } catch { /* ok */ }
    renderQuick();
  });
  applySearch();
  $$(".quick[data-user]", box).forEach(b => b.onclick = () => loadPreset(`user:${b.dataset.user}`));
  $("#mySave", box).onclick = savePreset;
}

// ------------------------------------------------------------------ top bar: power, presets, levels
function presetName() {
  const p = rig.preset;
  if (!p) return t("rig.custom");
  const name = p.kind === "factory" ? t(`rig.preset.${p.id}`) : p.name;
  return name + (p.edited ? " *" : "");
}

// Re-render the bar only when what it shows changes (re-rendering would cut a knob drag short).
const barKey = () => JSON.stringify([rig.running, rig.preset && [rig.preset.kind, rig.preset.id, rig.preset.name], (rig.userPresets || []).map(p => [p.id, p.name])]);
function updateBar() {
  const bar = $("#rigBar", root);
  if (!bar) return;
  if (bar.dataset.k !== barKey()) { renderBar(); renderQuick(); return; }
  const sel = $("#rigPreset", bar), opt = sel && sel.selectedOptions[0];     // only the "edited" mark changed
  if (opt) opt.textContent = opt.value ? opt.textContent.replace(/ \*$/, "") + (rig.preset && rig.preset.edited ? " *" : "") : presetName();
}

function renderBar() {
  const bar = $("#rigBar", root);
  if (!bar) return;
  bar.dataset.k = barKey();
  const on = rig.running;
  const user = rig.userPresets || [];
  const cur = rig.preset ? `${rig.preset.kind}:${rig.preset.id}` : "";
  bar.innerHTML = `
    <button class="power${on ? " on" : ""}" id="rigPower" aria-pressed="${on}"><span class="led"></span>${esc(t(on ? "rig.on" : "rig.off"))}</button>
    <div class="rig-preset">
      <label class="sr-only" for="rigPreset">${esc(t("rig.preset_label"))}</label>
      <select id="rigPreset">
        <option value="" ${cur ? "" : "selected"}>${esc(presetName())}</option>
        <optgroup label="${esc(t("rig.artists_title"))}">${Object.keys(ARTISTS).map(id => `<option value="factory:${id}" ${cur === "factory:" + id ? "selected" : ""}>${esc(t(`rig.preset.${id}`))}${cur === "factory:" + id && rig.preset.edited ? " *" : ""}</option>`).join("")}</optgroup>
        <optgroup label="${esc(t("rig.factory"))}">${Object.keys(FACTORY).map(id => `<option value="factory:${id}" ${cur === "factory:" + id ? "selected" : ""}>${esc(t(`rig.preset.${id}`))}${cur === "factory:" + id && rig.preset.edited ? " *" : ""}</option>`).join("")}</optgroup>
        ${user.length ? `<optgroup label="${esc(t("rig.mine"))}">${user.map(p => `<option value="user:${esc(p.id)}" ${cur === "user:" + p.id ? "selected" : ""}>${esc(p.name)}${cur === "user:" + p.id && rig.preset.edited ? " *" : ""}</option>`).join("")}</optgroup>` : ""}
      </select>
      <button class="btn small" id="rigSave">💾 ${esc(t("rig.save"))}</button>
      ${rig.preset && rig.preset.kind === "user" ? (confirmDelete
        ? `<span class="confirm-inline"><span class="small">${esc(t("rig.delete_confirm", { name: rig.preset.name }))}</span>
            <button class="btn small danger" id="rigDelYes">${esc(t("rig.yes"))}</button><button class="btn small" id="rigDelNo">${esc(t("rig.no"))}</button></span>`
        : `<button class="btn small ghost" id="rigDel" title="${esc(t("rig.delete_preset"))}" aria-label="${esc(t("rig.delete_preset"))}">✕</button>`) : ""}
    </div>
    <div class="rig-levels">
      <div class="mtr"><span>${esc(t("rig.in"))}</span><div class="lv" id="mIn"><div class="lv-fill"></div></div></div>
      <div class="mtr"><span>${esc(t("rig.out"))}</span><div class="lv" id="mOut"><div class="lv-fill"></div></div></div>
      <small class="muted" id="rigLat"></small>
    </div>
    <div class="rig-trims" id="rigTrims"></div>`;
  const trims = $("#rigTrims", bar);
  trims.append(
    knob({ label: t("rig.input_trim"), min: -24, max: 24, step: 0.5, value: rig.state.input.trim, def: 0, size: 44, format: v => fmt("dB", v), onInput: v => rig.setLevel("input", v) }),
    knob({ label: t("rig.level"), min: -24, max: 12, step: 0.5, value: rig.state.level || 0, def: 0, size: 44, format: v => fmt("dB", v), onInput: v => rig.setLevel("level", v) }),
    knob({ label: t("rig.volume"), min: -40, max: 6, step: 0.5, value: rig.state.master.volume, def: -12, size: 44, format: v => fmt("dB", v), onInput: v => rig.setLevel("master", v) }));
  knobsByTarget.set("master", trims.lastChild);
  $("#rigPower", bar).onclick = () => power();
  $("#rigPreset", bar).onchange = e => loadPreset(e.target.value);
  $("#rigSave", bar).onclick = savePreset;
  const del = $("#rigDel", bar);
  if (del) del.onclick = () => { confirmDelete = true; renderBar(); };
  const no = $("#rigDelNo", bar);
  if (no) no.onclick = () => { confirmDelete = false; renderBar(); };
  const yes = $("#rigDelYes", bar);
  if (yes) yes.onclick = deletePreset;
}

async function power() {
  if (rig.running) { await rig.stop(); return; }
  if (rig.source.kind === "input" && !ackHeadphones()) return askHeadphones();
  try {
    await rig.start();
    renderSource();
  } catch (e) {
    toast(e.name === "NotAllowedError" ? t("rig.mic_denied") : e.name === "NotFoundError" ? t("rig.no_input") : (e.message || t("errors.generic")));
  }
}

function askHeadphones() {
  const box = $("#rigHp", root);
  box.hidden = false;
  box.innerHTML = `<span>${icon("headphones", 20)} ${t("rig.headphones_html")}</span>
    <span class="row left"><button class="btn small" id="hpVirtual">${esc(t("rig.use_virtual"))}</button>
    <button class="btn primary small" id="hpOk">${esc(t("rig.headphones_ok"))}</button></span>`;
  $("#hpOk", box).onclick = () => { try { localStorage.setItem(HP_KEY, "1"); } catch { /* ok */ } box.hidden = true; power(); };
  $("#hpVirtual", box).onclick = async () => { box.hidden = true; await rig.setSource({ kind: "virtual" }); renderSource(); power(); };
}

function loadPreset(v) {
  if (!v) return;
  const [kind, id] = [v.slice(0, v.indexOf(":")), v.slice(v.indexOf(":") + 1)];
  if (kind === "factory") rig.loadState(factory(id), { kind, id });
  else {
    const p = (rig.userPresets || []).find(x => x.id === id);
    if (p) rig.loadState(p.rig, { kind, id, name: p.name });
  }
  renderAll();
}

function savePreset() {
  const dlg = $("#fxDialog", root);
  const suggested = rig.preset && rig.preset.kind === "user" ? rig.preset.name : "";
  dlg.innerHTML = `<form method="dialog" class="dlg-head"><h2>${esc(t("rig.save_title"))}</h2>
      <button class="btn small ghost" value="close" aria-label="${esc(t("rig.close"))}">✕</button></form>
    <form id="saveForm"><label class="field"><span>${esc(t("rig.preset_name"))}</span><input type="text" id="presetName" maxlength="60" required value="${esc(suggested)}" aria-describedby="presetErr"></label>
      <p class="field-err" id="presetErr" role="alert"></p>
      <p class="muted small">${esc(t("rig.save_hint"))}</p>
      <div class="setup-actions"><button class="btn primary" type="submit">${esc(t("rig.save"))}</button></div></form>`;
  $("#saveForm", dlg).onsubmit = async ev => {
    ev.preventDefault();
    const name = $("#presetName", dlg).value.trim();
    if (!name) return;
    try {
      const p = await api("/api/rig/presets", { json: { name, rig: rig.state } });
      rig.preset = { kind: "user", id: p.id, name: p.name };
      rig.save();
      dlg.close();
      await rig.refreshPresets();
      toast(t("rig.saved", { name: p.name }), true);
    } catch (e) { $("#presetErr", dlg).textContent = e.message; $("#presetName", dlg).focus(); }   // what you typed stays
  };
  dlg.showModal();
  $("#presetName", dlg).select();
}

async function deletePreset() {
  const p = rig.preset;
  confirmDelete = false;
  if (!p || p.kind !== "user") return renderBar();
  try {
    await api(`/api/rig/presets/${encodeURIComponent(p.id)}`, { method: "DELETE" });
    rig.preset = null;
    rig.save();
    await rig.refreshPresets();
  } catch (e) { toast(e.message); renderBar(); }
}

function meters() {
  if (!root) return;
  const lv = rig.levels();
  const put = (id, db) => {
    const m = $(id, root);
    if (!m) return;
    m.querySelector(".lv-fill").style.width = Math.max(0, Math.min(100, (db + 60) / 60 * 100)).toFixed(1) + "%";
    m.classList.toggle("hot", db > -3);
  };
  put("#mIn", lv.input);
  put("#mOut", lv.output);
  const lat = $("#rigLat", root);
  if (lat) lat.textContent = rig.running && rig.latencyMs() != null ? t("rig.latency", { ms: rig.latencyMs() }) : "";
}

// ------------------------------------------------------------------ source: your guitar or the virtual one
function renderSource() {
  const box = $("#rigSource", root);
  if (!box) return;
  const s = rig.source, virtual = s.kind === "virtual";
  const inputs = rig.inputs || [];
  box.innerHTML = `
    <div class="seg" id="srcKind">
      <button data-k="input" class="${virtual ? "" : "active"}">${icon("plug", 15)} ${esc(t("rig.src_input"))}</button>
      <button data-k="virtual" class="${virtual ? "active" : ""}">${icon("sparkle", 15)} ${esc(t("rig.src_virtual"))}</button>
    </div>
    ${virtual ? `
      <label class="field"><span>${esc(t("rig.voice"))}</span><select id="srcVoice">${Object.keys(VOICES).map(v => `<option value="${v}" ${v === s.voice ? "selected" : ""}>${esc(t(`rig.voice_${v}`))}</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("rig.riff"))}</span><select id="srcRiff">${Object.keys(RIFFS).map(r => `<option value="${r}" ${r === s.riff ? "selected" : ""}>${esc(t(`rig.riff_${r}`))}</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("rig.tempo"))}: <b id="srcBpmV">${s.bpm || RIFFS[s.riff].bpm}</b></span><input type="range" id="srcBpm" min="50" max="180" value="${s.bpm || RIFFS[s.riff].bpm}"></label>
      ${rig.running ? `<button class="btn small" id="srcPlay">${esc(t(rig.vg && rig.vg.playing ? "rig.pause" : "rig.play"))}</button>` : ""}`
    : `
      <label class="field"><span>${esc(t("rig.device"))}</span><select id="srcDev" ${inputs.length ? "" : "disabled"}>${inputs.length
        ? inputs.map(d => `<option value="${esc(d.deviceId)}" ${d.deviceId === s.deviceId ? "selected" : ""}>${esc(d.label || t("rig.unnamed"))}</option>`).join("")
        : `<option>${esc(s.label || t("rig.turn_on_to_list"))}</option>`}</select></label>
      ${rig.channels > 1 ? `<label class="field"><span>${esc(t("rig.channel"))}</span><select id="srcCh">${Array.from({ length: rig.channels }, (_, i) => `<option value="${i + 1}" ${i + 1 === s.channel ? "selected" : ""}>${esc(t("settings.channel_n", { n: i + 1 }))}</option>`).join("")}</select></label>` : ""}`}`;
  $$("#srcKind button", box).forEach(b => b.onclick = async () => {
    try { await rig.setSource({ kind: b.dataset.k }); } catch (e) { toast(e.message); }
    renderSource();
  });
  const on = (id, ev, fn) => { const n = $(id, box); if (n) n.addEventListener(ev, fn); };
  on("#srcVoice", "change", e => rig.setSource({ voice: e.target.value }));
  on("#srcRiff", "change", e => { rig.setSource({ riff: e.target.value, bpm: null }); renderSource(); });
  on("#srcBpm", "input", e => { $("#srcBpmV", box).textContent = e.target.value; rig.setSource({ bpm: +e.target.value }); });
  on("#srcPlay", "click", () => { rig.playVirtual(!(rig.vg && rig.vg.playing)); renderSource(); });
  on("#srcDev", "change", async e => {
    const d = inputs.find(x => x.deviceId === e.target.value);
    try { await rig.setSource({ deviceId: e.target.value, label: d ? d.label : "", channel: 1 }); } catch (err) { toast(err.message); }
    renderSource();
  });
  on("#srcCh", "change", e => rig.setSource({ channel: +e.target.value }));
}

// ------------------------------------------------------------------ tuner and expression pedal
function renderTools() {
  const box = $("#rigTools", root);
  if (!box) return;
  const m = rig.source.midi || {};
  const targets = rig.midiTargets();
  const label = tg => tg.type === "master" ? t("rig.volume") : `${t(`rig.fx_${tg.type}`)} · ${paramLabel(tg.param)}`;
  box.innerHTML = `
    <div class="tool-col">
      <h2>${esc(t("rig.tuner"))}</h2>
      <div class="row left wrap"><button class="btn small${rig.tuning ? " primary" : ""}" id="tuneBtn" ${rig.running ? "" : "disabled"} aria-pressed="${!!rig.tuning}">${esc(t(rig.tuning ? "rig.tuner_off" : "rig.tuner_on"))}</button>
        <span class="muted small">${esc(t(rig.running ? "rig.tuner_hint" : "rig.tuner_needs_on"))}</span></div>
      <div class="rig-tuner" id="rigTuner" ${rig.tuning ? "" : "hidden"}><b id="rtNote">—</b><div class="mt-scale"><i class="mt-mid"></i><i class="mt-needle" id="rtNeedle"></i></div><small class="muted" id="rtInfo"></small></div>
    </div>
    <div class="tool-col">
      <h2>${esc(t("rig.expression"))}</h2>
      ${rig.midiAccess ? `<div class="row left wrap">
          <button class="btn small${rig.midiLearning ? " primary" : ""}" id="midiLearn">${esc(rig.midiLearning ? t("rig.midi_move") : m.cc != null ? t("rig.midi_cc", { cc: m.cc }) : t("rig.midi_learn"))}</button>
          <label class="field-inline small">${esc(t("rig.midi_target"))}
            <select id="midiTarget"><option value="">—</option>${targets.map(tg => `<option value="${esc(tg.id)}" ${tg.id === m.target ? "selected" : ""}>${esc(label(tg))}</option>`).join("")}</select></label></div>
          <p class="muted small">${esc(t("rig.midi_devices", { names: [...rig.midiAccess.inputs.values()].map(i => i.name).join(", ") || "—" }))}</p>`
        : `<div class="row left wrap"><button class="btn small" id="midiConnect">${esc(t("rig.midi_connect"))}</button><span class="muted small">${esc(t("rig.midi_hint"))}</span></div>`}
    </div>`;
  const tb = $("#tuneBtn", box);
  if (tb) tb.onclick = () => { rig.setTuning(!rig.tuning); renderTools(); };
  const mc = $("#midiConnect", box);
  if (mc) mc.onclick = async () => {
    try { await rig.connectMidi(); renderTools(); }
    catch (e) { toast(e.message === "no_midi" ? t("rig.midi_unsupported") : t("rig.midi_denied")); }
  };
  const ml = $("#midiLearn", box);
  if (ml) ml.onclick = () => { rig.learnMidi(!rig.midiLearning); renderTools(); };
  const mt = $("#midiTarget", box);
  if (mt) mt.onchange = e => rig.setMidiTarget(e.target.value || null);
}

function tunerTick() {
  if (!rig.tuning) return;
  const p = rig.pitch(), note = $("#rtNote", root), needle = $("#rtNeedle", root), info = $("#rtInfo", root);
  if (!note) return;
  if (!p) { note.textContent = "—"; note.className = ""; needle.style.left = "50%"; info.textContent = t("tuner.play_open"); return; }
  const c = p.string ? p.stringCents : p.cents, ok = Math.abs(c) <= 5;
  note.textContent = p.note; note.className = ok ? "ok" : "";
  needle.style.left = (50 + Math.max(-50, Math.min(50, c))) + "%";
  needle.className = "mt-needle" + (ok ? " ok" : "");
  info.textContent = `${c > 0 ? "+" : ""}${c.toFixed(0)}¢ · ${p.freq.toFixed(1)} Hz` + (p.string ? ` · ${t("tuner.string_n", { n: p.string })}` : "");
}

// ------------------------------------------------------------------ signal flow strip
function renderFlow() {
  const f = $("#rigFlow", root);
  if (!f) return;
  const s = rig.state;
  const step = (id, label, active, extra = "") => `<a href="#" data-to="${id}" class="${active ? "on" : ""}">${esc(label)}${extra}</a>`;
  const n = list => list.filter(e => e.on).length;
  f.innerHTML = [
    step("sec-guitar", t("rig.sec_guitar"), s.guitar.type !== "as_is"),
    step("sec-pedals", t("rig.sec_pedals"), n(s.pedals) > 0, ` <small>${n(s.pedals)}</small>`),
    step("sec-amp", t(`rig.amp_${s.amp.type}`), s.amp.on),
    step("sec-cab", t(`rig.cab_${s.cab.type}`), s.cab.on),
    step("sec-post", t("rig.sec_post"), n(s.post) > 0, ` <small>${n(s.post)}</small>`),
    step("sec-looper", t("rig.sec_looper"), rig.looperState.state !== "empty"),
  ].join(`<span class="arrow">›</span>`);
  $$("a", f).forEach(a => a.onclick = e => { e.preventDefault(); $("#" + a.dataset.to, root).scrollIntoView({ behavior: "smooth", block: "start" }); });
}

// ------------------------------------------------------------------ guitar voicing
function renderGuitar() {
  const sec = $("#sec-guitar", root), g = rig.state.guitar;
  sec.innerHTML = `<div class="sec-head"><h2>${icon("charts")} ${esc(t("rig.sec_guitar"))}</h2><p class="muted small">${esc(t("rig.guitar_hint"))}</p></div>
    <div class="panel"><div class="pick-grid" id="gTypes">${Object.keys(GUITARS).map(id =>
      `<button class="pick${id === g.type ? " on" : ""}" data-id="${id}"><b>${esc(t(`rig.guitar_${id}`))}</b><small>${esc(t(`rig.guitar_${id}_desc`))}</small></button>`).join("")}</div>
      <div class="knobs" id="gKnobs"></div></div>`;
  $$("#gTypes .pick", sec).forEach(b => b.onclick = () => { rig.setGuitar({ type: b.dataset.id }); renderGuitar(); });
  if (g.type !== "as_is") {
    $("#gKnobs", sec).append(knob({ label: t("rig.pickup"), min: 0, max: 1, step: 0.01, value: g.pickup, def: 0.5,
      format: v => v < 0.34 ? t("rig.neck") : v > 0.66 ? t("rig.bridge") : t("rig.middle"), onInput: v => rig.setGuitar({ pickup: v }) }));
  }
}

// ------------------------------------------------------------------ pedalboard / effects loop
function renderBoard(where) {
  const sec = $(`#sec-${where}`, root), list = rig.state[where];
  sec.innerHTML = `<div class="sec-head"><h2>${icon(where === "pedals" ? "tools" : "sparkle")} ${esc(t(where === "pedals" ? "rig.sec_pedals" : "rig.sec_post"))}</h2>
      <p class="muted small">${esc(t(where === "pedals" ? "rig.pedals_hint" : "rig.post_hint"))}</p></div>
    <div class="board" data-where="${where}">
      <span class="jack" aria-hidden="true">${esc(t(where === "pedals" ? "rig.jack_guitar" : "rig.jack_amp"))}</span><span class="cable" aria-hidden="true"></span>
      ${list.map(e => `<div class="pedal-slot" data-uid="${esc(e.uid)}"></div><span class="cable" aria-hidden="true"></span>`).join("")}
      <span class="jack" aria-hidden="true">${esc(t(where === "pedals" ? "rig.jack_amp" : "rig.jack_out"))}</span>
      <button class="pedal add" data-add="${where}">${icon("sparkle", 22)}<b>${esc(t("rig.add_effect"))}</b></button></div>`;
  list.forEach(e => $(`.pedal-slot[data-uid="${e.uid}"]`, sec).replaceWith(pedal(e, where)));
  $(`[data-add=${where}]`, sec).onclick = () => openCatalog(where);
  const board = $(".board", sec);
  board.addEventListener("dragover", e => { e.preventDefault(); board.classList.add("drop"); });
  board.addEventListener("dragleave", () => board.classList.remove("drop"));
  board.addEventListener("drop", e => {
    e.preventDefault();
    board.classList.remove("drop");
    const id = e.dataTransfer.getData("text/x-pedal");
    if (!id) return;
    const target = e.target.closest(".pedal[data-uid]");
    let index = rig.state[where].length;
    if (target && target.dataset.uid !== id) index = rig.state[where].findIndex(x => x.uid === target.dataset.uid);
    const from = rig.find(id);
    if (from && from.where === where && from.i < index) index--;
    rig.moveEffect(id, where, index);
    renderBoard("pedals"); renderBoard("post");
  });
}

/** Dark or light print for a pedal's enclosure color (so labels stay readable on any finish). */
function inkFor(hex) {
  const n = parseInt(hex.slice(1), 16), [r, g, b] = [n >> 16, (n >> 8) & 255, n & 255].map(v => (v / 255) ** 2.2);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.25 ? "#16181d" : "#f4f1ea";
}

function pedal(e, where) {
  const def = EFFECTS[e.type], list = rig.state[where], i = list.indexOf(e);
  const el = document.createElement("div");
  el.className = "pedal stomp" + (e.on ? " on" : "");
  el.dataset.uid = e.uid;
  el.draggable = true;
  el.style.setProperty("--pc", def.color);
  el.style.setProperty("--ink", inkFor(def.color));
  el.innerHTML = `
    <div class="pedal-top">
      <span class="pedal-tools">
        <button class="ib" data-act="left" ${i === 0 ? "disabled" : ""} title="${esc(t("rig.move_left"))}" aria-label="${esc(t("rig.move_left"))}">‹</button>
        <button class="ib" data-act="right" ${i === list.length - 1 ? "disabled" : ""} title="${esc(t("rig.move_right"))}" aria-label="${esc(t("rig.move_right"))}">›</button>
        <button class="ib" data-act="swap" title="${esc(t(where === "pedals" ? "rig.to_post" : "rig.to_pedals"))}" aria-label="${esc(t(where === "pedals" ? "rig.to_post" : "rig.to_pedals"))}">⇄</button>
        <button class="ib" data-act="how" title="${esc(t("rig.how"))}" aria-label="${esc(t("rig.how"))}">ⓘ</button>
        <button class="ib" data-act="remove" title="${esc(t("rig.remove"))}" aria-label="${esc(t("rig.remove"))}">✕</button>
      </span>
      <span class="stomp-led"><span class="led"></span><small>${esc(t(e.on ? "rig.led_on" : "rig.led_off"))}</small></span></div>
    <div class="pedal-knobs"></div>
    <div class="pedal-choices"></div>
    <div class="stomp-plate"><b title="${esc(t(`rig.fx_${e.type}_desc`))}">${esc(t(`rig.fx_${e.type}`))}</b></div>
    <button class="footswitch" aria-pressed="${e.on}" title="${esc(t("rig.footswitch"))}" aria-label="${esc(t("rig.footswitch"))} · ${esc(t(`rig.fx_${e.type}`))}"></button>`;
  const knobs = $(".pedal-knobs", el), choices = $(".pedal-choices", el);
  for (const p of def.params) {
    if (p.type === "choice") {
      const seg = document.createElement("div");
      seg.className = "seg mini";
      seg.setAttribute("role", "group");
      seg.setAttribute("aria-label", paramLabel(p.id));
      seg.innerHTML = p.options.map(o => `<button data-o="${esc(o)}" class="${e.params[p.id] === o ? "active" : ""}">${esc(t(`rig.opt_${o}`))}</button>`).join("");
      $$("button", seg).forEach(b => b.onclick = () => {
        rig.setEffectParam(e.uid, p.id, b.dataset.o);
        $$("button", seg).forEach(x => x.classList.toggle("active", x === b));
      });
      choices.append(seg);
    } else {
      const k = knob({ label: paramLabel(p.id), min: p.min, max: p.max, step: p.step, value: e.params[p.id], def: p.def, size: 46, skin: "pedal",
        format: v => fmt(p.unit, v), onInput: v => rig.setEffectParam(e.uid, p.id, v) });
      knobsByTarget.set(`${e.uid}:${p.id}`, k);
      knobs.append(k);
    }
  }
  $(".footswitch", el).onclick = () => {
    rig.toggleEffect(e.uid);
    el.classList.toggle("on", e.on);
    $(".footswitch", el).setAttribute("aria-pressed", e.on);
    $(".stomp-led small", el).textContent = t(e.on ? "rig.led_on" : "rig.led_off");
  };
  $$(".ib", el).forEach(b => b.onclick = () => {
    if (b.dataset.act === "how") return openHow(e);
    const act = b.dataset.act, idx = rig.state[where].indexOf(e);
    if (act === "left") rig.moveEffect(e.uid, where, idx - 1);
    if (act === "right") rig.moveEffect(e.uid, where, idx + 1);
    if (act === "swap") { const other = where === "pedals" ? "post" : "pedals"; rig.moveEffect(e.uid, other, rig.state[other].length); }
    if (act === "remove") rig.removeEffect(e.uid);
    renderBoard("pedals"); renderBoard("post");
  });
  el.addEventListener("dragstart", ev => { ev.dataTransfer.setData("text/x-pedal", e.uid); ev.dataTransfer.effectAllowed = "move"; el.classList.add("dragging"); });
  el.addEventListener("dragend", () => el.classList.remove("dragging"));
  // dragging a knob must not drag the pedal
  $$(".knob", el).forEach(k => k.addEventListener("pointerdown", () => { el.draggable = false; }));
  el.addEventListener("pointerup", () => { el.draggable = true; });
  return el;
}

function openCatalog(where) {
  const dlg = $("#fxDialog", root);
  dlg.innerHTML = `<form method="dialog" class="dlg-head"><h2>${esc(t("rig.add_to", { where: t(where === "pedals" ? "rig.sec_pedals" : "rig.sec_post") }))}</h2>
      <button class="btn small ghost" value="close" aria-label="${esc(t("rig.close"))}">✕</button></form>
    ${EFFECT_GROUPS.map(g => `<h3>${esc(t(`rig.group_${g}`))}</h3><div class="pick-grid">${Object.entries(EFFECTS).filter(([, d]) => d.group === g).map(([id, d]) =>
      `<button class="pick fx" data-id="${id}" style="--pc:${d.color}"><b>${esc(t(`rig.fx_${id}`))}</b><small>${esc(t(`rig.fx_${id}_desc`))}</small></button>`).join("")}</div>`).join("")}`;
  $$(".pick", dlg).forEach(b => b.onclick = () => {
    rig.addEffect(where, makeEffect(b.dataset.id));
    dlg.close();
    renderBoard(where);
  });
  dlg.showModal();
}

// ------------------------------------------------------------------ amp
function renderAmp() {
  const sec = $("#sec-amp", root), a = rig.state.amp;
  sec.innerHTML = `<div class="sec-head"><h2>${icon("practice")} ${esc(t("rig.sec_amp"))}</h2>
      <label class="check"><input type="checkbox" id="ampOn" ${a.on ? "checked" : ""}> ${esc(t("rig.amp_on"))}</label></div>
    <div class="pick-row" id="ampTypes">${Object.keys(AMPS).map(id =>
      `<button class="pick amp-pick${id === a.type ? " on" : ""}" data-id="${id}" aria-pressed="${id === a.type}">${ampThumb(id)}
        <b>${esc(t(`rig.amp_${id}`))}</b><small>${esc(t(`rig.amp_${id}_desc`))}</small></button>`).join("")}</div>
    <div class="amp skin-${a.type}${a.on ? " on" : ""}">
      <div class="amp-handle" aria-hidden="true"></div>
      <div class="amp-front"><span class="amp-logo">${esc(t(`rig.amp_${a.type}`))}</span></div>
      <div class="amp-panel">
        <span class="amp-jewel" aria-hidden="true"></span><small class="amp-state">${esc(t(a.on ? "rig.led_on" : "rig.led_off"))}</small>
        <div class="knobs" id="ampKnobs"></div>
        <details class="stack-box"><summary class="small">${esc(t("rig.stack_title"))}</summary><p class="muted small">${esc(t("rig.stack_hint"))}</p><div id="stackCurve"></div></details>
      </div>
    </div>`;
  $$("#ampTypes .pick", sec).forEach(b => b.onclick = () => {
    if (b.dataset.id === a.type) return;
    rig.setAmp({ type: b.dataset.id, params: { ...defaultsOf(b.dataset.id) } });
    renderAmp(); renderFlow();
  });
  $("#ampOn", sec).onchange = e => { rig.setAmp({ on: e.target.checked }); renderAmp(); };
  const box = $("#ampKnobs", sec);
  for (const p of AMP_KNOBS) {
    box.append(knob({ label: t(`rig.amp_knob_${p.id}`), min: p.min, max: p.max, step: p.step, value: a.params[p.id], def: defaultsOf(a.type)[p.id], size: 58,
      skin: CHICKEN_AMPS.has(a.type) ? "chicken" : "pedal", format: v => (+v).toFixed(1), onInput: v => { rig.setAmpParam(p.id, v); drawStack(sec); } }));
  }
  drawStack(sec);
}
// amps whose panel uses pointer ("chicken-head") knobs; the rest use round caps
const CHICKEN_AMPS = new Set(["tweed", "chime", "crunch", "lead"]);
const ampThumb = id => `<span class="amp-thumb skin-${id}" aria-hidden="true"><i></i></span>`;
const defaultsOf = type => Object.fromEntries(AMP_KNOBS.map(p => [p.id, (AMPS[type].defaults || {})[p.id] ?? p.def]));

// ------------------------------------------------------------------ cabinet and microphone
async function renderCab() {
  const sec = $("#sec-cab", root), c = rig.state.cab, m = rig.state.mic;
  const irs = await rig.listIRs();
  if (!root) return;
  const usingIR = c.ir && irs.some(x => x.name === c.ir);
  sec.innerHTML = `<div class="sec-head"><h2>${icon("mic")} ${esc(t("rig.sec_cab"))}</h2>
      <label class="check"><input type="checkbox" id="cabOn" ${c.on ? "checked" : ""}> ${esc(t("rig.cab_on"))}</label></div>
    <div class="panel">
      <div class="pick-row" id="cabTypes">${Object.keys(CABS).map(id =>
        `<button class="pick${id === c.type && !usingIR ? " on" : ""}" data-id="${id}"><b>${esc(t(`rig.cab_${id}`))}</b><small>${esc(t(`rig.cab_${id}_desc`))}</small></button>`).join("")}</div>
      ${cabVisual(usingIR ? "ir" : c.type, c.on, usingIR ? c.ir : "")}
      <div class="cab-row">
        <div><h3>${esc(t("rig.mic"))}</h3>${usingIR ? `<p class="muted small">${esc(t("rig.ir_replaces_mic"))}</p>` : `<div class="seg mic-seg" id="micTypes">${Object.keys(MICS).map(id =>
          `<button data-id="${id}" class="${id === m.type ? "active" : ""}" title="${esc(t(`rig.mic_${id}_desc`))}">${esc(t(`rig.mic_${id}`))}</button>`).join("")}</div>`}
          <div class="knobs" id="micKnobs"></div></div>
        <div class="ir-box"><h3>${esc(t("rig.ir"))}</h3>
          <p class="muted small">${esc(usingIR ? t("rig.ir_loaded", { name: c.ir }) : t("rig.ir_hint"))}</p>
          ${irs.length ? `<ul class="ir-list">${irs.map(x => `<li class="${x.name === c.ir ? "on" : ""}">
              <button class="linkish" data-ir="${esc(x.name)}" aria-pressed="${x.name === c.ir}">${esc(x.name)}</button>
              <button class="ib" data-ir-del="${esc(x.name)}" title="${esc(t("rig.remove"))}" aria-label="${esc(t("rig.remove"))} ${esc(x.name)}">✕</button></li>`).join("")}</ul>` : ""}
          <div class="row left"><label class="btn small file-btn">${icon("upload", 14)} ${esc(t("rig.ir_load"))}<input type="file" id="irFile" accept=".wav,.flac,.aif,.aiff,audio/wav"></label>
          ${usingIR ? `<button class="btn small ghost" id="irClear">${esc(t("rig.ir_clear"))}</button>` : ""}</div></div>
      </div>
    </div>`;
  $$("#cabTypes .pick", sec).forEach(b => b.onclick = () => { rig.setCab({ type: b.dataset.id, ir: null }); renderCab(); renderFlow(); });
  $("#cabOn", sec).onchange = e => { rig.setCab({ on: e.target.checked }); renderFlow(); };
  $$("#micTypes button", sec).forEach(b => b.onclick = () => { rig.setMic({ type: b.dataset.id }); renderCab(); });
  if (!usingIR) {
    const box = $("#micKnobs", sec);
    const k = (id, def, f) => box.append(knob({ label: t(`rig.mic_${id}_knob`), min: 0, max: 1, step: 0.01, value: m[id], def, size: 48, format: f,
      onInput: v => { rig.setMic({ [id]: v }); placeMic(sec); } }));
    k("position", 0.3, v => v < 0.33 ? t("rig.center") : v > 0.66 ? t("rig.edge") : t("rig.off_axis"));
    k("distance", 0.2, v => `${Math.round(1 + v * 59)} cm`);
    k("room", 0.1, v => `${Math.round(v * 100)}%`);
  }
  $$("[data-ir]", sec).forEach(b => b.onclick = () => { rig.useIR(b.dataset.ir); renderCab(); });
  $$("[data-ir-del]", sec).forEach(b => b.onclick = async () => {
    try { await rig.deleteIR(b.dataset.irDel); renderCab(); } catch (e) { toast(e.message); }
  });
  $("#irFile", sec).onchange = async e => {
    const f = e.target.files[0];
    if (!f) return;
    try { const name = await rig.loadIR(f); renderCab(); toast(t("rig.ir_loaded", { name }), true); }
    catch (err) { toast(err.message); }
  };
  const clr = $("#irClear", sec);
  if (clr) clr.onclick = () => { rig.clearIR(); renderCab(); };
  placeMic(sec);
}

// speakers per cabinet: [count, size in inches]
const SPEAKERS = { c1x12_open: [1, 12], c2x12_open: [2, 12], c4x12_closed: [4, 12], c1x10: [1, 10], c2x10: [2, 10], c1x15: [1, 15], c4x10_bass: [4, 10] };

/** A drawn cabinet: grille cloth with its speakers, and the mic in front of the first one. */
function cabVisual(type, on, ir) {
  const [count, inch] = SPEAKERS[type] || [0, 0];
  const body = type === "direct" ? `<span class="cab-di">DI</span>`
    : type === "ir" ? `<span class="cab-di" title="${esc(ir)}">IR</span>`
    : `<div class="cab-grille n${count}" style="--sp:${inch}">${Array.from({ length: count }, (_, i) =>
        `<span class="speaker">${i === 0 ? `<span class="cab-mic"><i></i></span>` : ""}</span>`).join("")}</div>`;
  return `<div class="cab-visual${on ? "" : " off"}${count ? "" : " plain"}" aria-hidden="true">${body}</div>`;
}

/** Moves the drawn mic: position goes from the center to the edge of the cone, distance makes it smaller. */
function placeMic(sec) {
  const mic = $(".cab-mic", sec);
  if (!mic) return;
  const m = rig.state.mic;
  mic.style.setProperty("--x", `${(m.position * 42).toFixed(1)}%`);
  mic.style.setProperty("--s", (1.15 - m.distance * 0.6).toFixed(2));
}

// ------------------------------------------------------------------ recorder
let recTick = 0;
function renderRecorder(sec) {
  const box = $("#recBtns", sec);
  if (!box) return;
  const key = `${rig.running}|${!!rig.recording}|${!!rig.lastTake}`;
  if (box.dataset.k === key) return;
  box.dataset.k = key;
  clearInterval(recTick);
  if (rig.recording) {
    box.innerHTML = `<button class="btn lp-rec live" id="recStop">■ ${esc(t("rig.rec_stop"))}</button><span class="mono" id="recTime">0:00</span>`;
    recTick = setInterval(() => {
      const s = Math.floor(rig.recordingSeconds()), el = $("#recTime", sec);
      if (el) el.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }, 500);
    $("#recStop", box).onclick = () => { rig.stopRecording(); renderRecorder(sec); };
    return;
  }
  box.innerHTML = `<button class="btn lp-rec" id="recStart" ${rig.running ? "" : "disabled"}>● ${esc(t("rig.rec_start"))}</button>
    ${rig.lastTake ? `<a class="btn" id="recDl" download>${esc(t("rig.rec_download", { s: Math.round(rig.lastTakeSeconds) }))}</a>
      <button class="btn" id="recSave">${esc(t("rig.rec_save"))}</button>` : ""}`;
  $("#recStart", box).onclick = () => { rig.startRecording(); renderRecorder(sec); };
  const dl = $("#recDl", box);
  if (dl) {
    dl.href = URL.createObjectURL(rig.lastTake);
    dl.download = takeName();
  }
  const save = $("#recSave", box);
  if (save) save.onclick = async () => {
    const fd = new FormData();
    fd.append("file", new File([rig.lastTake], takeName(), { type: "audio/wav" }));
    try { const r = await api("/api/takes", { method: "POST", body: fd }); toast(t("rig.rec_saved", { name: r.name }), true); }
    catch (e) { toast(e.message); }
  };
}
const takeName = () => `rig-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.wav`;

// ------------------------------------------------------------------ looper
function renderLooper() {
  const sec = $("#sec-looper", root);
  if (!sec) return;
  const L = rig.looperState, st = L.state, running = rig.running;
  const pct = L.len ? (L.pos / L.len) * 100 : st === "recording" ? (L.pos / L.max) * 100 : 0;
  if (!sec.firstChild) {
    sec.innerHTML = `<div class="sec-head"><h2>${icon("history")} ${esc(t("rig.sec_looper"))}</h2><p class="muted small">${esc(t("rig.looper_hint"))}</p></div>
      <div class="panel looper"><div class="row left" id="lpBtns"></div><div class="lp-bar"><i id="lpPos"></i></div><b id="lpState"></b>
        <div class="rec-row"><h3>${esc(t("rig.rec_title"))}</h3><div class="row left wrap" id="recBtns"></div><p class="muted small">${esc(t("rig.rec_hint"))}</p></div></div>`;
  }
  const btns = $("#lpBtns", sec);
  const want = `${st}|${running}`;
  if (btns.dataset.k !== want) {
    btns.dataset.k = want;
    const recLabel = st === "empty" ? "rig.lp_rec" : st === "recording" ? "rig.lp_close" : st === "overdubbing" ? "rig.lp_stop_dub" : "rig.lp_dub";
    btns.innerHTML = `
      <button class="btn lp-rec${st === "recording" || st === "overdubbing" ? " live" : ""}" data-c="rec" ${running ? "" : "disabled"}>● ${esc(t(recLabel))}</button>
      <button class="btn" data-c="play" ${running && (st === "stopped" || st === "recording" || st === "overdubbing") ? "" : "disabled"}>▶ ${esc(t("rig.lp_play"))}</button>
      <button class="btn" data-c="stop" ${running && st !== "empty" && st !== "stopped" ? "" : "disabled"}>■ ${esc(t("rig.lp_stop"))}</button>
      <button class="btn ghost" data-c="clear" ${st !== "empty" ? "" : "disabled"}>${esc(t("rig.lp_clear"))}</button>`;
    $$("button", btns).forEach(b => b.onclick = () => rig.loop(b.dataset.c));
  }
  renderRecorder(sec);
  $("#lpPos", sec).style.width = pct.toFixed(1) + "%";
  $("#lpPos", sec).className = st;
  $("#lpState", sec).textContent = !running ? t("rig.lp_off") : t(`rig.lp_${st}`, { len: L.len.toFixed(1), pos: L.pos.toFixed(1) });
}

// ------------------------------------------------------------------ how it works, clipping and the tone stack
function openHow(e) {
  const dlg = $("#fxDialog", root), name = t(`rig.fx_${e.type}`);
  dlg.innerHTML = `<form method="dialog" class="dlg-head"><h2>${esc(t("rig.how_title", { name }))}</h2>
      <button class="btn small ghost" value="close" aria-label="${esc(t("rig.close"))}">✕</button></form>
    <p>${esc(t(`rig.how_${e.type}`))}</p>
    ${isDrive(e.type) ? `<h3>${esc(t("rig.clip_title"))}</h3><div class="clip-box">${clipPlot(e.type, e.params)}</div>
      <h3>${esc(t("rig.clip_compare"))}</h3><div class="cp-row">${comparePlots()}</div>` : ""}`;
  dlg.showModal();
}

function drawStack(sec) {
  const box = $("#stackCurve", sec);
  if (box) box.innerHTML = stackCurve(rig.state.amp.type, rig.state.amp.params);
}

// ------------------------------------------------------------------ capture your amp (experimental)
function renderCapture() {
  const sec = $("#sec-capture", root);
  if (!sec) return;
  sec.innerHTML = `<div class="sec-head"><h2>${icon("mic")} ${esc(t("rig.capture_title"))}</h2><p class="muted small">${esc(t("rig.capture_hint"))}</p></div>
    <form class="panel row wrap" id="capForm">
      <label class="field"><span>${esc(t("rig.capture_di"))}</span><input type="file" id="capDi" accept="audio/*,.wav,.flac,.ogg"></label>
      <label class="field"><span>${esc(t("rig.capture_amp"))}</span><input type="file" id="capAmp" accept="audio/*,.wav,.flac,.ogg"></label>
      <button class="btn primary" type="submit">${esc(t("rig.capture_go"))}</button>
      <p class="field-error" id="capErr" hidden></p>
      <div id="capOut"></div>
    </form>`;
  $("#capForm", sec).onsubmit = async ev => {
    ev.preventDefault();
    const err = $("#capErr", sec), out = $("#capOut", sec), di = $("#capDi", sec).files[0], amp = $("#capAmp", sec).files[0];
    err.hidden = true;
    if (!di || !amp) { err.textContent = t("rig.capture_need_both"); err.hidden = false; return; }
    const fd = new FormData();
    fd.append("di", di); fd.append("amp", amp);
    try {
      const r = await api("/api/rig/capture", { method: "POST", body: fd });
      out.innerHTML = `<p class="ex-msg ok">${esc(t("rig.capture_done", { drive: r.params.drive, match: r.match }))}</p>
        <p class="small muted">${Object.entries(r.bands).map(([f, g]) => `${+f >= 1000 ? f / 1000 + "k" : f}: ${g > 0 ? "+" : ""}${g} dB`).join(" · ")}</p>
        <button class="btn" type="button" id="capAdd">${esc(t("rig.capture_add"))}</button>`;
      $("#capAdd", sec).onclick = () => { rig.addEffect("pedals", makeEffect("capture", r.params)); renderBoard("pedals"); toast(t("rig.fx_capture"), true); };
    } catch (e) { err.textContent = e.message; err.hidden = false; }
  };
}
