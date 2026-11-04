// Herramientas: metrónomo (tap tempo), minuto de cambio (contado por audio) y diapasón.
import { $, $$, api, audioCtx, chordSvg, click, esc, NOTE_NAMES, OPEN, pluck, toast } from "../lib/ui.js";
import { listen } from "../lib/listen.js";

let metro = null, drill = null, countdownTimer = null;

export async function mount(el, { params }) {
  const tab = params.t || "metronomo";
  el.innerHTML = `
    <div class="gl-head"><h1>Herramientas</h1></div>
    <div class="seg tabs" id="tabs">
      <button data-t="metronomo">Metrónomo</button>
      <button data-t="minuto">Minuto de cambio</button>
      <button data-t="diapason">Diapasón</button>
    </div>
    <div id="tool"></div>`;
  $$("#tabs button", el).forEach(b => {
    b.classList.toggle("active", b.dataset.t === tab);
    b.onclick = () => { location.hash = `#/herramientas?t=${b.dataset.t}`; };
  });
  const box = $("#tool", el);
  if (tab === "minuto") await minuto(box);
  else if (tab === "diapason") diapason(box);
  else metronomo(box);
}

export function unmount() {
  if (metro) metro.stop();
  metro = null;
  if (drill) drill.stop();
  drill = null;
  clearInterval(countdownTimer);
}

// ------------------------------------------------------------------ metrónomo
function metronomo(box) {
  let bpm = 90, beats = 4, taps = [];
  box.innerHTML = `
    <div class="panel metro">
      <div class="metro-bpm"><button class="btn" data-d="-5">−5</button><button class="btn" data-d="-1">−1</button>
        <div><b id="bpm">${bpm}</b><small class="muted">bpm</small></div>
        <button class="btn" data-d="1">+1</button><button class="btn" data-d="5">+5</button></div>
      <input type="range" id="bpmR" min="40" max="240" value="${bpm}" aria-label="Tempo">
      <div class="metro-dots" id="dots"></div>
      <div class="row center">
        <div class="seg" id="sig">${[2, 3, 4, 6].map(n => `<button data-n="${n}">${n}/${n === 6 ? 8 : 4}</button>`).join("")}</div>
        <button class="btn" id="tap">Tap tempo</button>
        <button class="btn primary" id="play">▶ Empezar</button>
      </div>
      <p class="muted small center">Tap tempo: tocá el botón (o la barra espaciadora) al ritmo, al menos 3 veces.</p>
    </div>`;
  const setBpm = v => { bpm = Math.max(40, Math.min(240, Math.round(v))); $("#bpm", box).textContent = bpm; $("#bpmR", box).value = bpm; };
  const drawDots = (on = -1) => { $("#dots", box).innerHTML = Array.from({ length: beats }, (_, i) => `<i class="${i === on ? "on" : ""}${i === 0 ? " first" : ""}"></i>`).join(""); };
  const setSig = n => { beats = n; $$("#sig button", box).forEach(b => b.classList.toggle("active", +b.dataset.n === n)); drawDots(); };
  setSig(4);
  $$("[data-d]", box).forEach(b => b.onclick = () => setBpm(bpm + +b.dataset.d));
  $("#bpmR", box).oninput = e => setBpm(+e.target.value);
  $$("#sig button", box).forEach(b => b.onclick = () => setSig(+b.dataset.n));
  const tap = () => {
    const t = performance.now();
    taps = taps.filter(x => t - x < 3000).concat(t);
    if (taps.length >= 3) {
      const d = taps.slice(1).map((x, i) => x - taps[i]);
      setBpm(60000 / (d.reduce((a, b) => a + b) / d.length));
    }
  };
  $("#tap", box).onclick = tap;
  const onKey = e => { if (e.code === "Space" && document.body.contains(box)) { e.preventDefault(); tap(); } };
  document.addEventListener("keydown", onKey);

  // planificador con lookahead (el reloj de Web Audio es preciso; setInterval no)
  metro = {
    running: false, next: 0, n: 0, timer: null,
    start() {
      const ac = audioCtx();
      this.running = true; this.next = ac.currentTime + 0.1; this.n = 0;
      this.timer = setInterval(() => {
        while (this.next < ac.currentTime + 0.12) {
          const beat = this.n % beats;
          click(this.next, beat === 0);
          const delay = Math.max(0, (this.next - ac.currentTime) * 1000);
          setTimeout(() => drawDots(beat), delay);
          this.next += 60 / bpm * (beats === 6 ? 0.5 : 1);
          this.n++;
        }
      }, 25);
      $("#play", box).textContent = "■ Parar";
    },
    stop() {
      clearInterval(this.timer); this.running = false; drawDots();
      document.removeEventListener("keydown", onKey);
      const p = $("#play", box); if (p) p.textContent = "▶ Empezar";
    },
  };
  $("#play", box).onclick = () => {
    if (metro.running) { metro.stop(); document.addEventListener("keydown", onKey); } else metro.start();
  };
}

// ------------------------------------------------------------------ minuto de cambio
async function minuto(box) {
  const [data, prog] = await Promise.all([api("/api/acordes"), api("/api/progreso")]);
  const opts = data.chords.map(c => `<option value="${esc(c.id)}">${esc(c.id)} — ${esc(c.name)}</option>`).join("");
  box.innerHTML = `
    <div class="panel">
      <p class="muted">Un minuto cambiando entre dos acordes, lo más rápido que puedas <b>sin ensuciarlos</b>: solo cuentan los cambios que te escuché sonar bien. La mejor forma de destrabar un cambio que cuesta.</p>
      <div class="minuto">
        <div><select id="c1">${opts}</select><div id="d1" class="diagram"></div></div>
        <div class="minuto-center"><div class="big" id="count">0</div><div class="muted" id="clock">60 s</div>
          <button class="btn primary" id="go">🎧 Empezar</button><div class="muted small" id="best"></div></div>
        <div><select id="c2">${opts}</select><div id="d2" class="diagram"></div></div>
      </div>
      <div class="ex-msg muted" id="msg" aria-live="polite"></div>
    </div>
    ${Object.keys(prog.drills).length ? `<div class="panel"><h2>Tus récords</h2><div class="chips">${Object.entries(prog.drills).map(([k, v]) => `<span class="chip">${esc(k.replace("-", " ↔ "))}: <b>${v}</b></span>`).join("")}</div></div>` : ""}`;
  const c1 = $("#c1", box), c2 = $("#c2", box);
  c1.value = "Em"; c2.value = "Am";
  const draw = () => {
    $("#d1", box).innerHTML = chordSvg(data.chords.find(c => c.id === c1.value), { size: 110 });
    $("#d2", box).innerHTML = chordSvg(data.chords.find(c => c.id === c2.value), { size: 110 });
    const b = prog.drills[`${c1.value}-${c2.value}`];
    $("#best", box).textContent = b ? `récord: ${b}` : "";
  };
  c1.onchange = c2.onchange = draw;
  draw();
  $("#go", box).onclick = async () => {
    if (drill) { drill.stop(); return; }
    if (c1.value === c2.value) return toast("Elegí dos acordes distintos");
    const go = $("#go", box), msg = $("#msg", box), count = $("#count", box), clock = $("#clock", box);
    go.textContent = "■ Parar"; c1.disabled = c2.disabled = true;
    msg.textContent = "Arrancá con el de la izquierda.";
    let t0 = null;
    drill = listen({ drill: { chords: [c1.value, c2.value], seconds: 60 } }, {
      onState: s => {
        if (t0 === null && s.running) {   // el minuto corre desde que arranca la escucha
          t0 = Date.now();
          countdownTimer = setInterval(() => { clock.textContent = `${Math.max(0, 60 - Math.round((Date.now() - t0) / 1000))} s`; }, 250);
        }
        count.textContent = Math.max(0, s.k - 1);   // en modo espera, k avanza solo con acordes limpios
      },
      onMessage: m => { msg.textContent = m; msg.className = "ex-msg " + (/^[✗∅]/.test(m) ? "err" : "ok"); },
    });
    try {
      const rep = await drill.done;
      const a = rep.award || {};
      count.textContent = a.changes ?? 0;
      msg.className = "ex-msg ok";
      msg.textContent = `${a.changes ?? 0} cambios limpios${a.record ? " · ¡récord!" : ""}${a.xp ? ` · +${a.xp} XP` : ""}`;
      prog.drills[`${c1.value}-${c2.value}`] = a.best ?? prog.drills[`${c1.value}-${c2.value}`];
      draw();
    } catch (e) {
      msg.className = "ex-msg err"; msg.textContent = e.message;
    } finally {
      clearInterval(countdownTimer);
      drill = null; go.textContent = "🎧 Empezar"; c1.disabled = c2.disabled = false;
    }
  };
}

// ------------------------------------------------------------------ diapasón
const SCALES = {
  "": [], "mayor": [0, 2, 4, 5, 7, 9, 11], "menor natural": [0, 2, 3, 5, 7, 8, 10],
  "pentatónica menor": [0, 3, 5, 7, 10], "pentatónica mayor": [0, 2, 4, 7, 9], "blues": [0, 3, 5, 6, 7, 10],
  "acorde mayor": [0, 4, 7], "acorde menor": [0, 3, 7],
};

function diapason(box) {
  box.innerHTML = `
    <div class="panel">
      <div class="row">
        <label class="field"><span>Tónica</span><select id="root">${NOTE_NAMES.map((n, i) => `<option value="${i}"${i === 9 ? " selected" : ""}>${n}</option>`).join("")}</select></label>
        <label class="field"><span>Mostrar</span><select id="scale">${Object.keys(SCALES).map(s => `<option${s === "pentatónica menor" ? " selected" : ""} value="${s}">${s || "todas las notas"}</option>`).join("")}</select></label>
        <label class="check" style="align-self:end"><input type="checkbox" id="names" checked> nombres</label>
      </div>
      <div class="neck-wrap"><svg id="neck" viewBox="0 0 1000 230" role="img" aria-label="Diapasón"></svg></div>
      <p class="muted small">Tocá cualquier posición para escucharla. La tónica va resaltada.</p>
    </div>`;
  const draw = () => {
    const root = +$("#root", box).value, scale = SCALES[$("#scale", box).value], names = $("#names", box).checked;
    const F = 15, x0 = 40, w = 940, top = 25, gap = 34;
    const fx = n => x0 + w * (1 - 2 ** (-n / 12)) / (1 - 2 ** (-F / 12));   // trastes con espaciado real
    let s = "";
    for (let n = 0; n <= F; n++) s += `<line x1="${fx(n)}" x2="${fx(n)}" y1="${top}" y2="${top + 5 * gap}" stroke="currentColor" stroke-opacity="${n ? .3 : 1}" stroke-width="${n ? 2 : 6}"/>`;
    [3, 5, 7, 9, 15].forEach(n => s += `<circle cx="${(fx(n - 1) + fx(n)) / 2}" cy="${top + 2.5 * gap}" r="6" fill="currentColor" opacity=".12"/>`);
    s += `<circle cx="${(fx(11) + fx(12)) / 2}" cy="${top + 1.5 * gap}" r="6" fill="currentColor" opacity=".12"/><circle cx="${(fx(11) + fx(12)) / 2}" cy="${top + 3.5 * gap}" r="6" fill="currentColor" opacity=".12"/>`;
    for (let i = 0; i < 6; i++) s += `<line x1="${x0}" x2="${x0 + w}" y1="${top + i * gap}" y2="${top + i * gap}" stroke="currentColor" stroke-opacity=".5" stroke-width="${1 + i * 0.35}"/>`;
    for (let i = 0; i < 6; i++) {                 // i = 0 → 1ra cuerda (arriba)
      const open = OPEN[5 - i];
      for (let n = 0; n <= F; n++) {
        const p = open + n, pc = ((p % 12) - root + 12) % 12;
        const show = !scale.length || scale.includes(pc);
        const cx = n === 0 ? x0 - 18 : (fx(n - 1) + fx(n)) / 2, cy = top + i * gap;
        s += `<g class="pos" data-p="${p}" style="cursor:pointer"><rect x="${cx - 16}" y="${cy - 14}" width="32" height="28" fill="transparent"/>`;
        if (show) s += `<circle cx="${cx}" cy="${cy}" r="11" fill="${pc === 0 ? "var(--gl-accent)" : "var(--gl-panel-2)"}" stroke="${pc === 0 ? "none" : "var(--muted)"}"/>` +
          (names ? `<text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="10" font-weight="700" fill="${pc === 0 ? "var(--gl-accent-ink)" : "var(--text)"}">${NOTE_NAMES[p % 12]}</text>` : "");
        s += `</g>`;
      }
    }
    for (let n = 1; n <= F; n++) s += `<text x="${(fx(n - 1) + fx(n)) / 2}" y="${top + 5 * gap + 22}" text-anchor="middle" font-size="11" fill="var(--muted)">${n}</text>`;
    const svg = $("#neck", box);
    svg.innerHTML = s;
    $$(".pos", svg).forEach(g => g.addEventListener("click", () => pluck(+g.dataset.p)));
  };
  ["#root", "#scale", "#names"].forEach(q => $(q, box).onchange = draw);
  draw();
}
