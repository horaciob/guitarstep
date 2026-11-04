/* guitarr — vistas de escucha: practicar, analizar, afinador, historial y ajustes.
   Módulo ES sin dependencias: vanilla JS + canvas + SVG. El router (main.js)
   llama a showListenerView / hideListenerViews. */
const progressChanged = () => window.dispatchEvent(new CustomEvent("guitarr:progreso"));

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const noteName = p => NOTE_NAMES[((p % 12) + 12) % 12] + (Math.floor(p / 12) - 1);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// Lee un token de color y lo normaliza a #rrggbb (acepta hsl/rgb), así se le puede sumar alfa en hex.
const _cc = document.createElement("canvas").getContext("2d");
const css = v => {
  const raw = getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  if (!raw) return raw;
  _cc.fillStyle = "#000"; _cc.fillStyle = raw;
  return _cc.fillStyle;
};
const alpha = (c, a) => /^#[0-9a-f]{6}$/i.test(c) ? c + a : c;
const fmtPct = v => v == null ? "—" : `${Math.round(v)}%`;

const STATUS_COLOR = () => ({
  pending: css("--muted"), ok: css("--gl-ok"), octave: css("--gl-octave"), fixed: css("--gl-ok"),
  wrong: css("--gl-err"), missed: css("--gl-err"), timing: css("--gl-warn"), extra: css("--gl-info"),
  missing: css("--gl-err"), masked: css("--muted"), outside: css("--border"),
});
const ICON = { wrong: "✗", missed: "∅", missing: "∅", fixed: "↻", timing: "⏱", extra: "+", octave: "↕", ok: "✓" };

// ------------------------------------------------------------------ API
async function api(path, opts = {}) {
  const o = { ...opts };
  if (o.json !== undefined) {
    o.method = o.method || "POST";
    o.headers = { "Content-Type": "application/json" };
    o.body = JSON.stringify(o.json);
    delete o.json;
  }
  const r = await fetch(path, o);
  let data = null;
  try { data = await r.json(); } catch { /* sin cuerpo */ }
  if (!r.ok) throw new Error((data && (data.detail || data.error)) || `Error ${r.status}`);
  return data;
}

let toastTimer;
function toast(msg, ok = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "gl-toast" + (ok ? " ok" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 4500);
}

// ------------------------------------------------------------------ navegación (la maneja el router de main.js)
const VIEW_OF = { practicar: "practice", analizar: "analyze", afinador: "tuner", historial: "history", ajustes: "settings" };
const ROUTE_OF = Object.fromEntries(Object.entries(VIEW_OF).map(([r, v]) => [v, r]));
export const LISTENER_ROUTES = Object.keys(VIEW_OF);

export function hideListenerViews() {
  $$(".gl-view").forEach(v => (v.hidden = true));
  stopTuner();
}

export function showListenerView(route, params = {}) {
  const view = VIEW_OF[route];
  $$(".gl-view").forEach(v => (v.hidden = v.id !== "view-" + view));
  if (view === "history") loadHistory();
  if (view === "settings") loadSettings();
  if (view === "analyze") loadTakes();
  if (view !== "tuner") stopTuner();
  if (view === "practice" && params.cifrado) useSongChart(params.cifrado);
  requestAnimationFrame(() => drawTab());
}

function show(view) {
  const h = "#/" + ROUTE_OF[view];
  if (location.hash !== h) location.hash = h;
}

// ------------------------------------------------------------------ canciones (compartido)
const App = { songs: [], takes: [], preview: null, lane: null, snap: null, k: 0, kSmooth: 0, live: false, mode: "wait" };

async function loadSongs(select) {
  App.songs = await api("/api/songs");
  for (const sel of $$(".songSelect")) {
    const cur = select || sel.value;
    sel.innerHTML = App.songs.length
      ? App.songs.map(s => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join("")
      : `<option value="">(no hay canciones)</option>`;
    if (cur && App.songs.some(s => s.name === cur)) sel.value = cur;
  }
  if (!App.songs.length && !App.chart) showEmptyPractice();
}

function showEmptyPractice() {
  if (App.chart) return;
  $("#nowWhere").textContent = "subí una canción o cargá la demo";
  $("#log").innerHTML = `<li class="empty" style="display:block">
      Todavía no hay canciones. Subí un <b>MIDI</b> o <b>Guitar Pro</b> exportado de una tab (lo mejor),
      o un audio.<br><br><button class="btn primary" id="demoBtn">Cargar la demo</button></li>`;
  $("#demoBtn").onclick = async () => {
    try {
      const r = await api("/api/demo", { method: "POST" });
      await loadSongs(r.song);
      await loadTakes();
      $("#pSimulate").value = r.take;
      await onSongChange("p");
      $("#log").innerHTML = `<li class="info">Demo lista: tiene errores plantados. Como no tenés que enchufar nada,
        quedó elegida "Simular con una toma" en Avanzado. Probá el modo Tempo al 90%.</li>`;
      toast("Demo cargada", true);
    } catch (e) { toast(e.message); }
  };
}

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
      toast(`Subida: ${r.name}`, true);
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
      sel.innerHTML = tracks.map(t => `<option value="${t.index}">${t.index}. ${esc(t.name)} — ${esc(t.kind)} (${t.notes})</option>`).join("");
      const g = tracks.find(t => /guitar|cuerdas/i.test(t.kind));
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

// ------------------------------------------------------------------ cifrados
async function useSongChart(id) {
  try {
    const { chart } = await api(`/api/cifrados/${encodeURIComponent(id)}`);
    const info = { ...chart, bars: chart.bars.length };
    App.chart = info;
    $("#pChartBanner").hidden = false;
    $("#pSongField").hidden = true;
    $("#pTrackWrap").hidden = true;
    $("#pChartTitle").textContent = info.title;
    $("#pChartInfo").textContent = `${info.artist || ""} · ♩=${info.bpm}${info.capo ? " · capo " + info.capo : ""} · ${info.bars} compases`
      + (info.missing.length ? ` · sin digitación: ${info.missing.join(", ")}` : "");
    setMode("tempo");
    $("#pLoop").checked = false;
    $("#pStart").value = ""; $("#pEnd").value = "";
    $("#pTranspose").value = 0;
    $("#log").innerHTML = `<li class="muted">${esc(info.note || "Tocá con el metrónomo: un rasguido por acorde alcanza; los de relleno no cuentan como error.")}</li>`;
    loadPreview();
  } catch (e) { toast(e.message); }
}
$("#pChartClear").addEventListener("click", () => {
  App.chart = null;
  $("#pChartBanner").hidden = true;
  $("#pSongField").hidden = false;
  history.replaceState(null, "", "#/practicar");
  if (App.songs.length) onSongChange("p");
  else { App.lane = null; drawTab(); }
});

function refBody(prefix) {
  if (prefix === "p" && App.chart) {
    return { cifrado: App.chart.id, start_bar: $("#pStart").value || null, end_bar: $("#pEnd").value || null,
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
$("#aSong").addEventListener("change", () => onSongChange("a"));
$("#pTrack").addEventListener("change", loadPreview);
$("#pStart").addEventListener("change", loadPreview);
$("#pEnd").addEventListener("change", loadPreview);

// ------------------------------------------------------------------ vista previa (tab estática)
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
  if (!body.song && !body.cifrado) return;
  try {
    const pv = await api("/api/preview", { json: body });
    App.preview = pv;
    App.lane = groupEvents(pv.notes);
    App.k = App.kSmooth = 0;
    App.snap = null;
    $("#nowNote").firstChild.textContent = App.lane.length ? App.lane[0].label : "—";
    $("#nowWhere").textContent = `${pv.name}${pv.track ? " · " + pv.track : ""} · compases ${pv.first_bar}–${pv.last_bar} · ${App.lane.length} ${App.chart ? "acordes" : "notas"} · ♩=${pv.bpm}`;
    drawTab();
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ modo / opciones
function setMode(m) {
  App.mode = m;
  $$("#pMode button").forEach(b => b.classList.toggle("active", b.dataset.mode === m));
  $("#tempoOpts").hidden = m !== "tempo";
}
$$("#pMode button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode)));
$("#pSpeed").addEventListener("input", () => ($("#pSpeedVal").textContent = $("#pSpeed").value + "%"));
$("#pTrainer").addEventListener("change", () => {
  $("#trainerOpts").hidden = !$("#pTrainer").checked;
  if ($("#pTrainer").checked) $("#pLoop").checked = true;
});
$("#pSavePreset").addEventListener("click", async () => {
  const b = refBody("p");
  if (b.cifrado) return toast("Las opciones se recuerdan para archivos; los cifrados ya traen las suyas");
  try {
    await api("/api/presets", { json: { ...b, mode: App.mode, speed: $("#pSpeed").value / 100 } });
    await loadSongs();
    toast("Opciones guardadas para " + b.song, true);
  } catch (e) { toast(e.message); }
});

// ------------------------------------------------------------------ práctica en vivo
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
  b.textContent = on ? "■  Parar" : "▶  Empezar";
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
    simulate: $("#pSimulate").value || null,
  };
  if (!body.song && !body.cifrado) return toast("Elegí una canción primero");
  try {
    $("#liveReport").hidden = true;
    $("#log").innerHTML = "";
    App.logSeen = 0;
    connectLive();
    await api("/api/live/start", { json: body });
    setLive(true);
  } catch (e) { toast(e.message); setLive(false); }
});

function msgClass(m) {
  if (!m) return "";
  if (/^[✗∅+]/.test(m)) return "err";
  if (/^↻/.test(m)) return "info";
  return "ok";
}

function onState(s) {
  App.snap = s;
  if (!s.running) { if (s.done && App.live) setLive(false); return; }
  App.lane = s.lane;
  App.k = s.k;
  const cur = s.lane.find(e => e.current) || s.lane[s.lane.length - 1];
  $("#nowNote").firstChild.textContent = cur ? cur.label : "✓";
  $("#nowWhere").textContent = `compás ${s.bar} · tiempo ${s.beat.toFixed(2)} · nota ${Math.min(s.k + 1, s.total)}/${s.total}`;
  const lm = $("#lastMsg");
  lm.textContent = s.last || (s.mode === "tempo" ? "" : "Tocá la primera nota…");
  lm.className = "lastmsg " + msgClass(s.last);
  // chips
  const st = s.stats;
  const chips = [];
  if (st.pct != null) chips.push(`aciertos <b>${st.pct}%</b>`);
  chips.push(`errores <b>${st.errors}</b>`);
  if (st.extras) chips.push(`de más <b>${st.extras}</b>`);
  chips.push(`<span class="mono">${esc(s.source)}</span>`);
  $("#chips").innerHTML = chips.map(c => `<span class="chip">${c}</span>`).join("");
  // velocidad / cuenta
  $("#speedBadge").hidden = s.mode !== "tempo";
  $("#speedVal").textContent = Math.round(s.speed * 100) + "%";
  $("#countdown").hidden = !s.countdown;
  $("#countdown").textContent = s.countdown || "";
  $("#overlayMsg").hidden = !s.waiting_first;
  $("#overlayMsg").textContent = "Arrancá cuando quieras: el tempo se sincroniza con tu primera nota";
  // nivel
  const lv = Math.max(0, Math.min(1, (s.level_db + 60) / 60));
  $("#levelMeter > div").style.width = (lv * 100).toFixed(1) + "%";
  $("#levelMeter").classList.toggle("clip", s.peak >= 0.9);
  const lt = $("#levelTxt");
  lt.textContent = s.clip ? "¡CLIPEA! bajá la ganancia" : `${Math.round(s.level_db)} dB`;
  lt.className = s.clip ? "err" : (s.level_db < s.gate_db && s.now > 1 ? "warn" : "");
  if (s.tuning != null) {
    $("#tuneTxt").textContent = `${s.tuning > 0 ? "+" : ""}${Math.round(s.tuning)} cents` + (Math.abs(s.tuning) > 15 ? " — afiná" : "");
    $("#tuneTxt").className = Math.abs(s.tuning) > 15 ? "warn" : "";
    const tb = $("#tuneBar");
    const x = Math.max(-50, Math.min(50, s.tuning));
    tb.style.marginLeft = (50 + Math.min(0, x)) + "%";
    tb.style.width = Math.max(1, Math.abs(x)) + "%";
  }
  // log
  if (s.log.length) {
    $("#log").innerHTML = [...s.log].reverse().map(([t, m]) =>
      `<li class="${msgClass(m)}"><span class="t">${t.toFixed(2)}s</span><span>${esc(m)}</span></li>`).join("");
  }
  // vueltas
  renderPasses(s.passes);
}

function renderPasses(passes) {
  $("#passesPanel").hidden = !passes.length;
  $("#passes").innerHTML = passes.slice(-24).map((p, i) => {
    const cls = p.score >= 90 ? "" : p.score >= 65 ? "mid" : "low";
    const sp = p.speed ? `${Math.round(p.speed * 100)}%` : `#${i + 1}`;
    return `<div class="bar ${cls}" style="height:${Math.max(4, p.score * 0.7)}px" title="${p.score}% ${p.speed ? "a " + sp : ""}"><span>${sp}</span></div>`;
  }).join("");
}

function onReport(r) {
  setLive(false);
  if (r && r.award && App.rewarded !== r.date) {
    App.rewarded = r.date;
    if (r.award.xp) toast(`+${r.award.xp} XP por practicar`, true);
    progressChanged();
  }
  const el = $("#liveReport");
  el.hidden = false;
  el.innerHTML = renderReport(r);
  bindReport(el, r);
  el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ------------------------------------------------------------------ dibujo de la tablatura
const cv = $("#tabCanvas");
function drawTab() {
  const lane = App.lane;
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  if (!W) return;
  if (cv.width !== W * dpr) { cv.width = W * dpr; cv.height = H * dpr; }
  const g = cv.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, W, H);
  const top = 46, gap = 26, strings = 6;
  const colors = STATUS_COLOR();
  // cuerdas
  g.strokeStyle = css("--gl-string");
  g.lineWidth = 1;
  g.font = "600 11px ui-monospace, Menlo, monospace";
  g.fillStyle = css("--muted");
  const tun = (App.preview && App.preview.tuning) || [64, 59, 55, 50, 45, 40];
  for (let s = 0; s < strings; s++) {
    const y = top + s * gap;
    g.beginPath(); g.moveTo(34, y); g.lineTo(W - 8, y); g.stroke();
    g.fillText(NOTE_NAMES[tun[s] % 12] || "", 10, y + 4);
  }
  if (!lane || !lane.length) {
    g.fillStyle = css("--muted");
    g.font = "14px system-ui";
    g.textAlign = "center";
    g.fillText("La tablatura aparece acá", W / 2, top + 2.5 * gap + 5);
    g.textAlign = "left";
    return;
  }
  const spacing = Math.max(46, Math.min(80, W / 14));
  const cx = Math.min(W * 0.28, 260);
  // cursor
  g.fillStyle = alpha(css("--gl-accent"), "22");
  g.fillRect(cx - spacing / 2 + 4, top - 30, spacing - 8, (strings - 1) * gap + 52);
  g.textAlign = "center";
  for (const e of lane) {
    const x = cx + (e.i - App.kSmooth) * spacing;
    if (x < 20 || x > W + spacing) continue;
    const col = e.current ? css("--gl-accent") : colors[e.status] || colors.pending;
    const tab = (e.tab || []).filter(t => t && t[0]);
    if (tab.length) {
      for (const [s, f] of tab) {
        const y = top + (s - 1) * gap;
        const txt = String(f);
        g.font = (e.current ? "800 " : "700 ") + "15px ui-monospace, Menlo, monospace";
        const w = Math.max(18, g.measureText(txt).width + 10);
        g.fillStyle = css("--gl-panel");
        g.fillRect(x - w / 2, y - 9, w, 18);
        g.fillStyle = col;
        g.font = (e.current ? "800 " : "700 ") + "15px ui-monospace, Menlo, monospace";
        g.fillText(txt, x, y + 5);
      }
    } else {
      g.fillStyle = col;
      g.font = "700 13px system-ui";
      g.fillText(e.label, x, top + 2.5 * gap + 5);
    }
    // nombre de la nota abajo
    g.font = "11px system-ui";
    g.fillStyle = e.current ? css("--text") : css("--muted");
    g.fillText(e.label.length > 9 ? e.label.slice(0, 8) + "…" : e.label, x, top + (strings - 1) * gap + 24);
    // estado arriba
    if (e.status !== "pending") {
      g.fillStyle = col;
      g.font = "700 13px system-ui";
      const extra = e.dt != null && Math.abs(e.dt) >= 15 ? ` ${e.dt > 0 ? "+" : ""}${e.dt}` : "";
      g.fillText((ICON[e.status] || "") + extra, x, top - 16);
    }
  }
  g.textAlign = "left";
}

function animate() {
  const d = App.k - App.kSmooth;
  if (Math.abs(d) > 0.001) { App.kSmooth += d * 0.25; drawTab(); }
  requestAnimationFrame(animate);
}
window.addEventListener("resize", () => { drawTab(); drawRoll(); });

// ------------------------------------------------------------------ reportes (compartido)
function stat(v, l, cls = "") { return `<div class="stat ${cls}"><div class="v">${v}</div><div class="l">${l}</div></div>`; }

function renderReport(r) {
  const s = r.summary;
  let html = "";
  if (r.kind === "live") {
    html += `<h2>Resultado</h2><div class="summary">`;
    if (!s.judged) return html + `</div><p class="muted">No llegaste a tocar ninguna nota de la referencia.</p>`;
    html += stat(s.score != null ? Math.round(s.score) : "—", "puntaje", s.score >= 85 ? "good" : s.score >= 60 ? "warn" : "bad");
    html += stat(`${s.first_try}/${s.judged}`, `bien al primer intento (${fmtPct(s.first_try_pct)})`);
    if (r.mode === "wait") html += stat(s.fixed, "corregidas tras error", s.fixed ? "warn" : "");
    html += stat(s.wrong, "equivocadas", s.wrong ? "bad" : "good");
    html += stat(s.missed, "salteadas / no sonaron", s.missed ? "bad" : "good");
    if (r.mode === "tempo") {
      html += stat(s.extras, "notas de más", s.extras ? "warn" : "");
      if (s.timing_mean_ms != null) html += stat(`${s.timing_mean_ms > 0 ? "+" : ""}${Math.round(s.timing_mean_ms)} ms`, `timing promedio (±${Math.round(s.timing_std_ms)})`, Math.abs(s.timing_mean_ms) > 30 ? "warn" : "good");
    }
    if (s.tuning_cents != null && Math.abs(s.tuning_cents) > 15) html += stat(`${s.tuning_cents > 0 ? "+" : ""}${Math.round(s.tuning_cents)}¢`, "afinación: conviene afinar", "warn");
    html += `</div>`;
    if (r.passes && r.passes.length > 1) html += `<p class="muted">Vueltas: ${r.passes.map(p => `${Math.round(p.score)}%${p.speed ? " @" + Math.round(p.speed * 100) + "%" : ""}`).join(" · ")}</p>`;
  } else {
    html += `<h2>Resultado</h2><div class="summary">`;
    html += stat(Math.round(s.score), "puntaje", s.score >= 85 ? "good" : s.score >= 60 ? "warn" : "bad");
    html += stat(`${s.correct}/${s.ref_notes}`, `correctas (${fmtPct(s.correct_pct)})`);
    html += stat(s.wrong, "nota equivocada", s.wrong ? "bad" : "good");
    html += stat(s.missing, "faltantes", s.missing ? "bad" : "good");
    html += stat(s.extra, "de más", s.extra ? "warn" : "");
    html += stat(s.timing_loose, "con timing flojo", s.timing_loose ? "warn" : "good");
    html += stat(`${Math.round(100 * s.tempo_ratio)}%`, "tu tempo vs referencia");
    if (s.timing_mean_ms != null) html += stat(`${s.timing_mean_ms > 0 ? "+" : ""}${Math.round(s.timing_mean_ms)} ms`, Math.abs(s.timing_mean_ms) < 15 ? "a tiempo" : s.timing_mean_ms > 0 ? "tendés a ir atrás" : "tendés a apurarte");
    html += `</div>`;
    if (s.masked) html += `<p class="muted">+${s.masked} octavas de acorde no detectables, ignoradas.</p>`;
  }
  if (r.messages && r.messages.length) html += r.messages.map(m => `<p class="callout">${esc(m)}</p>`).join("");
  // mapa de compases
  if (r.bars && r.bars.length) {
    html += `<h3>Por compás</h3><div class="heat">` + r.bars.map(b => {
      const rate = b.notes ? (b.errors + 0.5 * b.timing) / b.notes : 0;
      const col = rate === 0 ? css("--gl-ok") : rate < 0.25 ? css("--gl-warn") : css("--gl-err");
      return `<div data-bar="${b.bar}" title="compás ${b.bar}: ${b.errors} errores, ${b.timing} de timing" style="background:${alpha(col, rate === 0 ? "33" : "88")};color:var(--text)">${b.bar}</div>`;
    }).join("") + `</div>`;
    const worst = [...r.bars].map(b => ({ ...b, rate: b.notes ? (b.errors + 0.5 * b.timing) / b.notes : 0 }))
      .filter(b => b.rate > 0).sort((a, b) => b.rate - a.rate).slice(0, 2);
    if (worst.length) {
      const a = Math.min(...worst.map(w => w.bar)), z = Math.max(...worst.map(w => w.bar));
      html += `<div class="callout" style="margin-top:12px"><span>Lo más flojo: <b>compás ${worst.map(w => w.bar).join(" y ")}</b>.</span>
        <button class="btn primary small" data-practice="${a}-${z}">Practicar compases ${a}–${z} con el entrenador</button></div>`;
    }
  }
  if (r.issues && r.issues.length) {
    html += `<h3>Detalle (${r.issues.length})</h3><table class="issues">` + r.issues.map(it =>
      `<tr class="t-${it.type}" data-t="${it.t}"><td class="ico">${ICON[it.type] || "·"}</td><td class="muted mono" style="white-space:nowrap">c.${it.bar} t.${it.beat.toFixed(2)}</td><td>${esc(it.msg.replace(/^[✗∅+⏱↕]\s+/, ""))}</td></tr>`).join("") + `</table>`;
  } else html += `<p style="color:var(--gl-ok);font-weight:600;margin-top:14px">¡Sin errores! 🎉</p>`;
  if (r.take && r.kind === "live") {
    const name = r.take.split("/").pop();
    html += `<div class="callout" style="margin-top:14px"><span>Tu toma quedó grabada.</span><button class="btn small" data-analyze="${esc(name)}">Analizarla en detalle</button></div>
      <audio controls src="/takes/${encodeURIComponent(name)}"></audio>`;
  }
  return html;
}

function bindReport(el, r) {
  const p = $("[data-practice]", el);
  if (p) p.onclick = () => {
    const [a, z] = p.dataset.practice.split("-");
    const song = r.reference && r.reference.path ? r.reference.path.split("/").pop() : $("#pSong").value;
    practiceBars(song, +a, +z);
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
  $$(".heat div", el).forEach(d => d.onclick = () => {
    const song = r.reference && r.reference.path ? r.reference.path.split("/").pop() : $("#pSong").value;
    practiceBars(song, +d.dataset.bar, +d.dataset.bar);
  });
  $$(".issues tr", el).forEach(tr => tr.onclick = () => { if (App.roll) scrollRollTo(+tr.dataset.t); });
}

async function practiceBars(song, a, z) {
  show("practice");
  if (song && song.startsWith("cifrado:")) await useSongChart(song.slice("cifrado:".length));
  else if (song && App.songs.some(s => s.name === song)) { $("#pSong").value = song; await loadTracks("p"); }
  $("#pStart").value = Math.max(1, a);
  $("#pEnd").value = z;
  setMode("tempo");
  $("#pSpeed").value = 70; $("#pSpeedVal").textContent = "70%";
  $("#pTrainer").checked = true; $("#trainerOpts").hidden = false; $("#pLoop").checked = true;
  await loadPreview();
  toast(`Listo: compases ${a}–${z} al 70% con el entrenador. Apretá Empezar.`, true);
}

// ------------------------------------------------------------------ analizar toma
async function loadTakes(select) {
  try { App.takes = await api("/api/takes"); } catch { App.takes = []; }
  const opts = App.takes.map(t => `<option value="${esc(t.name)}">${esc(t.name)}</option>`).join("");
  const cur = select || $("#aTake").value;
  $("#aTake").innerHTML = opts || `<option value="">(no hay tomas grabadas)</option>`;
  if (cur && App.takes.some(t => t.name === cur)) $("#aTake").value = cur;
  const simCur = $("#pSimulate").value;
  $("#pSimulate").innerHTML = `<option value="">— no, usar la guitarra —</option>` + opts;
  if (simCur) $("#pSimulate").value = simCur;
}

$("#aRun").addEventListener("click", runAnalysis);
async function runAnalysis() {
  const body = { ...refBody("a"), take: $("#aTake").value, timing_tol_ms: $("#aTol").value };
  const up = $("#aTakeUpload").files[0];
  if (!body.song) return toast("Elegí la referencia");
  if (!body.take && !up) return toast("Elegí o subí tu toma");
  const fd = new FormData();
  fd.append("options", JSON.stringify(body));
  if (up) fd.append("take", up);
  const btn = $("#aRun");
  btn.disabled = true;
  btn.innerHTML = `<span class="spinner"></span> Transcribiendo…`;
  $("#aResult").innerHTML = `<div class="panel empty"><span class="spinner"></span> Escuchando tu toma (basic-pitch). La primera vez tarda unos segundos; después queda en caché.</div>`;
  try {
    const r = await api("/api/analyze", { method: "POST", body: fd });
    $("#aTakeUpload").value = "";
    await loadTakes(r.take_name);
    renderAnalysis(r);
    if (r.award && r.award.xp) toast(`+${r.award.xp} XP por analizar tu toma`, true);
    progressChanged();
  } catch (e) {
    $("#aResult").innerHTML = `<div class="panel empty">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Analizar";
  }
}

function renderAnalysis(r) {
  App.roll = r;
  $("#aResult").innerHTML = `
    <div class="panel" id="aReport"></div>
    <div class="panel">
      <div class="row" style="align-items:center"><h2 style="margin:0">Referencia vs. lo que tocaste</h2>
        <label style="flex:none;display:flex;gap:8px;align-items:center" class="muted">zoom <input type="range" id="rollZoom" min="40" max="400" value="120" style="width:120px"></label></div>
      <div class="legend">
        <span><i style="border:1.5px solid var(--muted)"></i>referencia</span>
        <span><i style="background:var(--gl-ok)"></i>bien</span>
        <span><i style="background:var(--gl-warn)"></i>timing</span>
        <span><i style="background:var(--gl-err)"></i>nota equivocada / faltante</span>
        <span><i style="background:var(--gl-octave)"></i>otra octava</span>
        <span><i style="background:var(--gl-info)"></i>de más</span>
      </div>
      <div class="rollwrap" id="rollWrap"><canvas id="rollCanvas"></canvas></div>
      ${r.take_name ? `<audio controls src="/takes/${encodeURIComponent(r.take_name)}"></audio>` : ""}
    </div>`;
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
  const pps = +$("#rollZoom").value;   // píxeles por segundo
  const all = [...r.roll.ref, ...r.roll.user];
  const tEnd = Math.max(...all.map(n => n[1])) + 0.5;
  const pMin = Math.min(...all.map(n => n[2])) - 2, pMax = Math.max(...all.map(n => n[2])) + 2;
  const rowH = Math.max(6, Math.min(14, 360 / (pMax - pMin + 1)));
  const left = 44, W = Math.ceil(left + tEnd * pps + 20), H = Math.ceil((pMax - pMin + 1) * rowH + 30);
  const dpr = window.devicePixelRatio || 1;
  c.width = W * dpr; c.height = H * dpr; c.style.width = W + "px"; c.style.height = H + "px";
  const g = c.getContext("2d");
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  const X = t => left + t * pps, Y = p => 22 + (pMax - p) * rowH;
  const col = STATUS_COLOR();
  // filas de notas
  g.font = "10px ui-monospace, Menlo, monospace";
  for (let p = pMin; p <= pMax; p++) {
    if ([1, 3, 6, 8, 10].includes(((p % 12) + 12) % 12)) { g.fillStyle = css("--gl-panel"); g.fillRect(left, Y(p), W - left, rowH); }
    if (p % 12 === 0 || p % 12 === 4 || p % 12 === 9) { g.fillStyle = css("--muted"); g.fillText(noteName(p), 4, Y(p) + rowH - 2); }
  }
  // compases
  g.strokeStyle = css("--border");
  g.fillStyle = css("--muted");
  (r.downbeats || []).forEach((t, i) => {
    g.beginPath(); g.moveTo(X(t), 14); g.lineTo(X(t), H); g.stroke();
    if (pps * ((r.downbeats[1] || t + 1) - (r.downbeats[0] || 0)) > 24 || i % 4 === 0) g.fillText(String(i + 1), X(t) + 3, 11);
  });
  // referencia (contorno)
  for (const [s, e, p, st] of r.roll.ref) {
    g.strokeStyle = st === "missing" ? col.missing : css("--muted");
    g.lineWidth = st === "missing" ? 2 : 1.2;
    g.setLineDash(st === "missing" ? [3, 2] : []);
    g.strokeRect(X(s), Y(p) + 0.5, Math.max(3, (e - s) * pps), rowH - 1);
  }
  g.setLineDash([]);
  // lo tuyo (relleno)
  for (const [s, e, p, st] of r.roll.user) {
    g.fillStyle = alpha(col[st] || col.ok, "cc");
    g.fillRect(X(s), Y(p) + 2, Math.max(3, (e - s) * pps), rowH - 4);
  }
}

function scrollRollTo(t) {
  const w = $("#rollWrap");
  if (!w) return;
  const pps = +$("#rollZoom").value;
  w.scrollTo({ left: Math.max(0, 44 + t * pps - w.clientWidth / 3), behavior: "smooth" });
}

// ------------------------------------------------------------------ afinador
let tws = null;
const STD = [[64, "1ra", "E4"], [59, "2da", "B3"], [55, "3ra", "G3"], [50, "4ta", "D3"], [45, "5ta", "A2"], [40, "6ta", "E2"]];
function initTuner() {
  $("#tStrings").innerHTML = STD.slice().reverse().map(([m, n, l]) => `<div data-m="${m}"><b>${l}</b><small>${n}</small></div>`).join("");
  let ticks = "";
  for (let c = -50; c <= 50; c += 10) {
    const a = (c / 50) * (Math.PI / 2) * 0.98;
    const x1 = 200 + Math.sin(a) * 150, y1 = 200 - Math.cos(a) * 150, x2 = 200 + Math.sin(a) * (c % 50 === 0 || c === 0 ? 132 : 140), y2 = 200 - Math.cos(a) * (c % 50 === 0 || c === 0 ? 132 : 140);
    ticks += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="var(--muted)" stroke-width="2"/>`;
  }
  $("#ticks").innerHTML = ticks;
}
$("#tStart").addEventListener("click", () => (tws ? stopTuner() : startTuner()));
function startTuner() {
  if (App.live) return toast("Pará la práctica para usar el afinador");
  tws = new WebSocket(`ws://${location.host}/ws/tuner`);
  $("#tStart").textContent = "Apagar afinador";
  tws.onmessage = ev => {
    const r = JSON.parse(ev.data);
    if (r.error) { toast(r.error); stopTuner(); return; }
    if (r.source) { $("#tSource").textContent = "entrada: " + r.source; return; }
    const note = $("#tNote");
    if (!r.note) {
      note.textContent = "—"; note.className = "note";
      $("#tCents").textContent = r.level_db < -55 ? "Tocá una cuerda al aire" : "…";
      $("#needle").style.transform = "rotate(0deg)";
      $$("#tStrings div").forEach(d => d.className = "");
      return;
    }
    const cents = r.string_cents != null ? r.string_cents : r.cents;
    const ok = Math.abs(cents) <= 5;
    note.textContent = r.note; note.className = "note" + (ok ? " ok" : "");
    $("#tCents").textContent = `${cents > 0 ? "+" : ""}${cents.toFixed(1)} cents · ${r.freq.toFixed(1)} Hz` + (r.string ? ` · cuerda ${r.string}: ${ok ? "✓ afinada" : cents < 0 ? "subí" : "bajá"}` : "");
    const deg = Math.max(-50, Math.min(50, cents)) / 50 * 88;
    $("#needle").style.transform = `rotate(${deg}deg)`;
    const near = STD.reduce((a, b) => Math.abs(b[0] - r.midi) < Math.abs(a[0] - r.midi) ? b : a);
    $$("#tStrings div").forEach(d => d.className = +d.dataset.m === near[0] && Math.abs(near[0] - r.midi) < 0.75 ? (ok ? "ok" : "on") : "");
  };
  tws.onclose = () => { tws = null; $("#tStart").textContent = "Encender afinador"; };
}
function stopTuner() { if (tws) { tws.close(); tws = null; } $("#tStart").textContent = "Encender afinador"; }

// ------------------------------------------------------------------ historial
async function loadHistory() {
  const songs = await api("/api/history");
  const el = $("#hSongs");
  if (!songs.length) { el.innerHTML = `<p class="muted">Todavía no hay sesiones guardadas. Se guardan solas cuando practicás o analizás una toma.</p>`; return; }
  el.innerHTML = songs.map(s => `<button data-id="${esc(s.id)}"><b>${esc(s.name)}</b>${s.track ? ` <span class="muted">· ${esc(s.track)}</span>` : ""}
     <small>${s.sessions} sesiones · última ${esc((s.last_date || "").slice(0, 10))} · ${fmtPct(s.last_score)}</small></button>`).join("");
  $$("button", el).forEach(b => b.onclick = () => {
    $$("button", el).forEach(x => x.classList.toggle("active", x === b));
    loadSongHistory(b.dataset.id);
  });
}

async function loadSongHistory(id) {
  const h = await api(`/api/history/${encodeURIComponent(id)}`);
  const ss = h.sessions;
  const pb = h.problem_bars;
  let html = `<div class="panel"><h2>${esc(h.reference.name || id)} — progreso</h2><svg id="histChart" viewBox="0 0 800 220" preserveAspectRatio="none"></svg>
    <div class="legend"><span><i style="background:var(--gl-accent)"></i>puntaje</span><span><i style="background:var(--gl-info)"></i>velocidad (modo tempo)</span></div></div>`;
  if (pb.length) {
    const a = Math.min(...pb.slice(0, 2).map(b => b.bar)), z = Math.max(...pb.slice(0, 2).map(b => b.bar));
    html += `<div class="panel"><h2>Compases más flojos</h2><div class="summary">` +
      pb.map(b => stat(`c. ${b.bar}`, `${Math.round(100 * b.rate)}% de error`, b.rate > 0.3 ? "bad" : "warn")).join("") +
      `</div>${h.song ? `<div class="callout" style="margin-top:12px"><span>Practicalos lento y que el entrenador vaya subiendo la velocidad.</span><button class="btn primary small" id="hPractice">Practicar compases ${a}–${z}</button></div>` : ""}</div>`;
    App.histPractice = [h.song, a, z];
  }
  html += `<div class="panel"><h2>Sesiones</h2><table class="sessions"><tr><th>Fecha</th><th>Tipo</th><th>Compases</th><th>Velocidad</th><th>Puntaje</th></tr>` +
    ss.slice().reverse().map(s => `<tr><td>${esc((s.date || "").replace("T", " ").slice(0, 16))}</td><td>${s.kind === "file" ? "toma" : (s.mode === "tempo" ? "tempo" : "espera")}</td>
      <td>${s.section ? `${s.section.start_bar || 1}–${s.section.end_bar || "fin"}` : "todo"}</td>
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

// ------------------------------------------------------------------ ajustes
async function loadSettings() {
  const [dv, cfg] = await Promise.all([api("/api/devices"), api("/api/config")]);
  if (dv.error) toast(dv.error);
  const a = cfg.audio;
  $("#sDevice").innerHTML = dv.inputs.map(d => `<option value="${d.index}">${d.index}. ${esc(d.name)} (${d.channels} canales)${d.index === dv.suggested ? " — parece tu interfaz" : ""}</option>`).join("");
  if (a.device != null) $("#sDevice").value = typeof a.device === "number" ? a.device : (dv.inputs.find(d => d.name === a.device) || {}).index;
  $("#sOutput").innerHTML = `<option value="">(la del sistema)</option>` + dv.outputs.map(d => `<option value="${d.index}">${d.index}. ${esc(d.name)}</option>`).join("");
  $("#sOutput").value = a.output_device ?? "";
  $("#sChannel").value = a.channel || 1;
  $("#sGate").value = a.gate_db ?? -50; $("#sGateVal").textContent = $("#sGate").value + " dB";
  $("#sSens").value = a.sensitivity ?? 1; $("#sSensVal").textContent = (+$("#sSens").value).toFixed(1);
  $("#sLatency").value = a.latency_ms ?? 0;
  $("#sPath").textContent = "Se guarda en " + cfg.path;
}
$("#sGate").addEventListener("input", () => ($("#sGateVal").textContent = $("#sGate").value + " dB"));
$("#sSens").addEventListener("input", () => ($("#sSensVal").textContent = (+$("#sSens").value).toFixed(1)));
$("#sSave").addEventListener("click", async () => {
  try {
    await api("/api/config", { json: { device: $("#sDevice").value, channel: $("#sChannel").value, output_device: $("#sOutput").value, gate_db: $("#sGate").value, sensitivity: $("#sSens").value, latency_ms: $("#sLatency").value } });
    toast("Ajustes guardados", true);
    refreshDevicePill();
  } catch (e) { toast(e.message); }
});
$("#cStart").addEventListener("click", async () => {
  try {
    await api("/api/calibrate", { json: {} });
    $("#cStart").disabled = true;
    const poll = setInterval(async () => {
      const s = await api("/api/calibrate");
      if (s.running) {
        $("#cStatus").innerHTML = s.warmup ? `<span class="muted">Agarrá el pulso… ${s.beat}/${s.total}</span>` : `<b style="color:var(--gl-accent)">¡Tocá con cada click! ${s.beat}/${s.total}</b>`;
      } else {
        clearInterval(poll);
        $("#cStart").disabled = false;
        const r = s.result || {};
        $("#cStatus").innerHTML = r.ok ? `<b style="color:var(--gl-ok)">✓ ${esc(r.message)}</b> — guardada.` : `<span style="color:var(--gl-err)">${esc(r.message || "Falló la calibración")}</span>`;
        if (r.ok) $("#sLatency").value = r.latency_ms;
      }
    }, 150);
  } catch (e) { toast(e.message); }
});

async function refreshDevicePill() {
  try {
    const [dv, cfg] = await Promise.all([api("/api/devices"), api("/api/config")]);
    const a = cfg.audio;
    const d = dv.inputs.find(x => x.index === a.device || x.name === a.device);
    $("#deviceName").textContent = d ? `${d.name} · canal ${a.channel || 1}` : "entrada por defecto del sistema";
  } catch { $("#deviceName").textContent = "audio no disponible"; }
}

// ------------------------------------------------------------------ inicio
(async function init() {
  initTuner();
  animate();
  refreshDevicePill();
  await loadTakes();
  await loadSongs();
  if (App.songs.length) { await onSongChange("p"); await onSongChange("a"); }
  // si había una sesión corriendo (recargaste la página), reengancharse
  try {
    const st = await api("/api/live/state");
    if (st.active && st.state.running) { setLive(true); connectLive(); }
  } catch { }
  drawTab();
})();
