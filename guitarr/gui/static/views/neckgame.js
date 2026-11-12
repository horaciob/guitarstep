// The neck game: a note and a string appear, you play it, the next one comes. How many in 30 or 60 seconds?
// The listener grades each note; records are kept per set of strings on the server.
import { msgIsError, msgText, t } from "../lib/i18n.js";
import { $, $$, api, esc, NOTE_NAMES } from "../lib/ui.js";
import { listen } from "../lib/listen.js";

const SETS = { low: [6, 5], mid: [4, 3], high: [2, 1], all: [6, 5, 4, 3, 2, 1] };
let task = null, clock = 0;

export function stopNeck() { if (task) task.stop(); task = null; clearInterval(clock); }

export async function neckGame(box) {
  const prog = await api("/api/progress");
  const keyOf = (set, acc, sec) => `${SETS[set].join("")}${acc ? "#" : ""}-${sec}`;
  box.innerHTML = `
    <div class="panel">
      <p class="muted">${esc(t("neck.intro"))}</p>
      <div class="row left wrap">
        <div class="seg" id="nSet" role="group" aria-label="${esc(t("neck.strings"))}">${Object.keys(SETS).map((k, i) =>
          `<button data-set="${k}" class="${i === 0 ? "active" : ""}" aria-pressed="${i === 0}">${esc(t(`neck.set_${k}`))}</button>`).join("")}</div>
        <label class="check"><input type="checkbox" id="nAcc"> ${esc(t("neck.accidentals"))}</label>
        <label class="field-inline">${esc(t("neck.time"))} <select id="nSec"><option value="60">60 s</option><option value="30">30 s</option></select></label>
      </div>
      <p class="muted small" id="nBest"></p>
      <div class="neck-target" id="nTarget" aria-live="polite" hidden><b id="nNote">—</b><span id="nString"></span></div>
      <div class="row center"><button class="btn primary xl" id="nGo">▶ ${esc(t("neck.start"))}</button></div>
      <p class="center"><span class="mono" id="nClock"></span> <span id="nFound"></span></p>
      <p class="ex-msg muted center" id="nMsg" aria-live="polite"></p>
    </div>`;
  let set = "low";
  const best = () => {
    const r = (prog.neck || {})[keyOf(set, $("#nAcc", box).checked, +$("#nSec", box).value)];
    $("#nBest", box).textContent = r ? t("neck.best", { n: r.best }) : t("neck.no_best");
  };
  $$("#nSet button", box).forEach(b => b.onclick = () => {
    set = b.dataset.set;
    $$("#nSet button", box).forEach(x => { x.classList.toggle("active", x === b); x.setAttribute("aria-pressed", x === b); });
    best();
  });
  $("#nAcc", box).onchange = best;
  $("#nSec", box).onchange = best;
  best();

  $("#nGo", box).onclick = async () => {
    if (task) { task.stop(); return; }
    const go = $("#nGo", box), msg = $("#nMsg", box), seconds = +$("#nSec", box).value;
    go.textContent = `■ ${t("lesson.stop")}`;
    msg.className = "ex-msg muted center"; msg.textContent = "";
    $("#nTarget", box).hidden = false;
    let started = 0;
    task = listen({ neck: { strings: SETS[set], accidentals: $("#nAcc", box).checked, seconds } }, {
      onState: s => {
        if (!started) { started = performance.now(); clock = setInterval(() => {
          $("#nClock", box).textContent = `${Math.max(0, Math.ceil(seconds - (performance.now() - started) / 1000))} s`;
        }, 200); }
        const cur = (s.lane || []).find(e => e.current);
        if (cur && cur.pitches && cur.tab && cur.tab[0]) {
          $("#nNote", box).textContent = NOTE_NAMES[cur.pitches[0] % 12];
          $("#nString", box).textContent = t("neck.on_string", { s: cur.tab[0][0] });
        }
        $("#nFound", box).textContent = t("neck.found_so_far", { n: s.stats.judged - s.stats.errors, all: s.stats.judged });
      },
      onMessage: m => { msg.textContent = msgText(m); msg.className = `ex-msg center ${msgIsError(m) ? "err" : "ok"}`; },
    });
    try {
      const rep = await task.done;
      const a = rep.award || {};
      msg.className = "ex-msg ok center";
      msg.textContent = t("neck.result", { n: a.found || 0, first: a.first_try || 0, seconds }) +
        (a.record ? ` · ${t("improv.record")}` : "") + (a.xp ? ` · +${a.xp} XP` : "");
      if (a.found) {
        prog.neck = prog.neck || {};
        const k = keyOf(set, $("#nAcc", box).checked, seconds);
        prog.neck[k] = { best: a.best };
        best();
      }
    } catch (e) { msg.className = "ex-msg err center"; msg.textContent = e.message; }
    finally {
      clearInterval(clock); task = null;
      $("#nTarget", box).hidden = true; $("#nClock", box).textContent = "";
      go.textContent = `▶ ${t("neck.start")}`;
    }
  };
}
