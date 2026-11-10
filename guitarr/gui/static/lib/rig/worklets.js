// AudioWorklet processors for the tone rig: things the built-in Web Audio nodes can't do.
// Loaded with ctx.audioWorklet.addModule(); runs on the audio thread.
/* global sampleRate, registerProcessor, AudioWorkletProcessor */

const dbToLin = d => Math.pow(10, d / 20);
const coef = (seconds) => Math.exp(-1 / (Math.max(seconds, 1e-4) * sampleRate));

// ------------------------------------------------------------------ noise gate
class GateProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [
      { name: "threshold", defaultValue: -55, minValue: -100, maxValue: 0, automationRate: "k-rate" },
      { name: "release", defaultValue: 0.12, minValue: 0.005, maxValue: 2, automationRate: "k-rate" },
    ];
  }
  constructor() { super(); this.env = 0; this.gain = 0; this.hold = 0; this.open = false; }
  process(inputs, outputs, p) {
    const inp = inputs[0], out = outputs[0];
    if (!inp.length) return true;
    const thOpen = dbToLin(p.threshold[0]), thClose = dbToLin(p.threshold[0] - 4);
    const envRel = coef(0.05), gAtt = coef(0.001), gRel = coef(p.release[0]), holdN = 0.04 * sampleRate;
    const x0 = inp[0];
    for (let i = 0; i < x0.length; i++) {
      const a = Math.abs(x0[i]);
      this.env = a > this.env ? a : this.env * envRel;
      if (this.env > thOpen) { this.open = true; this.hold = holdN; }
      else if (this.env < thClose) { if (this.hold > 0) this.hold--; else this.open = false; }
      const target = this.open ? 1 : 0;
      const c = target > this.gain ? gAtt : gRel;
      this.gain = target + (this.gain - target) * c;
      for (let ch = 0; ch < out.length; ch++) out[ch][i] = (inp[ch] || x0)[i] * this.gain;
    }
    return true;
  }
}
registerProcessor("rig-gate", GateProcessor);

// ------------------------------------------------------------------ envelope follower (auto-wah)
class EnvelopeProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [{ name: "sensitivity", defaultValue: 1, minValue: 0, maxValue: 20, automationRate: "k-rate" }];
  }
  constructor() { super(); this.env = 0; }
  process(inputs, outputs, p) {
    const x = inputs[0][0], y = outputs[0][0];
    if (!x) { y && y.fill(this.env); return true; }
    const att = coef(0.004), rel = coef(0.12), s = p.sensitivity[0];
    for (let i = 0; i < x.length; i++) {
      const a = Math.abs(x[i]) * s;
      this.env = a > this.env ? a + (this.env - a) * att : this.env * rel;
      y[i] = Math.min(1, this.env);
    }
    return true;
  }
}
registerProcessor("rig-envelope", EnvelopeProcessor);

// ------------------------------------------------------------------ analog-style octave down
class OctaveProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [
      { name: "dry", defaultValue: 1, minValue: 0, maxValue: 2, automationRate: "k-rate" },
      { name: "down1", defaultValue: 0.8, minValue: 0, maxValue: 2, automationRate: "k-rate" },
      { name: "down2", defaultValue: 0, minValue: 0, maxValue: 2, automationRate: "k-rate" },
    ];
  }
  constructor() {
    super();
    this.lp1 = 0; this.lp2 = 0; this.env = 0; this.last = 0;
    this.ff1 = 1; this.ff2 = 1; this.armed = true; this.sm = 0;
  }
  process(inputs, outputs, p) {
    const x = inputs[0][0], out = outputs[0];
    if (!x) return true;
    const a = 1 - Math.exp(-2 * Math.PI * 700 / sampleRate);       // pre-filter: keep the fundamental
    const sa = 1 - Math.exp(-2 * Math.PI * 1800 / sampleRate);     // soften the square wave
    const rel = coef(0.08), dry = p.dry[0], d1 = p.down1[0], d2 = p.down2[0];
    for (let i = 0; i < x.length; i++) {
      this.lp1 += a * (x[i] - this.lp1);
      this.lp2 += a * (this.lp1 - this.lp2);
      const v = this.lp2, ab = Math.abs(x[i]);
      this.env = ab > this.env ? ab : this.env * rel;
      const hyst = this.env * 0.1;
      if (this.armed && v > hyst) {
        this.armed = false;
        this.ff1 = -this.ff1;
        if (this.ff1 > 0) this.ff2 = -this.ff2;
      } else if (v < -hyst) this.armed = true;
      const sq = (this.ff1 * d1 + this.ff2 * d2) * this.env;
      this.sm += sa * (sq - this.sm);
      const y = x[i] * dry + this.sm;
      for (let ch = 0; ch < out.length; ch++) out[ch][i] = y;
    }
    return true;
  }
}
registerProcessor("rig-octave", OctaveProcessor);

// ------------------------------------------------------------------ pitch shifter (two crossfaded taps)
class PitchProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [
      { name: "semitones", defaultValue: 12, minValue: -24, maxValue: 24, automationRate: "k-rate" },
      { name: "mix", defaultValue: 0.5, minValue: 0, maxValue: 1, automationRate: "k-rate" },
    ];
  }
  constructor() {
    super();
    this.N = 1 << 15; this.buf = new Float32Array(this.N); this.w = 0;
    this.W = Math.round(0.05 * sampleRate); this.phase = 0;
  }
  read(d) {
    let pos = this.w - d;
    while (pos < 0) pos += this.N;
    const i = Math.floor(pos), f = pos - i;
    return this.buf[i & (this.N - 1)] * (1 - f) + this.buf[(i + 1) & (this.N - 1)] * f;
  }
  process(inputs, outputs, p) {
    const x = inputs[0][0], out = outputs[0];
    if (!x) return true;
    const ratio = Math.pow(2, p.semitones[0] / 12), mix = p.mix[0], W = this.W;
    for (let i = 0; i < x.length; i++) {
      this.buf[this.w] = x[i];
      this.phase += 1 - ratio;
      while (this.phase < 0) this.phase += W;
      while (this.phase >= W) this.phase -= W;
      const p1 = this.phase, p2 = (p1 + W / 2) % W;
      const g1 = Math.sin(Math.PI * p1 / W) ** 2, g2 = Math.sin(Math.PI * p2 / W) ** 2;
      const wet = this.read(p1 + 1) * g1 + this.read(p2 + 1) * g2;
      const y = x[i] * (1 - mix) + wet * mix;
      for (let ch = 0; ch < out.length; ch++) out[ch][i] = y;
      this.w = (this.w + 1) & (this.N - 1);
    }
    return true;
  }
}
registerProcessor("rig-pitch", PitchProcessor);

// ------------------------------------------------------------------ looper (stereo)
class LooperProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return [{ name: "level", defaultValue: 1, minValue: 0, maxValue: 2, automationRate: "k-rate" }];
  }
  constructor(opts) {
    super();
    const secs = (opts.processorOptions && opts.processorOptions.seconds) || 90;
    this.max = Math.floor(secs * sampleRate);
    this.L = new Float32Array(this.max); this.R = new Float32Array(this.max);
    this.state = "empty"; this.pos = 0; this.len = 0; this.tick = 0;
    // "armed": waits for you to play. A short ring buffer keeps the attack that crossed the threshold.
    this.pre = Math.floor(0.05 * sampleRate);
    this.preL = new Float32Array(this.pre); this.preR = new Float32Array(this.pre); this.preAt = 0;
    this.port.onmessage = e => this.command(e.data);
  }
  command(cmd) {
    const s = this.state;
    if (cmd === "clear") { this.L.fill(0); this.R.fill(0); this.state = "empty"; this.pos = this.len = 0; }
    else if (cmd === "arm") {
      if (s === "empty") this.arm();
      else if (s === "armed") this.state = "empty";
    } else if (cmd === "rec") {
      if (s === "empty") { this.state = "recording"; this.pos = 0; }
      else if (s === "armed") this.state = "empty";
      else if (s === "recording") this.finish();
      else if (s === "playing") this.state = "overdubbing";
      else if (s === "overdubbing") this.state = "playing";
      else if (s === "stopped") { this.state = "overdubbing"; this.pos = 0; }
    } else if (cmd === "play") {
      if (s === "recording") this.finish();
      else if (s === "stopped") { this.state = "playing"; this.pos = 0; }
      else if (s === "overdubbing") this.state = "playing";
    } else if (cmd === "stop") {
      if (s === "armed") this.state = "empty";
      if (s === "recording") this.finish();
      if (this.len) { this.state = "stopped"; this.pos = 0; }
    }
    this.report();
  }
  arm() {
    this.state = "armed"; this.pos = 0; this.preAt = 0; this.preL.fill(0); this.preR.fill(0);
    this.floor = 0; this.armedFor = 0;
  }
  /** Starts the take at the first sound clearly above the hiss the rig makes on its own (measured in the first 0.2 s). */
  listen(xl, xr) {
    let peak = 0;
    for (let i = 0; i < xl.length; i++) peak = Math.max(peak, Math.abs(xl[i]));
    const quiet = this.armedFor < 0.2 * sampleRate;
    this.armedFor += xl.length;
    if (quiet) this.floor = Math.max(this.floor, peak);
    if (!quiet && peak > Math.max(0.02, this.floor * 3)) {
      for (let k = 0; k < this.pre; k++) {                 // the last 50 ms, oldest first, then this block
        const j = (this.preAt + k) % this.pre;
        this.L[k] = this.preL[j]; this.R[k] = this.preR[j];
      }
      this.L.set(xl, this.pre); this.R.set(xr, this.pre);
      this.pos = this.pre + xl.length; this.state = "recording"; this.report();
      return true;
    }
    for (let i = 0; i < xl.length; i++) {
      this.preL[this.preAt] = xl[i]; this.preR[this.preAt] = xr[i];
      this.preAt = (this.preAt + 1) % this.pre;
    }
    return false;
  }
  finish() { this.len = Math.max(1, this.pos); this.pos = 0; this.state = "playing"; }
  report() { this.port.postMessage({ state: this.state, pos: this.pos / sampleRate, len: this.len / sampleRate, max: this.max / sampleRate }); }
  process(inputs, outputs, p) {
    const inp = inputs[0], out = outputs[0];
    const xl = inp[0], xr = inp[1] || inp[0];
    const lv = p.level[0];
    let started = false;                                   // this block already went into the take
    if (this.state === "armed" && xl) started = this.listen(xl, xr);
    else if (this.state === "armed") this.armedFor += out[0].length;
    for (let i = 0; i < out[0].length; i++) {
      let yl = 0, yr = 0;
      const st = this.state;
      if (st === "recording" && !started) {
        if (xl) { this.L[this.pos] = xl[i]; this.R[this.pos] = xr[i]; }
        if (++this.pos >= this.max) { this.finish(); this.report(); }
      } else if (st === "playing" || st === "overdubbing") {
        yl = this.L[this.pos] * lv; yr = this.R[this.pos] * lv;
        if (st === "overdubbing" && xl) { this.L[this.pos] += xl[i]; this.R[this.pos] += xr[i]; }
        if (++this.pos >= this.len) this.pos = 0;
      }
      out[0][i] = yl;
      if (out[1]) out[1][i] = yr;
    }
    if (++this.tick % 16 === 0) this.report();
    return true;
  }
}
registerProcessor("rig-looper", LooperProcessor);

// ------------------------------------------------------------------ recorder (sends stereo blocks to the page)
class RecorderProcessor extends AudioWorkletProcessor {
  constructor() { super(); this.on = false; this.port.onmessage = e => { this.on = e.data === "start"; }; }
  process(inputs) {
    const inp = inputs[0];
    if (this.on && inp.length) {
      const l = inp[0], r = inp[1] || inp[0];
      this.port.postMessage([l.slice(0), r.slice(0)]);
    }
    return true;
  }
}
registerProcessor("rig-recorder", RecorderProcessor);
