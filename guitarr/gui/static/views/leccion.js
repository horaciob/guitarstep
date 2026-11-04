// Una lección: teoría, acordes, tutorías (videos) y ejercicios que se aprueban tocando.
import { $, $$, api, bindChordSvg, chordSvg, esc, noteName, pluck, strum, toast, youtubeId, youtubeSearch } from "../lib/ui.js";
import { listen } from "../lib/listen.js";

let task = null;

function exerciseTarget(ex) {
  if (ex.kind === "notas") return ex.notes.map(noteName).join(" ");
  if (ex.kind === "acorde") return `${ex.chord} × ${ex.times}`;
  if (ex.kind === "cambio") return `${ex.chords.join(" ↔ ")} × ${ex.times}`;
  if (ex.kind === "cifrado") return `cifrado al ${Math.round(ex.speed * 100)}%`;
  return "";
}

export async function mount(el, { segs }) {
  const id = decodeURIComponent(segs[0] || "");
  const [ruta, acordes] = await Promise.all([api("/api/ruta"), api("/api/acordes")]);
  const all = ruta.levels.flatMap(l => l.lessons.map(ls => ({ ...ls, level: l })));
  const idx = all.findIndex(l => l.id === id);
  if (idx < 0) { el.innerHTML = `<p>No existe esa lección. <a href="#/ruta">Volver a la ruta</a></p>`; return; }
  const ls = all[idx], next = all[idx + 1];
  const chords = (ls.chords || []).map(c => acordes.chords.find(x => x.id === c)).filter(Boolean);
  const vid = ls.pinned && youtubeId(ls.pinned);

  el.innerHTML = `
    <a class="btn small" href="#/ruta">← Ruta</a>
    <div class="gl-head" style="margin-top:12px"><small class="muted">Nivel ${ls.level.number} · ${esc(ls.level.title)} · ${ls.minutes} min</small>
      <h1>${esc(ls.title)} ${ls.done ? `<span class="pill ok">✓ completa</span>` : ""}</h1></div>
    <div class="lesson-layout">
      <div class="stack">
        <div class="panel"><h2>La idea</h2><ul class="theory">${ls.theory.map(t => `<li>${esc(t)}</li>`).join("")}</ul>
          ${(ls.tips || []).length ? `<h3>Consejos</h3><ul class="theory">${ls.tips.map(t => `<li>${esc(t)}</li>`).join("")}</ul>` : ""}</div>
        <div class="panel"><h2>Ejercicios</h2><p class="muted small">Apretá <b>Escuchame</b> y tocá. Se aprueba con el puntaje indicado.</p>
          <div class="exercises">${ls.exercises.map(ex => `
            <div class="exercise${ex.passed ? " passed" : ""}" data-id="${esc(ex.id)}">
              <div class="ex-head"><span class="state">${ex.passed ? "✓" : "○"}</span>
                <div><b>${esc(ex.title)}</b><small class="muted">${esc(exerciseTarget(ex))} · aprobás con ${ex.min}%${ex.best != null ? ` · tu mejor: ${Math.round(ex.best)}%` : ""}</small></div>
                <button class="btn small" data-act="hear" title="Escuchar cómo suena">♪</button>
                <button class="btn small primary" data-act="go">🎧 Escuchame</button></div>
              <div class="ex-live" hidden><div class="ex-progress"><i></i></div><div class="ex-msg muted"></div></div>
            </div>`).join("")}</div></div>
      </div>
      <div class="stack">
        ${chords.length ? `<div class="panel"><h2>Acordes</h2><div class="mini-chords">${chords.map(c =>
          `<div class="mini-chord" data-id="${esc(c.id)}"><b>${esc(c.id)}</b>${chordSvg(c, { size: 96 })}<button class="btn small" data-strum="${esc(c.id)}">▶</button></div>`).join("")}</div></div>` : ""}
        <div class="panel"><h2>Tutorías</h2>
          ${vid ? `<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/${vid}?rel=0" title="Video de la lección" allow="encrypted-media; picture-in-picture" allowfullscreen></iframe></div>`
                : ls.pinned ? `<p><a href="${esc(ls.pinned)}" target="_blank" rel="noopener">Tu video fijado ↗</a></p>` : ""}
          <p class="muted small">Buscá un video que te guste para esta lección:</p>
          <ul class="tutorias">${(ls.tutorias || []).map(q => `<li><a href="${youtubeSearch(q)}" target="_blank" rel="noopener">▶ ${esc(q)}</a></li>`).join("")}</ul>
          <label class="field"><span>Fijar un video para esta lección (link de YouTube u otro)</span>
            <div class="row"><input type="text" id="pin" placeholder="https://www.youtube.com/watch?v=…" value="${esc(ls.pinned || "")}"><button class="btn small" id="pinBtn">Fijar</button></div></label>
        </div>
        ${next ? `<a class="callout" href="#/leccion/${encodeURIComponent(next.id)}"><span>Siguiente: <b>${esc(next.title)}</b></span><span>→</span></a>` : ""}
      </div>
    </div>`;

  $$(".mini-chord", el).forEach(m => bindChordSvg(m, chords.find(c => c.id === m.dataset.id)));
  $$("[data-strum]", el).forEach(b => b.onclick = () => strum(chords.find(c => c.id === b.dataset.strum)));
  $("#pinBtn", el).onclick = async () => {
    try {
      await api("/api/progreso/tutoria", { json: { lesson: ls.id, url: $("#pin", el).value } });
      toast($("#pin", el).value ? "Video fijado" : "Video quitado", true);
      mount(el, { segs });
    } catch (e) { toast(e.message); }
  };
  $$(".exercise", el).forEach(box => {
    const ex = ls.exercises.find(e => e.id === box.dataset.id);
    $("[data-act=hear]", box).onclick = () => preview(ex, acordes);
    $("[data-act=go]", box).onclick = () => run(el, segs, ls, ex, box);
  });
}

function preview(ex, acordes) {
  if (ex.kind === "notas") ex.notes.forEach((p, k) => pluck(p, k * 0.45));
  else if (ex.kind === "acorde") strum(acordes.chords.find(c => c.id === ex.chord));
  else if (ex.kind === "cambio") ex.chords.forEach((c, k) => setTimeout(() => strum(acordes.chords.find(x => x.id === c)), k * 900));
  else toast("Para escuchar el cifrado, abrilo en Cifrados.");
}

async function run(el, segs, ls, ex, box) {
  if (task) return toast("Ya estoy escuchando otro ejercicio");
  const live = $(".ex-live", box), bar = $(".ex-progress i", box), msg = $(".ex-msg", box), btn = $("[data-act=go]", box);
  live.hidden = false;
  btn.textContent = "■ Parar";
  msg.className = "ex-msg muted";
  msg.textContent = ex.kind === "cifrado" ? "Esperá la cuenta de entrada…" : "Tocá cuando quieras.";
  const stopNow = () => task && task.stop();
  btn.onclick = stopNow;
  task = listen({ ejercicio: { lesson: ls.id, exercise: ex.id }, click: true }, {
    onState: s => {
      bar.style.width = `${Math.round(100 * Math.min(s.k, s.total) / s.total)}%`;
      if (s.countdown) msg.textContent = `Cuenta: ${s.countdown}…`;
    },
    onMessage: m => { msg.textContent = m; msg.className = "ex-msg " + (/^[✗∅+]/.test(m) ? "err" : "ok"); },
  });
  try {
    const rep = await task.done;
    const a = rep.award || {};
    const score = rep.summary.score;
    msg.className = "ex-msg " + (a.passed ? "ok" : "err");
    msg.textContent = a.passed ? `✓ Aprobado con ${Math.round(score)}%${a.xp ? ` · +${a.xp} XP` : ""}${a.lesson_done ? " · ¡lección completa!" : ""}`
      : score == null ? "No llegaste a tocar. Probá de nuevo." : `${Math.round(score)}% — necesitás ${a.need}%. ¡Otra vez!`;
    const here = location.hash;
    if (a.passed) setTimeout(() => { if (location.hash === here) mount(el, { segs }); }, 1800);
  } catch (e) {
    msg.className = "ex-msg err";
    msg.textContent = e.message;
  } finally {
    task = null;
    btn.textContent = "🎧 Escuchame";
    btn.onclick = () => run(el, segs, ls, ex, box);
  }
}

export function unmount() {
  if (task) { task.stop(); task = null; }
}
