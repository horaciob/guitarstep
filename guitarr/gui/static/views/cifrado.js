// Editor de cifrados (formato de texto propio) con vista previa en vivo.
import { $, api, esc, toast } from "../lib/ui.js";
import { barsHtml, strumHtml } from "./cancionero.js";

const TEMPLATE = `titulo: Mi cifrado
bpm: 80
compas: 4/4
rasgueo: D.DU.UDU
nota: Un consejo para vos mismo.

[Verso]
G | D | Em | C
G | D | C G | D
`;

export async function mount(el, { segs }) {
  const id = segs[0] && segs[0] !== "nuevo" ? decodeURIComponent(segs[0]) : null;
  let text = TEMPLATE, mine = false;
  if (id) {
    const c = await api(`/api/cifrados/${encodeURIComponent(id)}`);
    text = c.text; mine = c.mine;
  }
  el.innerHTML = `
    <div class="gl-head"><h1>${id ? (mine ? "Editar cifrado" : "Duplicar cifrado") : "Nuevo cifrado"}</h1>
      <p class="muted">Una línea por grupo de compases, separados con <code>|</code>. Dos acordes en un compás: <code>C G</code>. <code>%</code> repite el anterior, <code>-</code> es un compás sin tocar.</p></div>
    <div class="editor">
      <div class="panel">
        <textarea id="txt" spellcheck="false" rows="18" aria-label="Cifrado">${esc(text)}</textarea>
        <div class="row" style="margin-top:12px">
          <button class="btn primary" id="save">Guardar</button>
          ${mine ? `<button class="btn" id="del">Borrar</button>` : ""}
          <a class="btn" href="#/cancionero">Volver</a>
        </div>
        <details class="muted small" style="margin-top:12px"><summary>Encabezados posibles</summary>
          <p><code>titulo</code>, <code>bpm</code>, <code>compas</code> (4/4, 3/4, 6/8), <code>capo</code>, <code>rasgueo</code> (D abajo, U arriba, . nada; una casilla por corchea), <code>nivel</code>, <code>nota</code>. Las secciones van entre corchetes: <code>[Estribillo]</code>.</p></details>
      </div>
      <div class="panel" id="preview"></div>
    </div>`;
  const txt = $("#txt", el), pv = $("#preview", el);
  let timer;
  const validate = async () => {
    const r = await api("/api/cifrados/validar", { json: { text: txt.value } });
    if (!r.chart) { pv.innerHTML = `<p class="err">⚠️ ${esc(r.error)}</p>`; return r; }
    const c = r.chart;
    pv.innerHTML = `<h2>${esc(c.title)}</h2><p class="muted small">♩=${c.bpm} · ${c.beats_per_bar}/4${c.capo ? ` · capo ${c.capo}` : ""}</p>
      ${r.error ? `<p class="err">⚠️ ${esc(r.error)} — mirá los nombres en <a href="#/acordes">Acordes</a>.</p>` : ""}
      ${strumHtml(c.strum)}${barsHtml(c)}`;
    return r;
  };
  txt.oninput = () => { clearTimeout(timer); timer = setTimeout(validate, 300); };
  validate();
  $("#save", el).onclick = async () => {
    try {
      const r = await api("/api/cifrados", { json: { text: txt.value, id: mine ? id : null } });
      toast(`Guardado: ${r.title}`, true);
      location.hash = "#/cancionero";
    } catch (e) { toast(e.message); }
  };
  const del = $("#del", el);
  if (del) del.onclick = async () => {
    if (!del.dataset.sure) {  // segundo clic para confirmar (sin diálogos del navegador)
      del.dataset.sure = "1";
      del.textContent = "¿Seguro? Tocá de nuevo para borrar";
      setTimeout(() => { delete del.dataset.sure; del.textContent = "Borrar"; }, 4000);
      return;
    }
    try {
      await api(`/api/cifrados/${encodeURIComponent(id)}`, { method: "DELETE" });
      toast("Cifrado borrado", true);
      location.hash = "#/cancionero";
    } catch (e) { toast(e.message); }
  };
}
