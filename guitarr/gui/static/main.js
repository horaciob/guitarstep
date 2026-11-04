// Router por hash y barra lateral (progreso + entrada de audio).
import { LISTENER_ROUTES, showListenerView, hideListenerViews } from "./app.js";
import { $, $$, api, esc } from "./lib/ui.js";

const VIEWS = {
  inicio: () => import("./views/inicio.js"),
  ruta: () => import("./views/ruta.js"),
  leccion: () => import("./views/leccion.js"),
  acordes: () => import("./views/acordes.js"),
  cancionero: () => import("./views/cancionero.js"),
  cifrado: () => import("./views/cifrado.js"),
  herramientas: () => import("./views/herramientas.js"),
  camara: () => import("./views/camara.js"),
};
const NAV_OF = { leccion: "ruta", cifrado: "cancionero" };
const view = $("#view");
let current = null;   // módulo montado (para desmontarlo al salir)
let seq = 0;

function parse() {
  const [path, qs] = (location.hash || "#/inicio").slice(1).split("?");
  const segs = path.split("/").filter(Boolean);
  return { name: segs[0] || "inicio", segs: segs.slice(1), params: Object.fromEntries(new URLSearchParams(qs || "")) };
}

async function route() {
  const { name, segs, params } = parse();
  const my = ++seq;
  $$("#nav a").forEach(a => a.classList.toggle("active", a.dataset.route === (NAV_OF[name] || name)));
  if (current && current.unmount) { try { current.unmount(); } catch (e) { console.error(e); } }
  current = null;
  view.innerHTML = "";
  window.scrollTo(0, 0);
  if (LISTENER_ROUTES.includes(name)) {
    view.hidden = true;
    showListenerView(name, params);
    return;
  }
  hideListenerViews();
  view.hidden = false;
  const load = VIEWS[name];
  if (!load) { location.hash = "#/inicio"; return; }
  const mod = await load();
  if (my !== seq) return;           // navegaste a otra parte mientras cargaba
  current = mod;
  await mod.mount(view, { segs, params });
}

async function refreshProgress() {
  try {
    const p = await api("/api/progreso");
    const lv = p.level;
    $("#railProgress").innerHTML = `<b>Nivel ${lv.level}</b> · ${esc(lv.title)}
      <div class="bar"><i style="width:${Math.round(lv.progress * 100)}%"></i></div>
      <span class="muted">${p.xp} XP · 🔥 ${p.streak} ${p.streak === 1 ? "día" : "días"}${p.practiced_today ? " ✓" : ""}</span>`;
  } catch { /* sin servidor */ }
}

window.addEventListener("hashchange", route);
window.addEventListener("guitarr:progreso", refreshProgress);
refreshProgress();
route();
