// Catalog of everything that can go in the rig: guitar voicings, pedals/effects, amps,
// cabinets and microphones. Names and descriptions are translated in the UI
// (keys rig.fx.<id>, rig.amp.<id>, …); ids and parameters live here.
//
// Every build(ctx, params) returns { input, output, set(param, value), dispose() }.
import { biquad, dbToGain, dryWet, gainNode, lerp, lfo, logMap, ramp, reverbIR, series, shaper } from "./dsp.js";

const knob = (id, min, max, def, unit = "", step = null) => ({ id, type: "knob", min, max, def, unit, step: step ?? (max - min) / 100 });
const choice = (id, options, def) => ({ id, type: "choice", options, def: def ?? options[0] });
const ten = (id, def) => knob(id, 0, 10, def, "", 0.1);

function disposer(...sources) {
  return () => sources.forEach(s => { try { s.stop(); } catch { /* not started */ } try { s.disconnect(); } catch { /* gone */ } });
}

// ================================================================== pedals and effects
export const EFFECTS = {
  // ---------------------------------------------------------------- dynamics
  gate: {
    group: "dynamics", color: "#7d8597",
    params: [knob("threshold", -90, -20, -58, "dB", 1), knob("release", 10, 600, 120, "ms", 5)],
    build(ctx, p) {
      const n = new AudioWorkletNode(ctx, "rig-gate", { outputChannelCount: [2] });
      const set = (k, v) => {
        if (k === "threshold") n.parameters.get("threshold").value = v;
        if (k === "release") n.parameters.get("release").value = v / 1000;
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: n, output: n, set, dispose: disposer(n) };
    },
  },
  volume: {
    group: "dynamics", color: "#9aa0ad",
    params: [ten("level", 10)],
    build(ctx, p) {
      const g = gainNode(ctx);
      const set = (k, v) => { if (k === "level") ramp(ctx, g.gain, (v / 10) ** 2, 0.02); };   // squared: feels even
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: g, output: g, set, dispose: () => {} };
    },
  },
  compressor: {
    group: "dynamics", color: "#4f9dde",
    params: [ten("sustain", 5), knob("attack", 1, 50, 8, "ms", 1), ten("level", 6), ten("blend", 10)],
    build(ctx, p) {
      const dw = dryWet(ctx, 1), c = ctx.createDynamicsCompressor(), make = gainNode(ctx), out = gainNode(ctx);
      c.knee.value = 12; c.release.value = 0.25;
      dw.wetIn.connect(c).connect(make).connect(dw.wetOut);
      dw.output.connect(out);
      const set = (k, v) => {
        if (k === "sustain") { c.threshold.value = lerp(-8, -48, v / 10); c.ratio.value = lerp(2, 12, v / 10); ramp(ctx, make.gain, dbToGain(lerp(0, 11, v / 10))); }
        if (k === "attack") c.attack.value = v / 1000;
        if (k === "level") ramp(ctx, out.gain, dbToGain((v - 6) * 2));
        if (k === "blend") dw.setMix(v / 10);
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: dw.input, output: out, set, dispose: disposer(c) };
    },
  },
  // ---------------------------------------------------------------- drive
  boost: {
    group: "drive", color: "#e8e8e8",
    params: [knob("boost", 0, 20, 8, "dB", 0.5), knob("tilt", -6, 6, 0, "dB", 0.5)],
    build(ctx, p) {
      const g = gainNode(ctx), tilt = biquad(ctx, "highshelf", 1500, 0.7, 0);
      g.connect(tilt);
      const set = (k, v) => { if (k === "boost") ramp(ctx, g.gain, dbToGain(v)); if (k === "tilt") tilt.gain.value = v; };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: g, output: tilt, set, dispose: () => {} };
    },
  },
  overdrive: {
    group: "drive", color: "#3fb36b",
    params: [ten("drive", 5), ten("tone", 5), ten("level", 5)],
    build(ctx, p) {
      // Mid-hump screamer style: the lows bypass the clipper, so it stays tight.
      const input = gainNode(ctx), hp = biquad(ctx, "highpass", 720, 0.6), pre = gainNode(ctx), clip = shaper(ctx, "soft", 1.5);
      const lowDry = biquad(ctx, "lowpass", 720, 0.6), lowGain = gainNode(ctx, 0.5), sum = gainNode(ctx);
      const tone = biquad(ctx, "lowpass", 3000, 0.7), level = gainNode(ctx);
      series(input, hp, pre, clip, sum, tone, level);
      series(input, lowDry, lowGain, sum);
      const set = (k, v) => {
        if (k === "drive") ramp(ctx, pre.gain, dbToGain(lerp(6, 40, v / 10)));
        if (k === "tone") tone.frequency.value = logMap(900, 7000, v / 10);
        if (k === "level") ramp(ctx, level.gain, dbToGain(lerp(-24, 6, v / 10)));
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input, output: level, set, dispose: () => {} };
    },
  },
  distortion: {
    group: "drive", color: "#2b2b2b",
    params: [ten("drive", 6), ten("tone", 5), ten("level", 5)],
    build(ctx, p) {
      const hp = biquad(ctx, "highpass", 90), pre = gainNode(ctx), clip = shaper(ctx, "hard", 1), post = biquad(ctx, "lowpass", 3500, 0.8);
      const level = gainNode(ctx);
      series(hp, pre, clip, post, level);
      const set = (k, v) => {
        if (k === "drive") ramp(ctx, pre.gain, dbToGain(lerp(10, 50, v / 10)));
        if (k === "tone") post.frequency.value = logMap(700, 8000, v / 10);
        if (k === "level") ramp(ctx, level.gain, dbToGain(lerp(-30, 0, v / 10)));
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: hp, output: level, set, dispose: () => {} };
    },
  },
  fuzz: {
    group: "drive", color: "#c9452c",
    params: [ten("fuzz", 7), ten("tone", 5), ten("level", 5), choice("voice", ["vintage", "octave"])],
    build(ctx, p) {
      const pre = gainNode(ctx), clip = shaper(ctx, "fuzz", 6), rect = shaper(ctx, "rect", 1), hp = biquad(ctx, "highpass", 40);
      const tone = biquad(ctx, "lowpass", 2500, 0.9), mids = biquad(ctx, "peaking", 900, 0.8, -5), level = gainNode(ctx);
      let voice = "vintage";
      const wire = () => {
        pre.disconnect(); rect.disconnect();
        if (voice === "octave") series(pre, rect, clip); else pre.connect(clip);
      };
      series(clip, hp, mids, tone, level);
      wire();
      const set = (k, v) => {
        if (k === "fuzz") ramp(ctx, pre.gain, dbToGain(lerp(12, 46, v / 10)));
        if (k === "tone") tone.frequency.value = logMap(600, 6000, v / 10);
        if (k === "level") ramp(ctx, level.gain, dbToGain(lerp(-30, 0, v / 10)));
        if (k === "voice") { voice = v; wire(); }
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: pre, output: level, set, dispose: () => {} };
    },
  },
  // ---------------------------------------------------------------- filter
  wah: {
    group: "filter", color: "#3a3a3a",
    params: [choice("mode", ["auto", "manual"]), ten("pedal", 5), ten("sensitivity", 5), ten("resonance", 6)],
    build(ctx, p) {
      const input = gainNode(ctx), bp = biquad(ctx, "bandpass", 700, 6), wetG = gainNode(ctx, 2), dryG = gainNode(ctx, 0.12), out = gainNode(ctx);
      const env = new AudioWorkletNode(ctx, "rig-envelope", { outputChannelCount: [1] }), depth = gainNode(ctx, 0);
      series(input, bp, wetG, out);
      series(input, dryG, out);
      input.connect(env); env.connect(depth); depth.connect(bp.frequency);
      let mode = "auto", pedal = 5, sens = 5;
      const apply = () => {
        if (mode === "manual") { bp.frequency.value = logMap(350, 2400, pedal / 10); depth.gain.value = 0; }
        else { bp.frequency.value = 350; depth.gain.value = 2200; env.parameters.get("sensitivity").value = lerp(1, 18, sens / 10); }
      };
      const set = (k, v) => {
        if (k === "mode") mode = v;
        if (k === "pedal") pedal = v;
        if (k === "sensitivity") sens = v;
        if (k === "resonance") bp.Q.value = lerp(2, 12, v / 10);
        apply();
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input, output: out, set, dispose: disposer(env) };
    },
  },
  eq: {
    group: "filter", color: "#d9d9d9",
    params: [100, 200, 400, 800, 1600, 3200, 6400].map(f => knob(`b${f}`, -12, 12, 0, "dB", 0.5)).concat([knob("level", -12, 12, 0, "dB", 0.5)]),
    build(ctx, p) {
      const bands = [100, 200, 400, 800, 1600, 3200, 6400].map((f, i, a) => biquad(ctx, i === 0 ? "lowshelf" : i === a.length - 1 ? "highshelf" : "peaking", f, 1.1, 0));
      const level = gainNode(ctx);
      series(...bands, level);
      const set = (k, v) => {
        if (k === "level") ramp(ctx, level.gain, dbToGain(v));
        else { const i = [100, 200, 400, 800, 1600, 3200, 6400].indexOf(+k.slice(1)); if (i >= 0) bands[i].gain.value = v; }
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: bands[0], output: level, set, dispose: () => {} };
    },
  },
  // ---------------------------------------------------------------- modulation
  chorus: {
    group: "modulation", color: "#6ec6e8",
    params: [knob("rate", 0.1, 5, 0.8, "Hz", 0.05), ten("depth", 5), ten("mix", 5)],
    build(ctx, p) {
      const dw = dryWet(ctx, 0.5), merger = ctx.createChannelMerger(2);
      const dl = ctx.createDelay(0.05), dr = ctx.createDelay(0.05), osc = lfo(ctx, 0.8), dL = gainNode(ctx), dR = gainNode(ctx);
      dl.delayTime.value = dr.delayTime.value = 0.014;
      osc.connect(dL).connect(dl.delayTime);
      osc.connect(dR).connect(dr.delayTime);
      dw.wetIn.connect(dl).connect(merger, 0, 0);
      dw.wetIn.connect(dr).connect(merger, 0, 1);
      merger.connect(dw.wetOut);
      const set = (k, v) => {
        if (k === "rate") osc.frequency.value = v;
        if (k === "depth") { const d = lerp(0.0003, 0.005, v / 10); dL.gain.value = d; dR.gain.value = -d; }
        if (k === "mix") dw.setMix(v / 10 * 0.7);
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: dw.input, output: dw.output, set, dispose: disposer(osc) };
    },
  },
  flanger: {
    group: "modulation", color: "#9b7bd4",
    params: [knob("rate", 0.05, 3, 0.25, "Hz", 0.05), ten("depth", 6), ten("feedback", 6), ten("mix", 5)],
    build(ctx, p) {
      const dw = dryWet(ctx, 0.5), d = ctx.createDelay(0.02), fb = gainNode(ctx), osc = lfo(ctx, 0.25), dep = gainNode(ctx);
      d.delayTime.value = 0.003;
      osc.connect(dep).connect(d.delayTime);
      dw.wetIn.connect(d); d.connect(fb).connect(d); d.connect(dw.wetOut);
      const set = (k, v) => {
        if (k === "rate") osc.frequency.value = v;
        if (k === "depth") dep.gain.value = lerp(0.0002, 0.0028, v / 10);
        if (k === "feedback") fb.gain.value = lerp(0, 0.85, v / 10);
        if (k === "mix") dw.setMix(v / 10 * 0.7);
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: dw.input, output: dw.output, set, dispose: disposer(osc) };
    },
  },
  phaser: {
    group: "modulation", color: "#f08a3c",
    params: [knob("rate", 0.05, 6, 0.5, "Hz", 0.05), ten("depth", 7), ten("mix", 5), choice("stages", ["4", "8"])],
    build(ctx, p) {
      // Allpass sweep mixed with the dry signal (no feedback: Web Audio mutes cycles without a delay).
      const dw = dryWet(ctx, 0.5), osc = lfo(ctx, 0.5), dep = gainNode(ctx);
      const aps = Array.from({ length: 8 }, () => biquad(ctx, "allpass", 800, 0.6));
      aps.forEach(a => dep.connect(a.frequency));
      osc.connect(dep);
      let stages = 4;
      const wire = () => {
        [dw.wetIn, ...aps].forEach(n => { try { n.disconnect(); } catch { /* ok */ } });
        const used = aps.slice(0, stages);
        series(dw.wetIn, ...used);
        used[used.length - 1].connect(dw.wetOut);
      };
      wire();
      const set = (k, v) => {
        if (k === "rate") osc.frequency.value = v;
        if (k === "depth") dep.gain.value = lerp(100, 700, v / 10);
        if (k === "mix") dw.setMix(v / 10 * 0.8);
        if (k === "stages") { stages = +v; wire(); }
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: dw.input, output: dw.output, set, dispose: disposer(osc) };
    },
  },
  tremolo: {
    group: "modulation", color: "#e2c044",
    params: [knob("rate", 0.5, 12, 5, "Hz", 0.1), ten("depth", 6), choice("shape", ["sine", "square", "triangle"])],
    build(ctx, p) {
      const g = gainNode(ctx, 0.7), osc = lfo(ctx, 5), dep = gainNode(ctx, 0.3), soft = biquad(ctx, "lowpass", 40);
      osc.connect(soft).connect(dep).connect(g.gain);
      let shape = "sine";
      const set = (k, v) => {
        if (k === "rate") { osc.frequency.value = v; soft.frequency.value = Math.max(30, v * 8); }
        if (k === "depth") { const d = v / 10 / 2; g.gain.value = 1 - d; dep.gain.value = d; }
        if (k === "shape") { shape = v; osc.type = shape; soft.frequency.value = shape === "square" ? Math.max(30, osc.frequency.value * 8) : 20000; }
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: g, output: g, set, dispose: disposer(osc) };
    },
  },
  vibrato: {
    group: "modulation", color: "#57b7a6",
    params: [knob("rate", 0.5, 10, 5, "Hz", 0.1), ten("depth", 4)],
    build(ctx, p) {
      const d = ctx.createDelay(0.03), osc = lfo(ctx, 5), dep = gainNode(ctx);
      d.delayTime.value = 0.006;
      osc.connect(dep).connect(d.delayTime);
      const set = (k, v) => {
        if (k === "rate") osc.frequency.value = v;
        if (k === "depth") dep.gain.value = lerp(0.0001, 0.0045, v / 10);
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: d, output: d, set, dispose: disposer(osc) };
    },
  },
  // ---------------------------------------------------------------- pitch
  octaver: {
    group: "pitch", color: "#5c6bc0",
    params: [ten("dry", 7), ten("oct1", 7), ten("oct2", 0)],
    build(ctx, p) {
      const n = new AudioWorkletNode(ctx, "rig-octave", { outputChannelCount: [1] });
      const set = (k, v) => {
        const map = { dry: "dry", oct1: "down1", oct2: "down2" };
        if (map[k]) n.parameters.get(map[k]).value = v / 10 * (k === "dry" ? 1 : 0.35);
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: n, output: n, set, dispose: disposer(n) };
    },
  },
  pitch: {
    group: "pitch", color: "#c2185b",
    params: [knob("shift", -24, 24, 12, "st", 1), knob("fine", -50, 50, 0, "¢", 1), ten("mix", 5)],
    build(ctx, p) {
      const n = new AudioWorkletNode(ctx, "rig-pitch", { outputChannelCount: [1] });
      let shift = 12, fine = 0;
      const set = (k, v) => {
        if (k === "shift") shift = v;
        if (k === "fine") fine = v;
        if (k === "mix") n.parameters.get("mix").value = v / 10;
        n.parameters.get("semitones").value = shift + fine / 100;
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: n, output: n, set, dispose: disposer(n) };
    },
  },
  // ---------------------------------------------------------------- time
  delay: {
    group: "time", color: "#2f80ed",
    params: [knob("time", 40, 1500, 380, "ms", 5), ten("feedback", 4), ten("mix", 3.5), choice("mode", ["digital", "analog", "tape"])],
    build(ctx, p) {
      const dw = dryWet(ctx, 0.35), d = ctx.createDelay(2), fb = gainNode(ctx), color = biquad(ctx, "lowpass", 18000, 0.5), hp = biquad(ctx, "highpass", 80);
      const osc = lfo(ctx, 0.6), wob = gainNode(ctx, 0), sat = shaper(ctx, "soft", 1.2);
      osc.connect(wob).connect(d.delayTime);
      dw.wetIn.connect(d);
      series(d, color, hp, sat, fb, d);
      sat.connect(dw.wetOut);
      const set = (k, v) => {
        if (k === "time") ramp(ctx, d.delayTime, v / 1000, 0.08);
        if (k === "feedback") fb.gain.value = lerp(0, 0.92, v / 10);
        if (k === "mix") dw.setMix(v / 10);
        if (k === "mode") {
          color.frequency.value = { digital: 18000, analog: 2600, tape: 4500 }[v] || 18000;
          wob.gain.value = v === "tape" ? 0.0012 : v === "analog" ? 0.0003 : 0;
          sat.curve = shaper(ctx, "soft", v === "digital" ? 0.3 : 1.4).curve;
        }
      };
      Object.entries(p).forEach(([k, v]) => set(k, v));
      return { input: dw.input, output: dw.output, set, dispose: disposer(osc) };
    },
  },
  reverb: {
    group: "time", color: "#7cc4a8",
    params: [choice("type", ["room", "hall", "plate", "spring"], "hall"), knob("decay", 0.3, 8, 2.2, "s", 0.1), ten("tone", 5), ten("mix", 3)],
    build(ctx, p) {
      const dw = dryWet(ctx, 0.3), conv = ctx.createConvolver(), hp = biquad(ctx, "highpass", 120);
      dw.wetIn.connect(hp).connect(conv).connect(dw.wetOut);
      const st = { type: "hall", decay: 2.2, tone: 5 };
      let timer = null;
      const regen = () => { clearTimeout(timer); timer = setTimeout(() => { conv.buffer = reverbIR(ctx, st.type, st.decay, st.tone / 10); }, 120); };
      const set = (k, v) => {
        if (k === "mix") dw.setMix(v / 10);
        else { st[k] = v; regen(); }
      };
      Object.entries(p).forEach(([k, v]) => { if (k === "mix") set(k, v); else st[k] = v; });
      conv.buffer = reverbIR(ctx, st.type, st.decay, st.tone / 10);
      return { input: dw.input, output: dw.output, set, dispose: () => clearTimeout(timer) };
    },
  },
};

export const EFFECT_GROUPS = ["dynamics", "drive", "filter", "modulation", "pitch", "time"];

// ================================================================== guitar voicing (on a real input)
/** EQ approximations of other guitars/pickups. They change the character, not your instrument. */
export const GUITARS = {
  as_is: [],
  single_coil: [["highpass", 90, 0.7, 0], ["peaking", 1200, 1, -2], ["highshelf", 3000, 0.7, 3]],
  humbucker: [["peaking", 600, 0.8, 3], ["highshelf", 3000, 0.7, -3]],
  p90: [["peaking", 1500, 0.9, 3], ["highshelf", 5000, 0.7, 1.5]],
  hollow: [["peaking", 250, 1, 3], ["peaking", 800, 1, -2], ["lowpass", 4200, 0.7, 0]],
  acoustic: [["peaking", 110, 2, 5], ["peaking", 220, 1.4, 3], ["peaking", 600, 1, -5], ["highshelf", 5000, 0.7, 5]],
  nylon: [["peaking", 200, 1.2, 4], ["highshelf", 3000, 0.7, -4], ["lowpass", 5500, 0.7, 0]],
  twelve_string: [["highshelf", 4000, 0.7, 3]],          // + an octave-up voice, see buildGuitar
  baritone: [["lowshelf", 150, 0.7, 4], ["highshelf", 3500, 0.7, -2]],   // + pitch −5 semitones
};

export function buildGuitar(ctx, type, pickup = 0.5) {
  const input = gainNode(ctx), output = gainNode(ctx), nodes = [];
  const filters = (GUITARS[type] || []).map(([t, f, q, g]) => biquad(ctx, t, f, q, g));
  const pickupShelf = biquad(ctx, "highshelf", 2000, 0.7, lerp(-4, 4, pickup));
  const pickupMid = biquad(ctx, "peaking", 1000, 0.8, lerp(0, 2, pickup));
  let head = input;
  if (type === "twelve_string" || type === "baritone") {
    const pv = new AudioWorkletNode(ctx, "rig-pitch", { outputChannelCount: [1] });
    pv.parameters.get("semitones").value = type === "baritone" ? -5 : 12;
    pv.parameters.get("mix").value = type === "baritone" ? 1 : 0.38;
    input.connect(pv); head = pv; nodes.push(pv);
  }
  const chain = type === "as_is" ? [] : [...filters, pickupShelf, pickupMid];
  if (chain.length) { head.connect(chain[0]); series(...chain); chain[chain.length - 1].connect(output); }
  else head.connect(output);
  return {
    input, output,
    set(k, v) { if (k === "pickup") { pickupShelf.gain.value = lerp(-4, 4, v); pickupMid.gain.value = lerp(0, 2, v); } },
    dispose: disposer(...nodes),
  };
}

// ================================================================== amps
const AMP_PARAMS = [ten("gain", 5), ten("bass", 5), ten("mid", 5), ten("treble", 5), ten("presence", 5), ten("master", 5)];
/**
 * stages: preamp gain stages [curve, base dB, range dB, lowpass Hz]; tone: [bass Hz, mid Hz, mid Q, treble Hz];
 * inHp: input high-pass (tightness); voice: extra fixed filters; power: power-amp saturation.
 */
export const AMPS = {
  clean:     { trim: 15, stages: [["soft", 0, 22, 9000]], tone: [100, 650, 0.7, 3200], inHp: 70, voice: [["peaking", 450, 0.8, -3], ["highshelf", 4000, 0.7, 2]], power: 0.6, defaults: { gain: 3, mid: 4, treble: 6 } },
  jazz:      { trim: 25, stages: [["soft", 0, 18, 5000]], tone: [120, 500, 0.6, 2500], inHp: 60, voice: [["peaking", 250, 0.8, 2]], power: 0.5, defaults: { gain: 2.5, treble: 4, bass: 6 } },
  tweed:     { trim: 2, stages: [["asym", 6, 30, 6000], ["soft", 0, 6, 7000]], tone: [110, 800, 0.7, 2800], inHp: 60, voice: [["peaking", 700, 0.7, 3]], power: 1.4, defaults: { gain: 6 } },
  chime:     { trim: 3, stages: [["asym", 4, 28, 8000], ["soft", 0, 8, 9000]], tone: [120, 1200, 0.8, 3600], inHp: 90, voice: [["peaking", 2200, 0.9, 4], ["peaking", 300, 0.8, -2]], power: 1.2, defaults: { gain: 5, treble: 6.5 } },
  crunch:    { trim: 0, stages: [["asym", 8, 30, 7000], ["soft", 4, 16, 7500]], tone: [100, 900, 0.8, 3000], inHp: 80, voice: [["peaking", 900, 0.8, 4]], power: 1.1, defaults: { gain: 6, mid: 6.5 } },
  high_gain: { trim: -2, stages: [["asym", 14, 30, 8000], ["soft", 8, 18, 7000], ["soft", 4, 10, 6500]], tone: [90, 750, 0.9, 3200], inHp: 140, voice: [["peaking", 750, 0.9, -3], ["peaking", 2600, 1, 3]], power: 0.9, defaults: { gain: 7, mid: 4, presence: 6 } },
  lead:      { trim: -1, stages: [["asym", 12, 30, 6500], ["soft", 8, 16, 6000], ["soft", 4, 8, 5500]], tone: [100, 1000, 0.7, 2800], inHp: 110, voice: [["peaking", 1000, 0.7, 4]], power: 1.0, defaults: { gain: 7.5, mid: 6.5 } },
  acoustic:  { trim: 23, stages: [], tone: [100, 800, 0.7, 5000], inHp: 60, voice: [["peaking", 200, 1, -2], ["highshelf", 8000, 0.7, 2]], power: 0, defaults: { gain: 0, master: 6 } },
  bass:      { trim: 20, stages: [["soft", 0, 20, 4000]], tone: [60, 500, 0.7, 2500], inHp: 30, voice: [["lowshelf", 80, 0.7, 4], ["peaking", 400, 0.8, -2]], power: 0.8, defaults: { gain: 3, bass: 6 } },
};

export const ampDefaults = type => Object.fromEntries(AMP_PARAMS.map(pp => [pp.id, (AMPS[type].defaults || {})[pp.id] ?? pp.def]));
export const AMP_KNOBS = AMP_PARAMS;

export function buildAmp(ctx, type, p) {
  const A = AMPS[type] || AMPS.clean;
  const input = gainNode(ctx), inHp = biquad(ctx, "highpass", A.inHp, 0.7);
  const voice = A.voice.map(([t, f, q, g]) => biquad(ctx, t, f, q, g));
  const stages = A.stages.map(([kind, base, range, lp]) => {
    const g = gainNode(ctx), s = shaper(ctx, kind, 1), f = biquad(ctx, "lowpass", lp, 0.7), dc = biquad(ctx, "highpass", 25);
    series(g, s, f, dc);
    return { g, s, f, dc, base, range };
  });
  const [bF, mF, mQ, tF] = A.tone;
  const bass = biquad(ctx, "lowshelf", bF, 0.7), mid = biquad(ctx, "peaking", mF, mQ), treble = biquad(ctx, "highshelf", tF, 0.7);
  const presence = biquad(ctx, "highshelf", 4500, 0.7), powerIn = gainNode(ctx), power = shaper(ctx, "soft", 1), master = gainNode(ctx), trim = gainNode(ctx, dbToGain(A.trim || 0));
  // input → hp → voicing → stages → tone stack → presence → power amp → master
  let last = inHp;
  input.connect(inHp);
  for (const v of voice) { last.connect(v); last = v; }
  for (const st of stages) { last.connect(st.g); last = st.dc; }
  series(last, bass, mid, treble, presence, powerIn);
  if (A.power > 0) series(powerIn, power, master); else powerIn.connect(master);
  master.connect(trim);
  const knobs = { ...p };
  const set = (k, v) => {
    knobs[k] = v;
    const t = v / 10;
    if (k === "gain") {
      stages.forEach((st, i) => ramp(ctx, st.g.gain, dbToGain(st.base + st.range * t - (i === 0 ? 6 : 0))));
      if (!stages.length) ramp(ctx, input.gain, dbToGain(lerp(-6, 6, t)));
    }
    if (k === "bass") bass.gain.value = lerp(-12, 12, t);
    if (k === "mid") mid.gain.value = lerp(-12, 10, t);
    if (k === "treble") treble.gain.value = lerp(-12, 10, t);
    if (k === "presence") presence.gain.value = lerp(-6, 8, t);
    if (k === "master") {
      // more master pushes the power amp harder; keep the output level roughly constant
      const drive = A.power * lerp(0.4, 3, t);
      if (A.power > 0) { ramp(ctx, powerIn.gain, Math.max(0.2, drive)); ramp(ctx, master.gain, dbToGain(lerp(-26, -8, t)) / Math.max(0.6, Math.sqrt(drive))); }
      else ramp(ctx, master.gain, dbToGain(lerp(-24, 0, t)));
    }
  };
  Object.entries(knobs).forEach(([k, v]) => set(k, v));
  return { input, output: trim, set, dispose: () => {} };
}

// ================================================================== cabinets and mics
/** Speaker cabinets as filter chains: low resonance, cone break-up and the steep high roll-off. */
export const CABS = {
  direct: [],
  c1x12_open: [["highpass", 85, 0.9], ["peaking", 120, 1.2, 3], ["peaking", 2500, 1, 3], ["lowpass", 5600, 0.9], ["lowpass", 7000, 0.7]],
  c2x12_open: [["highpass", 75, 1], ["peaking", 110, 1.2, 4], ["peaking", 1800, 1, 2], ["lowpass", 5200, 0.9], ["lowpass", 6500, 0.7]],
  c4x12_closed: [["highpass", 70, 1.1], ["peaking", 100, 1.4, 6], ["peaking", 400, 1, -3], ["peaking", 2200, 1.2, 4], ["lowpass", 4600, 1], ["lowpass", 5500, 0.7]],
  c1x10: [["highpass", 120, 0.9], ["peaking", 1200, 1, 4], ["lowpass", 4800, 0.9], ["lowpass", 6000, 0.7]],
  c2x10: [["highpass", 100, 1], ["peaking", 1500, 1, 3], ["lowpass", 5200, 0.9], ["lowpass", 6500, 0.7]],
  c1x15: [["highpass", 55, 1], ["peaking", 90, 1.2, 3], ["lowpass", 3600, 0.9], ["lowpass", 4500, 0.7]],
  c4x10_bass: [["highpass", 45, 1], ["peaking", 80, 1.2, 4], ["peaking", 2000, 1, 2], ["lowpass", 4500, 0.9]],
};

export const MICS = {
  dynamic: [["highpass", 90, 0.7], ["peaking", 5500, 1.2, 4], ["lowpass", 12000, 0.7]],
  dynamic_large: [["highpass", 60, 0.7], ["peaking", 4000, 1, 3], ["lowpass", 14000, 0.7]],
  condenser: [["highpass", 30, 0.7], ["highshelf", 10000, 0.7, 2]],
  ribbon: [["peaking", 150, 1, 2], ["highshelf", 6000, 0.7, -6], ["lowpass", 9000, 0.7]],
};

/** Cabinet + microphone (position, distance, room). An impulse response file replaces both. */
export function buildCab(ctx, cab, mic, irBuffer = null) {
  const input = gainNode(ctx), output = gainNode(ctx), close = gainNode(ctx), room = gainNode(ctx, 0);
  const conv = ctx.createConvolver();
  let chain = [];
  if (irBuffer) {
    conv.buffer = irBuffer;
    input.connect(conv).connect(close);
  } else {
    const cf = (CABS[cab] || []).map(([t, f, q, g = 0]) => biquad(ctx, t, f, q, g));
    const mf = cab === "direct" ? [] : (MICS[mic.type] || MICS.dynamic).map(([t, f, q, g = 0]) => biquad(ctx, t, f, q, g));
    chain = [...cf, ...mf];
    if (cab !== "direct") {
      chain.push(biquad(ctx, "highshelf", 3000, 0.7, 0), biquad(ctx, "lowshelf", 200, 0.7, 0));   // position, proximity
    }
    if (chain.length) { input.connect(chain[0]); series(...chain); chain[chain.length - 1].connect(close); }
    else input.connect(close);
  }
  close.connect(output);
  const roomConv = ctx.createConvolver();
  roomConv.buffer = reverbIR(ctx, "room", 0.45, 0.4);
  close.connect(roomConv).connect(room).connect(output);
  const set = (k, v) => {
    const n = chain.length;
    if (k === "position" && n >= 2) chain[n - 2].gain.value = lerp(3, -7, v);        // 0 = center of the cone, 1 = edge
    if (k === "distance" && n >= 2) {
      const prox = mic.type === "condenser" ? 2 : 6;
      chain[n - 1].gain.value = lerp(prox, -2, v);
      ramp(ctx, close.gain, lerp(1, 0.6, v));
    }
    if (k === "room") ramp(ctx, room.gain, v * 0.8);
  };
  ["position", "distance", "room"].forEach(k => mic[k] != null && set(k, mic[k]));
  return { input, output, set, dispose: () => {} };
}
