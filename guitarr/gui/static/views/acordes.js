// Diccionario de acordes: diagramas, sonido y "comprobar con el oído".
import { $, $$, api, bindChordSvg, chordSvg, esc, strum, toast } from "../lib/ui.js";
import { listen } from "../lib/listen.js";

let task = null;

export async function mount(el, { params }) {
  const data = await api("/api/acordes");
  let group = params.grupo || "todos", q = "";
  el.innerHTML = `
    <div class="gl-head"><h1>Acordes</h1>
      <p class="muted">Tocá cada cuerda del diagrama para escucharla. Con <b>Comprobar</b> te escucha rasguearlo y te dice qué nota faltó.</p></div>
    <div class="toolbar">
      <div class="seg" id="groups"></div>
      <input type="search" id="q" placeholder="Buscar (Am, cejilla, 7…)" aria-label="Buscar acorde">
    </div>
    <div class="chord-grid" id="grid"></div>`;
  const groups = [{ id: "todos", name: "Todos" }, ...data.groups];
  $("#groups", el).innerHTML = groups.map(g => `<button data-g="${g.id}">${esc(g.name)}</button>`).join("");

  const render = () => {
    $$("#groups button", el).forEach(b => b.classList.toggle("active", b.dataset.g === group));
    const list = data.chords.filter(c => (group === "todos" || c.group === group) &&
      (!q || (c.id + " " + c.name + " " + c.group).toLowerCase().includes(q)));
    $("#grid", el).innerHTML = list.map(c => {
      const m = data.mastered[c.id] || {};
      const badges = (m.oido ? `<span class="pill ok" title="Dominado por oído">🎧</span>` : "") +
                     (m.camara ? `<span class="pill ok" title="Dominado con la cámara">◉</span>` : "");
      return `<article class="chord-card${m.oido || m.camara ? " mastered" : ""}" data-id="${esc(c.id)}">
        <header><b>${esc(c.id)}</b><span class="muted">${esc(c.name)}</span>${badges}</header>
        <div class="diagram">${chordSvg(c, { size: 112 })}</div>
        <div class="chord-notes muted">${c.notes.join(" · ")}</div>
        <p class="chord-tip">${esc(c.note)}</p>
        <div class="row">
          <button class="btn small" data-act="strum" title="Escuchar cómo suena" aria-label="Escuchar ${esc(c.id)}">▶</button>
          <button class="btn small primary" data-act="check">🎧 Comprobar</button>
          <a class="btn small" href="#/camara?acorde=${encodeURIComponent(c.id)}" title="Revisar la postura con la cámara">◉ Postura</a>
        </div>
        <div class="check-status muted" aria-live="polite"></div>
      </article>`;
    }).join("") || `<p class="muted">No hay acordes que coincidan.</p>`;
    $$(".chord-card", el).forEach(card => {
      const ch = data.chords.find(c => c.id === card.dataset.id);
      bindChordSvg(card, ch);
      $("[data-act=strum]", card).onclick = () => strum(ch);
      $("[data-act=check]", card).onclick = () => check(card, ch, data);
    });
  };
  $$("#groups button", el).forEach(b => b.onclick = () => { group = b.dataset.g; render(); });
  $("#q", el).oninput = e => { q = e.target.value.trim().toLowerCase(); render(); };
  render();
}

async function check(card, ch, data) {
  if (task) return toast("Ya estoy escuchando otro acorde");
  const st = $(".check-status", card), btn = $("[data-act=check]", card);
  btn.disabled = true;
  st.className = "check-status";
  st.innerHTML = `<span class="spinner"></span> Rasgueá <b>${esc(ch.id)}</b>…`;
  task = listen({ acorde: ch.id, mode: "wait", legato: false }, {
    timeoutS: 25,
    onMessage: m => { if (m.startsWith("✗")) st.innerHTML = `${esc(m.replace(/^✗\s*/, ""))} — <b>probá de nuevo</b>`; },
  });
  try {
    const rep = await task.done;
    const ok = rep.award && rep.award.passed;
    st.className = "check-status " + (ok ? "ok" : "err");
    st.textContent = ok ? `✓ ¡Sonó ${ch.id}!${rep.award.xp ? ` +${rep.award.xp} XP` : ""}` :
      `No escuché ${ch.id}. Revisá la entrada en Ajustes y probá de nuevo.`;
    if (ok) {
      data.mastered[ch.id] = { ...(data.mastered[ch.id] || {}), oido: true };
      card.classList.add("mastered");
    }
  } catch (e) {
    st.className = "check-status err";
    st.textContent = e.message;
  } finally {
    task = null;
    btn.disabled = false;
  }
}

export function unmount() {
  if (task) { task.stop(); task = null; }
}
