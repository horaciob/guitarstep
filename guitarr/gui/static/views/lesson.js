// A lesson: theory, chords, tutorials (videos) and exercises you pass by playing.
import { lang, msgIsError, msgText, t, tc } from "../lib/i18n.js";
import { $, $$, api, bindChordSvg, chordSvg, esc, noteName, pluck, strum, toast, youtubeId, youtubeSearch } from "../lib/ui.js";
import { listen } from "../lib/listen.js";
import { chartGuide, playChart } from "./charts.js";

let task = null, demo = null;
let focus = null;   // the exercise open on its own full screen: { ex, views, changed }
const guides = new Map();   // exercise id → { guide, chart } for chart exercises

const STRINGS = ["e", "B", "G", "D", "A", "E"];   // tab lines, 1st string on top

/** Tab for lick and bend steps: one column per note, with h p / \ b r ~ as in written tab. */
function tabText(steps) {
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

function exerciseTarget(ex) {
  if (ex.kind === "notes") return ex.notes.map(noteName).join(" ");
  if (ex.kind === "lick") return ex.steps.map(s => noteName(s.pitch)).join(" ");
  if (ex.kind === "bend") {
    const s = ex.steps[0];
    return t("lesson.bend_target", { string: s.string, fret: s.fret, note: noteName(s.pitch), tries: ex.steps.length, hold: (ex.hold ?? 1).toLocaleString(lang()) });
  }
  if (ex.kind === "chord") return `${ex.chord} × ${ex.times}`;
  if (ex.kind === "change") return `${ex.chords.join(" ↔ ")} × ${ex.times}`;
  if (ex.kind === "chart") return t("lesson.chart_at", { pct: Math.round(ex.speed * 100) });
  return "";
}

export async function mount(el, { segs }) {
  const id = decodeURIComponent(segs[0] || "");
  const [course, chordData] = await Promise.all([api("/api/course"), api("/api/chords")]);
  const all = course.levels.flatMap(l => l.lessons.map(ls => ({ ...ls, level: l })));
  const idx = all.findIndex(l => l.id === id);
  if (idx < 0) { el.innerHTML = `<div class="gl-head"><h1>${esc(t("lesson.not_found"))}</h1></div><p><a href="#/course">${esc(t("lesson.back"))}</a></p>`; return; }
  const ls = all[idx], next = all[idx + 1];
  const chords = (ls.chords || []).map(c => chordData.chords.find(x => x.id === c)).filter(Boolean);
  const vid = ls.pinned && youtubeId(ls.pinned);
  const lt = (k, fb) => tc(`lessons.${ls.id}.${k}`, fb);
  const theory = lt("theory", ls.theory), tips = lt("tips", ls.tips || []), tutorials = lt("tutorials", ls.tutorials || []);
  const exTitle = ex => tc(`exercises.${ls.id}/${ex.id}`, ex.title);
  const upNext = ls.exercises.find(e => !e.passed);   // the first exercise you haven't passed yet

  el.innerHTML = `
    <a class="btn small" href="#/course">← ${esc(t("nav.course"))}</a>
    <div class="gl-head" style="margin-top:12px"><small class="muted">${esc(t("lesson.meta", { n: ls.level.number, level: tc(`levels.${ls.level.id}.title`, ls.level.title), min: ls.minutes }))}</small>
      <h1>${esc(lt("title", ls.title))} ${ls.done ? `<span class="pill ok">${esc(t("lesson.complete"))}</span>` : ""}</h1></div>
    <div class="lesson-layout">
      <div class="stack">
        <div class="panel"><h2>${esc(t("lesson.idea"))}</h2><ul class="theory">${theory.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
          ${tips.length ? `<h3>${esc(t("lesson.tips"))}</h3><ul class="theory">${tips.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>
        <div class="panel"><div class="ex-panel-head"><h2>${esc(t("lesson.exercises"))}</h2>
            <button class="btn primary" id="exContinue">▶ ${esc(upNext ? t("lesson.continue_with", { title: exTitle(upNext) }) : t("lesson.practice_again"))}</button></div>
          <p class="muted small">${t("lesson.exercises_hint_html")}</p>
          <div class="exercises">${ls.exercises.map(ex => `
            <div class="exercise${ex.passed ? " passed" : ""}" data-id="${esc(ex.id)}">
              <div class="ex-head"><span class="state">${ex.passed ? "✓" : "○"}</span>
                <div><b>${esc(exTitle(ex))}</b><small class="muted">${esc(exerciseTarget(ex))} · ${esc(t("lesson.pass_with", { min: ex.min }))}${ex.best != null ? ` · ${esc(t("lesson.your_best", { best: Math.round(ex.best) }))}` : ""}</small></div>
                <button class="btn small" data-act="hear" title="${esc(t(ex.kind === "chart" ? "lesson.demo_hint" : "lesson.hear_hint"))}">♪</button>
                <button class="btn small primary" data-act="go">${esc(t("lesson.listen"))}</button></div>
              ${ex.kind === "lick" ? `<pre class="tab" aria-label="${esc(t("lesson.tab_label"))}">${esc(tabText(ex.steps))}</pre>` : ""}
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
      <div class="focus-head"><h1 id="fTitle"></h1><p class="muted" id="fTarget"></p></div>
      <div class="focus-body"></div>
      <div class="focus-foot">
        <div class="ex-progress"><i></i></div>
        <div class="f-result" hidden></div>
        <div class="ex-msg muted" aria-live="polite"></div>
        <div class="row center"><button class="btn" data-f="hear"></button>
          <button class="btn primary xl" data-f="go"></button>
          <button class="btn" data-f="next" hidden>${esc(t("lesson.focus_next"))} →</button></div>
        <p class="muted small center kbd-hint">${t("lesson.focus_keys_html")}</p>
      </div>
    </div></dialog>`;

  $$(".mini-chord", el).forEach(m => bindChordSvg(m, chords.find(c => c.id === m.dataset.id)));
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
  }));
  $$(".exercise", el).forEach(box => {
    const ex = ls.exercises.find(e => e.id === box.dataset.id);
    const hear = $("[data-act=hear]", box);
    hear.onclick = () => ex.kind === "chart" ? toggleDemo(ex, hear, [guides.get(ex.id).guide]) : preview(ex, chordData);
    $("[data-act=go]", box).onclick = () => openFocus(el, segs, ls, ex, chordData, exTitle, true);
  });
  const dlg = $(".ex-focus", el);
  dlg.addEventListener("cancel", e => { e.preventDefault(); closeFocus(el, segs); });   // Esc
  $("[data-f=back]", dlg).onclick = () => closeFocus(el, segs);
  // keys while the exercise is on screen: Space starts/stops, Enter goes to the next exercise
  dlg.addEventListener("keydown", e => {
    if (e.target.closest("button, input, a, .knob")) return;   // a focused control handles its own keys
    const next = $("[data-f=next]", dlg);
    if (e.key === " ") { e.preventDefault(); $("[data-f=go]", dlg).click(); }
    else if (e.key === "Enter" && !next.hidden) { e.preventDefault(); next.click(); }
  });
  $("#exContinue", el).onclick = () => openFocus(el, segs, ls, upNext || ls.exercises[0], chordData, exTitle);
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

/** What to play now and next, for exercises without a tempo (notes, chords, licks, bends). */
function nowView(box) {
  box.innerHTML = `<div class="focus-now"><small class="muted">${esc(t("lesson.focus_now"))}</small>
    <b class="f-now">–</b><span class="f-then muted"></span><small class="f-step muted"></small></div>`;
  return {
    setClock() {},
    update(s) {
      const cur = s.lane.findIndex(e => e.current), now = s.lane[cur], then = s.lane[cur + 1];
      $(".f-now", box).textContent = now ? now.label : "–";
      $(".f-then", box).textContent = then ? t("lesson.focus_then", { x: then.label }) : "";
      $(".f-step", box).textContent = t("lesson.focus_step", { k: Math.min(s.k + 1, s.total), total: s.total });
    },
  };
}

/** Opens an exercise on its own full screen (and starts listening when `start`). */
async function openFocus(el, segs, ls, ex, chordData, exTitle, start = false) {
  if (task && focus) return toast(t("lesson.busy"));
  if (task) await task.done.catch(() => {});   // you just closed one: let it finish stopping
  stopDemo();
  if (focus) focus.views.forEach(v => v.setClock(null));
  const dlg = $(".ex-focus", el), body = $(".focus-body", dlg), g = guides.get(ex.id);
  $("#fTitle", dlg).textContent = exTitle(ex);
  $("#fTarget", dlg).textContent = `${exerciseTarget(ex)} · ${t("lesson.pass_with", { min: ex.min })}`
    + (ex.best != null ? ` · ${t("lesson.your_best", { best: Math.round(ex.best) })}` : "");
  const views = [];
  let now = null;
  if (g) {
    body.innerHTML = `<div class="f-metro-box"></div><div class="ex-guide focus-guide"></div>`;
    views.push(metronomeView($(".f-metro-box", body), g.chart.beats_per_bar, Math.round(g.chart.bpm * ex.speed)));
    const note = g.chart.note && tc(`charts.${g.chart.id}.note`, g.chart.note);
    views.push(chartGuide($(".focus-guide", body), g.chart, { speed: ex.speed, note }));
  } else {
    body.innerHTML = `<div class="f-now-box"></div>${ex.kind === "lick" ? `<pre class="tab" aria-label="${esc(t("lesson.tab_label"))}">${esc(tabText(ex.steps))}</pre>` : ""}`;
    now = nowView($(".f-now-box", body));
    views.push(now);
  }
  focus = { ex, views, now, changed: focus?.changed || false };
  const bar = $(".ex-progress i", dlg), msg = $(".ex-msg", dlg);
  bar.style.width = "0%";
  msg.className = "ex-msg muted";
  msg.textContent = "";
  const hear = $("[data-f=hear]", dlg), labels = [`♪ ${t(g ? "lesson.focus_demo" : "lesson.focus_hear")}`, `■ ${t("lesson.demo_stop")}`];
  hear.textContent = labels[0];
  hear.onclick = () => g ? toggleDemo(ex, hear, views, labels) : preview(ex, chordData);
  $("[data-f=next]", dlg).hidden = true;
  const go = $("[data-f=go]", dlg);
  go.textContent = t("lesson.listen");
  go.onclick = () => run(el, segs, ls, ex, chordData, exTitle);
  $(".f-result", dlg).hidden = true;
  if (!dlg.open) dlg.showModal();
  $(".focus-inner", dlg).focus();   // so Space and Enter reach the shortcuts, not the Back button
  if (start) run(el, segs, ls, ex, chordData, exTitle);
}

function closeFocus(el, segs) {
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
  else if (ex.kind === "lick") ex.steps.forEach((s, k) => pluck(s.pitch, k * 0.3));
  else if (ex.kind === "bend") { pluck(ex.steps[0].glide_from, 0); pluck(ex.steps[0].pitch, 0.6); }
  else if (ex.kind === "chord") strum(ch(ex.chord));
  else if (ex.kind === "change") ex.chords.forEach((c, k) => setTimeout(() => strum(ch(c)), k * 900));
  else toast(t("lesson.open_chart"));
}

async function run(el, segs, ls, ex, chordData, exTitle) {
  if (task) return toast(t("lesson.busy"));
  stopDemo();   // the microphone would hear it
  const g = guides.get(ex.id), dlg = $(".ex-focus", el), views = focus.views, now = focus.now;
  let pos = null, at = 0;
  const rate = g ? g.chart.bpm * ex.speed / 60 : 0;
  // between state polls the playhead runs on its own at the exercise's tempo
  if (g) views.forEach(v => v.setClock(() => pos == null ? null : pos + (performance.now() - at) / 1000 * rate));
  const bar = $(".ex-progress i", dlg), msg = $(".ex-msg", dlg), btn = $("[data-f=go]", dlg), next = $("[data-f=next]", dlg);
  next.hidden = true;
  $(".f-result", dlg).hidden = true;
  $("[data-f=hear]", dlg).disabled = true;
  btn.textContent = t("lesson.stop");
  msg.className = "ex-msg muted";
  msg.textContent = t(ex.kind === "chart" ? "lesson.wait_count_in" : ex.kind === "bend" ? "lesson.bend_ready" : "lesson.play_when_ready");
  btn.onclick = () => task && task.stop();
  task = listen({ exercise: { lesson: ls.id, exercise: ex.id }, click: true }, {
    onState: s => {
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
    const a = rep.award || {};
    const score = rep.summary.score;
    msg.className = "ex-msg " + (a.passed ? "ok" : "err");
    msg.textContent = a.passed
      ? t("lesson.passed", { score: Math.round(score) }) + (a.xp ? ` · +${a.xp} XP` : "") + (a.lesson_done ? ` · ${t("lesson.lesson_done")}` : "")
      : score == null ? t("lesson.not_played") : t("lesson.failed", { score: Math.round(score), need: a.need });
    if (score != null) showResult($(".f-result", dlg), Math.round(score), !!a.passed, a.need ?? ex.min, a.xp);
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
  } catch (e) {
    msg.className = "ex-msg err";
    msg.textContent = e.message;
  } finally {
    views.forEach(v => v.setClock(null));
    task = null;
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
  if (task) { task.stop(); task = null; }
  stopDemo();
  focus = null;
  guides.forEach(g => g.guide.setClock(null));
  guides.clear();
}
