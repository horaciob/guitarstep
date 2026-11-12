// Tools: metronome, daily warm-up, rhythm test, strumming library, chord-change minute, ear training, random practice box,
// fretboard explorer and chord finder (the practice tools live in practice_tools.js).
import { msgIsError, msgText, t, tc } from "../lib/i18n.js";
import { $, $$, api, chordSvg, esc, instrument, NOTE_NAMES, strum, toast } from "../lib/ui.js";
import { neck } from "../lib/fretboard.js";
import { listen } from "../lib/listen.js";
import { slowPlayer } from "../lib/slowplayer.js";
import { improvise, stopImprov } from "./improv.js";
import { earTrainer, metronome, randomBox, rhythmTest, stopAll, strumLibrary, warmup } from "./practice_tools.js";

let drill = null, countdownTimer = null, slow = null;

export async function mount(el, { params }) {
  const tab = params.tab || "metronome";
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("tools.title"))}</h1></div>
    <div class="seg tabs" id="tabs">
      ${["metronome", "warmup", "rhythm", "strums", "drill", "ear", "improv", "random", "slow", "fretboard", "finder"].map(k =>
        `<button data-tab="${k}">${esc(t(`tools.${k === "rhythm" ? "rhythm_tab" : k === "strums" ? "strums_tab" : k === "ear" ? "ear_tab" : k === "random" ? "random_tab" : k === "warmup" ? "warmup_tab" : k === "slow" ? "slow_tab" : k === "improv" ? "improv_tab" : k}`))}</button>`).join("")}
    </div>
    <div id="tool"></div>`;
  $$("#tabs button", el).forEach(b => {
    b.classList.toggle("active", b.dataset.tab === tab);
    b.onclick = () => { location.hash = `#/tools?tab=${b.dataset.tab}`; };
  });
  const box = $("#tool", el);
  if (tab === "drill") await chordChangeMinute(box, (params.pair || "").split("-"));
  else if (tab === "fretboard") await fretboard(box);
  else if (tab === "finder") finder(box, params);
  else if (tab === "random") await randomBox(box);
  else if (tab === "warmup") await warmup(box, params);
  else if (tab === "rhythm") await rhythmTest(box);
  else if (tab === "ear") await earTrainer(box, params);
  else if (tab === "strums") await strumLibrary(box);
  else if (tab === "improv") await improvise(box);
  else if (tab === "slow") { box.innerHTML = `<div class="panel" id="slowBox"></div>`; slow = slowPlayer($("#slowBox", box)); }
  else metronome(box);
}

export function unmount() {
  stopAll();
  stopImprov();
  if (drill) drill.stop();
  drill = null;
  clearInterval(countdownTimer);
  if (slow) slow.stop();
  slow = null;
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

// ------------------------------------------------------------------ fretboard explorer
// Any scale or chord in any key, spelled from the key, labeled by note, degree or nothing, in a fret window.
const KEYS = ["C", "C#", "Db", "D", "Eb", "E", "F", "F#", "Gb", "G", "Ab", "A", "Bb", "B"];
const KEY_PC = { C: 0, "C#": 1, Db: 1, D: 2, Eb: 3, E: 4, F: 5, "F#": 6, Gb: 6, G: 7, Ab: 8, A: 9, Bb: 10, B: 11 };
const CHORD_TONES = ["maj", "min", "7", "maj7", "m7", "m7b5", "dim7"];
const WINDOWS = [[0, 15], [0, 4], [2, 5], [4, 8], [7, 10], [9, 13], [12, 15]];
const SUFFIX = { maj: "", min: "m", "7": "7", maj7: "maj7", m7: "m7", m7b5: "m7b5", dim7: "dim7", "6": "6", m6: "m6",
  sus2: "sus2", sus4: "sus4", "9": "9", maj9: "maj9", m9: "m9", "13": "13", "7b9": "7b9", "7#9": "7#9" };

// a scale note that isn't in the chord, named by its distance from the chord's root
const TENSION = { 0: "1", 1: "b9", 2: "9", 3: "#9", 4: "3", 5: "11", 6: "#11", 7: "5", 8: "b13", 9: "13", 10: "b7", 11: "7" };

async function fretboard(box) {
  const { scales } = await api("/api/theory/scale?key=C&name=major");
  box.innerHTML = `
    <div class="panel">
      <div class="row wrap">
        <label class="field"><span>${esc(t("tools.root"))}</span><select id="root">${KEYS.map(k => `<option${k === "A" ? " selected" : ""}>${k}</option>`).join("")}</select></label>
        <label class="field"><span>${esc(t("tools.show"))}</span><select id="scale">
          <option value="all">${esc(t("tools.scale_all"))}</option>
          <optgroup label="${esc(t("tools.scales"))}">${scales.map(s => `<option value="${s}"${s === "minor_pentatonic" ? " selected" : ""}>${esc(t(`quiz.scale_${s}`))}</option>`).join("")}</optgroup>
          <optgroup label="${esc(t("tools.chord_tones"))}">${CHORD_TONES.map(q => `<option value="chord:${q}">${esc(t("tools.chord_of", { q: SUFFIX[q] || t("quiz.q_maj") }))}</option>`).join("")}</optgroup>
        </select></label>
        <label class="field"><span>${esc(t("tools.labels"))}</span><select id="labels">
          <option value="note">${esc(t("tools.labels_notes"))}</option><option value="degree">${esc(t("tools.labels_degrees"))}</option><option value="none">${esc(t("tools.labels_none"))}</option></select></label>
        <label class="field"><span>${esc(t("tools.window"))}</span><select id="window">${WINDOWS.map(([lo, hi], i) =>
          `<option value="${i}">${esc(i ? t("tools.window_n", { lo, hi }) : t("tools.window_all"))}</option>`).join("")}</select></label>
        <label class="field"><span>${esc(t("tools.over_chord"))}</span><select id="over">
          <option value="">${esc(t("tools.over_none"))}</option>${CHORD_TONES.map(q => `<option value="${q}">${esc(t("tools.chord_of", { q: SUFFIX[q] || t("quiz.q_maj") }))}</option>`).join("")}</select></label>
      </div>
      <p class="muted small" id="fbLegend" hidden>${esc(t("tools.over_legend"))}</p>
      <div id="fbNeck"></div>
      <p class="muted small" id="fbNotes"></p>
      <p class="muted small">${esc(t("tools.fretboard_hint"))}</p>
    </div>`;
  const draw = async () => {
    const key = $("#root", box).value, what = $("#scale", box).value, labels = $("#labels", box).value;
    const [lo, hi] = WINDOWS[+$("#window", box).value];
    let tones;
    try {
      if (what === "all") tones = Array.from({ length: 12 }, (_, k) => ({ pc: (KEY_PC[key] + k) % 12, note: "", degree: "" }));
      else if (what.startsWith("chord:")) tones = (await api(`/api/theory/chord?symbol=${encodeURIComponent(key + SUFFIX[what.slice(6)])}`)).tones;
      else tones = (await api(`/api/theory/scale?key=${encodeURIComponent(key)}&name=${what}`)).notes;
    } catch (e) { toast(e.message); return; }
    // over a chord: chord tones are filled and labeled as chord degrees; the scale's other notes are tensions
    const over = $("#over", box).value;
    let chordTones = null;
    if (over) {
      try { chordTones = (await api(`/api/theory/chord?symbol=${encodeURIComponent(key + SUFFIX[over])}`)).tones; }
      catch (e) { toast(e.message); return; }
    }
    $("#fbLegend", box).hidden = !chordTones;
    const rootPc = tones[0].pc, byPc = new Map(tones.map(x => [x.pc, x]));
    const chordPc = chordTones && new Map(chordTones.map(x => [x.pc, x]));
    const tension = pc => TENSION[((pc - KEY_PC[key]) % 12 + 12) % 12];
    const marks = [];
    instrument.strings.forEach((open, i) => {
      for (let f = lo; f <= hi; f++) {
        const p = open + f, pc = p % 12, tn = byPc.get(pc);
        if (!tn && !(chordPc && chordPc.get(pc))) continue;
        const ct = chordPc && chordPc.get(pc);
        const deg = chordPc ? (ct ? ct.degree : tension(pc)) : tn.degree;
        const text = labels === "none" ? "" : labels === "degree" ? deg : (ct || tn).note || NOTE_NAMES[pc];
        const kind = chordPc ? (ct ? (ct.degree === "1" ? "root" : "tone") : "mark") : pc === rootPc ? "root" : "tone";
        marks.push({ string: i + 1, fret: f, text, kind });
      }
    });
    neck($("#fbNeck", box), { lo, hi, marks, label: t("tools.fretboard") });
    $("#fbNotes", box).textContent = what === "all" ? "" : chordPc
      ? t("tools.over_notes", { tones: chordTones.map(x => `${x.note} (${x.degree})`).join(" "),
          tensions: tones.filter(x => !chordPc.has(x.pc)).map(x => `${x.note} (${tension(x.pc)})`).join(" ") || "—" })
      : tones.map(x => `${x.note} (${x.degree})`).join(" · ");
  };
  ["#root", "#scale", "#labels", "#window", "#over"].forEach(q => $(q, box).onchange = draw);
  draw();
}

// ------------------------------------------------------------------ chord finder: find voicings, name a shape, voice-lead a progression
const QUALITIES = ["maj", "min", "7", "maj7", "m7", "m7b5", "dim7", "6", "m6", "sus2", "sus4", "9", "maj9", "m9", "13", "7b9", "7#9"];
const KINDS = ["triad", "drop2", "drop3", "shell"];
const TRIADS = new Set(["maj", "min", "sus2", "sus4"]);

function finder(box, params) {
  const mode = params.mode || "find";
  box.innerHTML = `
    <div class="panel">
      <div class="seg" id="cfMode">${["find", "name", "lead"].map(m => `<button data-m="${m}" class="${m === mode ? "active" : ""}">${esc(t(`tools.cf_${m}`))}</button>`).join("")}</div>
      <div id="cfBody"></div>
    </div>`;
  $$("#cfMode button", box).forEach(b => b.onclick = () => { location.hash = `#/tools?tab=finder&mode=${b.dataset.m}`; });
  const body = $("#cfBody", box);
  if (mode === "name") nameIt(body);
  else if (mode === "lead") leadIt(body);
  else findIt(body);
}

const card = (name, frets, sub = "") => `<div class="mini-chord cf-card"><b>${esc(name)}</b>${chordSvg({ id: name, frets }, { size: 100 })}
  ${sub ? `<small class="muted">${esc(sub)}</small>` : ""}<button class="btn small" data-play="${frets.join(",")}" aria-label="${esc(t("tools.cf_play", { name }))}">▶</button></div>`;
const bindPlay = el => $$("[data-play]", el).forEach(b => b.onclick = () => strum({ frets: b.dataset.play.split(",").map(Number) }));

function findIt(body) {
  body.innerHTML = `
    <div class="row wrap">
      <label class="field"><span>${esc(t("tools.root"))}</span><select id="cfRoot">${KEYS.map(k => `<option${k === "C" ? " selected" : ""}>${k}</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("tools.cf_quality"))}</span><select id="cfQ">${QUALITIES.map(q => `<option value="${q}"${q === "maj7" ? " selected" : ""}>${esc(SUFFIX[q] || t("quiz.q_maj"))}</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("tools.cf_kind"))}</span><select id="cfKind">${KINDS.map(k => `<option value="${k}"${k === "drop2" ? " selected" : ""}>${esc(t(`tools.kind_${k}`))}</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("tools.window"))}</span><select id="cfWin">${WINDOWS.map(([lo, hi], i) =>
        `<option value="${i}">${esc(i ? t("tools.window_n", { lo, hi }) : t("tools.window_all"))}</option>`).join("")}</select></label>
    </div>
    <p class="cf-tones" id="cfTones"></p>
    <div class="mini-chords cf-grid" id="cfGrid"></div>`;
  const draw = async () => {
    const sym = $("#cfRoot", body).value + SUFFIX[$("#cfQ", body).value], kind = $("#cfKind", body).value;
    const [lo, hi] = WINDOWS[+$("#cfWin", body).value];
    const grid = $("#cfGrid", body), tones = $("#cfTones", body);
    if (kind !== "triad" && TRIADS.has($("#cfQ", body).value)) {        // drop 2, drop 3 and shells need a 7th
      tones.textContent = "";
      grid.innerHTML = `<p class="muted">${esc(t("tools.cf_needs_seventh", { kind: t(`tools.kind_${kind}`) }))}</p>`;
      return;
    }
    try {
      const r = await api(`/api/theory/voicings?chord=${encodeURIComponent(sym)}&kind=${kind}`);
      tones.textContent = `${r.chord.symbol}: ${r.chord.tones.map(x => `${x.note} (${x.degree})`).join(" · ")}`;
      const vs = r.voicings.filter(v => v.frets.every(f => f < 0 || (f >= lo && f <= hi)));
      grid.innerHTML = vs.length ? vs.map(v => card(sym, v.frets, t("tools.cf_voicing", { strings: v.strings, bass: v.order[0] }))).join("")
        : `<p class="muted">${esc(t("tools.cf_none"))}</p>`;
      bindPlay(grid);
    } catch (e) {
      tones.textContent = "";
      grid.innerHTML = `<p class="muted">${esc(e.code === "theory" ? t("tools.cf_needs_seventh", { kind: t(`tools.kind_${kind}`) }) : e.message)}</p>`;
    }
  };
  ["#cfRoot", "#cfQ", "#cfKind", "#cfWin"].forEach(q => $(q, body).onchange = draw);
  draw();
}

function nameIt(body) {
  body.innerHTML = `<p class="muted small">${esc(t("tools.cf_name_hint"))}</p><div id="cfNeck"></div>
    <div class="cf-name-out"><div id="cfShape"></div><div><p class="cf-names" id="cfNames" aria-live="polite"></p><p class="muted small" id="cfNoteList"></p>
      <button class="btn small" id="cfClear">${esc(t("quiz.clear"))}</button></div></div>`;
  let fb = null;
  const update = async sel => {
    const frets = [-1, -1, -1, -1, -1, -1];
    sel.forEach(([s, f]) => { frets[6 - s] = f; });
    $("#cfShape", body).innerHTML = sel.length ? chordSvg({ id: "?", frets }, { size: 110 }) : "";
    if (sel.length < 2) { $("#cfNames", body).textContent = t("tools.cf_pick_more"); $("#cfNoteList", body).textContent = ""; return; }
    const r = await api("/api/theory/name", { json: { frets } });
    $("#cfNames", body).textContent = r.names.length ? r.names.slice(0, 4).join(" · ") : t("tools.cf_no_name");
    $("#cfNoteList", body).textContent = t("tools.cf_notes", { notes: r.notes.join(" ") });
  };
  fb = neck($("#cfNeck", body), { lo: 0, hi: 12, selectable: true, label: t("tools.cf_name"), onToggle: sel => {
    // one note per string: the newest click on a string replaces the older one
    const byString = new Map();
    sel.forEach(p => byString.set(p[0], p));
    const last = sel[sel.length - 1];
    if (last) byString.set(last[0], last);
    const keep = [...byString.values()];
    if (keep.length !== sel.length) fb.select(keep);
    update(keep);
  } });
  $("#cfClear", body).onclick = () => { fb.clear(); update([]); };
  update([]);
}

function leadIt(body) {
  body.innerHTML = `
    <form class="row wrap" id="cfForm">
      <label class="field grow"><span>${esc(t("tools.cf_progression"))}</span><input type="text" id="cfProg" value="Dm7 G7 Cmaj7 A7" aria-describedby="cfErr"></label>
      <label class="field"><span>${esc(t("tools.cf_kind"))}</span><select id="cfLKind">${[...KINDS, "guide"].map(k => `<option value="${k}"${k === "drop2" ? " selected" : ""}>${esc(t(`tools.kind_${k}`))}</option>`).join("")}</select></label>
      <label class="field"><span>${esc(t("tools.cf_lead_by"))}</span><select id="cfLead">${["smooth", "top", "bass"].map(l => `<option value="${l}">${esc(t(`tools.lead_${l}`))}</option>`).join("")}</select></label>
      <button class="btn primary" type="submit">${esc(t("tools.cf_voice"))}</button>
    </form>
    <p class="field-error" id="cfErr" hidden></p>
    <div class="mini-chords cf-grid" id="cfLGrid"></div>
    <button class="btn" id="cfPlayAll" hidden>▶ ${esc(t("tools.cf_play_all"))}</button>`;
  const go = async ev => {
    ev && ev.preventDefault();
    const err = $("#cfErr", body), grid = $("#cfLGrid", body), all = $("#cfPlayAll", body);
    err.hidden = true;
    const count = $("#cfProg", body).value.replace(/,/g, " ").split(/\s+/).filter(Boolean).length;
    if (count < 2 || count > 16) {                     // checked here too, so the message is instant
      err.textContent = t("tools.cf_bad_progression");
      err.hidden = false;
      grid.innerHTML = "";
      all.hidden = true;
      return;
    }
    try {
      const r = await api("/api/theory/voice-lead", { json: { progression: $("#cfProg", body).value, kind: $("#cfLKind", body).value, lead: $("#cfLead", body).value } });
      grid.innerHTML = r.shapes.map(s => card(s.name, s.frets)).join(`<span class="cf-arrow" aria-hidden="true">→</span>`);
      bindPlay(grid);
      all.hidden = false;
      all.onclick = () => r.shapes.forEach((s, k) => setTimeout(() => strum({ frets: s.frets }), k * 1100));
    } catch (e) {
      err.textContent = e.code === "bad_progression" ? t("tools.cf_bad_progression") : t("tools.cf_bad_chord");
      err.hidden = false;
      grid.innerHTML = "";
      all.hidden = true;
    }
  };
  $("#cfForm", body).onsubmit = go;
  go();
}
