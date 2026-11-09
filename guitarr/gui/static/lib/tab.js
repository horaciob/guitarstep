// Plain-text tab for a run of notes (lessons, licks, the daily warm-up).
import { stringRow } from "./ui.js";

const NAMES = ["e", "B", "G", "D", "A", "E"];     // 1st string → 6th; the line order follows your setting

/** Tab for lick and bend steps: one column per note, with h p / \ b r ~ as in written tab. */
export function tabText(steps) {
  const lines = [];
  NAMES.forEach((s, i) => { lines[stringRow(i + 1, NAMES.length)] = `${s}|-`; });
  steps.forEach(st => {
    const from = st.glide_from;
    const cell = st.tech === "bend" ? `${st.fret}b${st.fret + st.pitch - from}`
      : st.tech === "release" ? `r${st.fret}`
      : st.tech === "hammer" ? `h${st.fret}` : st.tech === "pull" ? `p${st.fret}`
      : st.tech === "slide" ? `${st.pitch > from ? "/" : "\\"}${st.fret}` : `${st.fret}`;
    const txt = cell + (st.vibrato ? "~" : "");
    const row = stringRow(st.string, NAMES.length);
    lines.forEach((l, i) => { lines[i] += (i === row ? txt : "-".repeat(txt.length)) + "--"; });
  });
  return lines.map(l => l + "|").join("\n");
}
