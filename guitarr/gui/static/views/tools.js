// Tools: metronome (tap tempo), chord-change minute (counted by ear) and fretboard explorer.
import { msgIsError, msgText, t, tc } from "../lib/i18n.js";
import { $, $$, api, audioCtx, chordSvg, click, esc, instrument, NOTE_NAMES, pluck, toast } from "../lib/ui.js";
import { listen } from "../lib/listen.js";

let metro = null, drill = null, countdownTimer = null;

export async function mount(el, { params }) {
  const tab = params.tab || "metronome";
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("tools.title"))}</h1></div>
    <div class="seg tabs" id="tabs">
      <button data-tab="metronome">${esc(t("tools.metronome"))}</button>
      <button data-tab="drill">${esc(t("tools.drill"))}</button>
      <button data-tab="fretboard">${esc(t("tools.fretboard"))}</button>
    </div>
    <div id="tool"></div>`;
  $$("#tabs button", el).forEach(b => {
    b.classList.toggle("active", b.dataset.tab === tab);
    b.onclick = () => { location.hash = `#/tools?tab=${b.dataset.tab}`; };
  });
  const box = $("#tool", el);
  if (tab === "drill") await chordChangeMinute(box, (params.pair || "").split("-"));
  else if (tab === "fretboard") fretboard(box);
  else metronome(box);
}

export function unmount() {
  if (metro) metro.stop();
  metro = null;
  if (drill) drill.stop();
  drill = null;
  clearInterval(countdownTimer);
}

// ------------------------------------------------------------------ metronome
function metronome(box) {
  let bpm = 90, beats = 4, taps = [];
  box.innerHTML = `
    <div class="panel metro">
      <div class="metro-bpm"><button class="btn" data-d="-5">−5</button><button class="btn" data-d="-1">−1</button>
        <div><b id="bpm">${bpm}</b><small class="muted">bpm</small></div>
        <button class="btn" data-d="1">+1</button><button class="btn" data-d="5">+5</button></div>
      <input type="range" id="bpmR" min="40" max="240" value="${bpm}" aria-label="${esc(t("tools.tempo"))}">
      <div class="metro-dots" id="dots"></div>
      <div class="row center">
        <div class="seg" id="sig">${[2, 3, 4, 6].map(n => `<button data-n="${n}">${n}/${n === 6 ? 8 : 4}</button>`).join("")}</div>
        <button class="btn" id="tap">${esc(t("tools.tap"))}</button>
        <button class="btn primary" id="play">${esc(t("tools.start"))}</button>
      </div>
      <p class="muted small center">${esc(t("tools.tap_hint"))}</p>
    </div>`;
  const setBpm = v => { bpm = Math.max(40, Math.min(240, Math.round(v))); $("#bpm", box).textContent = bpm; $("#bpmR", box).value = bpm; };
  const drawDots = (on = -1) => { $("#dots", box).innerHTML = Array.from({ length: beats }, (_, i) => `<i class="${i === on ? "on" : ""}${i === 0 ? " first" : ""}"></i>`).join(""); };
  const setSig = n => { beats = n; $$("#sig button", box).forEach(b => b.classList.toggle("active", +b.dataset.n === n)); drawDots(); };
  setSig(4);
  $$("[data-d]", box).forEach(b => b.onclick = () => setBpm(bpm + +b.dataset.d));
  $("#bpmR", box).oninput = e => setBpm(+e.target.value);
  $$("#sig button", box).forEach(b => b.onclick = () => setSig(+b.dataset.n));
  const tap = () => {
    const now = performance.now();
    taps = taps.filter(x => now - x < 3000).concat(now);
    if (taps.length >= 3) {
      const d = taps.slice(1).map((x, i) => x - taps[i]);
      setBpm(60000 / (d.reduce((a, b) => a + b) / d.length));
    }
  };
  $("#tap", box).onclick = tap;
  const onKey = e => { if (e.code === "Space" && document.body.contains(box)) { e.preventDefault(); tap(); } };
  document.addEventListener("keydown", onKey);

  // lookahead scheduler (the Web Audio clock is precise; setInterval isn't)
  metro = {
    running: false, next: 0, n: 0, timer: null,
    start() {
      const ac = audioCtx();
      this.running = true; this.next = ac.currentTime + 0.1; this.n = 0;
      this.timer = setInterval(() => {
        while (this.next < ac.currentTime + 0.12) {
          const beat = this.n % beats;
          click(this.next, beat === 0);
          setTimeout(() => drawDots(beat), Math.max(0, (this.next - ac.currentTime) * 1000));
          this.next += 60 / bpm * (beats === 6 ? 0.5 : 1);
          this.n++;
        }
      }, 25);
      $("#play", box).textContent = t("tools.stop");
    },
    stop() {
      clearInterval(this.timer); this.running = false; drawDots();
      document.removeEventListener("keydown", onKey);
      const p = $("#play", box); if (p) p.textContent = t("tools.start");
    },
  };
  $("#play", box).onclick = () => {
    if (metro.running) { metro.stop(); document.addEventListener("keydown", onKey); } else metro.start();
  };
}

// ------------------------------------------------------------------ chord-change minute
async function chordChangeMinute(box, pair = []) {
  const [data, prog] = await Promise.all([api("/api/chords"), api("/api/progress")]);
  const opts = data.chords.map(c => `<option value="${esc(c.id)}">${esc(c.id)} — ${esc(tc(`chords.${c.id}.name`, c.name))}</option>`).join("");
  box.innerHTML = `
    <div class="panel">
      <p class="muted">${t("tools.drill_intro_html")}</p>
      <div class="minuto">
        <div><select id="c1" aria-label="${esc(t("tools.chord_a"))}">${opts}</select><div id="d1" class="diagram"></div></div>
        <div class="minuto-center"><div class="big" id="count">0</div><div class="muted" id="clock">60 s</div>
          <button class="btn primary" id="go">${esc(t("tools.drill_start"))}</button><div class="muted small" id="best"></div></div>
        <div><select id="c2" aria-label="${esc(t("tools.chord_b"))}">${opts}</select><div id="d2" class="diagram"></div></div>
      </div>
      <div class="ex-msg muted" id="msg" aria-live="polite"></div>
    </div>
    ${Object.keys(prog.drills).length ? `<div class="panel"><h2>${esc(t("tools.records"))}</h2><div class="chips">${Object.entries(prog.drills).map(([k, v]) => `<span class="chip">${esc(k.replace("-", " ↔ "))}: <b>${v}</b></span>`).join("")}</div></div>` : ""}`;
  const c1 = $("#c1", box), c2 = $("#c2", box);
  const known = id => data.chords.some(c => c.id === id);
  c1.value = known(pair[0]) ? pair[0] : "Em";
  c2.value = known(pair[1]) ? pair[1] : "Am";
  const draw = () => {
    $("#d1", box).innerHTML = chordSvg(data.chords.find(c => c.id === c1.value), { size: 110 });
    $("#d2", box).innerHTML = chordSvg(data.chords.find(c => c.id === c2.value), { size: 110 });
    const b = prog.drills[`${c1.value}-${c2.value}`];
    $("#best", box).textContent = b ? t("tools.record", { n: b }) : "";
  };
  c1.onchange = c2.onchange = draw;
  draw();
  $("#go", box).onclick = async () => {
    if (drill) { drill.stop(); return; }
    if (c1.value === c2.value) return toast(t("tools.two_chords"));
    const go = $("#go", box), msg = $("#msg", box), count = $("#count", box), clock = $("#clock", box);
    go.textContent = t("tools.stop"); c1.disabled = c2.disabled = true;
    msg.textContent = t("tools.drill_go");
    let t0 = null;
    drill = listen({ drill: { chords: [c1.value, c2.value], seconds: 60 } }, {
      onState: s => {
        if (t0 === null && s.running) {   // the minute runs from the moment listening starts
          t0 = Date.now();
          countdownTimer = setInterval(() => { clock.textContent = `${Math.max(0, 60 - Math.round((Date.now() - t0) / 1000))} s`; }, 250);
        }
        count.textContent = Math.max(0, s.k - 1);   // in wait mode, k only advances on clean chords
      },
      onMessage: m => { msg.textContent = msgText(m); msg.className = "ex-msg " + (msgIsError(m) ? "err" : "ok"); },
    });
    try {
      const rep = await drill.done;
      const a = rep.award || {};
      count.textContent = a.changes ?? 0;
      msg.className = "ex-msg ok";
      msg.textContent = t("tools.drill_result", { count: a.changes ?? 0 }) + (a.record ? ` · ${t("tools.new_record")}` : "") + (a.xp ? ` · +${a.xp} XP` : "");
      prog.drills[`${c1.value}-${c2.value}`] = a.best ?? prog.drills[`${c1.value}-${c2.value}`];
      draw();
    } catch (e) {
      msg.className = "ex-msg err"; msg.textContent = e.message;
    } finally {
      clearInterval(countdownTimer);
      drill = null; go.textContent = t("tools.drill_start"); c1.disabled = c2.disabled = false;
    }
  };
}

// ------------------------------------------------------------------ fretboard
const SCALES = {
  all: [], major: [0, 2, 4, 5, 7, 9, 11], natural_minor: [0, 2, 3, 5, 7, 8, 10],
  minor_pentatonic: [0, 3, 5, 7, 10], major_pentatonic: [0, 2, 4, 7, 9], blues: [0, 3, 5, 6, 7, 10],
  major_triad: [0, 4, 7], minor_triad: [0, 3, 7],
};

function fretboard(box) {
  box.innerHTML = `
    <div class="panel">
      <div class="row">
        <label class="field"><span>${esc(t("tools.root"))}</span><select id="root">${NOTE_NAMES.map((n, i) => `<option value="${i}"${i === 9 ? " selected" : ""}>${n}</option>`).join("")}</select></label>
        <label class="field"><span>${esc(t("tools.show"))}</span><select id="scale">${Object.keys(SCALES).map(s => `<option${s === "minor_pentatonic" ? " selected" : ""} value="${s}">${esc(t(`tools.scale_${s}`))}</option>`).join("")}</select></label>
        <label class="check" style="align-self:end"><input type="checkbox" id="names" checked> ${esc(t("tools.names"))}</label>
      </div>
      <div class="neck-wrap"><svg id="neck" viewBox="0 0 1000 ${25 + (instrument.strings.length - 1) * 34 + 45}" role="img" aria-label="${esc(t("tools.fretboard"))}"></svg></div>
      <p class="muted small">${esc(t("tools.fretboard_hint"))}</p>
    </div>`;
  const draw = () => {
    const root = +$("#root", box).value, scale = SCALES[$("#scale", box).value], names = $("#names", box).checked;
    const F = 15, x0 = 40, w = 940, top = 25, gap = 34;
    const NS = instrument.strings.length, last = NS - 1;
    const fx0 = n => x0 + w * (1 - 2 ** (-n / 12)) / (1 - 2 ** (-F / 12));   // real fret spacing
    const fx = n => (instrument.left_handed ? 1000 - fx0(n) : fx0(n));       // mirrored for left-handed
    const nutX = instrument.left_handed ? 1000 - (x0 - 18) : x0 - 18;
    let s = "";
    for (let n = 0; n <= F; n++) s += `<line x1="${fx(n)}" x2="${fx(n)}" y1="${top}" y2="${top + last * gap}" stroke="currentColor" stroke-opacity="${n ? .3 : 1}" stroke-width="${n ? 2 : 6}"/>`;
    [3, 5, 7, 9, 15].forEach(n => s += `<circle cx="${(fx(n - 1) + fx(n)) / 2}" cy="${top + last / 2 * gap}" r="6" fill="currentColor" opacity=".12"/>`);
    s += `<circle cx="${(fx(11) + fx(12)) / 2}" cy="${top + 1.5 * gap}" r="6" fill="currentColor" opacity=".12"/><circle cx="${(fx(11) + fx(12)) / 2}" cy="${top + 3.5 * gap}" r="6" fill="currentColor" opacity=".12"/>`;
    for (let i = 0; i < NS; i++) s += `<line x1="${fx(0)}" x2="${fx(F)}" y1="${top + i * gap}" y2="${top + i * gap}" stroke="currentColor" stroke-opacity=".5" stroke-width="${1 + i * 0.35}"/>`;
    for (let i = 0; i < NS; i++) {                // i = 0 → 1st string (top)
      const open = instrument.strings[i];
      for (let n = 0; n <= F; n++) {
        const p = open + n, pc = ((p % 12) - root + 12) % 12;
        const shown = !scale.length || scale.includes(pc);
        const cx = n === 0 ? nutX : (fx(n - 1) + fx(n)) / 2, cy = top + i * gap;
        s += `<g class="pos" data-p="${p}" style="cursor:pointer"><rect x="${cx - 16}" y="${cy - 14}" width="32" height="28" fill="transparent"/>`;
        if (shown) s += `<circle cx="${cx}" cy="${cy}" r="11" fill="${pc === 0 ? "var(--gl-accent)" : "var(--gl-panel-2)"}" stroke="${pc === 0 ? "none" : "var(--muted)"}"/>` +
          (names ? `<text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="10" font-weight="700" fill="${pc === 0 ? "var(--gl-accent-ink)" : "var(--text)"}">${NOTE_NAMES[p % 12]}</text>` : "");
        s += `</g>`;
      }
    }
    for (let n = 1; n <= F; n++) s += `<text x="${(fx(n - 1) + fx(n)) / 2}" y="${top + last * gap + 22}" text-anchor="middle" font-size="11" fill="var(--muted)">${n}</text>`;
    const svg = $("#neck", box);
    svg.innerHTML = s;
    $$(".pos", svg).forEach(g => g.addEventListener("click", () => pluck(+g.dataset.p)));
  };
  ["#root", "#scale", "#names"].forEach(q => $(q, box).onchange = draw);
  draw();
}
