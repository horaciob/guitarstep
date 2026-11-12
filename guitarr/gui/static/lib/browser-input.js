// The guitar as heard by this browser, for the web service: the raw input (no effects: the listener
// grades the clean signal) goes to the server over /ws/stream, and the metronome clicks the server
// schedules are played here, on the same audio clock as the input.
import { api } from "./ui.js";

let current = null;
// asked once, up front, so starting to listen doesn't wait for another round trip
const service = api("/api/status").then(s => !!s.service, () => false);

export function isService() {
  return service;
}

/** Opens the input: { ctx, sr, latency_ms, onBlock(fn), close() }. Blocks are { start, samples, t0 }. */
export async function openInput() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: {
    echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 } });
  const ctx = new AudioContext({ latencyHint: "interactive" });
  try {
    await ctx.audioWorklet.addModule("/static/lib/stream-worklet.js");
  } catch (e) { stream.getTracks().forEach(tr => tr.stop()); ctx.close(); throw e; }
  const src = ctx.createMediaStreamSource(stream);
  const node = new AudioWorkletNode(ctx, "stream-capture", { numberOfOutputs: 0 });
  const settings = stream.getAudioTracks()[0].getSettings();
  // what the listener subtracts: input latency plus output latency (you play along with the clicks)
  const latency_ms = 1000 * ((settings.latency || 0) + (ctx.baseLatency || 0) + (ctx.outputLatency || 0));
  let closed = false;
  return {
    ctx, sr: ctx.sampleRate, latency_ms,
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

/** Plays clicks given in seconds of the stream once t0 (the context time of sample 0) is known. */
export function clickPlayer(ctx) {
  const queue = [];
  let t0 = null;
  const timer = setInterval(() => {
    if (t0 === null) return;
    const horizon = ctx.currentTime + 0.3;
    while (queue.length && t0 + queue[0][0] < horizon) {
      const [ct, accent] = queue.shift(), at = t0 + ct;
      if (at < ctx.currentTime) continue;            // too late to play: skip it
      const osc = ctx.createOscillator(), g = ctx.createGain();
      osc.frequency.value = accent ? 1600 : 1000;
      g.gain.setValueAtTime(0.5, at);
      g.gain.exponentialRampToValueAtTime(0.001, at + 0.04);
      osc.connect(g).connect(ctx.destination);
      osc.start(at);
      osc.stop(at + 0.05);
    }
  }, 50);
  return {
    add(clicks) { queue.push(...clicks); queue.sort((a, b) => a[0] - b[0]); },
    start(t) { if (t0 === null) t0 = t; },
    stop() { clearInterval(timer); queue.length = 0; },
  };
}

/** /api/live/start, with the guitar coming from this browser when this is the web service. */
export async function startLive(payload) {
  stopInput();
  if (payload.simulate || !(await isService())) return api("/api/live/start", { json: payload });
  const input = await openInput();
  let r;
  try {
    r = await api("/api/live/start", { json: { ...payload, input: "browser", sr: input.sr, latency_ms: input.latency_ms } });
  } catch (e) { input.close(); throw e; }
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/stream`);
  ws.binaryType = "arraybuffer";
  const clicks = clickPlayer(input.ctx);
  const me = current = { close() { clicks.stop(); input.close(); if (ws.readyState <= 1) ws.close(); if (current === me) current = null; } };
  ws.onopen = () => ws.send(JSON.stringify({ type: "attach" }));
  ws.onmessage = ev => {
    const m = JSON.parse(ev.data);
    if (m.type === "ready") {
      input.onBlock(b => { clicks.start(b.t0); if (ws.readyState === 1) ws.send(frame(b)); });
    } else if (m.type === "clicks") clicks.add(m.clicks);
    else if (m.type === "ended" || m.type === "error") me.close();
  };
  ws.onclose = () => me.close();
  return r;
}

export function stopInput() {
  if (current) current.close();
}
