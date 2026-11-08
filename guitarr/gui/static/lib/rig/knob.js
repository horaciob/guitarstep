// Rotary knob: drag up/down (Shift = fine), mouse wheel, arrow keys, double-click resets.
// Accessible as a slider (role="slider", aria-valuenow/valuetext).
const ARC = 270, START = -135;

function polar(cx, cy, r, deg) {
  const a = (deg - 90) * Math.PI / 180;
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}
function arc(cx, cy, r, a0, a1) {
  const [x0, y0] = polar(cx, cy, r, a0), [x1, y1] = polar(cx, cy, r, a1);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/**
 * knob({ label, min, max, step, value, def, format(v), onInput(v), size, color, skin })
 * skin: "" (flat), "pedal" (a stompbox knob) or "chicken" (an amp's pointer knob); colors come from CSS.
 * Returns the element; el.setValue(v) updates it without firing onInput.
 */
export function knob({ label, min, max, step = (max - min) / 100, value, def = value, format = v => v, onInput, size = 54, color = null, skin = "" }) {
  const el = document.createElement("div");
  el.className = "knob" + (skin ? ` knob-${skin}` : "");
  el.tabIndex = 0;
  el.setAttribute("role", "slider");
  el.setAttribute("aria-label", label);
  el.setAttribute("aria-valuemin", min);
  el.setAttribute("aria-valuemax", max);
  const c = size / 2, r = size / 2 - 5;
  el.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
      <path class="knob-track" d="${arc(c, c, r, START, START + ARC)}"/>
      <path class="knob-val" d="" ${color ? `style="stroke:${color}"` : ""}/>
      <circle class="knob-skirt" cx="${c}" cy="${c}" r="${r - 4}"/>
      <circle class="knob-cap" cx="${c}" cy="${c}" r="${r - 6}"/>
      <g class="knob-rot">
        ${skin === "chicken" ? `<path class="knob-head" d="M${c - 4} ${c + 6} L${c} ${c - r + 4} L${c + 4} ${c + 6} Z"/>` : ""}
        <line class="knob-ptr" x1="${c}" y1="${c}" x2="${c}" y2="${c - r + 9}"/>
      </g>
    </svg><b class="knob-v"></b><span class="knob-l"></span>`;
  el.querySelector(".knob-l").textContent = label;
  const valPath = el.querySelector(".knob-val"), ptr = el.querySelector(".knob-rot"), out = el.querySelector(".knob-v");
  let v = value;
  const snap = x => {
    const s = Math.round((x - min) / step) * step + min;
    return Math.min(max, Math.max(min, +s.toFixed(6)));
  };
  const draw = () => {
    const t = (v - min) / (max - min), deg = START + ARC * t;
    // bipolar knobs (min < 0 < max) fill from the center
    const zero = min < 0 && max > 0 ? START + ARC * (-min / (max - min)) : START;
    valPath.setAttribute("d", Math.abs(deg - zero) < 0.5 ? "" : arc(c, c, r, Math.min(zero, deg), Math.max(zero, deg)));
    ptr.setAttribute("transform", `rotate(${deg} ${c} ${c})`);
    const txt = String(format(v));
    out.textContent = txt;
    el.setAttribute("aria-valuenow", v);
    el.setAttribute("aria-valuetext", txt);
  };
  const set = (x, fire = true) => {
    const nv = snap(x);
    if (nv === v) return;
    v = nv; draw();
    if (fire && onInput) onInput(v);
  };
  el.setValue = x => { v = snap(x); draw(); };
  draw();

  let startY = 0, startV = 0, dragging = false;
  el.addEventListener("pointerdown", e => {
    if (e.button !== 0) return;
    dragging = true; startY = e.clientY; startV = v;
    el.setPointerCapture(e.pointerId);
    el.classList.add("drag");
    e.preventDefault();
    el.focus();
  });
  el.addEventListener("pointermove", e => {
    if (!dragging) return;
    const range = max - min, px = e.shiftKey ? 600 : 160;
    set(startV + (startY - e.clientY) / px * range);
  });
  const end = () => { dragging = false; el.classList.remove("drag"); };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
  el.addEventListener("dblclick", () => set(def));
  el.addEventListener("wheel", e => {
    e.preventDefault();
    set(v + Math.sign(-e.deltaY) * step * (e.shiftKey ? 1 : 5));
  }, { passive: false });
  el.addEventListener("keydown", e => {
    const big = (max - min) / 10;
    const k = { ArrowUp: step, ArrowRight: step, ArrowDown: -step, ArrowLeft: -step, PageUp: big, PageDown: -big }[e.key];
    if (k != null) { e.preventDefault(); set(v + k * (e.shiftKey ? 5 : 1)); }
    else if (e.key === "Home") { e.preventDefault(); set(min); }
    else if (e.key === "End") { e.preventDefault(); set(max); }
  });
  return el;
}
