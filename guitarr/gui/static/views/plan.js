// Practice plan: daily minutes per category, time counted while you play, a timer for the
// rest, the week at a glance and a streak of days that met their goal.
import { lang, t } from "../lib/i18n.js";
import { $, $$, api, esc, toast } from "../lib/ui.js";
import { icon } from "../lib/icons.js";
import { catName, fmtClock, fmtDay, fmtHM, ring, weekStrip } from "../lib/plan.js";

let root = null, data = null, fetchedAt = 0, tick = 0, editing = null;

export async function mount(el) {
  root = el;
  editing = null;
  el.innerHTML = `<div class="gl-head"><h1>${esc(t("plan.title"))}</h1><p class="muted">${esc(t("plan.subtitle"))}</p>
    <a class="btn small" href="#/report">${esc(t("report_week.open"))}</a></div><div id="planBody"></div>
    <div id="planStats"></div>`;
  await load();
  renderStats($("#planStats", el));
  tick = setInterval(liveTick, 1000);
  window.addEventListener("guitarr:plan", onExternal);
}

// ------------------------------------------------------------------ consistency map and tempo over time
const LEVELS = [0, 1, 15, 30, 60];            // minutes: none, a little, 15+, 30+, 60+ (written in the legend)
const levelOf = m => LEVELS.findLastIndex(x => m >= x && (x > 0 || m === 0));

async function renderStats(box) {
  let s;
  try { s = await api("/api/stats"); } catch { return; }
  if (!box.isConnected) return;
  const days = s.days, first = new Date(days[0].date + "T00:00:00");
  const offset = (first.getDay() + 6) % 7;                 // weeks start on Monday
  const cell = 13, gap = 3, weeks = Math.ceil((days.length + offset) / 7);
  const fmt = d => new Date(d + "T00:00:00").toLocaleDateString(lang(), { day: "numeric", month: "short", year: "numeric" });
  const cells = days.map((d, i) => {
    const k = i + offset, x = Math.floor(k / 7) * (cell + gap), y = (k % 7) * (cell + gap);
    return `<rect class="hm l${levelOf(d.minutes)}" x="${x}" y="${y}" width="${cell}" height="${cell}" rx="2"><title>${esc(t("stats.day_minutes", { date: fmt(d.date), count: d.minutes }))}</title></rect>`;
  }).join("");
  const big = [["songs", s.totals.songs], ["sessions", s.totals.sessions], ["hours", (s.totals.minutes / 60).toFixed(1)], ["streak", s.totals.streak]];
  box.innerHTML = `
    <div class="stats-header">${big.map(([k, v]) => `<div class="stat-big"><b>${esc(String(v))}</b><small>${esc(t(`stats.big_${k}`))}</small></div>`).join("")}</div>
    <section class="panel stats-panel" aria-labelledby="hmTitle">
      <div class="sec-progress-head"><h2 id="hmTitle">${esc(t("stats.consistency"))}</h2>
        <span class="muted small">${esc(t("stats.totals", { days: s.totals.active_days, hours: (s.totals.minutes / 60).toFixed(1) }))}</span></div>
      <div class="hm-wrap"><svg class="heatmap" viewBox="0 0 ${weeks * (cell + gap)} ${7 * (cell + gap)}" role="img" aria-label="${esc(t("stats.consistency_label", { days: s.totals.active_days }))}">${cells}</svg></div>
      <p class="hm-legend small muted">${LEVELS.map((m, i) => `<span><i class="hm l${i}"></i> ${esc(i === 0 ? t("stats.none") : i === LEVELS.length - 1 ? `${m}+ min` : `${m}–${LEVELS[i + 1] - 1} min`)}</span>`).join("")}</p>
    </section>
    <section class="panel stats-panel" aria-labelledby="tcTitle">
      <h2 id="tcTitle">${esc(t("stats.tempo"))}</h2>
      ${s.tempo.length ? `<label class="field-inline small">${esc(t("stats.song"))}
        <select id="tcSong">${s.tempo.map((x, i) => `<option value="${i}">${esc(x.name)}</option>`).join("")}</select></label>
        <div id="tcChart"></div>` : `<p class="muted">${esc(t("stats.no_tempo"))}</p>`}
    </section>`;
  const sel = $("#tcSong", box);
  if (sel) {
    const draw = () => { $("#tcChart", box).innerHTML = tempoChart(s.tempo[+sel.value]); };
    sel.onchange = draw;
    draw();
  }
}

/** Speed (or BPM, when the song's tempo is known) per session, as a line with every point labeled. */
function tempoChart(song) {
  const pts = song.points, useBpm = pts.every(p => p.bpm);
  const val = p => useBpm ? p.bpm : p.speed;
  const W = 640, H = 200, pad = 34;
  const lo = Math.min(...pts.map(val)), hi = Math.max(...pts.map(val));
  const span = Math.max(1, hi - lo);
  const x = i => pts.length === 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (pts.length - 1);
  const y = v => H - pad - ((v - lo) / span) * (H - 2 * pad);
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(val(p)).toFixed(1)}`).join(" ");
  const unit = useBpm ? " BPM" : "%";
  return `<svg class="tempo-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("stats.tempo_label", { name: song.name, from: val(pts[0]) + unit, to: val(pts[pts.length - 1]) + unit }))}">
    <line class="axis" x1="${pad}" y1="${H - pad}" x2="${W - pad}" y2="${H - pad}"/>
    <path class="tline" d="${line}"/>
    ${pts.map((p, i) => `<circle class="tdot" cx="${x(i)}" cy="${y(val(p))}" r="4"><title>${esc(`${p.date}: ${val(p)}${unit}${p.score != null ? ` · ${Math.round(p.score)}%` : ""}`)}</title></circle>`).join("")}
    <text x="${x(0)}" y="${y(val(pts[0])) - 10}" text-anchor="middle" class="tlabel">${val(pts[0])}${unit}</text>
    ${pts.length > 1 ? `<text x="${x(pts.length - 1)}" y="${y(val(pts[pts.length - 1])) - 10}" text-anchor="middle" class="tlabel">${val(pts[pts.length - 1])}${unit}</text>` : ""}
    <text x="${pad}" y="${H - 10}" class="tlabel muted">${esc(pts[0].date)}</text>
    <text x="${W - pad}" y="${H - 10}" text-anchor="end" class="tlabel muted">${esc(pts[pts.length - 1].date)}</text>
  </svg>`;
}

export function unmount() {
  clearInterval(tick);
  window.removeEventListener("guitarr:plan", onExternal);
  root = null;
}

function onExternal(e) {
  if (!e.detail) return;
  data = e.detail; fetchedAt = performance.now();
  const typing = root && root.contains(document.activeElement) && document.activeElement.closest("#planEdit");
  if (!typing) render();                      // don't wipe what you're typing in the plan editor
}

async function load() {
  try { set(await api("/api/plan")); } catch (e) { toast(e.message); }
}
function set(v) {
  data = v; fetchedAt = performance.now();
  window.dispatchEvent(new CustomEvent("guitarr:plan-changed", { detail: v }));
  render();
}

/** Seconds the running timer has added since the last fetch. */
const extra = () => (data && data.timer && data.timer.running ? (performance.now() - fetchedAt) / 1000 : 0);

function render() {
  if (!root || !data) return;
  const body = $("#planBody", root);
  const w = data.week, td = data.today;
  const pct = w.goal ? (100 * w.minutes) / w.goal : 0;
  body.innerHTML = `
    <div class="panel plan-sum">
      ${ring(pct, w.estimate)}
      <dl class="facts">
        <div><dt>${esc(t("plan.week"))}</dt><dd>${esc(fmtDay(w.start))} – ${esc(fmtDay(w.end))}</dd></div>
        <div><dt>${esc(t("plan.done_so_far"))}</dt><dd><b id="weekMin">${fmtHM(w.minutes)}</b> ${esc(t("plan.of"))} ${fmtHM(w.goal)}</dd></div>
        <div><dt>${esc(t("plan.last_week"))}</dt><dd>${w.previous == null ? esc(t("plan.no_data")) : fmtHM(w.previous) + compare(w.minutes, w.previous)}</dd></div>
        <div><dt>${esc(t("plan.goal_streak"))}</dt><dd><span class="streak-pill">🔥 ${esc(t("common.days", { count: data.streak }))}</span></dd></div>
      </dl>
      <p class="muted small ring-note">${esc(w.estimate ? t("plan.estimate_" + w.estimate) : t("plan.estimate_none"))}</p>
    </div>
    ${weekStrip(w.days)}
    <div class="panel today-card ${td.status || ""}">
      <div class="row-between"><b>${esc(t("plan.today"))} · ${esc(fmtDay(td.date, { weekday: "long", day: "numeric", month: "long" }))}</b>
        <span><b id="todayMin">${fmtHM(td.minutes)}</b> ${esc(t("plan.of"))} ${fmtHM(td.goal)}</span></div>
      <div class="pbar"><i id="todayBar" style="width:${Math.min(100, td.goal ? 100 * td.minutes / td.goal : 0)}%"></i></div>
      <div id="todayNote">${todayNote(td)}</div>
    </div>
    <div class="cat-list">${data.categories.map(catCard).join("")}</div>
    ${editPanel()}`;
  bind();
}

function compare(now, prev) {
  if (prev == null) return "";
  const d = now - prev;
  if (!d) return ` <span class="muted">(=)</span>`;
  return ` <span class="${d > 0 ? "ok" : "muted"}">(${d > 0 ? "+" : "−"}${fmtHM(Math.abs(d))})</span>`;
}

function todayNote(td) {
  if (td.remaining === 0) return `<p class="note ok">✓ ${esc(t("plan.today_met"))}</p>`;
  if (td.minutes === 0) return `<p class="note muted">${esc(t("plan.today_start"))}</p>`;
  return `<p class="note warn">⚠ ${esc(t("plan.left_today", { left: fmtHM(td.remaining) }))}</p>`;
}

function catCard(c) {
  const tm = data.timer, mine = tm && tm.category === c.id, other = tm && !mine;
  const secs = c.today_s + (mine ? extra() : 0), goal = c.minutes * 60;
  const met = goal > 0 && Math.round(secs / 60) >= c.minutes;
  const state = mine ? (tm.running ? "running" : "paused") : "idle";
  const btn = (act, label, ico, dis = false) => `<button class="ib2" data-act="${act}" data-cat="${esc(c.id)}" ${dis ? "disabled" : ""} title="${esc(label)}" aria-label="${esc(label)}">${ico}</button>`;
  let controls;
  // a stopwatch, not a player: worded so nobody waits for a sound
  const timerBtn = (act, dis = false) => `<button class="btn small" data-act="${act}" data-cat="${esc(c.id)}" ${dis ? "disabled" : ""} title="${esc(t("plan.timer_hint"))}">⏱ ${esc(t(act === "start" ? "plan.timer_btn" : "plan.resume"))}</button>`;
  if (state === "running") controls = `<span class="clock mono" data-clock="${esc(c.id)}">${fmtClock(tm.elapsed + extra())}</span>${btn("pause", t("plan.pause"), "❚❚")}${btn("stop", t("plan.stop"), "■")}`;
  else if (state === "paused") controls = `<span class="muted small">${esc(t("plan.paused"))}</span>${timerBtn("resume")}${btn("stop", t("plan.stop"), "■")}`;
  else controls = timerBtn("start", !!other);
  return `<div class="panel cat ${state}${met ? " met" : ""}">
    <div class="cat-main">
      <b>${esc(catName(c))}</b>
      <small class="muted">${esc(c.minutes ? t("plan.goal_day", { goal: fmtHM(c.minutes) }) : t("plan.no_goal"))} · ${c.auto ? `${icon("headphones", 12)} ${esc(t(c.id === "free" ? "plan.auto_free" : "plan.auto"))}` : esc(t("plan.manual"))}${state === "paused" ? " · " + esc(t("plan.paused")) : ""}</small>
      ${state === "running" ? `<small class="muted">${esc(t("plan.timer_hint"))}</small>` : ""}
      <div class="pbar thin"><i data-bar="${esc(c.id)}" style="width:${goal ? Math.min(100, 100 * secs / goal) : 0}%"></i></div>
    </div>
    <div class="cat-side"><span class="cat-time"><b data-time="${esc(c.id)}">${fmtHM(Math.round(secs / 60))}</b>${c.minutes ? ` / ${fmtHM(c.minutes)}` : ""}</span>
      ${met ? `<span class="pill ok">✓ ${esc(t("plan.done"))}</span>` : ""}<div class="cat-ctl">${controls}</div></div>
  </div>`;
}

// ------------------------------------------------------------------ live clock
function liveTick() {
  if (!root || !data || !data.timer || !data.timer.running) return;
  const tm = data.timer, c = data.categories.find(x => x.id === tm.category);
  if (!c) return;
  const ex = extra(), secs = c.today_s + ex;
  const clock = $(`[data-clock="${CSS.escape(c.id)}"]`, root);
  if (clock) clock.textContent = fmtClock(tm.elapsed + ex);
  const tEl = $(`[data-time="${CSS.escape(c.id)}"]`, root);
  if (tEl) tEl.textContent = fmtHM(Math.round(secs / 60));
  const bar = $(`[data-bar="${CSS.escape(c.id)}"]`, root);
  if (bar && c.minutes) bar.style.width = Math.min(100, 100 * secs / (c.minutes * 60)) + "%";
  const todayMin = Math.round((data.today.minutes * 60 + ex) / 60);
  $("#todayMin", root).textContent = fmtHM(todayMin);
  if (data.today.goal) $("#todayBar", root).style.width = Math.min(100, 100 * todayMin / data.today.goal) + "%";
  // crossing a goal (the category's or the day's) re-renders with fresh numbers
  if ((c.minutes && Math.round(secs / 60) === c.minutes && Math.round(c.today_s / 60) < c.minutes) ||
      (data.today.remaining && todayMin >= data.today.goal)) load();
}

// ------------------------------------------------------------------ editing the plan
function hmFields(id, minutes) {
  return `<span class="hm"><input type="number" id="${id}H" min="0" value="${Math.floor(minutes / 60)}" aria-label="${esc(t("plan.hours"))}"><span>:</span>
    <input type="number" id="${id}M" min="0" max="59" value="${minutes % 60}" aria-label="${esc(t("plan.minutes"))}"></span>`;
}

/** Reads an h:mm pair; returns minutes or an error key. */
function readHM(id) {
  const h = $(`#${id}H`, root).value.trim(), m = $(`#${id}M`, root).value.trim();
  if (h === "" || m === "" || !/^-?\d+$/.test(h) || !/^-?\d+$/.test(m)) return { err: "whole" };
  if (+h < 0 || +m < 0) return { err: "negative_minutes" };
  if (+m > 59) return { err: "minutes_range" };
  return { min: +h * 60 + +m };
}

function editPanel() {
  const open = editing !== null;
  const daily = data.today.goal;
  return `<details class="panel plan-edit" id="planEdit" ${open ? "open" : ""}>
    <summary><b>${esc(t("plan.edit"))}</b></summary>
    <div class="edit-block">
      <h3>${esc(t("plan.weekly_goal"))}</h3>
      <div class="row left wrap">${hmFields("goal", daily * 7)}<span class="muted small" id="goalDaily">${esc(t("plan.daily_is", { goal: fmtHM(daily) }))}</span>
        <button class="btn small" id="goalSave">${esc(t("plan.save_goal"))}</button></div>
      <p class="field-err" id="goalErr"></p>
      <p class="muted small">${esc(t("plan.weekly_hint"))}</p>
    </div>
    <div class="edit-block">
      <h3>${esc(t("plan.categories"))}</h3>
      <div class="cat-rows">${data.categories.map(c => `<div class="cat-row" data-id="${esc(c.id)}">
        <span class="cname">${esc(catName(c))}${c.auto ? ` <small class="muted">· ${esc(t("plan.auto_short"))}</small>` : ""}</span>
        ${hmFields("m_" + c.id, c.minutes)}
        <span class="rm">${editing === c.id
          ? `<span class="muted small">${esc(t("plan.remove_q"))}</span> <button class="btn small danger" data-rm-yes="${esc(c.id)}">${esc(t("plan.yes"))}</button> <button class="btn small" data-rm-no>${esc(t("plan.no"))}</button>`
          : `<button class="btn small ghost" data-rm="${esc(c.id)}">${esc(t("plan.remove"))}</button>`}</span>
        <p class="field-err" id="err_${esc(c.id)}"></p></div>`).join("")}</div>
      <div class="row left wrap"><span class="muted small" id="sumNote">${esc(t("plan.sum", { goal: fmtHM(daily) }))}</span>
        <button class="btn small primary" id="catsSave">${esc(t("plan.save_changes"))}</button></div>
      <p class="field-err" id="catsErr"></p>
    </div>
    <div class="edit-block">
      <h3>${esc(t("plan.add"))}</h3>
      <div class="row left wrap"><input type="text" id="newName" maxlength="40" placeholder="${esc(t("plan.new_name"))}" aria-label="${esc(t("plan.new_name"))}">
        ${hmFields("new", 10)}<button class="btn small" id="newAdd">${esc(t("plan.add_btn"))}</button></div>
      <p class="field-err" id="newErr"></p>
    </div>
  </details>`;
}

const errText = code => t(`plan.err_${code}`, { defaultValue: t("errors.generic") });
const showErr = (id, code) => { const el = $("#" + id, root); if (el) el.textContent = code ? errText(code) : ""; };

function bind() {
  $$("[data-act]", root).forEach(b => b.onclick = () => timerAction(b.dataset.act, b.dataset.cat));
  const det = $("#planEdit", root);
  det.ontoggle = () => { if (det.open && editing === null) editing = ""; if (!det.open) editing = null; };
  // live sums while typing; an error clears when its field changes
  const recalc = () => {
    const g = readHM("goal");
    if (!g.err) $("#goalDaily", root).textContent = t("plan.daily_is", { goal: fmtHM(Math.ceil(g.min / 7)) });
    let sum = 0, ok = true;
    for (const c of data.categories) { const r = readHM("m_" + c.id); if (r.err) ok = false; else sum += r.min; }
    if (ok) $("#sumNote", root).textContent = t("plan.sum", { goal: fmtHM(sum) });
  };
  $$(".plan-edit input", root).forEach(inp => inp.addEventListener("input", () => {
    const row = inp.closest(".cat-row");
    if (row) showErr("err_" + row.dataset.id, null);
    if (inp.id.startsWith("goal")) showErr("goalErr", null);
    if (inp.id.startsWith("new")) showErr("newErr", null);
    showErr("catsErr", null);
    recalc();
  }));
  $("#goalSave", root).onclick = async () => {
    const g = readHM("goal");
    if (g.err) return showErr("goalErr", g.err);
    if (g.min === 0) return showErr("goalErr", "zero_goal");
    try { editing = ""; set(await api("/api/plan/goal", { method: "PUT", json: { weekly_minutes: g.min } })); toast(t("plan.saved"), true); }
    catch (e) { showErr("goalErr", codeOf(e)); }
  };
  $("#catsSave", root).onclick = async () => {
    const changes = [];
    let bad = false;
    for (const c of data.categories) {
      const r = readHM("m_" + c.id);
      if (r.err) { showErr("err_" + c.id, r.err); bad = true; }
      else if (r.min !== c.minutes) changes.push([c.id, r.min]);
    }
    if (bad || !changes.length) return;
    const total = data.categories.reduce((s, c) => s + (changes.find(x => x[0] === c.id) || [0, c.minutes])[1], 0);
    if (total === 0) return showErr("catsErr", "zero_goal");
    // raise first, then lower, so the plan never passes through a zero goal
    changes.sort((a, b) => b[1] - a[1]);
    try {
      let v = null;
      for (const [id, min] of changes) v = await api(`/api/plan/categories/${encodeURIComponent(id)}`, { method: "PUT", json: { minutes: min } });
      editing = ""; set(v); toast(t("plan.saved"), true);
    } catch (e) { showErr("catsErr", codeOf(e)); load(); }
  };
  $("#newAdd", root).onclick = async () => {
    const name = $("#newName", root).value.trim(), r = readHM("new");
    if (!name) return showErr("newErr", "empty_name");
    const taken = data.categories.some(c => norm(catName(c)) === norm(name));
    if (taken) return showErr("newErr", "duplicate_name");
    if (r.err) return showErr("newErr", r.err);
    try { editing = ""; set(await api("/api/plan/categories", { json: { name, minutes: r.min } })); toast(t("plan.added", { name }), true); }
    catch (e) { showErr("newErr", codeOf(e)); }
  };
  $$("[data-rm]", root).forEach(b => b.onclick = () => { editing = b.dataset.rm; render(); });
  $$("[data-rm-no]", root).forEach(b => b.onclick = () => { editing = ""; render(); });
  $$("[data-rm-yes]", root).forEach(b => b.onclick = async () => {
    const id = b.dataset.rmYes;
    try { editing = ""; set(await api(`/api/plan/categories/${encodeURIComponent(id)}`, { method: "DELETE" })); }
    catch (e) { editing = id; render(); showErr("err_" + id, codeOf(e)); }
  });
}

const norm = s => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").trim().toLowerCase().replace(/\s+/g, " ");
/** API errors carry a translated message; recover the code for field errors when possible. */
function codeOf(e) { return e.code || "generic"; }

async function timerAction(action, category) {
  try {
    const v = await api("/api/plan/timer", { json: { action, category } });
    set(v);
    if ((action === "pause" || action === "stop") && v.today.remaining > 0) toast(t("plan.left_today", { left: fmtHM(v.today.remaining) }));
  } catch (e) { toast(e.message); }
}

