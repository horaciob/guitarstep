// The guitar as heard by this browser, for the web service: the raw input (no effects: the listener
// grades the clean signal) goes to the server over /ws/stream, and the metronome clicks the server
// schedules are played here, on the same audio clock as the input.
import { api } from "./ui.js";
import { t } from "./i18n.js";

let current = null;
// asked once, up front, so starting to listen doesn't wait for another round trip
const service = api("/api/status").then(s => !!s.service, () => false);

export function isService() {
  return service;
}

const NAME_KEY = "guitarr.inputName";

/** The name of the input last opened in this browser (its latency calibration is kept by that name). */
export function lastInputName() {
  try { return localStorage.getItem(NAME_KEY) || ""; } catch { return ""; }
}

/** Opens the input: { ctx, sr, name, latency_ms, onBlock(fn), close() }. Blocks are { start, samples, t0 }. */
export async function openInput() {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: {
      echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } });
  } catch (e) {
    throw Object.assign(new Error(t("errors.no_microphone")), { code: "no_microphone", cause: e });
  }
  const ctx = new AudioContext({ latencyHint: "interactive" });
  try {
    await ctx.audioWorklet.addModule("/static/lib/stream-worklet.js");
  } catch (e) { stream.getTracks().forEach(tr => tr.stop()); ctx.close(); throw e; }
  const src = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "stream-capture", { numberOfOutputs: 0 });
  const track = stream.getAudioTracks()[0], settings = track.getSettings();
  try { localStorage.setItem(NAME_KEY, track.label || ""); } catch { /* private mode */ }
  // what the listener subtracts: input latency plus output latency (you play along with the clicks)
  const latency_ms = 1000 * ((settings.latency || 0) + (ctx.baseLatency || 0) + (ctx.outputLatency || 0));
  let closed = false;
  return {
    ctx, sr: ctx.sampleRate, name: track.label || "", latency_ms,
    onBlock(fn) { node.port.onmessage = e => fn(e.data); src.connect(node); },
    close() {
      if (closed) return;
      closed = true;
      node.port.onmessage = null;
      try { src.disconnect(); } catch { /* not connected yet */ }
      stream.getTracks().forEach(tr => tr.stop());
      ctx.close();
    },
  };
}

/** Sends the input's blocks over an open /ws/stream socket. */
export function frame(block) {
  const buf = new ArrayBuffer(8 + block.samples.byteLength);
  new DataView(buf).setBigUint64(0, BigInt(block.start), true);
  new Float32Array(buf, 8).set(block.samples);
  return buf;
}

/** The name of an input as the server reports it ("browser" is this page's own input). */
export const sourceName = name => (name === "browser" ? t("account.browser_input") : name);

/** A socket to a listener of the input (/ws/tuner, /ws/signal). As a web service the server waits for this
 *  browser's input: it's opened here and streamed over the same socket ({type: "start", sr} first). A blocked
 *  microphone arrives as a message like the server's errors: {error: {code, message}}. */
export function inputSocket(path, params = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ""));
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}${path}${qs.toString() ? "?" + qs : ""}`);
  ws.binaryType = "arraybuffer";
  let input = null;
  if (!params.simulate) ws.addEventListener("open", async () => {
    if (!(await isService())) return;
    try { input = await openInput(); } catch (e) {
      ws.dispatchEvent(new MessageEvent("message", { data: JSON.stringify({ error: { code: e.code || "audio", message: e.message } }) }));
      ws.close();
      return;
    }
    if (ws.readyState !== 1) { input.close(); return; }
    ws.send(JSON.stringify({ type: "start", sr: input.sr }));
    input.onBlock(b => { if (ws.readyState === 1) ws.send(frame(b)); });
  });
  ws.addEventListener("close", () => input && input.close());
  return ws;
}

/** Plays sounds given in seconds of the stream once t0 (the context time of sample 0) is known.
 *  `sound(at, key)` makes one at context time `at`. */
function scheduler(ctx, sound) {
  const queue = [];
  let t0 = null;
  const timer = setInterval(() => {
    if (t0 === null) return;
    const horizon = ctx.currentTime + 0.3;
    while (queue.length && t0 + queue[0][0] < horizon) {
      const [ct, key] = queue.shift(), at = t0 + ct;
      if (at >= ctx.currentTime) sound(at, key);       // too late to play: skip it
    }
  }, 50);
  return {
    add(items) { queue.push(...items); queue.sort((a, b) => a[0] - b[0]); },
    start(t) { if (t0 === null) t0 = t; },
    stop() { clearInterval(timer); queue.length = 0; },
  };
}

/** The metronome: a click is [time, accent], or [time, i] with `tones` (Hz): the cable test gives each its own tone. */
export function clickPlayer(ctx, tones = null) {
  return scheduler(ctx, (at, accent) => {
    const osc = ctx.createOscillator(), g = ctx.createGain();
    osc.frequency.value = tones ? tones[accent] : accent ? 1600 : 1000;
    g.gain.setValueAtTime(0.5, at);
    g.gain.exponentialRampToValueAtTime(0.001, at + 0.04);
    osc.connect(g).connect(ctx.destination);
    osc.start(at);
    osc.stop(at + 0.05);
  });
}

/** Bass & drums for a chart: [time, "kick" | "snare" | "hat" | "bass:<midi>"], the sounds of audio_io.BackingSounds. */
export function backingPlayer(ctx, volume = 0.5) {
  const out = ctx.createGain();
  out.gain.value = volume;
  out.connect(ctx.destination);
  const noise = ctx.createBuffer(1, Math.round(0.2 * ctx.sampleRate), ctx.sampleRate);
  const d = noise.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  const env = (at, peak, decay, len) => {
    const g = ctx.createGain();
    g.gain.setValueAtTime(peak, at);
    g.gain.setTargetAtTime(0, at, decay);
    g.connect(out);
    return [g, at + len];
  };
  const tone = (at, freq, peak, decay, len, glide = null) => {
    const osc = ctx.createOscillator(), [g, end] = env(at, peak, decay, len);
    osc.frequency.setValueAtTime(freq, at);
    if (glide) osc.frequency.setTargetAtTime(glide, at, 0.03);
    osc.connect(g); osc.start(at); osc.stop(end);
  };
  const hiss = (at, peak, decay, len, cutoff) => {
    const src = ctx.createBufferSource(), hp = ctx.createBiquadFilter(), [g, end] = env(at, peak, decay, len);
    src.buffer = noise; hp.type = "highpass"; hp.frequency.value = cutoff;
    src.connect(hp).connect(g); src.start(at); src.stop(end);
  };
  return scheduler(ctx, (at, key) => {
    if (key === "kick") tone(at, 120, 0.9, 0.09, 0.25, 45);
    else if (key === "snare") { hiss(at, 0.35, 0.05, 0.18, 1500); tone(at, 185, 0.3, 0.03, 0.18); }
    else if (key === "hat") hiss(at, 0.12, 0.012, 0.05, 7000);
    else if (key.startsWith("bass:")) {
      const f = 440 * 2 ** ((+key.slice(5) - 69) / 12);
      [[1, 0.7], [2, 0.245], [3, 0.084]].forEach(([h, a]) => tone(at, f * h, a, 0.35, 0.7));
    }
  });
}

/** /api/live/start, with the guitar coming from this browser when this is the web service. */
export async function startLive(payload) {
  stopInput();
  if (payload.simulate || !(await isService())) return api("/api/live/start", { json: payload });
  const input = await openInput();
  let r;
  try {
    r = await api("/api/live/start", { json: { ...payload, input: "browser", sr: input.sr, input_name: input.name,
      latency_ms: input.latency_ms } });
  } catch (e) { input.close(); throw e; }
  attach(input, { type: "attach" });
  return r;
}

/** /api/calibrate: as a web service this browser plays the clicks and sends what its input hears. */
export async function startCalibration(body) {
  stopInput();
  if (!(await isService())) return api("/api/calibrate", { json: body });
  const input = await openInput();
  let r;
  try {
    r = await api("/api/calibrate", { json: { ...body, input: "browser", sr: input.sr, input_name: input.name } });
  } catch (e) { input.close(); throw e; }
  attach(input, { type: "attach", to: "calibrate" }, r.clicks, r.tones);
  return r;
}

/** Streams the input to what the server opened for it (over /ws/stream) and plays its clicks. */
function attach(input, hello, clicksNow = [], tones = null) {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/stream`);
  ws.binaryType = "arraybuffer";
  const clicks = clickPlayer(input.ctx, tones), backing = backingPlayer(input.ctx);
  clicks.add(clicksNow);
  const me = current = { close() { clicks.stop(); backing.stop(); input.close(); if (ws.readyState <= 1) ws.close(); if (current === me) current = null; } };
  ws.onopen = () => ws.send(JSON.stringify(hello));
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === "ready") {
      input.onBlock(b => { clicks.start(b.t0); backing.start(b.t0); if (ws.readyState === 1) ws.send(frame(b)); });
    } else if (m.type === "clicks") clicks.add(m.clicks);
    else if (m.type === "backing") backing.add(m.items);
    else if (m.type === "ended" || m.type === "error") me.close();
  };
  ws.onclose = () => me.close();
}

export function stopInput() {
  if (current) current.close();
}
