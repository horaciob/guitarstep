// A lesson: theory, chords, tutorials (videos) and exercises you pass by playing.
import { lang, msgIsError, msgText, t, tc } from "../lib/i18n.js";
import { $, $$, api, bindChordSvg, chordSvg, esc, noteName, pluck, strum, toast, youtubeId, youtubeSearch } from "../lib/ui.js";
import { listen } from "../lib/listen.js";
import { runAnswers, say } from "../lib/answer.js";
import { neck } from "../lib/fretboard.js";
import { linkTerms, loadGlossary, metersHtml, openTerms, stepperHtml } from "../lib/flow.js";
import { chipsHtml } from "../lib/chips.js";
import { bindTakePlayers, takePlayer, timingVerdictHtml } from "../lib/take.js";
import { hearBar, rhythmSvg } from "../lib/notation.js";
import { staffSvg } from "../lib/staff.js";
import { stepGroups, tabText } from "../lib/tab.js";
import { readable, speakButton, stopSpeaking, toggleSpeak } from "../lib/speak.js";
import { rig } from "../lib/rig/engine.js";
import { factory } from "../lib/rig/presets.js";
import { chartGuide, playChart } from "./charts.js";

const ANSWER_KINDS = ["quiz", "pick", "tap"], DRAWN_KINDS = ["find_note", "play_interval", "tone_row", "echo", "rhythm", "read_play"];
const hearable = ex => !ANSWER_KINDS.includes(ex.kind) && !DRAWN_KINDS.includes(ex.kind);
const shapeChord = s => ({ id: s.name, frets: s.frets });

let task = null, demo = null;
let focus = null;   // the exercise open on its own full screen: { ex, views, changed }
const guides = new Map();   // exercise id → { guide, chart } for chart exercises

function exerciseTarget(ex) {
  if (ex.kind === "notes") return ex.notes.map(noteName).join(" ");
  if (ex.kind === "lick") return stepGroups(ex.steps).map(g => g.map(s => noteName(s.pitch)).join("+")).join(" ");
  if (ex.kind === "bend") {
    const s = ex.steps[0];
    return t("lesson.bend_target", { string: s.string, fret: s.fret, note: noteName(s.pitch), tries: ex.steps.length, hold: (ex.hold ?? 1).toLocaleString(lang()) });
  }
  if (ex.kind === "chord") return `${ex.chord} × ${ex.times}`;
  if (ex.kind === "change") return `${ex.chords.join(" ↔ ")} × ${ex.times}`;
  if (ex.kind === "chart") return t("lesson.chart_at", { pct: Math.round(ex.speed * 100) });
  if (ex.kind === "scale") return t("lesson.t_scale", { key: ex.key, scale: t(`quiz.scale_${ex.scale}`), lo: (ex.frets || [0])[0], hi: (ex.frets || [0, 12])[1] });
  if (ex.kind === "arpeggio") return t("lesson.t_arpeggio", { chord: ex.chord });
  if (ex.kind === "caged") return t("lesson.t_caged", { chord: ex.chord, shapes: (ex.caged || "CAGED").split("").join(" · ") });
  if (ex.kind === "line") return ex.progression.join(" → ");
  if (ex.kind === "shape" || ex.kind === "voiced") return `${ex.shapes.map(s => s.name).join(" → ")} × ${ex.times ?? 2}`;
  if (ex.kind === "quiz") return t("lesson.t_quiz", { count: ex.count ?? 6 });
  if (ex.kind === "pick") return t("lesson.t_pick", { count: ex.count ?? 6 });
  if (ex.kind === "tap") return t("lesson.t_tap", { count: ex.count ?? ex.patterns.length, bpm: ex.bpm ?? 70 });
  if (ex.kind === "rhythm") return t("lesson.t_rhythm", { count: ex.count ?? 4, bpm: ex.bpm ?? 70 });
  if (DRAWN_KINDS.includes(ex.kind)) return t("lesson.t_drawn", { count: ex.count ?? 5 });
  return "";
}

/** One octave of a piano keyboard: white keys named, black keys with both names (C♯ = D♭). Each key plays. */
function pianoSvg() {
  const whites = ["C", "D", "E", "F", "G", "A", "B"], blacks = { 0: "C♯ D♭", 1: "D♯ E♭", 3: "F♯ G♭", 4: "G♯ A♭", 5: "A♯ B♭" };
  const W = 70, H = 210, midi = [60, 62, 64, 65, 67, 69, 71], bmidi = { 0: 61, 1: 63, 3: 66, 4: 68, 5: 70 };
  let s = `<svg class="piano" viewBox="0 0 ${W * 7 + 2} ${H + 2}" role="img" aria-label="${esc(t("lesson.piano_label"))}">`;
  whites.forEach((n, i) => s += `<g class="pk" data-p="${midi[i]}"><rect x="${1 + i * W}" y="1" width="${W}" height="${H}" rx="4" fill="#f6f4ee" stroke="#333"/>
    <text x="${1 + i * W + W / 2}" y="${H - 14}" text-anchor="middle" font-size="18" font-weight="700" fill="#222">${n}</text></g>`);
  Object.entries(blacks).forEach(([i, n]) => {
    const x = 1 + (+i + 1) * W - 22;
    const [a, b] = n.split(" ");
    s += `<g class="pk" data-p="${bmidi[i]}"><rect x="${x}" y="1" width="44" height="${H * 0.6}" rx="3" fill="#1d1d1f" stroke="#000"/>
      <text x="${x + 22}" y="${H * 0.6 - 30}" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">${a}</text>
      <text x="${x + 22}" y="${H * 0.6 - 14}" text-anchor="middle" font-size="12" font-weight="700" fill="#fff">${b}</text></g>`;
  });
  return s + `</svg>`;
}

/** Small chord diagrams for shape exercises. */
const shapesHtml = (ex, size = 84) => `<div class="mini-chords ex-shapes">${ex.shapes.map(s =>
  `<div class="mini-chord"><b>${esc(s.name)}</b>${chordSvg(shapeChord(s), { size })}</div>`).join("")}</div>`;

export async function mount(el, { segs, params = {} }) {
  const id = decodeURIComponent(segs[0] || "");
  const [course, chordData, terms] = await Promise.all([api("/api/course"), api("/api/chords"), loadGlossary()]);
  const flat = lvs => lvs.flatMap(l => l.lessons.map(ls => ({ ...ls, level: l })));
  const tracks = [course.levels, ...[...new Set((course.optional || []).map(l => l.track))].map(tr => course.optional.filter(l => l.track === tr))];
  const all = flat(tracks.find(g => flat(g).some(l => l.id === id)) || course.levels);   // "next" stays in the same course
  const idx = all.findIndex(l => l.id === id);
  if (idx < 0) { el.innerHTML = `<div class="gl-head"><h1>${esc(t("lesson.not_found"))}</h1></div><p><a href="#/course">${esc(t("lesson.back"))}</a></p>`; return; }
  const ls = all[idx], next = all[idx + 1];
  api("/api/lesson/seen", { json: { lesson: ls.id } }).catch(() => {});   // the "discover" step
  const chords = (ls.chords || []).map(c => chordData.chords.find(x => x.id === c)).filter(Boolean);
  const vid = ls.pinned && youtubeId(ls.pinned);
  const levelName = tc(`levels.${ls.level.id}.title`, ls.level.title);
  const levelNo = ls.level.badge || ls.level.number;
  const lt = (k, fb) => ls.recap ? (k === "title" ? t("lesson.recap_title", { n: levelNo, level: levelName })
    : k === "theory" ? [t("lesson.recap_theory_1"), t("lesson.recap_theory_2")] : fb) : tc(`lessons.${ls.id}.${k}`, fb);
  const theory = lt("theory", ls.theory), tips = lt("tips", ls.tips || []), tutorials = lt("tutorials", ls.tutorials || []);
  const captions = lt("captions", ls.captions || []);
  const exTitle = ex => ex.from ? tc(`exercises.${ex.from}`, ex.title) : tc(`exercises.${ls.id}/${ex.id}`, ex.title);
  // a short piece of theory for each exercise (plain sentences, so a voice can read them later)
  const exTheory = ex => ex.theory ? tc(`ex_theory.${ex.from || `${ls.id}/${ex.id}`}`, ex.theory) : "";
  const upNext = ls.exercises.find(e => !e.passed);   // the first exercise you haven't passed yet
  const used = new Set();                              // glossary terms already linked on this page

  el.innerHTML = `
    <a class="btn small" href="#/course">← ${esc(t("nav.course"))}</a>
    <div class="gl-head lesson-head" style="margin-top:12px"><div><small class="muted">${esc(t("lesson.meta", { n: levelNo, level: levelName, min: ls.minutes }))}</small>
      <h1>${esc(lt("title", ls.title))} ${ls.done ? `<span class="pill ok">${esc(t(ls.tested_out ? "lesson.tested_out" : "lesson.complete"))}</span>` : ""}</h1></div>
      ${!ls.done && !ls.recap ? `<button class="btn" id="testOut">${esc(t("lesson.testout_button"))}</button>` : ""}</div>
    ${stepperHtml(ls.flow)}
    ${ls.tone && factory(ls.tone) ? `<p class="small lesson-tone" id="lessonTone"></p>` : ""}
    <div class="first-action">
      <button class="btn primary xl" id="exContinueTop">▶ ${esc(upNext ? t("lesson.continue_with", { title: exTitle(upNext) }) : t("lesson.practice_again"))}</button>
      ${metersHtml(ls)}
    </div>
    <div class="lesson-layout">
      <div class="stack">
        <div class="panel"><div class="ex-panel-head"><h2>${esc(t("lesson.idea"))}</h2>${speakButton('data-speak-idea')}</div><ul class="theory" id="ideaText">${theory.map(x => `<li>${linkTerms(x, terms, used)}</li>`).join("")}</ul>
          ${(ls.figures || []).map((f, i) => `<figure class="lesson-figure" data-fig="${i}"><div class="fig-box"></div>
            ${captions[i] ? `<figcaption class="muted small">${esc(captions[i])}</figcaption>` : ""}</figure>`).join("")}
          ${tips.length ? `<h3>${esc(t("lesson.tips"))}</h3><ul class="theory" id="tipsText">${tips.map(x => `<li>${linkTerms(x, terms, used)}</li>`).join("")}</ul>` : ""}</div>
        <div class="panel"><div class="ex-panel-head"><h2>${esc(t("lesson.exercises"))}</h2>
            <button class="btn primary" id="exContinue">▶ ${esc(upNext ? t("lesson.continue_with", { title: exTitle(upNext) }) : t("lesson.practice_again"))}</button></div>
          <p class="muted small">${t("lesson.exercises_hint_html")}</p>
          <div class="exercises">${ls.exercises.map(ex => `
            <div class="exercise${ex.passed ? " passed" : ""}" data-id="${esc(ex.id)}">
              <div class="ex-head"><span class="state">${ex.passed ? "✓" : "○"}</span>
                <div><b>${esc(exTitle(ex))}</b><small class="muted">${esc(exerciseTarget(ex))} · ${esc(t("lesson.pass_with", { min: ex.min }))}${ex.best != null ? ` · ${esc(t("lesson.your_best", { best: Math.round(ex.best) }))}` : ""}</small></div>
                ${exTheory(ex) ? `<button class="btn small ex-theory-btn" data-act="theory" aria-expanded="false" title="${esc(t("lesson.theory_btn"))}" aria-label="${esc(t("lesson.theory_btn"))}">📖</button>` : ""}
                ${hearable(ex) ? `<button class="btn small" data-act="hear" title="${esc(t(ex.kind === "chart" ? "lesson.demo_hint" : "lesson.hear_hint"))}" aria-label="${esc(t(ex.kind === "chart" ? "lesson.demo_hint" : "lesson.hear_hint"))}">♪</button>` : ""}
                <button class="btn small primary" data-act="go">${esc(t(ex.how === "answer" ? "lesson.start_answer" : "lesson.listen"))}</button></div>
              ${exTheory(ex) ? `<p class="ex-theory" hidden>${speakButton()}<b>${esc(t("lesson.theory_short"))}:</b> <span class="ex-theory-text">${linkTerms(exTheory(ex), terms, used)}</span></p>` : ""}
              <div class="ex-chips"><span class="how-chip">${esc(t(`flow.${ex.stage}`))}</span>
                ${ex.how === "answer" ? `<span class="how-chip">${esc(t("lesson.how_answer"))}</span>` : ""}
                ${ex.fadeable ? [0, 1, 2].map(g => `<span class="how-chip${ex.guidance != null && ex.guidance >= g ? " ok" : ""}">${ex.guidance != null && ex.guidance >= g ? "✓ " : ""}${esc(t(`flow.guide_${g}`))}</span>`).join("") : ""}
                ${ex.can_vary && ex.passed ? `<button class="btn small" data-act="vary">${ex.varied ? "✓ " : ""}${esc(t("flow.try_vary"))}</button>` : ""}
                ${ex.kind === "chart" ? `<a class="btn small ghost" data-act="loop" href="#/practice?chart=${encodeURIComponent(ex.chart)}&from=1&to=999">${esc(t("flow.loop_it"))}</a>` : ""}</div>
              ${ex.steps && ex.kind !== "bend" ? `<pre class="tab" aria-label="${esc(t("lesson.tab_label"))}">${esc(tabText(ex.steps))}</pre>` : ""}
              ${ex.shapes ? shapesHtml(ex) : ""}
              ${ex.kind === "chart" ? `<div class="ex-guide"></div>` : ""}
            </div>`).join("")}</div></div>
      </div>
      <div class="stack">
        ${chords.length ? `<div class="panel"><h2>${esc(t("nav.chords"))}</h2><div class="mini-chords">${chords.map(c =>
          `<div class="mini-chord" data-id="${esc(c.id)}"><b>${esc(c.id)}</b>${chordSvg(c, { size: 96 })}<button class="btn small" data-strum="${esc(c.id)}">▶</button></div>`).join("")}</div></div>` : ""}
        <div class="panel"><h2>${esc(t("lesson.tutorials"))}</h2>
          ${vid ? `<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/${vid}?rel=0" title="${esc(t("lesson.video_title"))}" allow="encrypted-media; picture-in-picture" allowfullscreen></iframe></div>`
                : ls.pinned ? `<p><a href="${esc(ls.pinned)}" target="_blank" rel="noopener">${esc(t("lesson.pinned_link"))} ↗</a></p>` : ""}
          <p class="muted small">${esc(t("lesson.find_video"))}</p>
          <ul class="tutorias">${tutorials.map(q => `<li><a href="${youtubeSearch(q)}" target="_blank" rel="noopener">▶ ${esc(q)}</a></li>`).join("")}</ul>
          <label class="field"><span>${esc(t("lesson.pin_label"))}</span>
            <div class="row"><input type="text" id="pin" placeholder="https://www.youtube.com/watch?v=…" value="${esc(ls.pinned || "")}"><button class="btn small" id="pinBtn">${esc(t("lesson.pin"))}</button></div></label>
        </div>
        ${next ? `<a class="callout" href="#/lesson/${encodeURIComponent(next.id)}"><span>${t("lesson.next_html", { title: esc(tc(`lessons.${next.id}.title`, next.title)), interpolation: { escapeValue: false } })}</span><span>→</span></a>` : ""}
      </div>
    </div>
    <dialog class="ex-focus" aria-labelledby="fTitle"><div class="focus-inner" tabindex="-1">
      <div class="focus-top"><button class="btn small" data-f="back">← ${esc(t("lesson.focus_back"))}</button>
        <small class="muted">${esc(lt("title", ls.title))}</small></div>
      <div class="focus-head"><span class="f-state" id="fState" aria-live="polite"></span><h1 id="fTitle"></h1><p class="muted" id="fTarget"></p>
        <details class="f-theory" id="fTheory" hidden><summary>📖 ${esc(t("lesson.theory_short"))}</summary><p>${speakButton()}<span></span></p></details>
        <div class="seg mini f-guide" id="fGuide" role="group" aria-label="${esc(t("flow.guide_label"))}" hidden></div></div>
      <div class="focus-body"></div>
      <div class="focus-foot">
        <p class="f-hint" aria-live="polite"></p>
        <div class="ex-progress"><i></i></div>
        <div class="f-result" hidden></div>
        <div class="ex-msg muted" aria-live="polite"></div>
        <p class="f-next" aria-live="polite"></p>
        <div class="f-take"></div>
        <div class="row center"><button class="btn" data-f="hear"></button>
          <button class="btn" data-f="hint" hidden>💡 ${esc(t("flow.hint"))}</button>
          <button class="btn primary xl" data-f="go"></button>
          <button class="btn" data-f="next" hidden>${esc(t("lesson.focus_next"))} →</button></div>
        <p class="small muted center f-latency" id="fLat"></p>
        <p class="muted small center kbd-hint">${t("lesson.focus_keys_html")}</p>
      </div>
    </div></dialog>
    <dialog class="rig-dialog term-dialog" id="termDialog"></dialog>`;

  $$(".lesson-figure", el).forEach(fig => {
    const f = ls.figures[+fig.dataset.fig], box = $(".fig-box", fig);
    if (f.type === "keyboard") {
      box.innerHTML = pianoSvg();
      $$(".pk", box).forEach(k => k.addEventListener("click", () => pluck(+k.dataset.p)));
    }
    else if (f.type === "fretboard") neck(box, { lo: f.lo, hi: f.hi, marks: f.marks, label: captions[+fig.dataset.fig] || "" });
    else if (f.type === "staff") box.innerHTML = staffSvg(f.notes, { names: true, label: captions[+fig.dataset.fig] || "" });
    else if (f.type === "rhythm") {                    // a bar of rhythm you can hear, each note lighting up in time
      box.innerHTML = `<div class="rhythm-fig">${rhythmSvg(f.pattern, { label: captions[+fig.dataset.fig] || "", marks: f.marks })}</div>
        <button class="btn small" data-hear-rhythm>♪ ${esc(t("rhythm.hear_bar"))}</button>`;
      $("[data-hear-rhythm]", box).onclick = () => hearBar($(".rhythm-fig", box), f.pattern, f.bpm || 70);
    }
  });
  $$(".mini-chord[data-id]", el).forEach(m => bindChordSvg(m, chords.find(c => c.id === m.dataset.id)));
  $$("[data-strum]", el).forEach(b => b.onclick = () => strum(chords.find(c => c.id === b.dataset.strum)));
  $("#pinBtn", el).onclick = async () => {
    try {
      await api("/api/progress/tutorial", { json: { lesson: ls.id, url: $("#pin", el).value } });
      toast(t($("#pin", el).value ? "lesson.pinned" : "lesson.unpinned"), true);
      mount(el, { segs });
    } catch (e) { toast(e.message); }
  };
  guides.clear();
  await Promise.all(ls.exercises.filter(ex => ex.kind === "chart").map(async ex => {
    const { chart } = await api(`/api/charts/${encodeURIComponent(ex.chart)}`);
    const box = $(`.exercise[data-id="${CSS.escape(ex.id)}"] .ex-guide`, el);
    const note = chart.note && tc(`charts.${chart.id}.note`, chart.note);
    guides.set(ex.id, { chart, guide: chartGuide(box, chart, { speed: ex.speed, note }) });
    const bars = Math.ceil(chart.bars.reduce((s, b) => s + b.beats, 0) / chart.beats_per_bar);
    const loop = $(`.exercise[data-id="${CSS.escape(ex.id)}"] [data-act=loop]`, el);
    if (loop) loop.href = `#/practice?chart=${encodeURIComponent(ex.chart)}&from=1&to=${bars}`;
  }));
  showTone($("#lessonTone", el), ls.tone);
  const idea = $("[data-speak-idea]", el);
  if (idea) idea.onclick = () => toggleSpeak(idea, [readable($("#ideaText", el)), $("#tipsText", el) ? `${t("lesson.tips")}. ${readable($("#tipsText", el))}` : ""].join(" "));
  $$(".exercise", el).forEach(box => {
    const ex = ls.exercises.find(e => e.id === box.dataset.id);
    const hear = $("[data-act=hear]", box), thBtn = $("[data-act=theory]", box);
    if (thBtn) thBtn.onclick = () => {
      const p = $(".ex-theory", box), open = p.hidden;
      p.hidden = !open;
      thBtn.setAttribute("aria-expanded", String(open));
      if (!open) stopSpeaking();
    };
    const say_ = $(".ex-theory [data-speak]", box);
    if (say_) say_.onclick = () => toggleSpeak(say_, readable($(".ex-theory-text", box)));
    if (hear) hear.onclick = () => ex.kind === "chart" ? toggleDemo(ex, hear, [guides.get(ex.id).guide]) : preview(ex, chordData);
    $("[data-act=go]", box).onclick = () => openFocus(el, segs, ls, ex, chordData, exTitle, true);
    const vary = $("[data-act=vary]", box);
    if (vary) vary.onclick = () => openFocus(el, segs, ls, ex, chordData, exTitle, false, { variant: true });
  });
  const termDlg = $("#termDialog", el);
  $$(".term", el).forEach(b => b.onclick = () => openTerms(termDlg, terms, [b.dataset.term]));
  const testOut = $("#testOut", el);
  if (testOut) testOut.onclick = () => openTestOut(el, segs, ls, chordData, exTitle);
  if (params.ex) {                                        // a review on the home page links straight to its exercise
    const ex = ls.exercises.find(e => e.id === params.ex);
    if (ex) openFocus(el, segs, ls, ex, chordData, exTitle);
  }
  const dlg = $(".ex-focus", el);
  dlg.addEventListener("cancel", e => { e.preventDefault(); closeFocus(el, segs); });   // Esc
  $("[data-f=back]", dlg).onclick = () => closeFocus(el, segs);
  // keys while the exercise is on screen: Space starts/stops, Enter goes to the next exercise
  dlg.addEventListener("keydown", e => {
    if (e.target.closest("button, input, a, .knob, .quiz, .fb-pos")) return;   // a focused control (or a question) handles its own keys
    const next = $("[data-f=next]", dlg);
    if (e.key === " ") { e.preventDefault(); $("[data-f=go]", dlg).click(); }
    else if (e.key === "Enter" && !next.hidden) { e.preventDefault(); next.click(); }
  });
  $("#exContinue", el).onclick = () => openFocus(el, segs, ls, upNext || ls.exercises[0], chordData, exTitle);
  $("#exContinueTop", el).onclick = () => openFocus(el, segs, ls, upNext || ls.exercises[0], chordData, exTitle);
}

/** Chart exercises: plays the chart at the exercise's speed while the views (guide, metronome) follow it. */
function toggleDemo(ex, btn, views, labels = ["♪", "■"]) {
  if (demo) return stopDemo();
  if (task) return toast(t("lesson.busy"));
  const g = guides.get(ex.id);
  if (!g) return;
  demo = playChart(g.chart, { speed: ex.speed });
  const mine = demo;
  views.forEach(v => v.setClock(mine.clock));
  btn.textContent = labels[1];
  btn.title = t("lesson.demo_stop");
  mine.done.then(() => {
    views.forEach(v => v.setClock(null));
    btn.textContent = labels[0];
    btn.title = t("lesson.demo_hint");
    if (demo === mine) demo = null;
  });
}

/** A big metronome: the BPM, one numbered dot per beat of the bar and the beat you're on.
 * `setClock(fn)` as in chartGuide: fn() returns beats since the start (negative during the count-in). */
function metronomeView(box, bpb, bpm) {
  box.innerHTML = `
    <div class="f-metro" aria-hidden="true">
      <div class="f-num"><b>${bpm}</b><small class="muted">${esc(t("lesson.metro_bpm"))}</small></div>
      <div class="metro-dots">${Array.from({ length: bpb }, (_, i) => `<i class="${i ? "" : "first"}">${i + 1}</i>`).join("")}</div>
      <div class="f-num"><b class="f-beat">–</b><small class="muted f-beat-label">${esc(t("lesson.metro_beat"))}</small></div>
    </div>`;
  const dots = $$(".metro-dots i", box), num = $(".f-beat", box), label = $(".f-beat-label", box);
  let clock = null, raf = 0, shown = "";
  const show = beat => {
    const k = beat == null ? -1 : ((Math.floor(beat) % bpb) + bpb) % bpb;
    const counting = beat != null && beat < 0;
    const key = `${k}|${counting ? Math.ceil(-beat) : ""}`;
    if (key === shown) return;
    shown = key;
    dots.forEach((d, i) => d.classList.toggle("on", i === k));
    num.textContent = k < 0 ? "–" : counting ? Math.ceil(-beat) : k + 1;
    label.textContent = t(counting ? "lesson.metro_count_in" : "lesson.metro_beat");
  };
  const frame = () => { show(clock ? clock() : null); raf = clock ? requestAnimationFrame(frame) : 0; };
  show(null);
  return { setClock(fn) { clock = fn; cancelAnimationFrame(raf); frame(); } };
}

/** What to play now and next, for exercises without a tempo (notes, chords, licks, bends).
 * hide: no names on screen either (the "no help" level): only where you are. */
function nowView(box, hide = false) {
  box.innerHTML = `<div class="focus-now"><small class="muted">${esc(t("lesson.focus_now"))}</small>
    <b class="f-now">${hide ? "?" : "–"}</b><span class="f-then muted"></span><small class="f-step muted"></small></div>`;
  return {
    setClock() {},
    update(s) {
      const cur = s.lane.findIndex(e => e.current), now = s.lane[cur], then = s.lane[cur + 1];
      $(".f-now", box).textContent = hide ? "?" : now ? now.label : "–";
      $(".f-then", box).textContent = !hide && then ? t("lesson.focus_then", { x: then.label }) : "";
      $(".f-step", box).textContent = t("lesson.focus_step", { k: Math.min(s.k + 1, s.total), total: s.total });
    },
  };
}

/** Opens an exercise on its own full screen (and starts listening when `start`).
 * mode.variant: the exercise a 4th higher (another key or position) · mode.testout: the part you play to skip
 * the lesson (a higher bar). The guidance level hides the tab/diagrams (1) or every name (2). */
async function openFocus(el, segs, ls, ex, chordData, exTitle, start = false, mode = {}) {
  if (task && focus) return toast(t("lesson.busy"));
  if (task) await task.done.catch(() => {});   // you just closed one: let it finish stopping
  stopDemo();
  if (focus) focus.views.forEach(v => v.setClock(null));
  const dlg = $(".ex-focus", el), body = $(".focus-body", dlg), g = guides.get(ex.id);
  let view = ex, suffix = "";
  if (mode.variant) {
    try {
      const v = await api("/api/exercise/variation", { json: { lesson: ls.id, exercise: ex.id } });
      view = { ...ex, steps: v.steps ?? ex.steps, shapes: v.shapes ?? ex.shapes };
      suffix = ` · ${t(`flow.var_${v.label.code}`, v.label)}`;
    } catch (e) { return toast(e.message); }
  }
  // start with the least help you haven't passed yet
  const guidance = mode.testout ? 0 : focus?.ex === ex && focus.guidance != null ? focus.guidance
    : ex.fadeable && ex.passed ? Math.min(2, (ex.guidance ?? 0) + 1) : 0;
  $("#fTitle", dlg).textContent = (mode.testout ? `${t("lesson.testout_title")} · ` : "") + exTitle(ex) + suffix;
  showLatency($("#fLat", dlg), ex.how !== "answer");
  const fth = $("#fTheory", dlg), thText = !mode.testout && ex.theory ? tc(`ex_theory.${ex.from || `${ls.id}/${ex.id}`}`, ex.theory) : "";
  fth.hidden = !thText;
  $("p span", fth).textContent = thText;
  const sayF = $("[data-speak]", fth);
  if (sayF) { stopSpeaking(); sayF.onclick = () => toggleSpeak(sayF, thText); }
  const need = mode.testout ? Math.max(ex.min, 90) : ex.min;
  $("#fTarget", dlg).textContent = `${exerciseTarget(view)} · ${t("lesson.pass_with", { min: need })}`
    + (!mode.variant && ex.best != null ? ` · ${t("lesson.your_best", { best: Math.round(ex.best) })}` : "");
  const guideBox = $("#fGuide", dlg);
  guideBox.hidden = !(ex.fadeable && !mode.testout);
  guideBox.innerHTML = [0, 1, 2].map(lv => `<button data-g="${lv}" class="${lv === guidance ? "active" : ""}" aria-pressed="${lv === guidance}">${esc(t(`flow.guide_${lv}`))}</button>`).join("");
  $$("button", guideBox).forEach(b => b.onclick = () => {
    if (task) return;
    focus.guidance = +b.dataset.g;
    openFocus(el, segs, ls, ex, chordData, exTitle, false, mode);
  });
  $(".f-hint", dlg).textContent = "";
  const views = [];
  let now = null;
  if (g) {
    body.innerHTML = `${chipsHtml({ tuning: g.chart.tuning, bpm: Math.round(g.chart.bpm * ex.speed), time: `${g.chart.beats_per_bar}/4`, capo: g.chart.capo, swing: g.chart.swing })}
      <div class="f-metro-box"></div><div class="ex-guide focus-guide"></div>`;
    views.push(metronomeView($(".f-metro-box", body), g.chart.beats_per_bar, Math.round(g.chart.bpm * ex.speed)));
    const note = g.chart.note && tc(`charts.${g.chart.id}.note`, g.chart.note);
    views.push(chartGuide($(".focus-guide", body), g.chart, { speed: ex.speed, note }));
  } else if (ANSWER_KINDS.includes(ex.kind)) {
    body.innerHTML = `<div class="q-box"><p class="muted center">${esc(t(ex.kind === "pick" ? "lesson.answer_intro_pick" : "lesson.answer_intro_quiz", { count: ex.count ?? 6 }))}</p></div>`;
  } else if (DRAWN_KINDS.includes(ex.kind)) {
    body.innerHTML = `<div class="f-now-box"></div>${ex.kind === "rhythm" ? `<div class="rhythm-bars"></div>` : ""}<ol class="drawn-list"></ol>`;
    now = promptView($(".f-now-box", body), $(".drawn-list", body));
    views.push(now);
  } else {
    const showTab = guidance === 0 || !ex.fadeable;
    body.innerHTML = `<div class="f-now-box"></div>
      ${showTab && view.steps && ex.kind !== "bend" ? `<pre class="tab" aria-label="${esc(t("lesson.tab_label"))}">${esc(tabText(view.steps))}</pre>` : ""}
      ${showTab && view.shapes ? shapesHtml(view, 120) : ""}
      ${!showTab ? `<p class="muted center">${esc(t(`flow.guide_${guidance}_note`))}</p>` : ""}`;
    now = nowView($(".f-now-box", body), ex.fadeable && guidance === 2);
    views.push(now);
  }
  focus = { ex, view, views, now, changed: focus?.changed || false, guidance, variant: !!mode.variant, testout: !!mode.testout };
  const bar = $(".ex-progress i", dlg), msg = $(".ex-msg", dlg);
  bar.style.width = "0%";
  msg.className = "ex-msg muted";
  msg.textContent = "";
  const hear = $("[data-f=hear]", dlg), labels = [`♪ ${t(g ? "lesson.focus_demo" : "lesson.focus_hear")}`, `■ ${t("lesson.demo_stop")}`];
  hear.textContent = labels[0];
  hear.hidden = !hearable(ex);
  hear.onclick = () => g ? toggleDemo(ex, hear, views, labels) : preview(ex, chordData);
  $("[data-f=next]", dlg).hidden = true;
  const go = $("[data-f=go]", dlg);
  go.textContent = t(ex.how === "answer" ? "lesson.start_answer" : "lesson.listen");
  go.onclick = () => run(el, segs, ls, ex, chordData, exTitle);
  $("[data-f=hint]", dlg).hidden = true;
  $(".f-result", dlg).hidden = true;
  $(".f-take", dlg).innerHTML = "";
  $(".f-next", dlg).innerHTML = "";
  setState(dlg, "ready");
  if (!dlg.open) dlg.showModal();
  $(".focus-inner", dlg).focus();   // so Space and Enter reach the shortcuts, not the Back button
  if (start) run(el, segs, ls, ex, chordData, exTitle);
}

/** The rig sound that suits this lesson, one click away (it loads the sound; the rig stays off until you turn it on). */
async function showTone(box, id) {
  if (!box) return;
  await rig.load();
  const name = t(`rig.preset.${id}`), using = rig.preset && rig.preset.kind === "factory" && rig.preset.id === id && !rig.preset.edited;
  box.innerHTML = `🎛 ${esc(t("lesson.tone", { name }))} ${using
    ? `<span class="pill ok">✓ ${esc(t("lesson.tone_using"))}</span>`
    : `<button class="btn small" id="toneLoad">${esc(t("lesson.tone_load"))}</button>`} <a class="small" href="#/rig">${esc(t("lesson.tone_rig"))}</a>`;
  const b = $("#toneLoad", box);
  if (b) b.onclick = () => {
    rig.loadState(factory(id), { kind: "factory", id });
    toast(t(rig.running ? "lesson.tone_loaded_on" : "lesson.tone_loaded_off", { name }), true);
    showTone(box, id);
  };
}

/** The latency correction applied to your timing, so a "late" verdict can be trusted (or fixed). */
let latencyInfo = null;
async function showLatency(box, listening) {
  if (!box) return;
  box.innerHTML = "";
  if (!listening) return;
  try { latencyInfo = latencyInfo || await api("/api/latency"); } catch { return; }
  const st = latencyInfo, warn = (st.warnings || []).find(w => ["never_measured", "too_large", "devices_changed"].includes(w.code));
  const fix = `<a href="#/settings">${esc(t("lesson.lat_fix"))}</a>`;
  if (warn) box.innerHTML = `⚠ ${esc(t(`latency.warn_${warn.code}`, warn.params))} ${fix}`;
  else if (st.applied_ms != null) box.innerHTML = `⏱ ${esc(t("lesson.lat_applied", { ms: Math.round(st.applied_ms), how: t(`lesson.lat_${st.method || "manual"}`) }))}`;
}

function closeFocus(el, segs) {
  stopSpeaking();
  if (task) task.stop();
  stopDemo();
  if (!focus) return;
  focus.views.forEach(v => v.setClock(null));
  const changed = focus.changed;
  focus = null;
  $(".ex-focus", el).close();
  if (changed) mount(el, { segs });   // show the exercises you just passed
}

function stopDemo() {
  if (demo) { demo.stop(); demo = null; }
}

function preview(ex, chordData) {
  const ch = id => chordData.chords.find(c => c.id === id);
  if (ex.kind === "notes") ex.notes.forEach((p, k) => pluck(p, k * 0.45));
  else if (ex.kind === "lick") stepGroups(ex.steps).forEach((g, k) => g.forEach(s => pluck(s.pitch, k * 0.3)));
  else if (ex.kind === "bend") { pluck(ex.steps[0].glide_from, 0); pluck(ex.steps[0].pitch, 0.6); }
  else if (ex.kind === "chord") strum(ch(ex.chord));
  else if (ex.kind === "change") ex.chords.forEach((c, k) => setTimeout(() => strum(ch(c)), k * 900));
  else if (ex.steps) stepGroups(ex.steps).forEach((g, k) => g.forEach(s => pluck(s.pitch, k * 0.3)));
  else if (ex.shapes) ex.shapes.forEach((s, k) => setTimeout(() => strum(shapeChord(s)), k * 900));
  else toast(t("lesson.open_chart"));
}

/** For drawn exercises: what to play now, in big type, and the whole list (answers revealed at the end). */
function promptView(box, list) {
  let items = [], ends = [];
  box.innerHTML = `<div class="focus-now"><small class="muted">${esc(t("lesson.focus_now"))}</small>
    <b class="f-now f-prompt">–</b><div class="q-staff f-staff"></div><small class="f-step muted"></small></div>`;
  const staffBox = $(".f-staff", box);
  let shown = null;                                   // redraw the staff only when the item changes
  const showStaff = it => { if (it === shown) return; shown = it; staffBox.innerHTML = it && it.staff ? staffSvg(it.staff) : ""; };
  const render = (cur, reveal) => {
    list.innerHTML = items.map((it, i) => `<li class="${i === cur ? "cur" : i < cur ? "done" : ""}">${esc(say(it.prompt))}${reveal ? ` <span class="muted">· ${esc(say(it.reveal))}</span>` : ""}</li>`).join("");
  };
  return {
    setClock() {},
    setItems(its) {
      items = its;
      let acc = 0;
      ends = its.map(it => (acc += it.notes));
      $(".f-prompt", box).textContent = items.length ? say(items[0].prompt) : "–";
      showStaff(items[0]);
      $(".f-step", box).textContent = t("lesson.focus_step", { k: 1, total: items.length });
      render(0, false);
    },
    update(s) {
      const i = Math.min(ends.findIndex(e => s.k < e), items.length - 1);
      const cur = i < 0 ? items.length - 1 : i;
      $(".f-prompt", box).textContent = items[cur] ? say(items[cur].prompt) : "–";
      showStaff(items[cur]);
      $(".f-step", box).textContent = t("lesson.focus_step", { k: cur + 1, total: items.length });
      render(cur, false);
    },
    reveal() { render(-1, true); },
  };
}

/** The practice state, as a word: preparing → ready → playing → feedback, or "audio unavailable". */
function setState(dlg, state) {
  const b = $("#fState", dlg);
  if (!b) return;
  b.className = `f-state st-${state}`;
  b.textContent = t(`flow.state_${state}`);
}

/** "Next, and why": the server's suggestion after a take, with a button when it can take you there. */
function showNext(el, segs, ls, ex, chordData, exTitle, n) {
  const box = $(".ex-focus .f-next", el);
  if (!box) return;
  box.innerHTML = "";
  if (!n) return;
  const p = { ...(n.params || {}) };
  if (n.code === "less_help") p.level = t(`flow.guide_${p.level}`);
  if (n.code === "next_exercise") p.title = exTitle(ls.exercises.find(e => e.id === p.exercise) || { id: p.exercise, title: p.title });
  if (n.code === "next_lesson") p.title = tc(`lessons.${p.lesson}.title`, p.title);
  box.innerHTML = `<span>💡 ${esc(t(`next.${n.code}`, p))}</span>`;
  const btn = (label, fn) => { const b = document.createElement("button"); b.className = "btn small"; b.textContent = label; b.onclick = fn; box.append(" ", b); };
  if (n.code === "less_help") btn(t("next.do_less_help"), () => { focus.guidance = n.params.level; openFocus(el, segs, ls, ex, chordData, exTitle); });
  if (n.code === "try_variation") btn(t("flow.try_vary"), () => openFocus(el, segs, ls, ex, chordData, exTitle, false, { variant: true }));
  if (n.code === "next_exercise") btn(t("next.do_open"), () => openFocus(el, segs, ls, ls.exercises.find(e => e.id === n.params.exercise), chordData, exTitle));
  if (n.code === "next_lesson") { const a = document.createElement("a"); a.className = "btn small primary"; a.href = `#/lesson/${encodeURIComponent(n.params.lesson)}`; a.textContent = t("next.do_open"); box.append(" ", a); }
}

/** Shows how a take or a quiz went: message, result ring, and the next exercise when you passed. */
function showOutcome(el, segs, ls, ex, chordData, exTitle, rep) {
  const dlg = $(".ex-focus", el), msg = $(".ex-msg", dlg), next = $("[data-f=next]", dlg);
  const a = rep.award || {};
  const score = rep.summary.score;
  setState(dlg, "feedback");
  showNext(el, segs, ls, ex, chordData, exTitle, a.next);
  msg.className = "ex-msg " + (a.passed ? "ok" : "err");
  msg.textContent = a.passed
    ? t("lesson.passed", { score: Math.round(score) }) + (a.xp ? ` · +${a.xp} XP` : "") + (a.lesson_done ? ` · ${t("lesson.lesson_done")}` : "")
      + (a.tested_out ? ` · ${t("lesson.tested_out_done")}` : "") + (a.hints ? ` · ${t("flow.with_hints", { count: a.hints })}` : "")
      + (a.guidance ? ` · ${t(`flow.guide_${a.guidance}`)}` : "")
    : score == null ? t("lesson.not_played") : t("lesson.failed", { score: Math.round(score), need: a.need });
  if (score != null) showResult($(".f-result", dlg), Math.round(score), !!a.passed, a.need ?? ex.min, a.xp);
  const take = $(".f-take", dlg);
  if (take) {
    take.innerHTML = timingVerdictHtml(rep.summary && rep.summary.timing_verdict)
      + (rep.take ? `<span class="muted small">${esc(t("take.listen"))}</span>${takePlayer(rep.take.split("/").pop(), rep.take_info)}` : "");
    bindTakePlayers(take);
  }
  if (a.passed && focus && (a.variant || a.tested_out)) {   // not the plain exercise: no "next", just refresh later
    focus.changed = true;
    return;
  }
  if (a.passed && focus) {
    focus.changed = true;
    ex.passed = true;
    if (ex.best == null || score > ex.best) ex.best = score;
    const after = ls.exercises[ls.exercises.indexOf(ex) + 1];
    if (after) {
      next.hidden = false;
      next.onclick = () => openFocus(el, segs, ls, after, chordData, exTitle);
    }
  }
}

/** "I already know this": answer two questions from each of the lesson's quizzes (85% to pass), then play its
 * last exercise at 90%. The server decides; passing completes the lesson. */
async function openTestOut(el, segs, ls, chordData, exTitle) {
  if (task) return toast(t("lesson.busy"));
  const dlg = $(".ex-focus", el), body = $(".focus-body", dlg), go = $("[data-f=go]", dlg), msg = $(".ex-msg", dlg), bar = $(".ex-progress i", dlg);
  $("#fTitle", dlg).textContent = t("lesson.testout_title");
  $("#fTarget", dlg).textContent = t("lesson.testout_target");
  $("#fGuide", dlg).hidden = true;
  $("[data-f=hear]", dlg).hidden = true;
  $("[data-f=next]", dlg).hidden = true;
  $("[data-f=hint]", dlg).hidden = true;
  $(".f-result", dlg).hidden = true;
  $(".f-take", dlg).innerHTML = "";
  $(".f-hint", dlg).textContent = "";
  body.innerHTML = `<div class="q-box"><p class="muted center">${esc(t("lesson.testout_intro"))}</p></div>`;
  msg.className = "ex-msg muted";
  msg.textContent = "";
  bar.style.width = "0%";
  focus = { ex: null, views: [], now: null, changed: focus?.changed || false };
  const playFinal = finalId => {
    const fin = ls.exercises.find(e => e.id === finalId);
    if (!fin) return;
    msg.className = "ex-msg ok";
    msg.textContent = t("lesson.testout_now_play", { title: exTitle(fin) });
    go.textContent = `▶ ${t("lesson.testout_play")}`;
    go.onclick = () => openFocus(el, segs, ls, fin, chordData, exTitle, false, { testout: true });
  };
  go.textContent = t("lesson.testout_start");
  go.onclick = async () => {
    let d;
    try { d = await api("/api/lesson/testout", { json: { lesson: ls.id } }); } catch (e) { return toast(e.message); }
    if (!d.token) return playFinal(d.final);                 // nothing to answer: straight to playing
    go.textContent = t("lesson.stop");
    task = runAnswers(body, { drawn: d, finishUrl: "/api/lesson/testout/finish",
      onProgress: (k, n) => { bar.style.width = `${Math.round(100 * k / n)}%`; } });
    go.onclick = () => task && task.stop();
    try {
      const rep = await task.done;
      task = null;
      if (!rep) { msg.textContent = t("lesson.answer_stopped"); go.textContent = t("lesson.testout_start"); go.onclick = () => openTestOut(el, segs, ls, chordData, exTitle); return; }
      showResult($(".f-result", dlg), Math.round(rep.summary.score), rep.award.passed, rep.award.need, rep.award.xp);
      if (!rep.award.passed) {
        msg.className = "ex-msg err";
        msg.textContent = t("lesson.testout_failed", { need: rep.award.need });
        go.textContent = t("lesson.focus_again");
        go.onclick = () => openTestOut(el, segs, ls, chordData, exTitle);
      } else if (rep.final) playFinal(rep.final);
      else {
        focus.changed = true;
        msg.className = "ex-msg ok";
        msg.textContent = t("lesson.tested_out_done") + (rep.award.xp ? ` · +${rep.award.xp} XP` : "");
        go.textContent = t("lesson.focus_back");
        go.onclick = () => closeFocus(el, segs);
      }
    } catch (e) {
      task = null;
      msg.className = "ex-msg err";
      msg.textContent = e.message;
    }
  };
  if (!dlg.open) dlg.showModal();
  $(".focus-inner", dlg).focus();
}

/** Quiz and pick exercises: answer the drawn questions, then the server grades them. */
async function runAnswer(el, segs, ls, ex, chordData, exTitle) {
  const dlg = $(".ex-focus", el), bar = $(".ex-progress i", dlg), msg = $(".ex-msg", dlg), btn = $("[data-f=go]", dlg);
  $("[data-f=next]", dlg).hidden = true;
  $(".f-result", dlg).hidden = true;
  $(".f-take", dlg).innerHTML = "";
  bar.style.width = "0%";
  msg.className = "ex-msg muted";
  msg.textContent = "";
  btn.textContent = t("lesson.stop");
  setState(dlg, "playing");
  task = runAnswers($(".focus-body", dlg), { lesson: ls.id, exercise: ex.id,
    onProgress: (k, n) => { bar.style.width = `${Math.round(100 * k / n)}%`; } });
  btn.onclick = () => task && task.stop();
  try {
    const rep = await task.done;
    if (rep) showOutcome(el, segs, ls, ex, chordData, exTitle, rep);
    else msg.textContent = t("lesson.answer_stopped");
  } catch (e) {
    msg.className = "ex-msg err";
    msg.textContent = e.message;
  } finally {
    task = null;
    btn.textContent = t("lesson.focus_again");
    btn.onclick = () => run(el, segs, ls, ex, chordData, exTitle);
    if (dlg.open) $(".focus-inner", dlg).focus();
  }
}

async function run(el, segs, ls, ex, chordData, exTitle) {
  if (task) return toast(t("lesson.busy"));
  stopDemo();   // the microphone would hear it
  if (ANSWER_KINDS.includes(ex.kind)) return runAnswer(el, segs, ls, ex, chordData, exTitle);
  const g = guides.get(ex.id), dlg = $(".ex-focus", el), views = focus.views, now = focus.now;
  if (DRAWN_KINDS.includes(ex.kind)) {          // a fresh set of targets every time
    let d;
    try { d = await api("/api/exercise/draw", { json: { lesson: ls.id, exercise: ex.id } }); }
    catch (e) { return toast(e.message); }
    now.setItems(d.items);
    const barsBox = $(".rhythm-bars", dlg);
    if (barsBox && d.bars) barsBox.innerHTML = d.bars.map((b, k) => rhythmSvg(b, { width: 360, timeSig: k === 0, label: t("rhythm.bar_n", { n: k + 1 }),
      marks: d.marks && d.marks[k] })).join("");
    if (d.phrase) {                               // melodic echo: hear the phrase first, then play it back
      const goBtn = $("[data-f=go]", dlg), m = $(".ex-msg", dlg);
      goBtn.disabled = true;
      m.className = "ex-msg muted";
      m.textContent = t("ear.echo_listen");
      d.phrase.forEach(n => pluck(n.pitch, n.start * 60 / d.bpm, 0.4));
      const len = d.phrase.reduce((a, n) => Math.max(a, n.start + n.beats), 0) * 60 / d.bpm;
      await new Promise(r => setTimeout(r, len * 1000 + 600));
      goBtn.disabled = false;
    }
  }
  let pos = null, at = 0;
  const rate = g ? g.chart.bpm * ex.speed / 60 : 0;
  // between state polls the playhead runs on its own at the exercise's tempo
  if (g) views.forEach(v => v.setClock(() => pos == null ? null : pos + (performance.now() - at) / 1000 * rate));
  const bar = $(".ex-progress i", dlg), msg = $(".ex-msg", dlg), btn = $("[data-f=go]", dlg), next = $("[data-f=next]", dlg);
  next.hidden = true;
  $(".f-result", dlg).hidden = true;
  $(".f-take", dlg).innerHTML = "";
  $("[data-f=hear]", dlg).disabled = true;
  btn.textContent = t("lesson.stop");
  msg.className = "ex-msg muted";
  msg.textContent = t(ex.kind === "chart" ? "lesson.wait_count_in" : ex.kind === "bend" ? "lesson.bend_ready" : "lesson.play_when_ready");
  btn.onclick = () => task && task.stop();
  // hints: each press shows a bit more about the note you're on (string → fret → name); all are counted
  const hintBtn = $("[data-f=hint]", dlg), hintOut = $(".f-hint", dlg);
  let hintFor = "", hintLevel = 0;
  hintOut.textContent = "";
  hintBtn.hidden = !(focus.view.steps || DRAWN_KINDS.includes(ex.kind) || ex.kind === "notes");
  hintBtn.onclick = async () => {
    try {
      const r = await api("/api/live/hint", { method: "POST" });
      if (!r.hint) return;
      const k = JSON.stringify(r.hint);
      hintLevel = k === hintFor ? Math.min(3, hintLevel + 1) : 1;
      hintFor = k;
      const [s, f] = r.hint.tab[0] || [];
      hintOut.textContent = t("flow.hint_text", { count: r.hints }) + " " + [
        s != null ? t("flow.hint_string", { s }) : "", hintLevel >= 2 && f != null ? t("flow.hint_fret", { f }) : "",
        hintLevel >= 3 ? r.hint.label : ""].filter(Boolean).join(" · ");
    } catch { /* the take just ended */ }
  };
  setState(dlg, "preparing");
  $(".f-next", dlg).innerHTML = "";
  let playing = false;
  stopSpeaking();                  // the microphone shouldn't hear the voice
  task = listen({ exercise: { lesson: ls.id, exercise: ex.id, guidance: focus.guidance, variant: focus.variant, testout: focus.testout }, click: true }, {
    onState: s => {
      if (!playing) { playing = true; setState(dlg, "playing"); }
      bar.style.width = `${Math.round(100 * Math.min(s.k, s.total) / s.total)}%`;
      if (s.countdown) msg.textContent = t("lesson.count_in", { n: s.countdown });
      if (now && s.lane) now.update(s);
      pos = s.pos ?? null;
      at = performance.now();
    },
    onMessage: m => { msg.textContent = msgText(m); msg.className = "ex-msg " + (msgIsError(m) ? "err" : "ok"); },
  });
  try {
    const rep = await task.done;
    showOutcome(el, segs, ls, ex, chordData, exTitle, rep);
    if (now && now.reveal) now.reveal();
  } catch (e) {
    msg.className = "ex-msg err";
    if (e.code === "audio" || e.code === "no_device") {            // no input: say why and how to fix it
      setState(dlg, "audio_unavailable");
      msg.innerHTML = t("flow.no_audio_html", { error: esc(e.message), interpolation: { escapeValue: false } });
    } else msg.textContent = e.message;
  } finally {
    views.forEach(v => v.setClock(null));
    task = null;
    hintBtn.hidden = true;
    $("[data-f=hear]", dlg).disabled = false;
    btn.textContent = t("lesson.focus_again");
    btn.onclick = () => run(el, segs, ls, ex, chordData, exTitle);
    if (dlg.open) $(".focus-inner", dlg).focus();   // Space = again, Enter = next
  }
}

/** The score as a ring with the number inside, a mark at the passing score, and the XP you earned. */
function showResult(box, score, passed, need, xp) {
  const r = 52, len = 2 * Math.PI * r, at = a => `rotate(${a * 3.6 - 90} 60 60)`;
  box.className = `f-result ${passed ? "ok" : "err"}`;
  box.innerHTML = `
    <svg viewBox="0 0 120 120" width="132" height="132" aria-hidden="true">
      <circle class="r-track" cx="60" cy="60" r="${r}"/>
      <circle class="r-val" cx="60" cy="60" r="${r}" stroke-dasharray="${len}" stroke-dashoffset="${len}" transform="${at(0)}" style="--to:${(len * (1 - Math.min(score, 100) / 100)).toFixed(1)}"/>
      <line class="r-need" x1="60" y1="2" x2="60" y2="16" transform="rotate(${need * 3.6} 60 60)"/>
    </svg>
    <div class="r-text"><b>${score}%</b><small>${esc(passed ? t("lesson.result_passed") : t("lesson.result_need", { need }))}</small></div>
    ${passed && xp ? `<span class="r-xp">+${xp} XP</span>` : ""}`;
  box.hidden = false;
}

export function unmount() {
  stopSpeaking();
  latencyInfo = null;                                       // measured again on the next visit
  if (task) { task.stop(); task = null; }
  stopDemo();
  focus = null;
  guides.forEach(g => g.guide.setClock(null));
  guides.clear();
}
