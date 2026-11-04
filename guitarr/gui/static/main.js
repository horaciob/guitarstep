// Hash router, sidebar (progress + audio input) and language switcher.
import { applyDom, initI18n, lang, LANGS, setLang, t } from "./lib/i18n.js";

await initI18n();
applyDom();

const { LISTENER_ROUTES, showListenerView, hideListenerViews } = await import("./app.js");
const { $, $$, api, esc } = await import("./lib/ui.js");
const { fillIcons } = await import("./lib/icons.js");
const { isOnboarded } = await import("./views/setup.js");
fillIcons();

const VIEWS = {
  home: () => import("./views/home.js"),
  course: () => import("./views/course.js"),
  lesson: () => import("./views/lesson.js"),
  chords: () => import("./views/chords.js"),
  charts: () => import("./views/charts.js"),
  chart: () => import("./views/chart.js"),
  tools: () => import("./views/tools.js"),
  camera: () => import("./views/camera.js"),
  setup: () => import("./views/setup.js"),
};
const NAV_OF = { lesson: "course", chart: "charts", camera: "chords", setup: "settings" };
const view = $("#view");
let current = null;   // mounted module (to unmount it when leaving)
let seq = 0;

function parse() {
  const [path, qs] = (location.hash || "#/home").slice(1).split("?");
  const segs = path.split("/").filter(Boolean);
  return { name: segs[0] || "home", segs: segs.slice(1), params: Object.fromEntries(new URLSearchParams(qs || "")) };
}

async function route() {
  const { name, segs, params } = parse();
  const my = ++seq;
  $$("[data-route]").forEach(a => a.classList.toggle("active", a.dataset.route === (NAV_OF[name] || name)));
  document.body.classList.toggle("is-setup", name === "setup");
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
  if (!load) { location.hash = "#/home"; return; }
  const mod = await load();
  if (my !== seq) return;           // you navigated elsewhere while it was loading
  current = mod;
  await mod.mount(view, { segs, params });
}

async function refreshProgress() {
  try {
    const p = await api("/api/progress");
    const lv = p.level;
    $("#railProgress").innerHTML = `<b>${esc(t("level.label", { n: lv.level }))}</b> · ${esc(t(`level.title_${lv.level}`))}
      <div class="bar"><i style="width:${Math.round(lv.progress * 100)}%"></i></div>
      <span class="muted">${p.xp} XP · 🔥 ${esc(t("common.days", { count: p.streak }))}${p.practiced_today ? " ✓" : ""}</span>`;
  } catch { /* no server */ }
}

const sel = $("#langSelect");
sel.innerHTML = Object.entries(LANGS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
sel.value = lang();
sel.onchange = () => setLang(sel.value);

window.addEventListener("hashchange", route);
window.addEventListener("guitarr:progress", refreshProgress);
refreshProgress();

// First run: nothing configured yet → the setup wizard instead of an empty dashboard.
try {
  const cfg = await api("/api/config");
  const { name } = parse();
  if (!isOnboarded() && cfg.saved.device == null && name === "home") history.replaceState(null, "", "#/setup");
} catch { /* no server */ }
route();
