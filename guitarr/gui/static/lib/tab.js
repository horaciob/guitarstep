// Plain-text tab for a run of notes (lessons, licks, the daily warm-up).
const STRINGS = ["e", "B", "G", "D", "A", "E"];   // tab lines, 1st string on top

/** Tab for lick and bend steps: one column per note, with h p / \ b r ~ as in written tab. */
export function tabText(steps) {
  const lines = STRINGS.map(s => `${s}|-`);
  steps.forEach(st => {
    const from = st.glide_from;
    const cell = st.tech === "bend" ? `${st.fret}b${st.fret + st.pitch - from}`
      : st.tech === "release" ? `r${st.fret}`
      : st.tech === "hammer" ? `h${st.fret}` : st.tech === "pull" ? `p${st.fret}`
      : st.tech === "slide" ? `${st.pitch > from ? "/" : "\\"}${st.fret}` : `${st.fret}`;
    const txt = cell + (st.vibrato ? "~" : "");
    lines.forEach((l, i) => { lines[i] += (i === st.string - 1 ? txt : "-".repeat(txt.length)) + "--"; });
  });
  return lines.map(l => l + "|").join("\n");
}
