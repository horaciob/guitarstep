// Building blocks for the tone rig: filters, clipping curves, LFOs and generated impulse responses.

export const dbToGain = d => Math.pow(10, d / 20);
export const lerp = (a, b, t) => a + (b - a) * t;
/** 0..1 → a..b on a log scale (for frequencies and times). */
export const logMap = (a, b, t) => a * Math.pow(b / a, t);

export function biquad(ctx, type, frequency, Q = 0.707, gain = 0) {
  const f = ctx.createBiquadFilter();
  f.type = type;
  f.frequency.value = frequency;
  f.Q.value = Q;
  f.gain.value = gain;
  return f;
}

export function gainNode(ctx, value = 1) {
  const g = ctx.createGain();
  g.gain.value = value;
  return g;
}

/** Connects nodes in series; returns [first, last]. */
export function series(...nodes) {
  for (let i = 0; i < nodes.length - 1; i++) nodes[i].connect(nodes[i + 1]);
  return [nodes[0], nodes[nodes.length - 1]];
}

/** Smoothly moves an AudioParam (no zipper noise). */
export function ramp(ctx, param, value, time = 0.03) {
  const now = ctx.currentTime;
  param.cancelScheduledValues(now);
  param.setTargetAtTime(value, now, time / 3);
}

export function lfo(ctx, rate, type = "sine") {
  const o = ctx.createOscillator();
  o.type = type;
  o.frequency.value = rate;
  o.start();
  return o;
}

// ------------------------------------------------------------------ clipping curves
const curves = new Map();
/**
 * Transfer curve for a WaveShaperNode.
 * soft: symmetric tanh (tube preamp) · asym: uneven tube clipping (even harmonics)
 * hard: diode-like hard clip · fuzz: heavy, asymmetric, almost square · rect: full-wave (octave up)
 */
export function curve(kind, amount = 1) {
  const key = kind + ":" + amount.toFixed(3);
  if (curves.has(key)) return curves.get(key);
  const n = 4096, c = new Float32Array(n), k = Math.max(0.01, amount);
  for (let i = 0; i < n; i++) {
    const x = (i / (n - 1)) * 2 - 1;
    let y;
    switch (kind) {
      case "asym": y = x >= 0 ? Math.tanh(k * x) : Math.tanh(k * 0.6 * x) * 1.2; break;
      case "hard": { const v = k * x; y = Math.abs(v) < 0.8 ? v : Math.sign(v) * (0.8 + 0.2 * Math.tanh((Math.abs(v) - 0.8) * 5)); break; }
      case "fuzz": { const v = k * (x + 0.15); y = Math.sign(v) * (1 - Math.exp(-Math.abs(v) * 2)) - Math.sign(0.15 * k) * (1 - Math.exp(-Math.abs(0.15 * k) * 2)); break; }
      case "rect": y = Math.abs(x) * 2 - 0.5; break;
      default: y = Math.tanh(k * x);
    }
    c[i] = y;
  }
  // normalize to ±1
  let peak = 0;
  for (const v of c) peak = Math.max(peak, Math.abs(v));
  if (peak > 0) for (let i = 0; i < n; i++) c[i] /= peak;
  curves.set(key, c);
  return c;
}

export function shaper(ctx, kind, amount) {
  const s = ctx.createWaveShaper();
  s.curve = curve(kind, amount);
  s.oversample = "4x";
  return s;
}

// ------------------------------------------------------------------ dry / wet
/** A node pair with dry and wet paths: connect your effect between wetIn and wetOut. */
export function dryWet(ctx, mix = 0.5) {
  const input = gainNode(ctx), output = gainNode(ctx), dry = gainNode(ctx), wet = gainNode(ctx), wetIn = gainNode(ctx);
  input.connect(dry).connect(output);
  input.connect(wetIn);
  wet.connect(output);
  const set = m => {
    ramp(ctx, dry.gain, Math.cos(m * Math.PI / 2));
    ramp(ctx, wet.gain, Math.sin(m * Math.PI / 2));
  };
  set(mix);
  return { input, output, wetIn, wetOut: wet, setMix: set };
}

// ------------------------------------------------------------------ impulse responses
let seed = 1;
const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 * 2 - 1; };

/**
 * Synthetic reverb IR: decaying stereo noise with a darkening tail.
 * kind: room | hall | plate | spring
 */
export function reverbIR(ctx, kind, decay = 2, tone = 0.5) {
  seed = 12345;
  const sr = ctx.sampleRate;
  const len = Math.floor(sr * Math.min(8, decay * 1.2 + 0.1));
  const buf = ctx.createBuffer(2, len, sr);
  const pre = Math.floor(sr * ({ room: 0.004, hall: 0.025, plate: 0.002, spring: 0.008 }[kind] || 0.01));
  const density = kind === "room" ? 0.35 : 1;
  const k = 6.9 / (decay * sr);                          // −60 dB at `decay` seconds
  const cutStart = logMap(2500, 12000, tone), cutEnd = cutStart * (kind === "plate" ? 0.7 : 0.25);
  for (let ch = 0; ch < 2; ch++) {
    const d = buf.getChannelData(ch);
    let lp = 0;
    for (let i = pre; i < len; i++) {
      const t = (i - pre) / len;
      const cut = lerp(cutStart, cutEnd, t);
      const a = 1 - Math.exp(-2 * Math.PI * cut / sr);
      let v = (rnd() + 1) / 2 < density ? rnd() : 0;
      lp += a * (v - lp);
      d[i] = lp * Math.exp(-k * (i - pre));
    }
    if (kind === "room") {        // early reflections
      for (const [ms, g] of [[7, 0.6], [11, 0.45], [17, 0.35], [23, 0.3], [31, 0.2]]) {
        const i = pre + Math.floor(ms / 1000 * sr * (ch ? 1.07 : 1));
        if (i < len) d[i] += g * (ch ? -1 : 1);
      }
    }
    if (kind === "spring") {      // the "boing": repeating dispersive chirps
      const period = Math.floor(sr * 0.033);
      for (let rep = 0, start = pre; start < len && rep < 60; rep++, start += period + (ch ? 40 : 0)) {
        const g = 0.25 * Math.exp(-k * (start - pre)), n = Math.floor(sr * 0.018);
        for (let j = 0; j < n && start + j < len; j++) {
          const tt = j / sr, f = lerp(4200, 600, j / n);
          d[start + j] += g * Math.sin(2 * Math.PI * f * tt) * (1 - j / n);
        }
      }
    }
  }
  return buf;
}
