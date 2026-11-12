// Web service, phase 0: the guitar captured in this browser, sent over a WebSocket and graded by the
// server with the same listener. Shows the measurements that decide whether this is enough:
// response time, lost audio and server CPU per second of playing. Nothing is recorded as progress.
import { msgText, t } from "../lib/i18n.js";
import { $, api, esc } from "../lib/ui.js";
import { frame, openInput } from "../lib/browser-input.js";

let run = null;

export async function mount(el) {
  const songs = await api("/api/songs").catch(() => []);
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("stream.title"))}</h1><p class="muted">${esc(t("stream.subtitle"))}</p></div>
    <form class="panel row wrap" id="streamForm">
      <label class="field grow"><span>${esc(t("stream.song"))}</span>
        <select id="streamSong" aria-describedby="streamErr">${songs.map(s => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("stream.mode"))}</span>
        <select id="streamMode"><option value="wait">${esc(t("stream.mode_wait"))}</option><option value="tempo">${esc(t("stream.mode_tempo"))}</option></select></label>
      <button class="btn primary" type="submit" id="streamGo">${esc(t("stream.start"))}</button>
      <button class="btn" type="button" id="streamStop" hidden>${esc(t("stream.stop"))}</button>
      <p class="field-error" id="streamErr" hidden></p>
    </form>
    <section class="panel" aria-live="polite">
      <p id="streamMsg" class="muted">${esc(songs.length ? t("stream.idle") : t("stream.no_songs"))}</p>
      <dl class="stream-metrics" id="streamMetrics"></dl>
    </section>`;
  const err = $("#streamErr", el), showErr = m => { err.textContent = m; err.hidden = false; };
  $("#streamForm", el).onsubmit = async ev => {
    ev.preventDefault();
    err.hidden = true;
    if (!$("#streamSong", el).value) { showErr(t("stream.no_songs")); return; }
    try {
      run = await start(el, { song: $("#streamSong", el).value, mode: $("#streamMode", el).value }, showErr);
    } catch (e) { showErr(e.name === "NotAllowedError" ? t("stream.err_mic") : e.message); }
  };
  $("#streamStop", el).onclick = () => run && run.stop();
}

export function unmount() {
  if (run) run.close();
  run = null;
}

async function start(el, body, showErr) {
  const input = await openInput();
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/stream`);
  ws.binaryType = "arraybuffer";
  const m = { rtt: [], sent: 0 };
  let ping = 0;
  const close = () => {
    clearInterval(ping);
    input.close();
    if (ws.readyState <= 1) ws.close();
    $("#streamGo", el).hidden = false;
    $("#streamStop", el).hidden = true;
  };
  ws.onopen = () => ws.send(JSON.stringify({ type: "start", sr: input.sr, latency_ms: input.latency_ms, ...body }));
  ws.onerror = () => { showErr(t("stream.err_connection")); close(); };
  ws.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "ready") {
      input.onBlock(b => {
        if (ws.readyState === 1) ws.send(frame(b));
        m.sent = (b.start + b.samples.length) / input.sr;
      });
      ping = setInterval(() => ws.send(JSON.stringify({ type: "ping", t: performance.now() })), 1000);
      $("#streamGo", el).hidden = true;
      $("#streamStop", el).hidden = false;
    } else if (msg.type === "pong") {
      m.rtt = [...m.rtt.slice(-19), performance.now() - msg.t];
    } else if (msg.type === "state") {
      const s = msg.state;
      $("#streamMsg", el).textContent = s.last ? msgText(s.last) : t("stream.listening");
      show(el, m, msg.metrics, s.stats);
    } else if (msg.type === "report") {
      $("#streamMsg", el).textContent = t("stream.done", { judged: msg.report.summary.judged });
      show(el, m, msg.metrics, null);
      close();
    } else if (msg.type === "error") {
      showErr(t(`errors.${msg.detail.code}`, { defaultValue: msg.detail.message }));
      close();
    }
  };
  return { stop: () => { if (ws.readyState === 1) ws.send(JSON.stringify({ type: "stop" })); }, close };
}

function show(el, m, met, stats) {
  const med = a => a.length ? [...a].sort((x, y) => x - y)[a.length >> 1] : null;
  const rtt = med(m.rtt), behind = Math.max(0, m.sent - met.heard_s) * 1000;
  const rows = [
    ["stream.m_rtt", rtt == null ? "—" : t("stream.ms", { n: Math.round(rtt) })],
    ["stream.m_behind", t("stream.ms", { n: Math.round(behind) })],
    ["stream.m_heard", t("stream.s", { n: met.heard_s.toFixed(1) })],
    ["stream.m_gaps", String(met.gaps)],
  ];
  if (stats && stats.judged) rows.push(["stream.m_score", t("stream.pct", { n: stats.pct, judged: stats.judged })]);
  if (met.cpu_per_audio_s) rows.push(["stream.m_cpu", t("stream.cpu", {
    pct: (100 * met.cpu_per_audio_s).toFixed(1), n: Math.floor(1 / met.cpu_per_audio_s) })]);
  $("#streamMetrics", el).innerHTML = rows.map(([k, v]) => `<dt>${esc(t(k))}</dt><dd>${esc(v)}</dd>`).join("");
}
