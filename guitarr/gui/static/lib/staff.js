// Standard notation: notes on a five-line staff in the treble clef with the small 8 below (guitar sounds an
// octave lower than written). The server says where each note goes (theory.staff_note): its step from the middle
// line (+ up, each step half a space) and its accidental.
import { esc } from "./ui.js";
import { t } from "./i18n.js";

const GAP = 12;                                             // space between two lines

/** notes: [{ step, acc, name? }] · opts: { width, label, names (show each name under its note) } */
export function staffSvg(notes, { width = 0, label = "", names = false } = {}) {
  const steps = notes.map(n => n.step);
  const top = Math.max(6, ...steps), bottom = Math.min(-6, ...steps);
  const y0 = 18 + (top - 4) * GAP / 2 + 2 * GAP;             // y of the middle line
  const y = step => y0 - step * GAP / 2;
  const H = Math.round(y(bottom) + (names ? 40 : 22));
  const each = 64, left = 70, W = width || left + Math.max(1, notes.length) * each + 20;
  let s = `<svg class="staff-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label || t("staff.label"))}">`;
  for (let l = -4; l <= 4; l += 2) s += `<line x1="8" x2="${W - 8}" y1="${y(l)}" y2="${y(l)}" class="st-line"/>`;
  s += `<line x1="${W - 8}" x2="${W - 8}" y1="${y(4)}" y2="${y(-4)}" class="st-line"/>`;
  s += `<text x="10" y="${y(-5)}" class="st-clef" aria-hidden="true">𝄞</text><text x="27" y="${y(-9) + 2}" class="st-eight" aria-hidden="true">8</text>`;
  notes.forEach((n, i) => {
    const cx = left + 26 + i * each, cy = y(n.step);
    for (let l = 6; l <= n.step; l += 2) s += `<line x1="${cx - 13}" x2="${cx + 13}" y1="${y(l)}" y2="${y(l)}" class="st-line"/>`;
    for (let l = -6; l >= n.step; l -= 2) s += `<line x1="${cx - 13}" x2="${cx + 13}" y1="${y(l)}" y2="${y(l)}" class="st-line"/>`;
    if (n.acc) s += `<text x="${cx - 20}" y="${cy + 6}" class="st-acc">${n.acc > 0 ? "♯" : "♭"}</text>`;
    s += `<ellipse cx="${cx}" cy="${cy}" rx="7.5" ry="5.6" transform="rotate(-20 ${cx} ${cy})" class="st-head"/>`;
    const up = n.step < 0;                                   // stems up below the middle line, down above it
    s += `<line x1="${up ? cx + 6.8 : cx - 6.8}" x2="${up ? cx + 6.8 : cx - 6.8}" y1="${cy}" y2="${up ? cy - 3.5 * GAP : cy + 3.5 * GAP}" class="st-stem"/>`;
    if (names && n.name) s += `<text x="${cx}" y="${H - 8}" class="st-name">${esc(n.name.replace("#", "♯").replace(/b$/, "♭"))}</text>`;
  });
  return s + `</svg>`;
}
