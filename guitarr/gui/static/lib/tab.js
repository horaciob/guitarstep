// Plain-text tab for a run of notes (lessons, licks, the daily warm-up).
import { stringRow } from "./ui.js";

const NAMES = ["e", "B", "G", "D", "A", "E"];     // 1st string → 6th; the line order follows your setting

/** Steps grouped by moment: a step and the notes played together with it (together: true). */
export function stepGroups(steps) {
  const out = [];
  steps.forEach(st => { if (st.together && out.length) out[out.length - 1].push(st); else out.push([st]); });
  return out;
}

/** Tab for lick and bend steps: one column per moment (notes together share it), with h p / \ b r ~ as in written tab. */
export function tabText(steps) {
  const lines = [];
  NAMES.forEach((s, i) => { lines[stringRow(i + 1, NAMES.length)] = `${s}|-`; });
  stepGroups(steps).forEach(group => {
    const cells = new Map();
    group.forEach(st => {
      const from = st.glide_from;
      const cell = st.tech === "bend" ? `${st.fret}b${st.fret + st.pitch - from}`
        : st.tech === "release" ? `r${st.fret}`
        : st.tech === "hammer" ? `h${st.fret}` : st.tech === "pull" ? `p${st.fret}`
        : st.tech === "slide" ? `${st.pitch > from ? "/" : "\\"}${st.fret}` : `${st.fret}`;
      cells.set(stringRow(st.string, NAMES.length), cell + (st.vibrato ? "~" : ""));
    });
    const w = Math.max(...[...cells.values()].map(c => c.length));
    lines.forEach((l, i) => { const c = cells.get(i) || ""; lines[i] += c + "-".repeat(w - c.length) + "--"; });
  });
  return lines.map(l => l + "|").join("\n");
}
