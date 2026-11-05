// First-run setup: pick the guitar input (with a live level meter), tune, and start playing.
import { t, tc } from "../lib/i18n.js";
import { $, $$, api, esc, instrument, markOnboarded, noteName, toast } from "../lib/ui.js";
import { icon } from "../lib/icons.js";
import { levelVerdict, meterHtml, openInput, setMeter } from "../lib/input.js";

// open strings of your tuning, lowest first: [midi, string number, name]
const openStrings = () => instrument.strings.map((m, i) => [m, i + 1, noteName(m)]).reverse();
const STEPS = ["welcome", "input", "tune", "done"];


let input = null, retry = null;

export async function mount(el, { params }) {
  const [dv, cfg, course] = await Promise.all([
    api("/api/devices").catch(() => ({ inputs: [], outputs: [] })), api("/api/config"), api("/api/course")]);
  const firstLesson = course.levels[0] && course.levels[0].lessons[0];
  const st = {
    step: STEPS.includes(params.step) ? params.step : "welcome",
    device: cfg.saved.device ?? dv.suggested ?? (dv.inputs[0] && dv.inputs[0].index),
    channel: cfg.saved.channel || 1,
    tuned: new Set(),
  };
  if (typeof st.device === "string") st.device = (dv.inputs.find(d => d.name === st.device) || {}).index ?? st.device;

  const frame = body => {
    const i = STEPS.indexOf(st.step);
    el.innerHTML = `<div class="setup">
      <ol class="steps">${STEPS.map((s, k) => `<li class="${k < i ? "done" : k === i ? "on" : ""}"><span>${k < i ? icon("check", 14) : k + 1}</span>${esc(t(`setup.step_${s}`))}</li>`).join("")}</ol>
      <div class="panel setup-card">${body}</div></div>`;
  };
  const go = step => { close(); st.step = step; render(); };

  function render() {
    if (st.step === "welcome") return welcome();
    if (st.step === "input") return pickInput();
    if (st.step === "tune") return tune();
    return done();
  }

  function welcome() {
    frame(`<h1>${esc(t("setup.welcome_title"))}</h1>
      <p class="lead">${esc(t("setup.welcome_lead"))}</p>
      <ul class="setup-list">
        <li>${icon("plug")}<span>${esc(t("setup.welcome_1"))}</span></li>
        <li>${icon("tuner")}<span>${esc(t("setup.welcome_2"))}</span></li>
        <li>${icon("play")}<span>${esc(t("setup.welcome_3"))}</span></li>
      </ul>
      <div class="setup-actions"><button class="btn ghost" id="skip">${esc(t("setup.skip_all"))}</button>
        <button class="btn primary" id="next">${esc(t("setup.lets_go"))} →</button></div>`);
    $("#next", el).onclick = () => go("input");
    $("#skip", el).onclick = () => { markOnboarded(); location.hash = "#/home"; };
  }

  function pickInput() {
    const devs = dv.inputs;
    const cur = devs.find(d => d.index === st.device);
    const nch = Math.min(cur ? cur.channels : 1, 8);
    if (st.channel > nch) st.channel = 1;
    frame(`<h1>${esc(t("setup.input_title"))}</h1>
      <p class="lead">${esc(t("setup.input_lead"))}</p>
      ${devs.length ? `<div class="dev-list" role="radiogroup" aria-label="${esc(t("settings.input"))}">${devs.map(d => {
        const builtin = d.index !== dv.suggested && /micro|built-in|integrad|internal/i.test(d.name);
        return `<button class="dev${d.index === st.device ? " on" : ""}" role="radio" aria-checked="${d.index === st.device}" data-i="${d.index}">
          ${icon(builtin ? "mic" : "plug", 20)}<span><b>${esc(d.name)}</b><small class="muted">${esc(t("settings.n_channels", { count: d.channels }))}${builtin ? " · " + esc(t("setup.builtin_hint")) : ""}</small></span>
          ${d.index === dv.suggested ? `<em class="pill ok">${esc(t("setup.recommended"))}</em>` : ""}</button>`;
      }).join("")}</div>` : `<p class="callout">${esc(t("setup.no_inputs"))}</p>`}
      ${nch > 1 ? `<div class="field-inline"><span>${esc(t("setup.channel_q"))}</span><div class="seg" id="ch">${Array.from({ length: nch }, (_, k) =>
        `<button data-c="${k + 1}" class="${k + 1 === st.channel ? "active" : ""}">${k + 1}</button>`).join("")}</div></div>` : ""}
      <div class="listen-box">
        <div class="listen-head"><b id="verdict" class="muted">${esc(t("setup.connecting"))}</b><span class="mono muted" id="db"></span></div>
        ${meterHtml("lv")}
        <small class="muted">${esc(t("setup.meter_hint"))}</small>
      </div>
      <div class="setup-actions"><button class="btn ghost" id="back">← ${esc(t("common.back"))}</button>
        <a class="btn ghost" href="#/practice?demo=1" id="nogtr">${esc(t("setup.no_guitar"))}</a>
        <button class="btn primary" id="next" ${devs.length ? "" : "disabled"}>${esc(t("setup.use_input"))} →</button></div>`);
    $$(".dev", el).forEach(b => b.onclick = () => { st.device = +b.dataset.i; st.channel = 1; close(); pickInput(); });
    $$("#ch button", el).forEach(b => b.onclick = () => { st.channel = +b.dataset.c; close(); pickInput(); });
    $("#back", el).onclick = () => go("welcome");
    $("#nogtr", el).onclick = () => markOnboarded();
    $("#next", el).onclick = async () => {
      try {
        const saved = { ...cfg.saved, device: st.device, channel: st.channel };
        if (cfg.saved.device !== st.device) delete saved.samplerate;   // the old rate may not fit the new device
        await api("/api/config", { json: saved });
        cfg.saved = saved;
        window.dispatchEvent(new CustomEvent("guitarr:device"));
        go("tune");
      } catch (e) { toast(e.message); }
    };
    if (devs.length) listenTo(r => r);
  }

  function tune() {
    frame(`<h1>${esc(t("setup.tune_title"))}</h1>
      <p class="lead">${esc(t("setup.tune_lead"))}</p>
      <div class="mini-tuner">
        <div class="mt-note" id="note">—</div>
        <div class="mt-scale"><i class="mt-mid"></i><i class="mt-needle" id="needle"></i></div>
        <div class="muted" id="cents">${esc(t("tuner.play_open"))}</div>
        <div class="strings" id="strs">${openStrings().map(([m, n, l]) => `<div data-m="${m}" class="${st.tuned.has(m) ? "ok" : ""}"><b>${l}</b><small>${esc(t("tuner.string_n", { n }))}</small></div>`).join("")}</div>
      </div>
      <div class="listen-box slim">${meterHtml("lv")}</div>
      <div class="setup-actions"><button class="btn ghost" id="back">← ${esc(t("common.back"))}</button>
        <button class="btn ghost" id="skip">${esc(t("setup.skip_tune"))}</button>
        <button class="btn primary" id="next">${esc(t("setup.continue"))} →</button></div>`);
    $("#back", el).onclick = () => go("input");
    $("#skip", el).onclick = () => go("done");
    $("#next", el).onclick = () => go("done");
    listenTo(r => {
      const note = $("#note", el), cents = $("#cents", el), needle = $("#needle", el);
      if (!note) return;
      if (!r.note || r.string == null) {
        note.textContent = r.note || "—"; note.className = "mt-note";
        needle.style.left = "50%"; needle.className = "mt-needle";
        if (!r.note) cents.textContent = t("tuner.play_open");
        return;
      }
      const c = r.string_cents, ok = Math.abs(c) <= 5;
      note.textContent = r.string_note; note.className = "mt-note" + (ok ? " ok" : "");
      needle.style.left = (50 + Math.max(-50, Math.min(50, c))) + "%";
      needle.className = "mt-needle" + (ok ? " ok" : "");
      cents.textContent = `${c > 0 ? "+" : ""}${c.toFixed(0)}¢ · ` + t("tuner.string_status", { n: r.string, status: t(ok ? "tuner.in_tune" : c < 0 ? "tuner.tune_up" : "tuner.tune_down") });
      const m = openStrings().find(s => s[1] === r.string)[0];
      if (ok) st.tuned.add(m);
      $$("#strs div", el).forEach(d => d.className = st.tuned.has(+d.dataset.m) ? "ok" : +d.dataset.m === m ? "on" : "");
      if (st.tuned.size === instrument.strings.length) cents.textContent = t("setup.all_tuned");
    });
  }

  function done() {
    markOnboarded();
    const lt = firstLesson && tc(`lessons.${firstLesson.id}.title`, firstLesson.title);
    frame(`<div class="done-mark">${icon("check", 34)}</div>
      <h1>${esc(t("setup.done_title"))}</h1>
      <p class="lead">${esc(t("setup.done_lead"))}</p>
      <div class="choice-grid">
        ${firstLesson ? `<a class="choice primary" href="#/lesson/${encodeURIComponent(firstLesson.id)}">${icon("course", 22)}<b>${esc(t("setup.start_course"))}</b><small>${esc(lt)}</small></a>` : ""}
        <a class="choice" href="#/charts">${icon("charts", 22)}<b>${esc(t("setup.play_chart"))}</b><small>${esc(t("setup.play_chart_hint"))}</small></a>
        <a class="choice" href="#/practice?demo=1">${icon("sparkle", 22)}<b>${esc(t("setup.try_demo"))}</b><small>${esc(t("setup.try_demo_hint"))}</small></a>
      </div>
      <p class="muted small center" style="margin-top:18px">${esc(t("setup.later"))}</p>`);
  }

  function listenTo(extra) {
    close();
    const vs = {};
    input = openInput({
      device: st.step === "input" ? st.device : null, channel: st.step === "input" ? st.channel : null,
      onReading: r => {
        setMeter($("#lv", el), r.level_db);
        const v = levelVerdict(vs, r), vd = $("#verdict", el);
        if (vd) { vd.textContent = v.text; vd.className = v.cls; }
        const db = $("#db", el);
        if (db) db.textContent = `${Math.round(r.level_db)} dB`;
        extra(r);
      },
      onError: msg => {
        const vd = $("#verdict", el);
        if (vd) { vd.textContent = msg; vd.className = "err"; }
        close();
        // The input may be busy for a moment (e.g. a tuner closing elsewhere): retry once.
        retry = setTimeout(() => { if (!input) listenTo(extra); }, 2500);
      },
    });
  }

  render();
}

function close() {
  clearTimeout(retry);
  if (input) { input.close(); input = null; }
}

export function unmount() { close(); }
