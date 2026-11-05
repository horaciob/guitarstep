// A lesson: theory, chords, tutorials (videos) and exercises you pass by playing.
import { msgIsError, msgText, t, tc } from "../lib/i18n.js";
import { $, $$, api, bindChordSvg, chordSvg, esc, noteName, pluck, strum, toast, youtubeId, youtubeSearch } from "../lib/ui.js";
import { listen } from "../lib/listen.js";

let task = null;

function exerciseTarget(ex) {
  if (ex.kind === "notes") return ex.notes.map(noteName).join(" ");
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

  el.innerHTML = `
    <a class="btn small" href="#/course">← ${esc(t("nav.course"))}</a>
    <div class="gl-head" style="margin-top:12px"><small class="muted">${esc(t("lesson.meta", { n: ls.level.number, level: tc(`levels.${ls.level.id}.title`, ls.level.title), min: ls.minutes }))}</small>
      <h1>${esc(lt("title", ls.title))} ${ls.done ? `<span class="pill ok">${esc(t("lesson.complete"))}</span>` : ""}</h1></div>
    <div class="lesson-layout">
      <div class="stack">
        <div class="panel"><h2>${esc(t("lesson.idea"))}</h2><ul class="theory">${theory.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
          ${tips.length ? `<h3>${esc(t("lesson.tips"))}</h3><ul class="theory">${tips.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}</div>
        <div class="panel"><h2>${esc(t("lesson.exercises"))}</h2><p class="muted small">${t("lesson.exercises_hint_html")}</p>
          <div class="exercises">${ls.exercises.map(ex => `
            <div class="exercise${ex.passed ? " passed" : ""}" data-id="${esc(ex.id)}">
              <div class="ex-head"><span class="state">${ex.passed ? "✓" : "○"}</span>
                <div><b>${esc(exTitle(ex))}</b><small class="muted">${esc(exerciseTarget(ex))} · ${esc(t("lesson.pass_with", { min: ex.min }))}${ex.best != null ? ` · ${esc(t("lesson.your_best", { best: Math.round(ex.best) }))}` : ""}</small></div>
                <button class="btn small" data-act="hear" title="${esc(t("lesson.hear_hint"))}">♪</button>
                <button class="btn small primary" data-act="go">${esc(t("lesson.listen"))}</button></div>
              <div class="ex-live" hidden><div class="ex-progress"><i></i></div><div class="ex-msg muted"></div></div>
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
    </div>`;

  $$(".mini-chord", el).forEach(m => bindChordSvg(m, chords.find(c => c.id === m.dataset.id)));
  $$("[data-strum]", el).forEach(b => b.onclick = () => strum(chords.find(c => c.id === b.dataset.strum)));
  $("#pinBtn", el).onclick = async () => {
    try {
      await api("/api/progress/tutorial", { json: { lesson: ls.id, url: $("#pin", el).value } });
      toast(t($("#pin", el).value ? "lesson.pinned" : "lesson.unpinned"), true);
      mount(el, { segs });
    } catch (e) { toast(e.message); }
  };
  $$(".exercise", el).forEach(box => {
    const ex = ls.exercises.find(e => e.id === box.dataset.id);
    $("[data-act=hear]", box).onclick = () => preview(ex, chordData);
    $("[data-act=go]", box).onclick = () => run(el, segs, ls, ex, box);
  });
}

function preview(ex, chordData) {
  const ch = id => chordData.chords.find(c => c.id === id);
  if (ex.kind === "notes") ex.notes.forEach((p, k) => pluck(p, k * 0.45));
  else if (ex.kind === "chord") strum(ch(ex.chord));
  else if (ex.kind === "change") ex.chords.forEach((c, k) => setTimeout(() => strum(ch(c)), k * 900));
  else toast(t("lesson.open_chart"));
}

async function run(el, segs, ls, ex, box) {
  if (task) return toast(t("lesson.busy"));
  const live = $(".ex-live", box), bar = $(".ex-progress i", box), msg = $(".ex-msg", box), btn = $("[data-act=go]", box);
  live.hidden = false;
  btn.textContent = t("lesson.stop");
  msg.className = "ex-msg muted";
  msg.textContent = ex.kind === "chart" ? t("lesson.wait_count_in") : t("lesson.play_when_ready");
  btn.onclick = () => task && task.stop();
  task = listen({ exercise: { lesson: ls.id, exercise: ex.id }, click: true }, {
    onState: s => {
      bar.style.width = `${Math.round(100 * Math.min(s.k, s.total) / s.total)}%`;
      if (s.countdown) msg.textContent = t("lesson.count_in", { n: s.countdown });
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
    const here = location.hash;
    if (a.passed) setTimeout(() => { if (location.hash === here) mount(el, { segs }); }, 1800);
  } catch (e) {
    msg.className = "ex-msg err";
    msg.textContent = e.message;
  } finally {
    task = null;
    btn.textContent = t("lesson.listen");
    btn.onclick = () => run(el, segs, ls, ex, box);
  }
}

export function unmount() {
  if (task) { task.stop(); task = null; }
}
