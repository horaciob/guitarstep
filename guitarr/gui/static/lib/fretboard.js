// A fretboard drawing: a window of frets with marks (notes, degrees, chord tones), optionally clickable.
// Used by lessons (pick the notes, show a scale) and tools. Marks always carry a label, never color alone.
import { esc, instrument, pluck } from "./ui.js";

/**
 * neck(box, { lo, hi, marks, selectable, onToggle, label })
 *   marks: [{ string, fret, text, kind }]  kind: "root" | "tone" | "mark" | "right" | "wrong" | "missed"
 *   selectable: click a position to select it (it also sounds); onToggle(selected) after each click.
 * Returns { set(marks), selected(), clear(), lock() }.
 */
export function neck(box, { lo = 0, hi = 12, marks = [], selectable = false, onToggle = null, label = "" } = {}) {
  const strings = instrument.strings;                       // 1st string first, MIDI numbers
  const NS = strings.length, first = Math.max(0, lo), last = Math.max(first + 3, hi);
  const nF = last - first + (first === 0 ? 0 : 1);           // fret spaces drawn
  const W = 1000, x0 = first === 0 ? 46 : 18, top = 24, gap = 32, H = top + (NS - 1) * gap + 40;
  const span = W - x0 - 14;
  const fx0 = n => x0 + span * (n - (first === 0 ? 0 : first - 1)) / nF;     // even spacing: easier to click
  const fx = n => (instrument.left_handed ? W - fx0(n) : fx0(n));
  const nutX = instrument.left_handed ? W - (x0 - 22) : x0 - 22;
  const cx = n => n === 0 ? nutX : (fx(n - 1) + fx(n)) / 2;
  const cy = i => top + i * gap;
  let sel = new Set(), cur = marks, locked = false;
  const key = (s, f) => `${s}:${f}`;

  const draw = () => {
    let s = "";
    const f0 = first === 0 ? 0 : first - 1;
    for (let n = f0; n <= last; n++) s += `<line x1="${fx(n)}" x2="${fx(n)}" y1="${top}" y2="${cy(NS - 1)}" stroke="currentColor" stroke-opacity="${n === 0 ? 1 : .3}" stroke-width="${n === 0 ? 6 : 2}"/>`;
    [3, 5, 7, 9, 15, 17].filter(n => n >= Math.max(1, first) && n <= last).forEach(n =>
      s += `<circle cx="${cx(n)}" cy="${cy((NS - 1) / 2)}" r="6" fill="currentColor" opacity=".12"/>`);
    if (12 >= Math.max(1, first) && 12 <= last) s += `<circle cx="${cx(12)}" cy="${cy(1.5)}" r="6" fill="currentColor" opacity=".12"/><circle cx="${cx(12)}" cy="${cy(NS - 2.5)}" r="6" fill="currentColor" opacity=".12"/>`;
    for (let i = 0; i < NS; i++) s += `<line x1="${fx(f0)}" x2="${fx(last)}" y1="${cy(i)}" y2="${cy(i)}" stroke="currentColor" stroke-opacity=".5" stroke-width="${1 + i * 0.35}"/>`;
    const byPos = new Map(cur.map(m => [key(m.string, m.fret), m]));
    for (let i = 0; i < NS; i++) {
      const string = i + 1;
      for (let n = first; n <= last; n++) {
        const m = byPos.get(key(string, n)), on = sel.has(key(string, n));
        const kind = m ? m.kind || "mark" : on ? "sel" : "";
        s += `<g class="fb-pos${selectable ? " click" : ""}" data-s="${string}" data-f="${n}" data-p="${strings[i] + n}"
          ${selectable ? `role="checkbox" tabindex="0" aria-checked="${on}" aria-label="${esc(`${string} · ${n}`)}"` : ""}>
          <rect x="${cx(n) - 18}" y="${cy(i) - 14}" width="36" height="28" fill="transparent"/>`;
        if (kind) {
          s += `<circle class="fb-dot ${kind}" cx="${cx(n)}" cy="${cy(i)}" r="12"/>`;
          const text = m ? m.text ?? "" : "✓";
          if (text !== "") s += `<text class="fb-txt ${kind}" x="${cx(n)}" y="${cy(i) + 4}" text-anchor="middle">${esc(String(text))}</text>`;
        }
        s += `</g>`;
      }
    }
    for (let n = Math.max(1, first); n <= last; n++) s += `<text x="${cx(n)}" y="${cy(NS - 1) + 26}" text-anchor="middle" font-size="12" fill="var(--muted)">${n}</text>`;
    box.innerHTML = `<div class="neck-wrap"><svg class="fb" viewBox="0 0 ${W} ${H}" role="${selectable ? "group" : "img"}" aria-label="${esc(label)}">${s}</svg></div>`;
    box.querySelectorAll(".fb-pos").forEach(g => {
      const act = () => {
        pluck(+g.dataset.p);
        if (!selectable || locked) return;
        const k = key(g.dataset.s, g.dataset.f);
        sel.has(k) ? sel.delete(k) : sel.add(k);
        draw();
        onToggle && onToggle(api.selected());
        box.querySelector(`.fb-pos[data-s="${g.dataset.s}"][data-f="${g.dataset.f}"]`)?.focus();
      };
      g.addEventListener("click", act);
      g.addEventListener("keydown", e => { if (e.key === " " || e.key === "Enter") { e.preventDefault(); e.stopPropagation(); act(); } });
    });
  };
  const api = {
    set(m) { cur = m; draw(); },
    selected: () => [...sel].map(k => k.split(":").map(Number)),
    clear() { sel = new Set(); draw(); },
    lock() { locked = true; },
  };
  draw();
  return api;
}
