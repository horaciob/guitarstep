// Hash router, sidebar (progress + audio input) and language switcher.
import { applyDom, initI18n, lang, LANGS, setLang, t } from "./lib/i18n.js";

await initI18n();
applyDom();

const { LISTENER_ROUTES, showListenerView, hideListenerViews } = await import("./app.js");
const { $, $$, api, esc, isOnboarded, toast } = await import("./lib/ui.js");
const { fillIcons } = await import("./lib/icons.js");
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
  rig: () => import("./views/rig.js"),
  plan: () => import("./views/plan.js"),
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

// The tone rig keeps playing across pages: show it in the sidebar with an off switch.
// Its engine is only loaded when you open the rig page (or something else needs it).
let rig = null;
window.addEventListener("guitarr:rig-ready", e => {
  if (rig) return;
  rig = e.detail;
  rig.addEventListener("change", refreshRigPill);
  refreshRigPill();
});
function refreshRigPill() {
  const pill = $("#rigPill");
  pill.hidden = !rig.running;
  if (!rig.running) return;
  const p = rig.preset;
  $("#rigPillName").textContent = t("rig.pill", { name: p ? (p.kind === "factory" ? t(`rig.preset.${p.id}`) : p.name) : t("rig.custom") });
}
$("#rigPillOff").title = t("rig.turn_off");
$("#rigPillOff").setAttribute("aria-label", t("rig.turn_off"));
$("#rigPillOff").onclick = () => rig && rig.stop();

// Practice plan: today's minutes in the sidebar, the running timer (kept alive with a
// heartbeat while any page is open) and a nudge after each session.
const { catName, fmtClock, fmtHM } = await import("./lib/plan.js");
let plan = null, planAt = 0, beat = null;
function showPlan(v) {
  plan = v; planAt = performance.now();
  const td = v.today, el = $("#railToday");
  el.hidden = false;
  el.innerHTML = `<span>${esc(t("plan.rail_today"))} <b>${fmtHM(td.minutes)}</b> / ${fmtHM(td.goal)}${td.remaining === 0 ? " ✓" : ""}</span>
    <div class="bar"><i class="${td.status || ""}" style="width:${td.goal ? Math.min(100, 100 * td.minutes / td.goal) : 0}%"></i></div>`;
  const tm = v.timer, pill = $("#timerPill");
  pill.hidden = !tm;
  if (tm) {
    const c = v.categories.find(x => x.id === tm.category);
    pill.classList.toggle("paused", !tm.running);
    $("#timerPillPause").textContent = tm.running ? "❚❚" : "▶";
    $("#timerPillPause").title = t(tm.running ? "plan.pause" : "plan.resume");
    $("#timerPillPause").setAttribute("aria-label", $("#timerPillPause").title);
    pill.dataset.name = c ? catName(c) : "";
    paintTimer();
  }
  clearInterval(beat); beat = null;
  if (tm && tm.running) beat = setInterval(async () => {
    try { const r = await api("/api/plan/timer", { json: { action: "beat" } }); showPlan(r); window.dispatchEvent(new CustomEvent("guitarr:plan", { detail: r })); }
    catch { /* offline: the server pauses the timer by itself */ }
  }, 20000);
}
function paintTimer() {
  const tm = plan && plan.timer;
  if (!tm) return;
  const secs = tm.elapsed + (tm.running ? (performance.now() - planAt) / 1000 : 0);
  $("#timerPillName").textContent = `⏱ ${$("#timerPill").dataset.name} · ${tm.running ? fmtClock(secs) : t("plan.paused")}`;
}
setInterval(paintTimer, 1000);
$("#timerPillPause").onclick = async () => {
  try {
    const r = await api("/api/plan/timer", { json: { action: plan.timer.running ? "pause" : "resume" } });
    showPlan(r); window.dispatchEvent(new CustomEvent("guitarr:plan", { detail: r }));
  } catch (e) { toast(e.message); }
};
async function refreshPlan(afterSession = false) {
  const before = plan && plan.today;
  try {
    const v = await api("/api/plan");
    showPlan(v);
    window.dispatchEvent(new CustomEvent("guitarr:plan", { detail: v }));
    const td = v.today;
    if (afterSession && before && td.minutes > before.minutes) {
      if (td.remaining === 0 && before.remaining > 0) toast(t("plan.goal_met_toast"), true);
      else if (td.remaining > 0) toast(t("plan.left_today", { left: fmtHM(td.remaining) }));
    }
  } catch { /* no server */ }
}
window.addEventListener("guitarr:plan-changed", e => showPlan(e.detail));
window.addEventListener("guitarr:progress", () => refreshPlan(true));
refreshPlan();

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
