// Pitch detection for the rig's tuner: normalized autocorrelation with parabolic
// interpolation (works well for single guitar notes from 70 Hz to 1.3 kHz).

const NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const STANDARD = [40, 45, 50, 55, 59, 64];            // E2 A2 D3 G3 B3 E4

/** Frequency in Hz of the strongest periodicity in `buf`, or null if there isn't a clear one. */
export function detectPitch(buf, sampleRate, { minHz = 70, maxHz = 1300, minRms = 0.004 } = {}) {
  const n = buf.length;
  let rms = 0;
  for (let i = 0; i < n; i++) rms += buf[i] * buf[i];
  if (Math.sqrt(rms / n) < minRms) return null;
  const minLag = Math.floor(sampleRate / maxHz), maxLag = Math.min(Math.floor(sampleRate / minHz), n >> 1);
  const corr = new Float32Array(maxLag + 2);
  for (let lag = minLag; lag <= maxLag + 1; lag++) {
    let sum = 0, e1 = 0, e2 = 0;
    for (let i = 0; i < n - lag; i++) {
      const a = buf[i], b = buf[i + lag];
      sum += a * b; e1 += a * a; e2 += b * b;
    }
    corr[lag] = sum / (Math.sqrt(e1 * e2) || 1);
  }
  // the first peak above 90% of the best one avoids octave errors (picking 2× the period)
  let best = 0;
  for (let lag = minLag; lag <= maxLag; lag++) best = Math.max(best, corr[lag]);
  if (best < 0.8) return null;
  let lag = minLag;
  while (lag <= maxLag && !(corr[lag] >= 0.9 * best && corr[lag] >= corr[lag - 1] && corr[lag] >= corr[lag + 1])) lag++;
  if (lag > maxLag) return null;
  const a = corr[lag - 1], b = corr[lag], c = corr[lag + 1];
  const shift = (a - c) / (2 * (a - 2 * b + c) || 1);
  return sampleRate / (lag + (Number.isFinite(shift) ? shift : 0));
}

/** Note name, cents off, and the nearest open string (standard tuning) when it's close. */
export function noteOf(freq, a4 = 440) {
  const midi = 69 + 12 * Math.log2(freq / a4), near = Math.round(midi);
  const string = STANDARD.reduce((x, y) => (Math.abs(y - midi) < Math.abs(x - midi) ? y : x));
  return {
    note: NOTE_NAMES[((near % 12) + 12) % 12] + (Math.floor(near / 12) - 1),
    cents: (midi - near) * 100,
    string: Math.abs(string - midi) < 0.75 ? 6 - STANDARD.indexOf(string) : null,
    stringCents: (midi - string) * 100,
  };
}
