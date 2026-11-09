// Stage mode: one song at a time on the whole screen, big chords, auto-scroll at ten speeds, a click at the
// song's tempo and what comes next. Arrows, PageUp/PageDown (most foot pedals send these) change song.
import { t, tc } from "../lib/i18n.js";
import { $, api, audioCtx, click, esc } from "../lib/ui.js";
import { barsHtml, strumHtml } from "./charts.js";
import { chipsHtml } from "../lib/chips.js";

const SIZE_KEY = "guitarr.stage.size";
let root = null, keys = null, scroller = 0, metro = null;

const loadSize = () => { try { return +localStorage.getItem(SIZE_KEY) || 1; } catch { return 1; } };
const saveSize = v => { try { localStorage.setItem(SIZE_KEY, String(v)); } catch { /* a convenience only */ } };

export async function mount(el, { params = {} }) {
  root = el;
  let items = [], listName = "";
  if (params.setlist) {
    try { const s = await api(`/api/setlists/${encodeURIComponent(params.setlist)}`); items = s.items; listName = s.name; }
    catch { items = []; }
  } else if (params.chart) items = [{ kind: "chart", id: params.chart }];
  else if (params.song) items = [{ kind: "song", id: params.song }];
  if (!items.length) { el.innerHTML = `<div class="gl-head"><h1>${esc(t("stage.nothing"))}</h1></div><a class="btn" href="#/setlists">${esc(t("setlists.title"))}</a>`; return; }
  const state = { i: Math.min(+params.i || 0, items.length - 1), size: loadSize(), speed: 0, click: false };
  const back = params.setlist ? `#/setlists?id=${encodeURIComponent(params.setlist)}` : params.chart ? `#/chart/${encodeURIComponent(params.chart)}` : "#/practice";

  const title = async it => {
    if (it.kind === "chart") { try { const { chart } = await api(`/api/charts/${encodeURIComponent(it.id)}`); return tc(`charts.${chart.id}.title`, chart.title); } catch { return it.id; } }
    return it.id;
  };
  const show = async () => {
    stopScroll(); stopClick();
    const it = items[state.i];
    let body = "", chips = "", bpm = null;
    if (it.kind === "chart") {
      try {
        const { chart } = await api(`/api/charts/${encodeURIComponent(it.id)}`);
        bpm = chart.bpm;
        chips = chipsHtml({ tuning: chart.tuning, bpm: chart.bpm, time: `${chart.beats_per_bar}/4`, capo: chart.capo, swing: chart.swing });
        body = `<h1 class="stage-title">${esc(tc(`charts.${chart.id}.title`, chart.title))}</h1>${chips}${strumHtml(chart.strum)}<div class="stage-bars">${barsHtml(chart)}</div>`;
      } catch (e) { body = `<p class="err">${esc(e.message)}</p>`; }
    } else {
      try {
        const f = await api(`/api/songs/${encodeURIComponent(it.id)}/facts`);
        bpm = f.bpm;
        body = `<h1 class="stage-title">${esc(f.title)}</h1>${chipsHtml({ tuning: f.tuning, key: f.key, bpm: f.bpm, time: f.time, capo: f.capo })}
          <ol class="stage-sections">${f.sections.map(s => `<li><b>${esc(s.name)}</b> <small>${esc(t("sections.bars", { from: s.from, to: s.to }))}</small></li>`).join("")}</ol>`;
      } catch (e) { body = `<p class="err">${esc(e.message)}</p>`; }
    }
    const next = items[state.i + 1];
    el.innerHTML = `
      <div class="stage-mode" style="--stage-size:${state.size}">
        <div class="stage-top"><a class="btn small" href="${esc(back)}">✕ ${esc(t("stage.exit"))}</a>
          <span class="muted small">${esc(listName)} ${esc(t("stage.n_of", { n: state.i + 1, total: items.length }))}</span>
          <span class="row left"><button class="btn small" data-a="smaller" aria-label="${esc(t("stage.smaller"))}">A−</button>
            <button class="btn small" data-a="bigger" aria-label="${esc(t("stage.bigger"))}">A+</button>
            <button class="btn small${state.click ? " primary" : ""}" data-a="click" aria-pressed="${state.click}" ${bpm ? "" : "disabled"}>♩ ${esc(t("stage.click", { bpm: bpm ? Math.round(bpm) : "—" }))}</button>
            <a class="btn small" href="#/tuner">${esc(t("stage.tune"))}</a></span></div>
        <div class="stage-body" id="stageBody" tabindex="-1">${body}</div>
        <div class="stage-foot">
          <button class="btn" data-a="prev" ${state.i === 0 ? "disabled" : ""}>← ${esc(t("stage.prev"))}</button>
          <label class="stage-speed small">${esc(t("stage.scroll"))} <input type="range" min="0" max="10" value="${state.speed}" id="speed" aria-valuetext="${state.speed ? state.speed : esc(t("stage.off"))}"> <b id="speedV">${state.speed || esc(t("stage.off"))}</b></label>
          <span class="stage-next">${next ? `${esc(t("stage.up_next"))}: <b id="nextTitle">…</b>` : esc(t("stage.last"))}</span>
          <button class="btn" data-a="next" ${next ? "" : "disabled"}>${esc(t("stage.next"))} →</button>
        </div>
        <p class="kbd-hint muted small center">${t("stage.keys_html")}</p>
      </div>`;
    if (next) title(next).then(x => { const n = $("#nextTitle", el); if (n) n.textContent = x; });
    el.querySelectorAll("[data-a]").forEach(b => b.onclick = () => act(b.dataset.a));
    $("#speed", el).oninput = e => setSpeed(+e.target.value);
    if (state.speed) setSpeed(state.speed);
    metroBpm = bpm;
    if (state.click) { state.click = false; toggleClick(); }        // the click follows you to the next song's tempo
    $("#stageBody", el).focus();
  };
  let metroBpm = null;
  const setSpeed = v => {
    state.speed = Math.max(0, Math.min(10, v));
    const s = $("#speed", el), out = $("#speedV", el);
    if (s) s.value = state.speed;
    if (out) out.textContent = state.speed || t("stage.off");
    stopScroll();
    if (!state.speed) return;
    const box = $("#stageBody", el);
    let last = performance.now();
    const step = now => {                           // pixels per second grow with the speed (1 slow … 10 fast)
      const dt = (now - last) / 1000; last = now;
      if (box) box.scrollTop += dt * state.speed * 9;
      scroller = requestAnimationFrame(step);
    };
    scroller = requestAnimationFrame(step);
  };
  const toggleClick = () => {
    if (!metroBpm) return;
    state.click = !state.click;
    stopClick();
    if (state.click) {
      const ac = audioCtx();
      let next = ac.currentTime + 0.1, n = 0;
      metro = setInterval(() => { while (next < ac.currentTime + 0.12) { click(next, n % 4 === 0); next += 60 / metroBpm; n++; } }, 25);
    }
    const b = el.querySelector('[data-a="click"]');
    if (b) { b.classList.toggle("primary", state.click); b.setAttribute("aria-pressed", state.click); }
  };
  const act = a => {
    if (a === "prev" && state.i > 0) { state.i--; show(); }
    else if (a === "next" && state.i < items.length - 1) { state.i++; show(); }
    else if (a === "bigger" || a === "smaller") {
      state.size = Math.max(0.6, Math.min(2.4, +(state.size + (a === "bigger" ? 0.2 : -0.2)).toFixed(1)));
      saveSize(state.size);
      el.querySelector(".stage-mode").style.setProperty("--stage-size", state.size);
    } else if (a === "click") toggleClick();
  };
  keys = e => {
    if (e.target.closest("input, select, textarea")) return;
    const k = e.key;
    if (k === "ArrowRight" || k === "PageDown") { e.preventDefault(); act("next"); }
    else if (k === "ArrowLeft" || k === "PageUp") { e.preventDefault(); act("prev"); }
    else if (k === " ") { e.preventDefault(); setSpeed(state.speed ? 0 : 4); }
    else if (k === "ArrowUp") { e.preventDefault(); setSpeed(state.speed + 1); }
    else if (k === "ArrowDown") { e.preventDefault(); setSpeed(state.speed - 1); }
    else if (k === "+" || k === "=") act("bigger");
    else if (k === "-") act("smaller");
    else if (k === "m" || k === "M") toggleClick();
    else if (k === "Escape") location.hash = back;
  };
  document.addEventListener("keydown", keys);
  show();
}

function stopScroll() { cancelAnimationFrame(scroller); scroller = 0; }
function stopClick() { clearInterval(metro); metro = null; }

export function unmount() {
  stopScroll(); stopClick();
  if (keys) document.removeEventListener("keydown", keys);
  keys = null; root = null;
}
