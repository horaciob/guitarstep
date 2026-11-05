// Virtual guitar: plucked-string synthesis (Karplus-Strong) playing short original riffs in a
// loop, so you can try the rig without a guitar at hand. It feeds the rig like a real input.
const OPEN = [40, 45, 50, 55, 59, 64];                 // 6th … 1st string
const chord = frets => frets.map((f, i) => (f < 0 ? null : OPEN[i] + f)).filter(n => n != null);

/** decay: string feedback · bright: pick brightness 0..1 · body: [type, Hz, Q, dB] filters · octave shift. */
export const VOICES = {
  electric_single: { decay: 0.9986, bright: 0.95, pick: 0.13, body: [["highpass", 90, 0.7, 0], ["peaking", 3000, 1, 2]], gain: 1 },
  electric_hum:    { decay: 0.9984, bright: 0.65, pick: 0.25, body: [["peaking", 600, 0.8, 3], ["highshelf", 3500, 0.7, -3]], gain: 1.1 },
  acoustic:        { decay: 0.9965, bright: 0.85, pick: 0.18, body: [["peaking", 110, 2, 6], ["peaking", 220, 1.4, 3], ["highshelf", 5000, 0.7, 4]], gain: 0.9 },
  nylon:           { decay: 0.9955, bright: 0.35, pick: 0.2, body: [["peaking", 180, 1.2, 4], ["lowpass", 5000, 0.7, 0]], gain: 1 },
  bass:            { decay: 0.9993, bright: 0.4, pick: 0.2, body: [["lowpass", 2500, 0.7, 0]], gain: 1.3, octave: -12 },
};

// Riffs: [beat, notes, length in beats, {mute, up}] over `beats` beats; tempo in BPM.
const strum = (b, frets, len = 1, o = {}) => [b, chord(frets), len, o];
export const RIFFS = {
  open_chords: { bpm: 96, beats: 16, events: [
    strum(0, [3, 2, 0, 0, 0, 3], 1.5), strum(1.5, [3, 2, 0, 0, 0, 3], 0.5, { up: true }), strum(2, [3, 2, 0, 0, 0, 3], 2),
    strum(4, [-1, 3, 2, 0, 1, 0], 1.5), strum(5.5, [-1, 3, 2, 0, 1, 0], 0.5, { up: true }), strum(6, [-1, 3, 2, 0, 1, 0], 2),
    strum(8, [-1, -1, 0, 2, 3, 2], 1.5), strum(9.5, [-1, -1, 0, 2, 3, 2], 0.5, { up: true }), strum(10, [-1, -1, 0, 2, 3, 2], 2),
    strum(12, [0, 2, 2, 0, 0, 0], 1.5), strum(13.5, [0, 2, 2, 0, 0, 0], 0.5, { up: true }), strum(14, [0, 2, 2, 0, 0, 0], 2)] },
  blues_lick: { bpm: 84, beats: 8, events: [
    [0, [69], 0.5], [0.5, [72], 0.5], [1, [74], 0.75], [1.75, [72], 0.25], [2, [69], 1], [3, [67], 0.5], [3.5, [64], 0.5],
    [4, [62], 0.5], [4.5, [64], 0.5], [5, [57], 1.5], [6.5, [60], 0.5], [7, [57], 1]] },
  power_riff: { bpm: 120, beats: 8, events: [
    ...[0, 0.5, 1, 1.5].map(b => strum(b, [0, 2, 2, -1, -1, -1], 0.5, { mute: true })),
    strum(2, [3, 5, 5, -1, -1, -1], 1), strum(3, [5, 7, 7, -1, -1, -1], 1),
    ...[4, 4.5, 5, 5.5].map(b => strum(b, [0, 2, 2, -1, -1, -1], 0.5, { mute: true })),
    strum(6, [5, 7, 7, -1, -1, -1], 0.75), strum(6.75, [3, 5, 5, -1, -1, -1], 1.25)] },
  arpeggio: { bpm: 100, beats: 16, events: [
    [[-1, 0, 2, 2, 1, 0], 0], [[1, 3, 3, 2, 1, 1], 4], [[-1, 3, 2, 0, 1, 0], 8], [[3, 2, 0, 0, 0, 3], 12],
  ].flatMap(([frets, start]) => { const n = chord(frets); const order = [0, 2, 1, 3, 2, 4, 3, n.length - 1]; return order.map((k, i) => [start + i * 0.5, [n[Math.min(k, n.length - 1)]], 1.5]); }) },
  sustained: { bpm: 60, beats: 8, events: [[0, [64], 3.5], [4, [57], 1.5], [6, [chord([0, 2, 2, 1, 0, 0])].flat(), 2]] },
};

let seed = 7;
const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 * 2 - 1; };

export class VirtualGuitar {
  constructor(ctx, out) {
    this.ctx = ctx; this.out = out; this.voice = "electric_single"; this.riff = "open_chords"; this.bpm = null;
    this.cache = new Map(); this.timer = null; this.playing = false;
    this.bus = ctx.createGain();
    this.bus.gain.value = 0.2;          // about the level of a real guitar into an interface
    this.filters = [];
    this.setVoice(this.voice);
  }
  setVoice(v) {
    this.voice = VOICES[v] ? v : "electric_single";
    this.bus.disconnect(); this.filters.forEach(f => f.disconnect());
    this.filters = VOICES[this.voice].body.map(([type, f, q, g]) => {
      const b = this.ctx.createBiquadFilter(); b.type = type; b.frequency.value = f; b.Q.value = q; b.gain.value = g; return b;
    });
    let last = this.bus;
    for (const f of this.filters) { last.connect(f); last = f; }
    last.connect(this.out);
  }
  setRiff(r) { if (RIFFS[r]) { this.riff = r; if (this.playing) this.restart(); } }
  setTempo(bpm) { this.bpm = bpm; }

  buffer(midi, mute) {
    const V = VOICES[this.voice], key = `${this.voice}|${midi}|${mute ? 1 : 0}`;
    if (this.cache.has(key)) return this.cache.get(key);
    const sr = this.ctx.sampleRate, dur = mute ? 0.35 : 3, n = Math.floor(sr * dur);
    const f = 440 * 2 ** ((midi - 69) / 12), P = Math.max(2, Math.round(sr / f));
    const decay = mute ? 0.95 : V.decay, out = new Float32Array(n), buf = new Float32Array(P);
    seed = midi * 31 + 7;
    let lp = 0;
    const a = 0.15 + 0.85 * (mute ? 0.3 : V.bright);
    for (let i = 0; i < P; i++) { lp += a * (rnd() - lp); buf[i] = lp; }
    // pick position: a comb notch (picking near the bridge is brighter)
    const pp = Math.max(1, Math.round(P * V.pick));
    for (let i = P - 1; i >= pp; i--) buf[i] -= buf[i - pp] * 0.5;
    for (let i = 0; i < n; i++) {
      const j = i % P;
      out[i] = buf[j];
      buf[j] = decay * 0.5 * (buf[j] + buf[(j + 1) % P]);
    }
    for (let i = 0; i < 300 && i < n; i++) out[n - 1 - i] *= i / 300;
    const ab = this.ctx.createBuffer(1, n, sr);
    ab.copyToChannel(out, 0);
    this.cache.set(key, ab);
    return ab;
  }

  note(midi, when, len, { mute = false, vel = 0.3 } = {}) {
    const V = VOICES[this.voice], src = this.ctx.createBufferSource(), g = this.ctx.createGain();
    src.buffer = this.buffer(midi + (V.octave || 0), mute);
    g.gain.setValueAtTime(vel * V.gain, when);
    g.gain.setTargetAtTime(0, when + Math.max(0.05, len), 0.05);    // let go of the string
    src.connect(g).connect(this.bus);
    src.start(when);
    src.stop(when + len + 0.4);
  }

  schedule() {
    const R = RIFFS[this.riff], spb = 60 / (this.bpm || R.bpm), loopLen = R.beats * spb;
    const horizon = this.ctx.currentTime + 0.15;
    while (this.next < horizon) {
      const loopStart = this.loopStart, ev = R.events[this.idx];
      const when = loopStart + ev[0] * spb, opts = ev[3] || {};
      const notes = opts.up ? [...ev[1]].reverse() : ev[1];
      const gap = notes.length > 1 ? 0.012 : 0;
      notes.forEach((m, k) => this.note(m, when + k * gap, ev[2] * spb, { mute: opts.mute, vel: (opts.up ? 0.18 : 0.26) * (notes.length > 1 ? 0.75 : 1) }));
      this.idx++;
      if (this.idx >= R.events.length) { this.idx = 0; this.loopStart += loopLen; }
      const nxt = R.events[this.idx];
      this.next = this.loopStart + nxt[0] * spb;
    }
  }
  start() {
    if (this.playing) return;
    this.playing = true;
    this.loopStart = this.ctx.currentTime + 0.1; this.idx = 0;
    this.next = this.loopStart + RIFFS[this.riff].events[0][0] * 60 / (this.bpm || RIFFS[this.riff].bpm);
    this.timer = setInterval(() => this.schedule(), 25);
    this.schedule();
  }
  stop() { this.playing = false; clearInterval(this.timer); this.timer = null; }
  restart() { this.stop(); this.start(); }
  dispose() { this.stop(); this.bus.disconnect(); this.filters.forEach(f => f.disconnect()); }
}
