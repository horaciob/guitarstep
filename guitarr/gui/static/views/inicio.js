// Inicio: tu nivel, racha, qué sigue y lo último que hiciste.
import { api, esc } from "../lib/ui.js";

const ago = iso => {
  const d = (Date.now() - new Date(iso)) / 1000;
  if (d < 90) return "recién";
  if (d < 3600) return `hace ${Math.round(d / 60)} min`;
  if (d < 86400) return `hace ${Math.round(d / 3600)} h`;
  return `hace ${Math.round(d / 86400)} d`;
};

export async function mount(el) {
  const [p, ruta, hist] = await Promise.all([api("/api/progreso"), api("/api/ruta"), api("/api/history").catch(() => [])]);
  const lv = p.level;
  let weak = null;
  if (hist.length) {
    try {
      const h = await api(`/api/history/${encodeURIComponent(hist[0].id)}`);
      if (h.problem_bars.length && h.song) weak = { h, bars: h.problem_bars.slice(0, 2).map(b => b.bar) };
    } catch { /* sin detalle */ }
  }
  const all = ruta.levels.flatMap(l => l.lessons);
  const week = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(); d.setDate(d.getDate() - (6 - i));
    const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    return { iso, on: p.days.includes(iso), label: "DLMMJVS"[d.getDay()] };
  });
  el.innerHTML = `
    <div class="gl-head"><h1>${p.practiced_today ? "¡Bien, hoy ya practicaste!" : "¿Tocamos un rato?"}</h1>
      <p class="muted">${p.streak ? `Llevás ${p.streak} ${p.streak === 1 ? "día" : "días"} seguidos.` : "Arrancá una racha: un ejercicio por día alcanza."}</p></div>
    <div class="dash">
      <div class="panel level-card">
        <small class="muted">Nivel ${lv.level}</small><h2>${esc(lv.title)}</h2>
        <div class="xpbar"><i style="width:${Math.round(lv.progress * 100)}%"></i></div>
        <div class="muted small">${p.xp} XP${lv.next_xp ? ` · faltan ${lv.next_xp - p.xp} para el nivel ${lv.level + 1}` : " · nivel máximo"}</div>
      </div>
      <div class="panel">
        <small class="muted">Racha</small><h2>🔥 ${p.streak} ${p.streak === 1 ? "día" : "días"}</h2>
        <div class="week">${week.map(d => `<span class="${d.on ? "on" : ""}" title="${d.iso}"><i></i>${d.label}</span>`).join("")}</div>
      </div>
      <div class="panel">
        <small class="muted">Ruta</small><h2>${p.lessons.length}/${all.length} lecciones</h2>
        <div class="muted small">${Object.keys(p.chords).length} acordes dominados · ${Object.keys(p.drills).length} récords de cambio</div>
      </div>
    </div>
    <div class="dash two">
      <div class="stack">
        ${ruta.next ? `<a class="callout" href="#/leccion/${encodeURIComponent(ruta.next.id)}"><span>Siguiente lección: <b>${esc(ruta.next.title)}</b></span><span class="btn small primary">Seguir →</span></a>` : ""}
        ${weak ? `<a class="callout" href="#/historial"><span>En <b>${esc(weak.h.reference.name || weak.h.id)}</b> te cuestan los compases <b>${weak.bars.join(" y ")}</b>.</span><span class="btn small">Ver</span></a>` : ""}
        <div class="quick">
          <a class="panel" href="#/cancionero"><b>♫ Tocar un cifrado</b><span class="muted small">con metrónomo y escucha</span></a>
          <a class="panel" href="#/herramientas?t=minuto"><b>⏱ Minuto de cambio</b><span class="muted small">destrabá un cambio de acordes</span></a>
          <a class="panel" href="#/acordes"><b>▦ Comprobar acordes</b><span class="muted small">rasgueá y te digo si salió</span></a>
          <a class="panel" href="#/afinador"><b>◎ Afinar</b><span class="muted small">antes de empezar</span></a>
        </div>
      </div>
      <div class="panel"><h2>Lo último</h2>
        ${p.events.length ? `<ul class="events">${p.events.slice(0, 8).map(e => `<li><span>${esc(e.text)}</span><span class="muted small">${e.xp ? `+${e.xp} XP · ` : ""}${ago(e.at)}</span></li>`).join("")}</ul>`
          : `<p class="muted">Todavía nada. Empezá por la <a href="#/ruta">ruta</a>.</p>`}
      </div>
    </div>`;
}
