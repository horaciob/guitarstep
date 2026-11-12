// Tone match: compares the balance of lows, mids and highs of a recording with your sound, and sets the
// 7-band EQ to move your sound toward it. It matches the spectrum, not the gain or the effects: pick a part
// where the guitar plays alone (a full mix also carries bass, drums and voice).
import { biquad } from "./dsp.js";

export const BANDS = [100, 200, 400, 800, 1600, 3200, 6400];
const Q = 1.4;

const db = power => 10 * Math.log10(Math.max(power, 1e-12));

/** Level (dB) of each band of an audio file, over `seconds` from `start`. */
export async function fileBands(file, start = 0, seconds = 30) {
  const bytes = await file.arrayBuffer();
  const tmp = new OfflineAudioContext(1, 1, 44100);
  const buf = await tmp.decodeAudioData(bytes);
  const sr = buf.sampleRate, from = Math.min(Math.floor(start * sr), Math.max(0, buf.length - sr));
  const len = Math.max(sr, Math.min(buf.length - from, Math.floor(seconds * sr)));
  const out = [];
  for (const f of BANDS) {
    const ctx = new OfflineAudioContext(1, len, sr);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(biquad(ctx, "bandpass", f, Q)).connect(ctx.destination);
    src.start(0, from / sr, len / sr);
    const data = (await ctx.startRendering()).getChannelData(0);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
    out.push(db(sum / data.length));
  }
  return { bands: out, duration: buf.duration };
}

/** Level (dB) of each band of the rig's sound while you play, over `seconds` with signal. onTick(0..1) reports progress. */
export function liveBands(rig, seconds = 6, onTick = () => {}) {
  const ctx = rig.ctx, taps = BANDS.map(f => {
    const bp = biquad(ctx, "bandpass", f, Q), an = ctx.createAnalyser();
    an.fftSize = 2048;
    rig.level.connect(bp); bp.connect(an);
    return { bp, an, sum: 0, n: 0 };
  });
  const buf = new Float32Array(2048);
  return new Promise(resolve => {
    let heard = 0;
    const timer = setInterval(() => {
      if (rig.levels().input < -50) return;                     // only while you play
      heard += 0.05;
      for (const tp of taps) {
        tp.an.getFloatTimeDomainData(buf);
        let s = 0;
        for (const v of buf) s += v * v;
        tp.sum += s / buf.length; tp.n++;
      }
      onTick(Math.min(1, heard / seconds));
      if (heard >= seconds) {
        clearInterval(timer);
        for (const tp of taps) { try { rig.level.disconnect(tp.bp); } catch { /* gone */ } }
        resolve(taps.map(tp => db(tp.sum / Math.max(1, tp.n))));
      }
    }, 50);
  });
}

/** EQ gains that move `mine` toward `target` (shapes compared, not overall level), added to the gains `now`. */
export function eqFor(target, mine, now = BANDS.map(() => 0)) {
  const shape = xs => { const m = xs.reduce((a, b) => a + b, 0) / xs.length; return xs.map(x => x - m); };
  const t = shape(target), m = shape(mine);
  return BANDS.map((_, i) => Math.max(-12, Math.min(12, Math.round((now[i] + t[i] - m[i]) * 2) / 2)));
}
