// Practice tools: metronome, random practice box, rhythm test, ear training and the strumming library.
// Grading and records are decided on the server; random picks for warm-ups are just suggestions.
import { msgIsError, msgText, t, tc } from "../lib/i18n.js";
import { $, $$, api, audioCtx, chordSvg, click, esc, pluck, strum, toast } from "../lib/ui.js";
import { neck } from "../lib/fretboard.js";
import { listen } from "../lib/listen.js";
import { runAnswers, say } from "../lib/answer.js";
import { playChart, strumHtml } from "./charts.js";

const running = new Set();      // things to stop when you leave the page: { stop() }
export function stopAll() { running.forEach(r => { try { r.stop(); } catch { /* already stopped */ } }); running.clear(); }

// ------------------------------------------------------------------ metronome
// Accents per beat (click a dot: accent → normal → silent), subdivisions, a count-in bar, and "silent bars"
// (it clicks a few bars, then drops out for one: your inner time keeps going).
const SUBS = { off: [], eighths: [0.5], light: [0.6], hard: [0.67], triplets: [1 / 3, 2 / 3], sixteenths: [0.25, 0.5, 0.75] };
const GAPS = { off: 0, "3+1": 3, "1+1": 1 };

export function metronome(box) {
  let bpm = 90, beats = 4, taps = [], accents = [2, 1, 1, 1];
  box.innerHTML = `
    <div class="panel metro">
      <div class="metro-bpm"><button class="btn" data-d="-5">−5</button><button class="btn" data-d="-1">−1</button>
        <div><b id="bpm">${bpm}</b><small class="muted">bpm</small></div>
        <button class="btn" data-d="1">+1</button><button class="btn" data-d="5">+5</button></div>
      <input type="range" id="bpmR" min="40" max="240" value="${bpm}" aria-label="${esc(t("tools.tempo"))}">
      <div class="metro-dots accents" id="dots" role="group" aria-label="${esc(t("metro.accents"))}"></div>
      <p class="muted small center" id="metroState" aria-live="polite">${esc(t("metro.accents_hint"))}</p>
      <div class="row center wrap">
        <div class="seg" id="sig">${[2, 3, 4, 5, 6, 7].map(n => `<button data-n="${n}">${n}/${n === 6 || n === 7 ? 8 : 4}</button>`).join("")}</div>
        <label class="field-inline small">${esc(t("metro.subdivision"))}
          <select id="subs">${Object.keys(SUBS).map(k => `<option value="${k}">${esc(t(`metro.sub_${k}`))}</option>`).join("")}</select></label>
        <label class="field-inline small">${esc(t("metro.gap"))}
          <select id="gap">${Object.keys(GAPS).map(k => `<option value="${k}">${esc(t(`metro.gap_${k.replace("+", "_")}`))}</option>`).join("")}</select></label>
        <label class="check small"><input type="checkbox" id="countIn"> ${esc(t("metro.count_in"))}</label>
      </div>
      <div class="row center">
        <button class="btn" id="tap">${esc(t("tools.tap"))}</button>
        <button class="btn primary" id="play">${esc(t("tools.start"))}</button>
      </div>
      <p class="muted small center">${esc(t("tools.tap_hint"))}</p>
      <p class="kbd-hint muted small center">${t("keys.metronome_html")}</p>
    </div>`;
  const setBpm = v => { bpm = Math.max(40, Math.min(240, Math.round(v))); $("#bpm", box).textContent = bpm; $("#bpmR", box).value = bpm; };
  const label = a => t(a === 2 ? "metro.accent" : a === 1 ? "metro.normal" : "metro.silent");
  const drawDots = (on = -1) => {
    $("#dots", box).innerHTML = accents.map((a, i) => `<button class="dot a${a}${i === on ? " on" : ""}" data-i="${i}"
      aria-label="${esc(t("metro.beat_n", { n: i + 1 }))}: ${esc(label(a))}" title="${esc(label(a))}"><b>${i + 1}</b><small>${a === 2 ? ">" : a === 0 ? "×" : ""}</small></button>`).join("");
    $$("#dots .dot", box).forEach(b => b.onclick = () => { const i = +b.dataset.i; accents[i] = (accents[i] + 2) % 3; drawDots(); });
  };
  const setSig = n => {
    beats = n;
    accents = Array.from({ length: n }, (_, i) => (i === 0 ? 2 : n >= 6 && i === 3 ? 2 : 1));     // 6/8: two big pulses
    $$("#sig button", box).forEach(b => b.classList.toggle("active", +b.dataset.n === n));
    drawDots();
  };
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
  const onKey = e => {
    if (!document.body.contains(box) || e.target.closest("button, input, select")) return;
    if (e.code === "Space") { e.preventDefault(); tap(); }
    else if (e.key === "m" || e.key === "M") { e.preventDefault(); $("#play", box).click(); }      // M: start / stop
    else if (e.key === "+" || e.key === "=") setBpm(bpm + 1);
    else if (e.key === "-") setBpm(bpm - 1);
  };
  document.addEventListener("keydown", onKey);
  const state = $("#metroState", box);
  const m = {
    running: false, next: 0, n: 0, timer: null,
    start() {
      const ac = audioCtx();
      this.running = true; this.next = ac.currentTime + 0.1; this.n = $("#countIn", box).checked ? -beats : 0;
      this.timer = setInterval(() => {
        while (this.next < ac.currentTime + 0.12) {
          const len = 60 / bpm * (beats >= 6 ? 0.5 : 1), beat = ((this.n % beats) + beats) % beats;
          const bar = Math.floor(this.n / beats), gap = GAPS[$("#gap", box).value];
          const counting = this.n < 0, silentBar = !counting && gap && bar % (gap + 1) === gap;
          const a = accents[beat];
          if (counting) click(this.next, beat === 0, 0.8);
          else if (!silentBar && a > 0) click(this.next, a === 2);
          if (!counting && !silentBar && a > 0) for (const off of SUBS[$("#subs", box).value]) click(this.next + len * off, false, 0.4);
          const when = Math.max(0, (this.next - ac.currentTime) * 1000), shown = beat;
          setTimeout(() => {
            if (!this.running) return;
            drawDots(shown);
            state.textContent = counting ? t("metro.counting", { n: beats - beat }) : silentBar ? t("metro.silent_bar") : t("metro.bar_n", { n: bar + 1 });
          }, when);
          this.next += len;
          this.n++;
        }
      }, 25);
      $("#play", box).textContent = t("tools.stop");
    },
    stop() {
      clearInterval(this.timer); this.running = false; drawDots();
      document.removeEventListener("keydown", onKey);
      state.textContent = t("metro.accents_hint");
      const p = $("#play", box); if (p) p.textContent = t("tools.start");
    },
  };
  $("#play", box).onclick = () => {
    if (m.running) { m.stop(); document.addEventListener("keydown", onKey); } else m.start();
  };
  running.add(m);
  return m;
}

// ------------------------------------------------------------------ random practice box
const KEYS = ["C", "G", "D", "A", "E", "B", "F#", "F", "Bb", "Eb", "Ab", "Db"];
const QUALITIES = ["maj", "min", "7", "maj7", "m7", "m7b5", "sus4", "6"];
const SUFFIX = { maj: "", min: "m", "7": "7", maj7: "maj7", m7: "m7", m7b5: "m7b5", sus4: "sus4", "6": "6" };
const SCALES = ["major", "natural_minor", "minor_pentatonic", "major_pentatonic", "dorian", "mixolydian", "blues", "harmonic_minor"];
const POSITIONS = [[0, 4], [2, 5], [4, 8], [7, 10], [9, 13], [12, 15]];

export async function randomBox(box) {
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const cur = { key: "A", quality: "m7", scale: "minor_pentatonic", pos: 2 }, locked = new Set();
  box.innerHTML = `
    <div class="panel">
      <p class="muted">${esc(t("rand.intro"))}</p>
      <div class="rand-grid" id="rand"></div>
      <div class="row center"><button class="btn primary xl" id="roll">🎲 ${esc(t("rand.roll"))}</button></div>
      <p class="muted small center">${esc(t("rand.keys_hint"))}</p>
      <div id="randNeck"></div><p class="cf-tones center" id="randNotes"></p>
    </div>`;
  const field = (k, label, value) => `<div class="rand-field${locked.has(k) ? " locked" : ""}"><small class="muted">${esc(label)}</small>
    <b>${esc(value)}</b><button class="btn small" data-lock="${k}" aria-pressed="${locked.has(k)}">${locked.has(k) ? "🔒 " + esc(t("rand.locked")) : "🔓 " + esc(t("rand.lock"))}</button></div>`;
  const draw = async () => {
    const [lo, hi] = POSITIONS[cur.pos];
    $("#rand", box).innerHTML = field("key", t("rand.key"), cur.key) + field("quality", t("rand.chord"), cur.key + SUFFIX[cur.quality])
      + field("scale", t("rand.scale"), t(`quiz.scale_${cur.scale}`)) + field("pos", t("rand.position"), t("tools.window_n", { lo, hi }));
    $$("[data-lock]", box).forEach(b => b.onclick = () => { locked.has(b.dataset.lock) ? locked.delete(b.dataset.lock) : locked.add(b.dataset.lock); draw(); });
    try {
      const sc = (await api(`/api/theory/scale?key=${encodeURIComponent(cur.key)}&name=${cur.scale}`)).notes;
      const byPc = new Map(sc.map(x => [x.pc, x]));
      const marks = [];
      [64, 59, 55, 50, 45, 40].forEach((open, i) => {
        for (let f = lo; f <= hi; f++) { const tn = byPc.get((open + f) % 12); if (tn) marks.push({ string: i + 1, fret: f, text: tn.degree, kind: tn.degree === "1" ? "root" : "tone" }); }
      });
      neck($("#randNeck", box), { lo, hi, marks, label: t("rand.scale") });
      $("#randNotes", box).textContent = sc.map(x => x.note).join(" · ");
    } catch (e) { toast(e.message); }
  };
  const roll = () => {
    if (!locked.has("key")) cur.key = pick(KEYS);
    if (!locked.has("quality")) cur.quality = pick(QUALITIES);
    if (!locked.has("scale")) cur.scale = pick(SCALES);
    if (!locked.has("pos")) cur.pos = Math.floor(Math.random() * POSITIONS.length);
    draw();
  };
  $("#roll", box).onclick = roll;
  draw();
}

// ------------------------------------------------------------------ rhythm test
export async function rhythmTest(box) {
  const prog = await api("/api/progress");
  box.innerHTML = `
    <div class="panel">
      <p class="muted">${esc(t("rhythm.intro"))}</p>
      <div class="row center wrap">
        <label class="field-inline">${esc(t("rhythm.bpm"))} <input type="number" id="rBpm" min="40" max="200" value="80"></label>
        <label class="field-inline">${esc(t("rhythm.bars"))} <select id="rBars">${[2, 4, 8].map(n => `<option${n === 4 ? " selected" : ""}>${n}</option>`).join("")}</select></label>
        <label class="field-inline">${esc(t("rhythm.chord"))} <select id="rChord">${["Em", "Am", "E", "A", "D", "G", "C"].map(c => `<option>${c}</option>`).join("")}</select></label>
        <button class="btn primary" id="rGo">${esc(t("lesson.listen"))}</button>
      </div>
      <p class="ex-msg muted center" id="rMsg" aria-live="polite"></p>
      <div id="rOut"></div>
      ${Object.keys(prog.rhythm || {}).length ? `<p class="muted small">${esc(t("rhythm.records"))} ${Object.entries(prog.rhythm).map(([b, r]) => esc(t("rhythm.record", { bpm: b, std: r.std, within: r.within }))).join(" · ")}</p>` : ""}
    </div>`;
  let task = null;
  $("#rGo", box).onclick = async () => {
    if (task) { task.stop(); return; }
    const msg = $("#rMsg", box), btn = $("#rGo", box);
    btn.textContent = t("lesson.stop");
    msg.className = "ex-msg muted center";
    msg.textContent = t("lesson.wait_count_in");
    task = listen({ rhythm: { bpm: +$("#rBpm", box).value, bars: +$("#rBars", box).value, chord: $("#rChord", box).value }, click: true }, {
      onState: s => { if (s.countdown) msg.textContent = t("lesson.count_in", { n: s.countdown }); else if (s.k) msg.textContent = t("rhythm.strum_n", { k: s.k, total: s.total }); },
      onMessage: m => { if (msgIsError(m)) { msg.textContent = msgText(m); msg.className = "ex-msg err center"; } },
    });
    running.add(task);
    try {
      const rep = await task.done;
      const r = rep.award && rep.award.rhythm;
      if (!r || !r.n) { msg.textContent = t("lesson.not_played"); $("#rOut", box).innerHTML = ""; return; }
      msg.className = "ex-msg ok center";
      msg.textContent = t("rhythm.result", { within: r.within, mean: r.mean, std: r.std }) + (rep.award.xp ? ` · +${rep.award.xp} XP` : "");
      $("#rOut", box).innerHTML = histogram(r);
    } catch (e) { msg.className = "ex-msg err center"; msg.textContent = e.message; }
    finally { running.delete(task); task = null; btn.textContent = t("lesson.listen"); }
  };
}

/** Bars per timing bin, each with its count and range written out (never color alone). */
function histogram(r) {
  const max = Math.max(1, ...r.bins.map(b => b.count));
  const range = b => b.lo == null ? `< ${b.hi}` : b.hi == null ? `> ${b.lo}` : `${b.lo}…${b.hi}`;
  return `<div class="histo" role="img" aria-label="${esc(t("rhythm.histo_label", { within: r.within }))}">${r.bins.map(b => `
    <div class="h-col${b.lo === -10 ? " center" : ""}"><span class="h-n">${b.count}</span><i style="height:${Math.round(100 * b.count / max)}%"></i><small>${range(b)}</small></div>`).join("")}</div>
    <p class="muted small center">${esc(t("rhythm.axis"))}</p>`;
}

// ------------------------------------------------------------------ ear training: chord qualities, intervals, melodic echo
export async function earTrainer(box, params) {
  const kind = params.ear || "chord_quality";
  const prog = await api("/api/progress");
  const best = k => (prog.ear || {})[k]?.best;
  box.innerHTML = `
    <div class="panel">
      <div class="seg" id="earKind">${["chord_basic", "chord_quality", "interval", "echo"].map(k =>
        `<button data-k="${k}" class="${k === kind ? "active" : ""}">${esc(t(`ear.kind_${k}`))}${best(k) != null ? ` · ${Math.round(best(k))}%` : ""}</button>`).join("")}</div>
      <p class="muted">${esc(t(`ear.intro_${kind}`))}</p>
      <div class="q-box" id="earBox"></div>
      <div class="f-result" id="earResult" hidden></div>
      <p class="ex-msg muted center" id="earMsg" aria-live="polite"></p>
      <div class="row center"><button class="btn primary xl" id="earGo">▶ ${esc(t("lesson.start_answer"))}</button></div>
    </div>`;
  $$("#earKind button", box).forEach(b => b.onclick = () => { location.hash = `#/tools?tab=ear&ear=${b.dataset.k}`; });
  if (kind === "echo") return echo(box);
  let task = null;
  const go = $("#earGo", box), msg = $("#earMsg", box), out = $("#earBox", box);
  go.onclick = async () => {
    if (task) { task.stop(); return; }
    $("#earResult", box).hidden = true;
    let d;
    try { d = await api("/api/ear/draw", { json: { kind, count: 10 } }); } catch (e) { return toast(e.message); }
    go.textContent = t("lesson.stop");
    task = runAnswers(out, { drawn: d, finishUrl: "/api/ear/finish", onReveal: r => r && r.frets ? `<div class="mini-chord">${chordSvg({ id: r.name, frets: r.frets }, { size: 100 })}<b>${esc(r.name)}</b></div>` : "" });
    running.add(task);
    try {
      const rep = await task.done;
      if (rep) {
        msg.className = "ex-msg " + (rep.award.passed ? "ok" : "err") + " center";
        msg.textContent = t("ear.result", { score: Math.round(rep.summary.score), best: Math.round(rep.award.best) }) + (rep.award.record ? ` · ${t("tools.new_record")}` : "") + (rep.award.xp ? ` · +${rep.award.xp} XP` : "");
      }
    } catch (e) { msg.className = "ex-msg err center"; msg.textContent = e.message; }
    finally { running.delete(task); task = null; go.textContent = `▶ ${t("lesson.focus_again")}`; }
  };
}

/** Melodic echo: the app plays a short phrase it just made up; you play it back on the metronome. */
function echo(box) {
  const go = $("#earGo", box), msg = $("#earMsg", box), out = $("#earBox", box);
  let task = null, phrase = null, bpm = 80;
  const playPhrase = () => phrase && phrase.forEach(n => pluck(n.pitch, n.start * 60 / bpm, 0.4));
  go.textContent = `▶ ${t("ear.echo_new")}`;
  go.onclick = async () => {
    if (task) { task.stop(); return; }
    let d;
    try { d = await api("/api/ear/draw", { json: { kind: "echo" } }); } catch (e) { return toast(e.message); }
    phrase = d.phrase; bpm = d.bpm;
    out.innerHTML = `<p class="q-prompt">${esc(say(d.items[0].prompt))}</p><button class="btn" id="echoAgain">♪ ${esc(t("quiz.play_again"))}</button>`;
    $("#echoAgain", box).onclick = playPhrase;
    playPhrase();
    const len = phrase.reduce((a, n) => Math.max(a, n.start + n.beats), 0) * 60 / bpm;
    msg.className = "ex-msg muted center";
    msg.textContent = t("ear.echo_listen");
    await new Promise(r => setTimeout(r, len * 1000 + 600));       // let the phrase finish before the count-in
    go.textContent = t("lesson.stop");
    task = listen({ echo: true, click: true }, {
      onState: s => { if (s.countdown) msg.textContent = t("lesson.count_in", { n: s.countdown }); },
      onMessage: m => { msg.textContent = msgText(m); msg.className = "ex-msg " + (msgIsError(m) ? "err" : "ok") + " center"; },
    });
    running.add(task);
    try {
      const rep = await task.done;
      const a = rep.award || {}, score = rep.summary.score;
      msg.className = "ex-msg " + (a.passed ? "ok" : "err") + " center";
      msg.textContent = (score == null ? t("lesson.not_played") : t("ear.echo_result", { score: Math.round(score) })) + " · " + say(d.items[0].reveal) + (a.xp ? ` · +${a.xp} XP` : "");
    } catch (e) { msg.className = "ex-msg err center"; msg.textContent = e.message; }
    finally { running.delete(task); task = null; go.textContent = `▶ ${t("ear.echo_new")}`; }
  };
}

// ------------------------------------------------------------------ strumming library
export async function strumLibrary(box) {
  const { patterns } = await api("/api/strums");
  const name = p => tc(`strums.${p.id}.name`, p.name), tip = p => tc(`strums.${p.id}.tip`, p.tip);
  box.innerHTML = `<div class="panel"><p class="muted">${esc(t("strum.intro"))}</p>
    <div class="strum-list">${patterns.map(p => `
      <article class="strum-card" data-id="${esc(p.id)}">
        <header><b>${esc(name(p))}</b><small class="muted">${esc(p.time)} · ${esc(t("charts.level", { n: p.level }))}</small></header>
        ${strumHtml(p.strum)}
        <p class="small muted">${esc(tip(p))}</p>
        <div class="row left wrap"><button class="btn small" data-act="demo">♪ ${esc(t("strum.hear"))}</button>
          <button class="btn small primary" data-act="practice">${esc(t("lesson.listen"))}</button>
          <a class="btn small ghost" href="#/chart/new?strum=${encodeURIComponent(p.strum)}&time=${encodeURIComponent(p.time)}">${esc(t("strum.use"))}</a></div>
        <p class="ex-msg muted small" aria-live="polite"></p>
      </article>`).join("")}</div></div>`;
  let demo = null, task = null;
  $$(".strum-card", box).forEach(card => {
    const p = patterns.find(x => x.id === card.dataset.id), msg = $(".ex-msg", card);
    const bpb = +p.time.split("/")[0];
    const chart = { id: p.id, title: name(p), bpm: 80, beats_per_bar: bpb, strum: p.strum, capo: 0,
      bars: ["G", "C", "G", "C"].map((c, i) => ({ chord: c, beats: bpb, frets: i % 2 ? [-1, 3, 2, 0, 1, 0] : [3, 2, 0, 0, 0, 3] })) };
    $("[data-act=demo]", card).onclick = () => {
      if (demo) { demo.stop(); demo = null; return; }
      demo = playChart(chart);
      running.add(demo);
      demo.done.then(() => { running.delete(demo); demo = null; });
    };
    $("[data-act=practice]", card).onclick = async () => {
      if (task) { task.stop(); return; }
      if (demo) { demo.stop(); demo = null; }
      const btn = $("[data-act=practice]", card);
      btn.textContent = t("lesson.stop");
      msg.textContent = t("lesson.wait_count_in");
      task = listen({ strum: { pattern: p.id, chords: ["G", "C"] }, mode: "tempo", click: true }, {
        onState: s => { if (s.countdown) msg.textContent = t("lesson.count_in", { n: s.countdown }); },
        onMessage: m => { msg.textContent = msgText(m); msg.className = "ex-msg small " + (msgIsError(m) ? "err" : "ok"); },
      });
      running.add(task);
      try {
        const rep = await task.done;
        const sc = rep.summary.score;
        msg.className = "ex-msg small " + (sc != null && sc >= 80 ? "ok" : "err");
        msg.textContent = sc == null ? t("lesson.not_played") : t("strum.result", { score: Math.round(sc) });
      } catch (e) { msg.className = "ex-msg small err"; msg.textContent = e.message; }
      finally { running.delete(task); task = null; btn.textContent = t("lesson.listen"); }
    };
  });
}
