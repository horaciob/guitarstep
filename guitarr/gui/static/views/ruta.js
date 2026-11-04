// Ruta de aprendizaje: niveles → lecciones. Cada lección se aprueba tocando sus ejercicios.
import { api, esc } from "../lib/ui.js";

export async function mount(el) {
  const r = await api("/api/ruta");
  const all = r.levels.flatMap(l => l.lessons);
  const done = all.filter(l => l.done).length;
  el.innerHTML = `
    <div class="gl-head"><h1>Ruta</h1>
      <p class="muted">${done}/${all.length} lecciones. Cada ejercicio se aprueba tocándolo: te escucha y te dice si salió.</p></div>
    ${r.next ? `<a class="callout" href="#/leccion/${encodeURIComponent(r.next.id)}"><span>Seguís con <b>${esc(r.next.title)}</b></span><span class="btn small primary">Continuar →</span></a>` : `<div class="callout"><span>¡Terminaste la ruta! 🎉 Seguí con los cifrados.</span></div>`}
    ${r.levels.map(lv => `
      <section class="level">
        <h2><span class="lvl-num">${lv.number}</span> ${esc(lv.title)}</h2>
        <p class="muted">${esc(lv.subtitle)}</p>
        <div class="lessons">
          ${lv.lessons.map(ls => {
            const passed = ls.exercises.filter(e => e.passed).length;
            return `<a class="lesson${ls.done ? " done" : ""}${r.next && r.next.id === ls.id ? " next" : ""}" href="#/leccion/${encodeURIComponent(ls.id)}">
              <span class="state">${ls.done ? "✓" : passed ? `${passed}/${ls.exercises.length}` : "○"}</span>
              <span><b>${esc(ls.title)}</b><small class="muted">${ls.minutes} min · ${ls.exercises.length} ejercicio${ls.exercises.length === 1 ? "" : "s"}${(ls.chords || []).length ? " · " + ls.chords.join(", ") : ""}</small></span>
            </a>`;
          }).join("")}
        </div>
      </section>`).join("")}`;
}
