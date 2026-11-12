/* guitarr — listening views: practice, analyze, tuner, history and settings.
   Dependency-free ES module: vanilla JS + canvas + SVG. The router (main.js) calls
   showListenerView / hideListenerViews. All user-facing text goes through i18n. */
import { issueText, msgIsError, msgText, t, tc } from "./lib/i18n.js";
import { $, $$, api, esc, instrument, loadInstrument, noteName, NOTE_NAMES, progressChanged, stringRow, toast } from "./lib/ui.js";
import { levelVerdict, meterHtml, openInput, setGate, setMeter } from "./lib/input.js";
import { bindTakePlayers, grooveHtml, takePlayer, timingVerdictHtml } from "./lib/take.js";

// Reads a color token and normalizes it to #rrggbb (accepts hsl/rgb) so a hex alpha can be appended.
const _cc = document.createElement("canvas").getContext("2d");
const css = v => {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  if (!raw) return raw;
  _cc.fillStyle = "#000"; _cc.fillStyle = raw;
  return _cc.fillStyle;
};
const alpha = (c, a) => /^#[0-9a-f]{6}$/i.test(c) ? c + a : c;
const fmtPct = v => v == null ? "—" : `${Math.round(v)}%`;
const signed = v => `${v > 0 ? "+" : ""}${Math.round(v)}`;

const STATUS_COLOR = () => ({
  pending: css("--muted"), ok: css("--gl-ok"), octave: css("--gl-octave"), fixed: css("--gl-ok"),
  wrong: css("--gl-err"), missed: css("--gl-err"), timing: css("--gl-warn"), extra: css("--gl-info"),
  missing: css("--gl-err"), masked: css("--muted"), outside: css("--border"),
});
const ICON = { wrong: "✗", missed: "∅", missing: "∅", fixed: "↻", timing: "⏱", extra: "+", octave: "↕", ok: "✓" };

// ------------------------------------------------------------------ navigation (driven by main.js)
const VIEWS = ["practice", "analyze", "tuner", "history", "settings"];
export const LISTENER_ROUTES = VIEWS;

export function hideListenerViews() {
  $$(".gl-view").forEach(v => (v.hidden = true));
  stopTuner();
  stopTest();
}

export function showListenerView(view, params = {}) {
  $$(".gl-view").forEach(v => (v.hidden = v.id !== "view-" + view));
  if (view === "history") loadHistory();
  if (view === "settings") loadSettings();
  if (view === "analyze") loadTakes();
  if (view !== "tuner") stopTuner();
  if (view !== "settings") stopTest();
  if (view === "practice" && params.chart && !params.from) useChart(params.chart);
  if (view === "practice" && params.demo) loadDemo();
  if (view === "practice" && params.from && (params.song || params.chart)) {     // deep link to some bars
    practiceBars(params.chart ? `chart:${params.chart}` : params.song, +params.from, +(params.to || params.from));
    history.replaceState(null, "", "#/practice");
  }
  requestAnimationFrame(() => drawTab());
}

function show(view) {
  const h = "#/" + view;
  if (location.hash !== h) location.hash = h;
}

// ------------------------------------------------------------------ songs (shared)
const App = { songs: [], takes: [], preview: null, lane: null, snap: null, k: 0, kSmooth: 0, live: false, mode: "wait" };

async function loadSongs(select) {
  App.songs = await api("/api/songs");
  for (const sel of $$(".songSelect")) {
    const cur = select || sel.value;
    sel.innerHTML = App.songs.length
      ? App.songs.map(s => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join("")
      : `<option value="">${esc(t("practice.no_songs_option"))}</option>`;
    if (cur && App.songs.some(s => s.name === cur)) sel.value = cur;
  }
  showEmptyPractice();
}

function showEmptyPractice() {
  const empty = !App.songs.length && !App.chart;
  $("#pEmpty").hidden = !empty;
  $("#pStage").classList.toggle("is-empty", empty);
  if (empty) $("#nowWhere").textContent = t("practice.upload_or_demo");
}

let demoLoading = false;
async function loadDemo() {
  if (demoLoading || App.live) return;
  demoLoading = true;
  history.replaceState(null, "", "#/practice");
  try {
    const r = await api("/api/demo", { method: "POST" });
    App.chart = null;
    laneHint();
    $("#pChartBanner").hidden = true;
    $("#pBackingWrap").hidden = true;
    $("#pSongField").hidden = false;
    await loadSongs(r.song);
    await loadTakes();
    $("#pSimulate").value = r.take;
    await onSongChange("p");
    $("#log").innerHTML = `<li class="info">${esc(t("practice.demo_ready"))}</li>`;
    toast(t("practice.demo_loaded"), true);
  } catch (e) { toast(e.message); }
  finally { demoLoading = false; }
}
$("#demoBtn").addEventListener("click", loadDemo);

for (const up of $$(".songUpload")) {
  up.addEventListener("change", async () => {
    const f = up.files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await api("/api/songs", { method: "POST", body: fd });
      await loadSongs(r.name);
      await onSongChange("p");
      await onSongChange("a");
      toast(t("practice.uploaded", { name: r.name }), true);
    } catch (e) { toast(e.message); }
    up.value = "";
  });
}

async function loadTracks(prefix) {
  const song = $(`#${prefix}Song`).value;
  const wrap = $(`#${prefix}TrackWrap`), sel = $(`#${prefix}Track`);
  sel.innerHTML = "";
  wrap.hidden = true;
  if (!song) return;
  try {
    const tracks = await api(`/api/songs/${encodeURIComponent(song)}/tracks`);
    if (tracks.length > 1) {
      sel.innerHTML = tracks.map(tr => `<option value="${tr.index}">${tr.index}. ${esc(tr.name)} — ${esc(tr.kind)} (${tr.notes})</option>`).join("");
      const g = tracks.find(tr => /guitar|strings/i.test(tr.kind));
      if (g) sel.value = g.index;
      wrap.hidden = false;
    }
  } catch (e) { toast(e.message); }
}

function applyPreset(prefix) {
  const s = App.songs.find(x => x.name === $(`#${prefix}Song`).value);
  const p = (s && s.preset) || {};
  if (p.track != null && $(`#${prefix}Track`).querySelector(`option[value="${p.track}"]`)) $(`#${prefix}Track`).value = p.track;
  $(`#${prefix}Start`).value = p.start_bar ?? "";
  $(`#${prefix}End`).value = p.end_bar ?? "";
  $(`#${prefix}Transpose`).value = p.transpose ?? 0;
  if (prefix === "p") {
    if (p.mode) setMode(p.mode);
    if (p.speed) { $("#pSpeed").value = Math.round(p.speed * 100); $("#pSpeed").dispatchEvent(new Event("input")); }
  }
}

async function onSongChange(prefix) {
  await loadTracks(prefix);
  applyPreset(prefix);
  if (prefix === "p") loadPreview();
}

// ------------------------------------------------------------------ charts
async function useChart(id) {
  try {
    const { chart } = await api(`/api/charts/${encodeURIComponent(id)}`);
    const info = { ...chart, bars: chart.bars.length };
    App.chart = info;
    showEmptyPractice();
    $("#pBackingWrap").hidden = false;
    $("#pChartBanner").hidden = false;
    $("#pSongField").hidden = true;
    $("#pTrackWrap").hidden = true;
    $("#pChartTitle").textContent = tc(`charts.${info.id}.title`, info.title);
    $("#pChartInfo").textContent = [info.artist, `♩=${info.bpm}`, info.capo ? t("charts.capo", { n: info.capo }) : "",
      t("charts.n_chords", { count: info.bars }), info.missing.length ? t("charts.no_fingering", { chords: info.missing.join(", ") }) : ""]
      .filter(Boolean).join(" · ");
    setMode("tempo");
    $("#pLoop").checked = false;
    $("#pStart").value = ""; $("#pEnd").value = "";
    $("#pTranspose").value = 0;
    const note = info.note ? tc(`charts.${info.id}.note`, info.note) : t("practice.chart_hint");
    $("#log").innerHTML = `<li class="muted">${esc(note)}</li>`;
    loadPreview();
  } catch (e) { toast(e.message); }
}
$("#pChartClear").addEventListener("click", () => {
  App.chart = null;
  laneHint();
  $("#pChartBanner").hidden = true;
  $("#pBackingWrap").hidden = true;
  $("#pSongField").hidden = false;
  history.replaceState(null, "", "#/practice");
  if (App.songs.length) onSongChange("p");
  else { App.lane = null; drawTab(); }
  showEmptyPractice();
});

function refBody(prefix) {
  if (prefix === "p" && App.chart) {
    return { chart: App.chart.id, start_bar: $("#pStart").value || null, end_bar: $("#pEnd").value || null,
             transpose: $("#pTranspose").value || 0 };
  }
  const tw = $(`#${prefix}TrackWrap`);
  return {
    song: $(`#${prefix}Song`).value,
    track: tw.hidden ? null : $(`#${prefix}Track`).value,
    start_bar: $(`#${prefix}Start`).value || null,
    end_bar: $(`#${prefix}End`).value || null,
    transpose: $(`#${prefix}Transpose`).value || 0,
  };
}

$("#pSong").addEventListener("change", () => onSongChange("p"));
// the song page: what the file says, progress per section, videos (not for the built-in charts)
const songPageLink = () => { const a = $("#pSongPage"), v = $("#pSong").value; if (a) { a.hidden = !v; a.href = `#/song/${encodeURIComponent(v)}`; } };
$("#pSong").addEventListener("change", songPageLink);
setInterval(songPageLink, 1000);
$("#aSong").addEventListener("change", () => onSongChange("a"));
$("#pTrack").addEventListener("change", loadPreview);
$("#pStart").addEventListener("change", loadPreview);
$("#pEnd").addEventListener("change", loadPreview);

// ------------------------------------------------------------------ preview (static tab)
function groupEvents(notes) {
  const evs = [];
  for (const n of notes) {
    const last = evs[evs.length - 1];
    if (last && n.s - last.time <= 0.035) {
      if (!last.pitches.includes(n.p)) { last.pitches.push(n.p); last.tab.push([n.string, n.fret]); }
    } else evs.push({ time: n.s, pitches: [n.p], tab: [[n.string, n.fret]], status: "pending", name: n.label });
  }
  return evs.map((e, i) => ({ ...e, i, label: e.name || [...e.pitches].sort((a, b) => a - b).map(noteName).join("+") }));
}

async function loadPreview() {
  if (App.live) return;
  const body = refBody("p");
  if (!body.song && !body.chart) return;
  try {
    const pv = await api("/api/preview", { json: body });
    App.preview = pv;
    App.lane = groupEvents(pv.notes);
    App.k = App.kSmooth = 0;
    App.snap = null;
    laneHint();
    $("#nowNote").firstChild.textContent = App.lane.length ? App.lane[0].label : "—";
    const name = App.chart ? $("#pChartTitle").textContent : pv.name;
    $("#nowWhere").textContent = [name + (pv.track ? " · " + pv.track : ""),
      t("practice.bars_range", { from: pv.first_bar, to: pv.last_bar }),
      t(App.chart ? "practice.n_chords" : "practice.n_notes", { count: App.lane.length }), `♩=${pv.bpm}`].join(" · ");
    drawTab();
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ mode / options
function setMode(m) {
  App.mode = m;
  $$("#pMode button").forEach(b => b.classList.toggle("active", b.dataset.mode === m));
  $("#tempoOpts").hidden = m !== "tempo";
  laneHint();
}
$$("#pMode button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode)));
$("#pSpeed").addEventListener("input", () => ($("#pSpeedVal").textContent = $("#pSpeed").value + "%"));
$("#pTrainer").addEventListener("change", () => {
  $("#trainerOpts").hidden = !$("#pTrainer").checked;
  if ($("#pTrainer").checked) $("#pLoop").checked = true;
});
$("#pSavePreset").addEventListener("click", async () => {
  const b = refBody("p");
  if (b.chart) return toast(t("practice.presets_files_only"));
  try {
    await api("/api/presets", { json: { ...b, mode: App.mode, speed: $("#pSpeed").value / 100 } });
    await loadSongs();
    toast(t("practice.preset_saved", { song: b.song }), true);
  } catch (e) { toast(e.message); }
});

// ------------------------------------------------------------------ live practice
let ws;
function connectLive() {
  if (ws && ws.readyState <= 1) return;
  ws = new WebSocket(`ws://${location.host}/ws/live`);
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === "state") onState(m.state);
    else if (m.type === "report") onReport(m.report);
    else if (m.type === "error") { toast(m.error); setLive(false); }
  };
  ws.onclose = () => { if (App.live) setTimeout(connectLive, 500); };
}

function setLive(on) {
  App.live = on;
  const b = $("#pStartBtn");
  b.textContent = on ? t("practice.stop") : t("practice.start");
  b.className = "btn big " + (on ? "danger" : "primary");
  $$("#practiceForm input, #practiceForm select, #practiceForm .seg button").forEach(el => (el.disabled = on));
  $("#devicePill").classList.toggle("live", on);
}

$("#pStartBtn").addEventListener("click", async () => {
  if (App.live) {
    try { const r = await api("/api/live/stop", { method: "POST" }); if (r.report) onReport(r.report); } catch (e) { toast(e.message); }
    setLive(false);
    return;
  }
  const body = {
    ...refBody("p"), mode: App.mode, speed: $("#pSpeed").value / 100, click: $("#pClick").checked,
    loop: $("#pLoop").checked, trainer: $("#pTrainer").checked, speed_step: $("#pStep").value,
    target: $("#pTarget").value, max_speed: $("#pMax").value, legato: $("#pLegato").checked,
    simulate: $("#pSimulate").value || null, backing: !!App.chart && $("#pBacking").checked && $("#pClick").checked,
  };
  if (!body.song && !body.chart) return toast(t("practice.pick_song_first"));
  try {
    $("#liveReport").hidden = true;
    $("#log").innerHTML = "";
    connectLive();
    await api("/api/live/start", { json: body });
    setLive(true);
  } catch (e) { toast(e.message); setLive(false); }
});

// Space toggles practice, Esc stops it (ignored while typing in a field).
document.addEventListener("keydown", e => {
  if ($("#view-practice").hidden || e.metaKey || e.ctrlKey || e.altKey) return;
  const tag = (e.target.tagName || "").toLowerCase();
  if (["input", "select", "textarea", "button"].includes(tag) || e.target.isContentEditable) return;
  if (e.code === "Space") { e.preventDefault(); $("#pStartBtn").click(); }
  else if (e.key === "Escape" && App.live) { e.preventDefault(); $("#pStartBtn").click(); }
});

function msgClass(m) {
  if (!m) return "";
  if (msgIsError(m)) return "err";
  if (m.code === "pass") return "info";
  return "ok";
}

function onState(s) {
  App.snap = s;
  if (!s.running) { if (s.done && App.live) setLive(false); return; }
  App.lane = s.lane;
  App.k = s.k;
  const cur = s.lane.find(e => e.current) || s.lane[s.lane.length - 1];
  $("#nowNote").firstChild.textContent = cur ? cur.label : "✓";
  $("#nowWhere").textContent = t("practice.position", { bar: s.bar, beat: s.beat.toFixed(2), k: Math.min(s.k + 1, s.total), total: s.total });
  const lm = $("#lastMsg");
  lm.textContent = s.last ? msgText(s.last) : (s.mode === "tempo" ? "" : t("practice.play_first"));
  lm.className = "lastmsg " + msgClass(s.last);
  const st = s.stats;
  const chips = [];
  if (st.pct != null) chips.push(t("practice.chip_hits", { pct: st.pct }));
  chips.push(t("practice.chip_mistakes", { n: st.errors }));
  if (st.extras) chips.push(t("practice.chip_extra", { n: st.extras }));
  $("#chips").innerHTML = chips.map(c => `<span class="chip">${esc(c)}</span>`).join("") +
    `<span class="chip"><span class="mono">${esc(s.source)}</span></span>`;
  $("#speedBadge").hidden = s.mode !== "tempo";
  $("#speedVal").textContent = Math.round(s.speed * 100) + "%";
  $("#countdown").hidden = !s.countdown;
  $("#countdown").textContent = s.countdown || "";
  $("#overlayMsg").hidden = !s.waiting_first;
  $("#overlayMsg").textContent = t("practice.waiting_first");
  const lv = Math.max(0, Math.min(1, (s.level_db + 60) / 60));
  $("#levelMeter > div").style.width = (lv * 100).toFixed(1) + "%";
  $("#levelMeter").classList.toggle("clip", s.peak >= 0.9);
  const lt = $("#levelTxt");
  lt.textContent = s.clip ? t("practice.clipping") : `${Math.round(s.level_db)} dB`;
  lt.className = s.clip ? "err" : (s.level_db < s.gate_db && s.now > 1 ? "warn" : "");
  if (s.tuning != null) {
    $("#tuneTxt").textContent = `${signed(s.tuning)} cents` + (Math.abs(s.tuning) > 15 ? ` — ${t("practice.tune_up")}` : "");
    $("#tuneTxt").className = Math.abs(s.tuning) > 15 ? "warn" : "";
    const tb = $("#tuneBar");
    const x = Math.max(-50, Math.min(50, s.tuning));
    tb.style.marginLeft = (50 + Math.min(0, x)) + "%";
    tb.style.width = Math.max(1, Math.abs(x)) + "%";
  }
  if (s.log.length) {
    $("#log").innerHTML = [...s.log].reverse().map(([tm, m]) =>
      `<li class="${msgClass(m)}"><span class="t">${tm.toFixed(2)}s</span><span>${esc(msgText(m))}</span></li>`).join("");
  }
  renderPasses(s.passes);
}

function renderPasses(passes) {
  $("#passesPanel").hidden = !passes.length;
  $("#passes").innerHTML = passes.slice(-24).map((p, i) => {
    const cls = p.score >= 90 ? "" : p.score >= 65 ? "mid" : "low";
    const sp = p.speed ? `${Math.round(p.speed * 100)}%` : `#${i + 1}`;
    return `<div class="bar ${cls}" style="height:${Math.max(4, p.score * 0.7)}px" title="${p.score}%${p.speed ? " @ " + sp : ""}"><span>${sp}</span></div>`;
  }).join("");
}

function onReport(r) {
  setLive(false);
  if (r && r.award && App.rewarded !== r.date) {
    App.rewarded = r.date;
    if (r.award.xp) toast(t("practice.xp_practice", { xp: r.award.xp }), true);
    progressChanged();
  }
  const el = $("#liveReport");
  el.hidden = false;
  el.innerHTML = renderReport(r);
  bindReport(el, r);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ------------------------------------------------------------------ tab drawing
const cv = $("#tabCanvas");

/** Charts: where each column sits in its bar, so "Em | Em" reads as two bars of 4 beats, not two loose chords.
 *  → Map(event index → { bar, first (starts the bar), from (beat it starts on), n (beats it lasts), start (beats from
 *  the start of the section) }), or null for songs. */
function chartBeats(lane) {
  const pv = App.preview;
  if (!App.chart || !pv || !pv.downbeats || !pv.bpm || !lane) return null;
  const db = pv.downbeats, beat = 60 / pv.bpm, out = new Map();
  lane.forEach((e, j) => {
    let b = 0;
    while (b + 1 < db.length && db[b + 1] <= e.time + 0.02) b++;
    const barEnd = db[b + 1] ?? e.time + (App.chart.beats_per_bar || 4) * beat;
    const nxt = lane[j + 1] && lane[j + 1].time < barEnd - 0.02 ? lane[j + 1].time : barEnd;
    out.set(e.i, { bar: pv.first_bar + b, first: Math.abs(e.time - db[b]) < 0.02, from: Math.round((e.time - db[b]) / beat),
                   n: Math.max(1, Math.round((nxt - e.time) / beat)), start: Math.round((e.time - db[0]) / beat) });
  });
  return out;
}

/** The chart's strum pattern as arrows, one group per beat: "D.DU.UDU" → "↓ ↓↑ ·↑ ↓↑". */
function strumArrows(pattern) {
  const sym = c => c === "D" ? "↓" : c === "U" ? "↑" : c === "_" ? "–" : "·";
  const slots = (pattern || "").replace(/[^DU._^]/g, "").replace(/\^/g, "");
  const out = [];
  for (let i = 0; i < slots.length; i += 2) out.push(sym(slots[i]) + (slots[i + 1] && slots[i + 1] !== "." ? sym(slots[i + 1]) : ""));
  return out.join(" ");
}

/** Under the tab, for charts: what a column is and what each mode expects from you. */
function laneHint() {
  const el = $("#laneHint");
  if (!el) return;
  el.hidden = !App.chart;
  if (!App.chart) return;
  const n = App.chart.beats_per_bar || 4, strum = strumArrows(App.chart.strum) || Array(n).fill("↓").join(" ");
  el.textContent = t(App.mode === "tempo" ? "practice.chart_hint_tempo" : "practice.chart_hint_wait", { n, strum });
}
function drawTab() {
  const lane = App.lane;
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  if (!W) return;
  if (cv.width !== W * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);
  const tun = (App.preview && App.preview.tuning) || instrument.strings;
  const strings = tun.length, top = 46, gap = strings > 6 ? 22 : 26;
  const colors = STATUS_COLOR();
  g.strokeStyle = css("--gl-string");
  g.lineWidth = 1;
  g.font = "600 11px ui-monospace, Menlo, monospace";
  g.fillStyle = css("--muted");
  for (let s = 0; s < strings; s++) {
    const y = top + stringRow(s + 1, strings) * gap;
    g.beginPath(); g.moveTo(34, y); g.lineTo(W - 8, y); g.stroke();
    g.fillText(NOTE_NAMES[tun[s] % 12] || "", 10, y + 4);
  }
  describeTab(lane);
  if (!lane || !lane.length) {
    g.fillStyle = css("--muted");
    g.font = "14px system-ui";
    g.textAlign = "center";
    g.fillText(t("practice.tab_placeholder"), W / 2, top + 2.5 * gap + 5);
    g.textAlign = "left";
    return;
  }
  const beats = chartBeats(lane);
  const spacing = beats ? Math.max(72, Math.min(110, W / 9)) : Math.max(46, Math.min(80, W / 14));   // a bar needs room for its beats
  const nowBeat = App.snap && App.snap.running && App.snap.mode === "tempo" && App.snap.pos != null ? Math.floor(App.snap.pos) : null;
  const cx = Math.min(W * 0.28, 260);
  g.fillStyle = alpha(css("--gl-accent"), "22");
  g.fillRect(cx - spacing / 2 + 4, top - 30, spacing - 8, (strings - 1) * gap + 52);
  g.textAlign = "center";
  for (const e of lane) {
    const x = cx + (e.i - App.kSmooth) * spacing;
    if (x < 20 || x > W + spacing) continue;
    const col = e.current ? css("--gl-accent") : colors[e.status] || colors.pending;
    const tab = (e.tab || []).filter(tb => tb && tb[0]);
    if (tab.length) {
      for (const [s, f] of tab) {
        const y = top + stringRow(s, strings) * gap;
        const txt = String(f);
        g.font = (e.current ? "800 " : "700 ") + "15px ui-monospace, Menlo, monospace";
        const w = Math.max(18, g.measureText(txt).width + 10);
        g.fillStyle = css("--gl-panel");
        g.fillRect(x - w / 2, y - 9, w, 18);
        g.fillStyle = col;
        g.fillText(txt, x, y + 5);
      }
    } else {
      g.fillStyle = col;
      g.font = "700 13px system-ui";
      g.fillText(e.label, x, top + 2.5 * gap + 5);
    }
    g.font = "11px system-ui";
    g.fillStyle = e.current ? css("--text") : css("--muted");
    g.fillText(e.label.length > 9 ? e.label.slice(0, 8) + "…" : e.label, x, top + (strings - 1) * gap + 24);
    const bi = beats && beats.get(e.i);
    if (bi) {
      if (bi.first) {                                          // bar line and bar number
        const bx = x - spacing / 2;
        g.strokeStyle = css("--muted"); g.lineWidth = 1.5;
        g.beginPath(); g.moveTo(bx, top - 4); g.lineTo(bx, top + (strings - 1) * gap + 4); g.stroke();
        g.strokeStyle = css("--gl-string"); g.lineWidth = 1;
        g.font = "10px system-ui"; g.fillStyle = css("--muted"); g.textAlign = "left";
        g.fillText(t("practice.bar_short", { n: bi.bar }), bx + 3, top - 32);
        g.textAlign = "center";
      }
      const step = Math.min(12, (spacing - 8) / bi.n);         // the beats this chord lasts: 1 2 3 4
      for (let k = 0; k < bi.n; k++) {
        const on = nowBeat != null && nowBeat === bi.start + k;
        g.font = on ? "800 12px system-ui" : "10px system-ui";
        g.fillStyle = on ? css("--gl-accent") : css("--muted");
        g.fillText(String(bi.from + k + 1), x - (bi.n - 1) * step / 2 + k * step, top + (strings - 1) * gap + 40);
      }
    }
    if (e.status !== "pending") {
      g.fillStyle = col;
      g.font = "700 13px system-ui";
      const extra = e.dt != null && Math.abs(e.dt) >= 15 ? ` ${signed(e.dt)}` : "";
      g.fillText((ICON[e.status] || "") + extra, x, top - 16);
    }
  }
  g.textAlign = "left";
}

/** The canvas is a picture: tell screen readers what it shows (the note or chord to play now). */
function describeTab(lane) {
  let label = t("practice.tab_placeholder");
  if (lane && lane.length) {
    const e = lane.find(x => x.current) || lane[Math.min(Math.round(App.k), lane.length - 1)];
    const where = (e.tab || []).filter(tb => tb && tb[0]).map(([s, f]) => t("practice.string_fret", { s, f })).join(", ");
    label = t("practice.tab_now", { label: e.label, where: where || "—", k: e.i + 1, total: lane.length });
  }
  if (cv.getAttribute("aria-label") !== label) cv.setAttribute("aria-label", label);
}

function animate() {
  const d = App.k - App.kSmooth;
  if (Math.abs(d) > 0.001) { App.kSmooth += d * 0.25; drawTab(); }
  requestAnimationFrame(animate);
}
window.addEventListener("resize", () => { drawTab(); drawRoll(); });

// ------------------------------------------------------------------ reports (shared)
function stat(v, l, cls = "") { return `<div class="stat ${cls}"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`; }

function renderReport(r) {
  const s = r.summary;
  let html = `<h2>${esc(t("report.title"))}</h2><div class="summary">`;
  if (r.kind === "live") {
    if (!s.judged) return html + `</div><p class="muted">${esc(t("report.nothing_played"))}</p>`;
    html += stat(s.score != null ? Math.round(s.score) : "—", t("report.score"), s.score >= 85 ? "good" : s.score >= 60 ? "warn" : "bad");
    html += stat(`${s.first_try}/${s.judged}`, t("report.first_try", { pct: fmtPct(s.first_try_pct) }));
    if (r.mode === "wait") html += stat(s.fixed, t("report.fixed"), s.fixed ? "warn" : "");
    html += stat(s.wrong, t("report.wrong"), s.wrong ? "bad" : "good");
    html += stat(s.missed, t("report.missed"), s.missed ? "bad" : "good");
    if (r.mode === "tempo") {
      html += stat(s.extras, t("report.extra_notes"), s.extras ? "warn" : "");
      if (s.timing_mean_ms != null) html += stat(`${signed(s.timing_mean_ms)} ms`, t("report.avg_timing", { std: Math.round(s.timing_std_ms) }), Math.abs(s.timing_mean_ms) > 30 ? "warn" : "good");
    }
    if (s.tuning_cents != null && Math.abs(s.tuning_cents) > 15) html += stat(`${signed(s.tuning_cents)}¢`, t("report.tune"), "warn");
    html += `</div>`;
    if (s.timing_verdict) html += timingVerdictHtml(s.timing_verdict);
    if (r.passes && r.passes.length > 1) html += `<p class="muted">${esc(t("report.passes"))}: ${r.passes.map(p => `${Math.round(p.score)}%${p.speed ? " @" + Math.round(p.speed * 100) + "%" : ""}`).join(" · ")}</p>`;
  } else {
    html += stat(Math.round(s.score), t("report.score"), s.score >= 85 ? "good" : s.score >= 60 ? "warn" : "bad");
    html += stat(`${s.correct}/${s.ref_notes}`, t("report.correct", { pct: fmtPct(s.correct_pct) }));
    html += stat(s.wrong, t("report.wrong_note"), s.wrong ? "bad" : "good");
    html += stat(s.missing, t("report.missing"), s.missing ? "bad" : "good");
    html += stat(s.extra, t("report.extra"), s.extra ? "warn" : "");
    html += stat(s.timing_loose, t("report.loose_timing"), s.timing_loose ? "warn" : "good");
    html += stat(`${Math.round(100 * s.tempo_ratio)}%`, t("report.tempo_ratio"));
    if (s.timing_mean_ms != null) html += stat(`${signed(s.timing_mean_ms)} ms`,
      Math.abs(s.timing_mean_ms) < 15 ? t("timing.on_time") : t(s.timing_mean_ms > 0 ? "report.drag" : "report.rush"));
    html += `</div>`;
    if (s.masked) html += `<p class="muted">${esc(t("report.masked", { n: s.masked }))}</p>`;
  }
  html += grooveHtml(s.groove);
  if (r.transpose_suggestion) html += `<p class="callout">${esc(t("report.transpose_hint", { k: r.transpose_suggestion }))}</p>`;
  if (r.bars && r.bars.length) {
    html += `<h3>${esc(t("report.per_bar"))}</h3><div class="heat">` + r.bars.map(b => {
      const rate = b.notes ? (b.errors + 0.5 * b.timing) / b.notes : 0;
      const col = rate === 0 ? css("--gl-ok") : rate < 0.25 ? css("--gl-warn") : css("--gl-err");
      return `<div data-bar="${b.bar}" title="${esc(t("report.bar_tooltip", { bar: b.bar, errors: b.errors, timing: b.timing }))}" style="background:${alpha(col, rate === 0 ? "33" : "88")};color:var(--text)">${b.bar}</div>`;
    }).join("") + `</div>`;
    const worst = [...r.bars].map(b => ({ ...b, rate: b.notes ? (b.errors + 0.5 * b.timing) / b.notes : 0 }))
      .filter(b => b.rate > 0).sort((a, b) => b.rate - a.rate).slice(0, 2);
    if (worst.length) {
      const a = Math.min(...worst.map(w => w.bar)), z = Math.max(...worst.map(w => w.bar));
      html += `<div class="callout" style="margin-top:12px"><span>${t("report.weakest_html", { bars: worst.map(w => w.bar).join(" & ") })}</span>
        <button class="btn primary small" data-practice="${a}-${z}">${esc(t("report.practice_bars", { from: a, to: z }))}</button></div>`;
    }
  }
  if (r.issues && r.issues.length) {
    html += `<h3>${esc(t("report.details", { n: r.issues.length }))}</h3><table class="issues">` + r.issues.map(it =>
      `<tr class="t-${it.type}" data-t="${it.t}"><td class="ico">${ICON[it.type] || "·"}</td><td class="muted mono" style="white-space:nowrap">${esc(t("report.where", { bar: it.bar, beat: it.beat.toFixed(2) }))}</td><td>${esc(issueText(it))}</td></tr>`).join("") + `</table>`;
  } else html += `<p style="color:var(--gl-ok);font-weight:600;margin-top:14px">${esc(t("report.no_mistakes"))}</p>`;
  if (r.take && r.kind === "live") {
    const name = r.take.split("/").pop();
    html += `<div class="callout" style="margin-top:14px"><span>${esc(t("report.take_saved"))}</span><button class="btn small" data-analyze="${esc(name)}">${esc(t("report.analyze_take"))}</button></div>
      ${takePlayer(name, r.take_info)}`;
  }
  return html;
}

function refOf(r) {
  return r.reference && r.reference.path ? r.reference.path.split("/").pop() : $("#pSong").value;
}

function bindReport(el, r) {
  bindTakePlayers(el);
  const p = $("[data-practice]", el);
  if (p) p.onclick = () => {
    const [a, z] = p.dataset.practice.split("-");
    practiceBars(refOf(r), +a, +z);
  };
  const an = $("[data-analyze]", el);
  if (an) an.onclick = async () => {
    show("analyze");
    await loadTakes(an.dataset.analyze);
    $("#aSong").value = $("#pSong").value;
    await onSongChange("a");
    $("#aStart").value = $("#pStart").value;
    $("#aEnd").value = $("#pEnd").value;
    runAnalysis();
  };
  $$(".heat div", el).forEach(d => d.onclick = () => practiceBars(refOf(r), +d.dataset.bar, +d.dataset.bar));
  $$(".issues tr", el).forEach(tr => tr.onclick = () => { if (App.roll) scrollRollTo(+tr.dataset.t); });
}

async function practiceBars(song, a, z) {
  show("practice");
  if (song && song.startsWith("chart:")) await useChart(song.slice("chart:".length));
  else if (song && App.songs.some(s => s.name === song)) { $("#pSong").value = song; await loadTracks("p"); }
  $("#pStart").value = Math.max(1, a);
  $("#pEnd").value = z;
  setMode("tempo");
  $("#pSpeed").value = 70; $("#pSpeedVal").textContent = "70%";
  $("#pTrainer").checked = true; $("#trainerOpts").hidden = false; $("#pLoop").checked = true;
  await loadPreview();
  toast(t("practice.bars_ready", { from: a, to: z }), true);
}

// ------------------------------------------------------------------ analyze a take
async function loadTakes(select) {
  try { App.takes = await api("/api/takes"); } catch { App.takes = []; }
  const opts = App.takes.map(tk => `<option value="${esc(tk.name)}">${esc(tk.name)}</option>`).join("");
  const cur = select || $("#aTake").value;
  $("#aTake").innerHTML = opts || `<option value="">${esc(t("analyze.no_takes"))}</option>`;
  if (cur && App.takes.some(tk => tk.name === cur)) $("#aTake").value = cur;
  const simCur = $("#pSimulate").value;
  $("#pSimulate").innerHTML = `<option value="">${esc(t("practice.use_guitar"))}</option>` + opts;
  if (simCur) $("#pSimulate").value = simCur;
}

$("#aRun").addEventListener("click", runAnalysis);
async function runAnalysis() {
  const body = { ...refBody("a"), take: $("#aTake").value, timing_tol_ms: $("#aTol").value };
  const up = $("#aTakeUpload").files[0];
  if (!body.song) return toast(t("analyze.pick_reference"));
  if (!body.take && !up) return toast(t("analyze.pick_take"));
  const fd = new FormData();
  fd.append("options", JSON.stringify(body));
  if (up) fd.append("take", up);
  const btn = $("#aRun");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> ${esc(t("analyze.transcribing"))}`;
  $("#aResult").innerHTML = `<div class="panel empty"><span class="spinner"></span> ${esc(t("analyze.listening"))}</div>`;
  try {
    const r = await api("/api/analyze", { method: "POST", body: fd });
    $("#aTakeUpload").value = "";
    await loadTakes(r.take_name);
    renderAnalysis(r);
    if (r.award && r.award.xp) toast(t("analyze.xp", { xp: r.award.xp }), true);
    progressChanged();
  } catch (e) {
    $("#aResult").innerHTML = `<div class="panel empty">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = t("analyze.run");
  }
}

function renderAnalysis(r) {
  App.roll = r;
  $("#aResult").innerHTML = `
    <div class="panel" id="aReport"></div>
    <div class="panel">
      <div class="row" style="align-items:center"><h2 style="margin:0">${esc(t("analyze.roll_title"))}</h2>
        <label style="flex:none;display:flex;gap:8px;align-items:center" class="muted">${esc(t("analyze.zoom"))} <input type="range" id="rollZoom" min="40" max="400" value="120" style="width:120px"></label></div>
      <div class="legend">
        <span><i style="border:1.5px solid var(--muted)"></i>${esc(t("analyze.legend_reference"))}</span>
        <span><i style="background:var(--gl-ok)"></i>${esc(t("analyze.legend_ok"))}</span>
        <span><i style="background:var(--gl-warn)"></i>${esc(t("analyze.legend_timing"))}</span>
        <span><i style="background:var(--gl-err)"></i>${esc(t("analyze.legend_wrong"))}</span>
        <span><i style="background:var(--gl-octave)"></i>${esc(t("analyze.legend_octave"))}</span>
        <span><i style="background:var(--gl-info)"></i>${esc(t("analyze.legend_extra"))}</span>
      </div>
      <div class="rollwrap" id="rollWrap"><canvas id="rollCanvas"></canvas></div>
      ${r.take_name ? takePlayer(r.take_name, r.take_info) : ""}
    </div>`;
  bindTakePlayers($("#aResult"));
  const rep = $("#aReport");
  rep.innerHTML = renderReport(r);
  bindReport(rep, r);
  $("#rollZoom").addEventListener("input", drawRoll);
  drawRoll();
}

function drawRoll() {
  const r = App.roll;
  const c = $("#rollCanvas");
  if (!r || !c) return;
  const pps = +$("#rollZoom").value;   // pixels per second
  const all = [...r.roll.ref, ...r.roll.user];
  const tEnd = Math.max(...all.map(n => n[1])) + 0.5;
  const pMin = Math.min(...all.map(n => n[2])) - 2, pMax = Math.max(...all.map(n => n[2])) + 2;
  const rowH = Math.max(6, Math.min(14, 360 / (pMax - pMin + 1)));
  const left = 44, W = Math.ceil(left + tEnd * pps + 20), H = Math.ceil((pMax - pMin + 1) * rowH + 30);
  const dpr = window.devicePixelRatio || 1;
  c.width = W * dpr; c.height = H * dpr; c.style.width = W + "px"; c.style.height = H + "px";
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const X = tm => left + tm * pps, Y = p => 22 + (pMax - p) * rowH;
  const col = STATUS_COLOR();
  g.font = "10px ui-monospace, Menlo, monospace";
  for (let p = pMin; p <= pMax; p++) {
    if ([1, 3, 6, 8, 10].includes(((p % 12) + 12) % 12)) { g.fillStyle = css("--gl-panel"); g.fillRect(left, Y(p), W - left, rowH); }
    if (p % 12 === 0 || p % 12 === 4 || p % 12 === 9) { g.fillStyle = css("--muted"); g.fillText(noteName(p), 4, Y(p) + rowH - 2); }
  }
  g.strokeStyle = css("--border");
  g.fillStyle = css("--muted");
  (r.downbeats || []).forEach((tm, i) => {
    g.beginPath(); g.moveTo(X(tm), 14); g.lineTo(X(tm), H); g.stroke();
    if (pps * ((r.downbeats[1] || tm + 1) - (r.downbeats[0] || 0)) > 24 || i % 4 === 0) g.fillText(String(i + 1), X(tm) + 3, 11);
  });
  for (const [s, e, p, st] of r.roll.ref) {        // reference (outline)
    g.strokeStyle = st === "missing" ? col.missing : css("--muted");
    g.lineWidth = st === "missing" ? 2 : 1.2;
    g.setLineDash(st === "missing" ? [3, 2] : []);
    g.strokeRect(X(s), Y(p) + 0.5, Math.max(3, (e - s) * pps), rowH - 1);
  }
  g.setLineDash([]);
  for (const [s, e, p, st] of r.roll.user) {       // what you played (filled)
    g.fillStyle = alpha(col[st] || col.ok, "cc");
    g.fillRect(X(s), Y(p) + 2, Math.max(3, (e - s) * pps), rowH - 4);
  }
}

function scrollRollTo(tm) {
  const w = $("#rollWrap");
  if (!w) return;
  const pps = +$("#rollZoom").value;
  w.scrollTo({ left: Math.max(0, 44 + tm * pps - w.clientWidth / 3), behavior: "smooth" });
}

// ------------------------------------------------------------------ tuner
let tws = null;
// open strings of your tuning: [midi, string number, name]
const strings = () => instrument.strings.map((m, i) => [m, i + 1, noteName(m)]);
function initTuner() {
  $("#tStrings").innerHTML = strings().reverse().map(([m, n, l]) =>
    `<div data-m="${m}"><b>${l}</b><small>${esc(t("tuner.string_n", { n }))}</small></div>`).join("");
  let ticks = "";
  for (let c = -50; c <= 50; c += 10) {
    const a = (c / 50) * (Math.PI / 2) * 0.98;
    const len = c % 50 === 0 || c === 0 ? 132 : 140;
    ticks += `<line x1="${200 + Math.sin(a) * 150}" y1="${200 - Math.cos(a) * 150}" x2="${200 + Math.sin(a) * len}" y2="${200 - Math.cos(a) * len}" stroke="var(--muted)" stroke-width="2"/>`;
  }
  $("#ticks").innerHTML = ticks;
}
$("#tStart").addEventListener("click", () => (tws ? stopTuner() : startTuner()));
function startTuner() {
  if (App.live) return toast(t("tuner.stop_practice"));
  tws = new WebSocket(`ws://${location.host}/ws/tuner`);
  $("#tStart").textContent = t("tuner.stop");
  tws.onmessage = ev => {
    const r = JSON.parse(ev.data);
    if (r.error) { toast(t(`errors.${r.error.code}`, { defaultValue: r.error.message })); stopTuner(); return; }
    if (r.source) { $("#tSource").textContent = t("tuner.input", { name: r.source }); return; }
    const note = $("#tNote");
    if (!r.note) {
      note.textContent = "—"; note.className = "note";
      $("#tCents").textContent = r.level_db < -55 ? t("tuner.play_open") : "…";
      $("#needle").style.transform = "rotate(0deg)";
      $$("#tStrings div").forEach(d => d.className = "");
      return;
    }
    const cents = r.string_cents != null ? r.string_cents : r.cents;
    const ok = Math.abs(cents) <= 5;
    note.textContent = r.note; note.className = "note" + (ok ? " ok" : "");
    let line = `${cents > 0 ? "+" : ""}${cents.toFixed(1)} cents · ${r.freq.toFixed(1)} Hz`;
    if (r.string) line += ` · ${t("tuner.string_status", { n: r.string, status: t(ok ? "tuner.in_tune" : cents < 0 ? "tuner.tune_up" : "tuner.tune_down") })}`;
    $("#tCents").textContent = line;
    $("#needle").style.transform = `rotate(${Math.max(-50, Math.min(50, cents)) / 50 * 88}deg)`;
    const near = strings().reduce((a, b) => Math.abs(b[0] - r.midi) < Math.abs(a[0] - r.midi) ? b : a);
    $$("#tStrings div").forEach(d => d.className = +d.dataset.m === near[0] && Math.abs(near[0] - r.midi) < 0.75 ? (ok ? "ok" : "on") : "");
  };
  tws.onclose = () => { tws = null; $("#tStart").textContent = t("tuner.start"); };
}
function stopTuner() { if (tws) { tws.close(); tws = null; } $("#tStart").textContent = t("tuner.start"); }

// ------------------------------------------------------------------ history
async function loadHistory() {
  const songs = await api("/api/history");
  const el = $("#hSongs");
  if (!songs.length) { el.innerHTML = `<p class="muted">${esc(t("history.empty"))}</p>`; return; }
  el.innerHTML = songs.map(s => `<button data-id="${esc(s.id)}"><b>${esc(s.name)}</b>${s.track ? ` <span class="muted">· ${esc(s.track)}</span>` : ""}
     <small>${esc(t("history.song_meta", { count: s.sessions, date: (s.last_date || "").slice(0, 10), score: fmtPct(s.last_score) }))}</small></button>`).join("");
  $$("button", el).forEach(b => b.onclick = () => {
    $$("button", el).forEach(x => x.classList.toggle("active", x === b));
    loadSongHistory(b.dataset.id);
  });
}

async function loadSongHistory(id) {
  const h = await api(`/api/history/${encodeURIComponent(id)}`);
  const ss = h.sessions;
  const pb = h.problem_bars;
  let html = `<div class="panel"><h2>${esc(t("history.progress_of", { name: h.reference.name || id }))}</h2><svg id="histChart" viewBox="0 0 800 220" preserveAspectRatio="none"></svg>
    <div class="legend"><span><i style="background:var(--gl-accent)"></i>${esc(t("report.score"))}</span><span><i style="background:var(--gl-info)"></i>${esc(t("history.speed_legend"))}</span></div></div>`;
  if (pb.length) {
    const a = Math.min(...pb.slice(0, 2).map(b => b.bar)), z = Math.max(...pb.slice(0, 2).map(b => b.bar));
    html += `<div class="panel"><h2>${esc(t("history.weakest"))}</h2><div class="summary">` +
      pb.map(b => stat(t("history.bar_n", { n: b.bar }), t("history.error_rate", { pct: Math.round(100 * b.rate) }), b.rate > 0.3 ? "bad" : "warn")).join("") +
      `</div>${h.song ? `<div class="callout" style="margin-top:12px"><span>${esc(t("history.practice_hint"))}</span><button class="btn primary small" id="hPractice">${esc(t("history.practice_bars", { from: a, to: z }))}</button></div>` : ""}</div>`;
    App.histPractice = [h.song, a, z];
  }
  html += `<div class="panel"><h2>${esc(t("history.sessions"))}</h2><table class="sessions"><tr><th>${esc(t("history.col_date"))}</th><th>${esc(t("history.col_kind"))}</th><th>${esc(t("history.col_bars"))}</th><th>${esc(t("history.col_speed"))}</th><th>${esc(t("history.col_score"))}</th></tr>` +
    ss.slice().reverse().map(s => `<tr><td>${esc((s.date || "").replace("T", " ").slice(0, 16))}</td><td>${esc(t(s.kind === "file" ? "history.kind_take" : s.mode === "tempo" ? "history.kind_tempo" : "history.kind_wait"))}</td>
      <td>${esc(s.section ? `${s.section.start_bar || 1}–${s.section.end_bar || t("practice.end")}` : t("history.all"))}</td>
      <td>${typeof s.speed === "number" && s.kind !== "file" ? Math.round(s.speed * 100) + "%" : "—"}</td><td><b>${fmtPct(s.score)}</b></td></tr>`).join("") + `</table></div>`;
  $("#hDetail").innerHTML = html;
  const btn = $("#hPractice");
  if (btn) btn.onclick = () => practiceBars(...App.histPractice);
  drawHistChart(ss);
}

function drawHistChart(ss) {
  const svg = $("#histChart");
  const W = 800, H = 220, pad = 28;
  const n = ss.length;
  const x = i => pad + (n === 1 ? (W - 2 * pad) / 2 : i * (W - 2 * pad) / (n - 1));
  const y = v => H - pad - (v / 100) * (H - 2 * pad);
  let out = "";
  for (const v of [0, 50, 100]) out += `<line x1="${pad}" x2="${W - pad}" y1="${y(v)}" y2="${y(v)}" stroke="var(--border)"/><text x="4" y="${y(v) + 4}" font-size="11" fill="var(--muted)">${v}</text>`;
  const pts = ss.map((s, i) => s.score == null ? null : [x(i), y(s.score)]).filter(Boolean);
  if (pts.length > 1) out += `<polyline points="${pts.map(p => p.join(",")).join(" ")}" fill="none" stroke="var(--gl-accent)" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`;
  out += pts.map(([a, b]) => `<circle cx="${a}" cy="${b}" r="4" fill="var(--gl-accent)"/>`).join("");
  ss.forEach((s, i) => { if (typeof s.speed === "number" && s.kind !== "file") out += `<rect x="${x(i) - 3}" y="${y(Math.min(100, s.speed * 100)) - 3}" width="6" height="6" fill="var(--gl-info)"><title>${Math.round(s.speed * 100)}%</title></rect>`; });
  svg.innerHTML = out;
}

// ------------------------------------------------------------------ settings
const Settings = { devices: [], saved: {}, test: null, timer: null };

// ------------------------------------------------------------------ instrument: tuning and handedness
async function loadInstrumentPanel() {
  // until it's loaded you can't change it (a late load would undo your change)
  $("#iTuning").disabled = $("#iLefty").disabled = $("#iTabOrder").disabled = true;
  $("#iStatus").textContent = "";
  const inst = await loadInstrument();
  $("#iTuning").innerHTML = Object.entries(inst.tunings || {}).map(([id, ms]) =>
    `<option value="${id}">${esc(t(`instrument.t_${id}`))} · ${ms.slice().reverse().map(m => NOTE_NAMES[m % 12]).join(" ")}</option>`).join("");
  $("#iTuning").value = inst.tuning;
  $("#iLefty").checked = inst.left_handed;
  $("#iTabOrder").value = inst.tab_low_on_top === false ? "high" : "low";
  $("#iTuning").disabled = $("#iLefty").disabled = $("#iTabOrder").disabled = false;
}
// saves run one after another, and the status says "Saving…" until the last one is done
let instSaving = Promise.resolve(), instPending = 0;
function saveInstrument() {
  instPending++;
  $("#iStatus").textContent = t("instrument.saving");
  instSaving = instSaving.then(doSaveInstrument).finally(() => {
    if (--instPending === 0 && !$("#iStatus").dataset.err) $("#iStatus").innerHTML = `<span class="ok">✓ ${esc(t("instrument.saved"))}</span>`;
  });
  return instSaving;
}
async function doSaveInstrument() {
  try {
    await api("/api/instrument", { method: "PUT", json: { tuning: $("#iTuning").value, left_handed: $("#iLefty").checked, tab_low_on_top: $("#iTabOrder").value === "low" } });
    await loadInstrument();
    initTuner();
    delete $("#iStatus").dataset.err;
    window.dispatchEvent(new CustomEvent("guitarr:instrument"));
  } catch (e) { $("#iStatus").textContent = e.message; $("#iStatus").dataset.err = "1"; }
}
$("#iTuning").addEventListener("change", saveInstrument);
$("#iLefty").addEventListener("change", saveInstrument);
$("#iTabOrder").addEventListener("change", saveInstrument);

async function loadReminder() {
  try {
    const r = await api("/api/reminder");
    $("#remOn").checked = r.enabled;
    $("#remTime").value = r.time;
    const browserOnly = !r.desktop;
    $("#remAllow").hidden = !browserOnly || !("Notification" in window) || Notification.permission === "granted";
    $("#remStatus").textContent = t(browserOnly ? "reminder.browser_only" : "reminder.desktop_ok");
  } catch { /* no server */ }
}
async function saveReminder() {
  try {
    await api("/api/reminder", { method: "PUT", json: { enabled: $("#remOn").checked, time: $("#remTime").value,
      title: t("reminder.notif_title"), body: t("reminder.notif_body") } });
    $("#remStatus").innerHTML = `<span class="ok">✓ ${esc(t("reminder.saved"))}</span>`;
  } catch (e) { $("#remStatus").textContent = e.message; }
}
$("#remOn").addEventListener("change", saveReminder);
$("#remTime").addEventListener("change", saveReminder);
$("#remTest").addEventListener("click", async () => {
  await saveReminder();
  const r = await api("/api/reminder/test", { method: "POST" });
  if (!r.desktop) showBrowserNotification(t("reminder.notif_title"), t("reminder.notif_body").replace("{left}", "0:15"));
});
$("#remAllow").addEventListener("click", async () => {
  if ("Notification" in window) await Notification.requestPermission();
  loadReminder();
});
export function showBrowserNotification(title, body) {
  if ("Notification" in window && Notification.permission === "granted") new Notification(title, { body });
  else toast(body);
}

/** Where each setting comes from (environment, saved by you, auto-detected or default), so a hidden override
 * is never a mystery. */
async function loadSources() {
  const box = $("#sSources");
  if (!box) return;
  let r;
  try { r = await api("/api/settings/sources"); } catch { box.hidden = true; return; }
  const rows = ["home", "device", "channel", "output_device", "latency_ms", "tuning", "left_handed", "tab_low_on_top"];
  const val = (k, v) => v == null || v === "" ? "—" : k === "tuning" ? t(`instrument.t_${v}`) : k === "left_handed" ? t(v ? "common.yes" : "common.no")
    : k === "tab_low_on_top" ? t(v ? "instrument.tab_low_top" : "instrument.tab_high_top") : String(v);
  box.innerHTML = `<h2>${esc(t("sources.title"))}</h2><p class="muted small">${esc(t("sources.hint"))}</p>
    <table class="sources"><tbody>${rows.map(k => `<tr><th scope="row">${esc(t(`sources.k_${k}`))}</th><td class="mono small">${esc(val(k, r[k].value))}</td>
      <td><span class="how-chip src-${r[k].source}">${esc(t(`sources.${r[k].source}`, { env: r[k].env || "" }))}</span></td></tr>`).join("")}</tbody></table>`;
}

async function loadSettings() {
  loadReminder();
  loadTakesUsage();
  loadInstrumentPanel();
  loadSources();
  loadLatency();
  const [dv, cfg] = await Promise.all([api("/api/devices"), api("/api/config")]);
  if (dv.error) toast(dv.error);
  Settings.devices = dv.inputs;
  Settings.saved = cfg.saved;
  const a = cfg.audio;
  $("#sDevice").innerHTML = dv.inputs.map(d => `<option value="${d.index}">${esc(d.name)}${d.index === dv.suggested ? " — " + esc(t("settings.looks_like_interface")) : ""}</option>`).join("");
  if (a.device != null) $("#sDevice").value = typeof a.device === "number" ? a.device : (dv.inputs.find(d => d.name === a.device) || {}).index;
  fillChannels(a.channel || 1);
  $("#sOutput").innerHTML = `<option value="">${esc(t("settings.system_output"))}</option>` + dv.outputs.map(d => `<option value="${d.index}">${esc(d.name)}</option>`).join("");
  $("#sOutput").value = a.output_device ?? "";
  $("#sGate").value = a.gate_db ?? -50; $("#sGateVal").textContent = $("#sGate").value + " dB";
  $("#sSens").value = a.sensitivity ?? 1; $("#sSensVal").textContent = sensLabel(+$("#sSens").value);
  $("#sLatency").value = a.latency_ms ?? 0;
  $("#sMeterBox").innerHTML = meterHtml("sMeter", +$("#sGate").value);
  $("#sState").textContent = t("settings.autosave", { path: cfg.path });
}

function fillChannels(cur) {
  const d = Settings.devices.find(x => String(x.index) === $("#sDevice").value);
  const n = Math.max(1, Math.min(d ? d.channels : 1, 16));
  $("#sChannel").innerHTML = Array.from({ length: n }, (_, k) => `<option value="${k + 1}">${esc(t("settings.channel_n", { n: k + 1 }))}</option>`).join("");
  $("#sChannel").value = Math.min(cur, n);
  $("#sChannelWrap").hidden = n < 2;
}

const sensLabel = v => `${v.toFixed(1)} · ${t(v < 0.8 ? "settings.sens_low" : v > 1.6 ? "settings.sens_high" : "settings.sens_mid")}`;

function saveSettings() {
  clearTimeout(Settings.timer);
  $("#sState").textContent = t("settings.saving");
  Settings.timer = setTimeout(async () => {
    const body = { ...Settings.saved, device: $("#sDevice").value, channel: $("#sChannel").value, output_device: $("#sOutput").value,
                   gate_db: $("#sGate").value, sensitivity: $("#sSens").value, latency_ms: $("#sLatency").value };
    if (String(Settings.saved.device) !== body.device) delete body.samplerate;
    try {
      const r = await api("/api/config", { json: body });
      Settings.saved = r.saved;
      $("#sState").innerHTML = `<span class="ok">✓ ${esc(t("settings.saved"))}</span>`;
      refreshDevicePill();
      loadLatency();
    } catch (e) { $("#sState").textContent = e.message; toast(e.message); }
  }, 350);
}

$("#sDevice").addEventListener("change", () => { fillChannels(1); saveSettings(); restartTest(); });
$("#sChannel").addEventListener("change", () => { saveSettings(); restartTest(); });
$("#sOutput").addEventListener("change", saveSettings);
$("#sLatency").addEventListener("change", saveSettings);
$("#sGate").addEventListener("input", () => { $("#sGateVal").textContent = $("#sGate").value + " dB"; setGate($("#sMeter"), +$("#sGate").value); });
$("#sGate").addEventListener("change", saveSettings);
$("#sSens").addEventListener("input", () => ($("#sSensVal").textContent = sensLabel(+$("#sSens").value)));
$("#sSens").addEventListener("change", saveSettings);

function startTest() {
  if (App.live) return toast(t("tuner.stop_practice"));
  stopTuner();
  const vs = {};
  $("#sTest").textContent = t("settings.test_stop");
  Settings.test = openInput({
    device: $("#sDevice").value, channel: $("#sChannel").value,
    onReading: r => {
      setMeter($("#sMeter"), r.level_db);
      const v = levelVerdict(vs, r);
      const below = vs.heardAt && performance.now() - vs.heardAt < 2000 && vs.heardDb < +$("#sGate").value;
      $("#sVerdict").textContent = below ? t("settings.below_gate") : `${v.text} · ${Math.round(r.level_db)} dB`;
      $("#sVerdict").className = "small " + (below ? "warn" : v.cls);
    },
    onError: msg => { $("#sVerdict").textContent = msg; $("#sVerdict").className = "small err"; stopTest(); },
  });
}
function stopTest() {
  if (Settings.test) { Settings.test.close(); Settings.test = null; }
  $("#sTest").textContent = t("settings.test_start");
  setMeter($("#sMeter"), -120);
}
function restartTest() { if (Settings.test) { stopTest(); setTimeout(startTest, 300); } }
$("#sTest").addEventListener("click", () => (Settings.test ? stopTest() : startTest()));
/** The cable help's drawing: the metronome output going back into input 2 (labels translated, colors from the theme). */
function cableDiagram() {
  const L = k => esc(t(`cable.d_${k}`));   // rebuilt on every visit, so it follows the language
  return `<svg viewBox="0 0 520 185" role="img">
    <rect x="150" y="40" width="300" height="115" rx="12" fill="var(--gl-panel-2)" stroke="currentColor" stroke-opacity=".5"/>
    <text x="300" y="146" text-anchor="middle" font-size="12" fill="currentColor">${L("interface")}</text>
    <circle cx="200" cy="90" r="14" fill="none" stroke="currentColor" stroke-width="2"/><text x="200" y="122" text-anchor="middle" font-size="11" fill="var(--muted)">${L("in1")}</text>
    <circle cx="270" cy="90" r="14" fill="none" stroke="var(--gl-accent)" stroke-width="3"/><text x="270" y="122" text-anchor="middle" font-size="11" fill="var(--gl-accent)">${L("in2")}</text>
    <circle cx="400" cy="90" r="10" fill="none" stroke="var(--gl-accent)" stroke-width="3"/><text x="400" y="122" text-anchor="middle" font-size="11" fill="var(--gl-accent)">${L("phones")}</text>
    <path d="M400 80 C 400 -5, 270 -5, 270 76" fill="none" stroke="var(--gl-accent)" stroke-width="4" stroke-linecap="round"/>
    <text x="392" y="26" font-size="12" font-weight="700" fill="var(--gl-accent)">${L("cable")}</text>
    <path d="M30 90 L 186 90" stroke="currentColor" stroke-opacity=".45" stroke-width="3" stroke-dasharray="6 5"/>
    <text x="70" y="80" text-anchor="middle" font-size="11" fill="var(--muted)">${L("guitar")}</text>
    <text x="300" y="177" text-anchor="middle" font-size="11" fill="var(--muted)">${L("monitor_off")}</text>
  </svg>`;
}

// latency: how it was measured, your own tendency, and warnings about the devices
async function loadLatency() {
  const dg = $("#cableDiagram");
  if (dg) dg.innerHTML = cableDiagram();
  const box = $("#latStatus");
  if (!box) return;
  let st;
  try { st = await api("/api/latency"); } catch { box.innerHTML = ""; return; }
  const now = $("#cableNow");
  if (now) now.textContent = st.current_output ? t(st.current_output === st.current_input ? "cable.now_same" : "cable.now_other",
    { output: st.current_output, input: st.current_input || "?" }) : "";
  const lines = [];
  if (st.applied_ms != null) lines.push(`<b>${esc(t("latency.applied", { ms: Math.round(st.applied_ms) }))}</b> · ${esc(st.method ? t(`latency.how_${st.method}`, { input: st.input || "?", output: st.output || "?" }) : t("latency.how_manual"))}`);
  if (st.tendency_ms != null) lines.push(esc(t(Math.abs(st.tendency_ms) < 15 ? "latency.tendency_none" : st.tendency_ms < 0 ? "latency.tendency_early" : "latency.tendency_late", { ms: Math.round(Math.abs(st.tendency_ms)) })));
  const warn = (st.warnings || []).map(w => `<li>${esc(t(`latency.warn_${w.code}`, w.params))}</li>`).join("");
  box.innerHTML = `<p class="small">${lines.join("<br>")}</p>${warn ? `<ul class="callout warn small lat-warn">${warn}</ul>` : ""}`;
}

function runCalibration(body, status) {
  return async () => {
    stopTest();
    try {
      await api("/api/calibrate", { json: body });
      $("#cStart").disabled = $("#cLoop").disabled = true;
      const poll = setInterval(async () => {
        const s = await api("/api/calibrate");
        if (s.running) {
          status.innerHTML = s.mode === "loopback"
            ? `<span class="muted">${esc(t("latency.loop_running", { beat: s.beat, total: s.total }))}</span>`
            : s.warmup
              ? `<span class="muted">${esc(t("settings.cal_pulse", { beat: s.beat, total: s.total }))}</span>`
              : `<b style="color:var(--gl-accent)">${esc(t("settings.cal_play", { beat: s.beat, total: s.total }))}</b>`;
          return;
        }
        clearInterval(poll);
        $("#cStart").disabled = $("#cLoop").disabled = false;
        const r = s.result || {};
        if (r.ok) {
          const msg = r.method === "loopback" ? t("latency.loop_ok", { ms: Math.round(r.latency_ms), spread: r.spread_ms })
            : t("settings.cal_ok", { ms: Math.round(r.latency_ms), spread: Math.round(r.spread_ms), hits: r.hits });
          status.innerHTML = `<b style="color:var(--gl-ok)">✓ ${esc(msg)}</b>`;
          if (r.status) { $("#sLatency").value = r.status.applied_ms; Settings.saved.latency_ms = r.status.applied_ms; }
        } else {
          const known = { too_few_hits: "settings.cal_few_hits", no_loop: "latency.no_loop", loop_unsteady: "latency.loop_unsteady",
            loop_other_sound: "latency.loop_other_sound" }[r.code];
          status.innerHTML = `<span style="color:var(--gl-err)">${esc(known ? t(known, r) : (r.message || t("settings.cal_failed")))}</span>`;
          if (r.code?.startsWith("loop") || r.code === "no_loop") $("#cableHelp").open = true;   // the guide has the fixes
        }
        loadLatency();
      }, 150);
    } catch (e) { toast(e.message); }
  };
}
$("#cStart").addEventListener("click", runCalibration({ mode: "play" }, $("#cStatus")));
$("#cLoop").addEventListener("click", () => runCalibration({ mode: "loopback", channel: +$("#cLoopCh").value }, $("#cStatus"))());

async function refreshDevicePill() {
  try {
    const [dv, cfg] = await Promise.all([api("/api/devices"), api("/api/config")]);
    const a = cfg.audio;
    const d = dv.inputs.find(x => x.index === a.device || x.name === a.device);
    $("#deviceName").textContent = d ? t("settings.device_pill", { name: d.name, ch: a.channel || 1 }) : t("settings.default_input");
  } catch { $("#deviceName").textContent = t("settings.no_audio"); }
}

// ------------------------------------------------------------------ startup
// ------------------------------------------------------------------ your data: backup / restore
$("#bkTakes").addEventListener("change", e => { $("#bkDownload").href = "/api/backup" + (e.target.checked ? "?takes=true" : ""); });
$("#bkFile").addEventListener("change", e => {
  const f = e.target.files[0];
  if (!f) return;
  const box = $("#bkConfirm");
  box.hidden = false;
  box.innerHTML = `<span class="small">${esc(t("data.restore_q", { name: f.name }))}</span>
    <button class="btn small danger" id="bkYes">${esc(t("data.yes"))}</button><button class="btn small" id="bkNo">${esc(t("data.no"))}</button>`;
  const done = () => { box.hidden = true; box.innerHTML = ""; $("#bkFile").value = ""; };
  $("#bkNo").onclick = done;
  $("#bkYes").onclick = async () => {
    const fd = new FormData();
    fd.append("file", f);
    $("#bkStatus").textContent = t("data.restoring");
    $("#bkStatus").className = "small muted";
    try {
      const r = await api("/api/backup", { method: "POST", body: fd });
      $("#bkStatus").textContent = t("data.restored", { n: r.restored });
      $("#bkStatus").className = "small ok";
      setTimeout(() => location.reload(), 1200);
    } catch (err) { $("#bkStatus").textContent = err.message; $("#bkStatus").className = "small err"; }
    done();
  };
});

// ------------------------------------------------------------------ your data: recorded takes
const mb = bytes => (bytes / 1e6).toFixed(bytes < 1e7 ? 1 : 0);
let takesRoom = null;
async function loadTakesUsage() {
  try { takesRoom = await api("/api/takes/usage"); } catch { return; }
  $("#tkUsage").textContent = t("data.takes_usage", { count: takesRoom.count, mb: mb(takesRoom.bytes) });
  $("#tkDel").disabled = !takesRoom.count;
}
$("#tkDays").addEventListener("change", () => { $("#tkConfirm").hidden = true; });
$("#tkDel").addEventListener("click", () => {
  const days = $("#tkDays").value, o = takesRoom && takesRoom.older[days];
  const box = $("#tkConfirm");
  box.hidden = false;
  if (!o || !o.count) { box.innerHTML = `<span class="small muted">${esc(t("data.takes_none_older"))}</span>`; return; }
  box.innerHTML = `<span class="small">${esc(t("data.takes_q", { count: o.count, mb: mb(o.bytes) }))}</span>
    <button class="btn small danger" id="tkYes">${esc(t("data.yes"))}</button><button class="btn small" id="tkNo">${esc(t("data.no"))}</button>`;
  $("#tkNo").onclick = () => { box.hidden = true; };
  $("#tkYes").onclick = async () => {
    box.hidden = true;
    try {
      const r = await api("/api/takes/cleanup", { json: { days: +days } });
      $("#tkStatus").textContent = t("data.takes_deleted", { count: r.deleted, mb: mb(r.freed) });
      $("#tkStatus").className = "small ok";
      loadTakes();
    } catch (err) { $("#tkStatus").textContent = err.message; $("#tkStatus").className = "small err"; }
    loadTakesUsage();
  };
});

window.addEventListener("guitarr:device", refreshDevicePill);

(async function init() {
  initTuner();
  animate();
  refreshDevicePill();
  await loadTakes();
  await loadSongs();
  if (App.songs.length) { await onSongChange("p"); await onSongChange("a"); }
  try {   // a session was running (you reloaded the page): reattach
    const st = await api("/api/live/state");
    if (st.active && st.state.running) { setLive(true); connectLive(); }
  } catch { /* no server */ }
  drawTab();
})();

