// Exercises you pass by answering: multiple-choice questions and picking notes on the fretboard.
// The server draws the questions, keeps the answers and grades them; this module only shows them.
import { t } from "./i18n.js";
import { api, esc, pluck } from "./ui.js";
import { neck } from "./fretboard.js";

const PARAM = { scale: "scale", mode: "scale", iv: "iv", which: "voice", q: "q" };

/** Text for a prompt/choice label from the server: a plain string, or {code, params} → quiz.<code>. */
export function say(label) {
  if (label == null) return "";
  if (typeof label !== "object") return String(label);
  const { code, params = {} } = label;
  if (code === "iv") return t(`quiz.iv_${params.name}`);
  if (code === "quality") return t(`quiz.q_${params.q}`);
  if (code === "voice") return t(`quiz.voice_${params.which}`);
  if (code === "inv") return t(`quiz.inv_${params.k}`, { name: params.name });
  const p = { ...params };
  for (const [k, prefix] of Object.entries(PARAM)) if (p[k] != null) p[k] = t(`quiz.${prefix}_${p[k]}`);
  return t(`quiz.${code}`, p);
}

/** A one-note tab (for "read the tab" questions). */
const tabFigure = ({ string, fret }) => ["e", "B", "G", "D", "A", "E"]
  .map((s, i) => `${s}|---${i === string - 1 ? String(fret).padEnd(2, "-") : "--"}---|`).join("\n");

/** Plays what a question asks you to hear: a melodic pair/run, or a chord (notes together). */
function play(item) {
  (item.play || []).forEach((p, k) => pluck(p, item.melodic ? k * 0.55 : k * 0.02));
}

/**
 * Runs a drawn quiz/pick exercise inside `box`.
 * onProgress(done, total) after each answer; resolves with the server's {summary, award} when finished,
 * or null if stopped. Returns { done, stop }.
 */
export function runAnswers(box, { lesson, exercise, onProgress, drawn = null, finishUrl = "/api/exercise/finish", onReveal = null }) {
  let stopped = false, finishNow = null;
  const done = (async () => {
    const d = drawn || await api("/api/exercise/draw", { json: { lesson, exercise } });
    const n = d.items.length;
    for (let i = 0; i < n && !stopped; i++) {
      await ask(box, d.token, d.items[i], i, n, () => stopped, f => { finishNow = f; }, onReveal);
      onProgress && onProgress(i + 1, n);
    }
    if (stopped) return null;
    return api(finishUrl, { json: { token: d.token } });
  })();
  return { done, stop() { stopped = true; finishNow && finishNow(); } };
}

function ask(box, token, item, i, n, isStopped, setCancel, onReveal) {
  return new Promise(resolve => {
    setCancel(resolve);
    const head = `<p class="q-count muted small">${esc(t("quiz.question_n", { n: i + 1, total: n }))}</p>
      <p class="q-prompt">${esc(say(item.prompt))}</p>
      ${item.tab ? `<pre class="tab q-tab" aria-label="${esc(t("lesson.tab_label"))}">${esc(tabFigure(item.tab))}</pre>` : ""}
      ${item.play ? `<button class="btn" data-q="replay">♪ ${esc(t("quiz.play_again"))}</button>` : ""}`;
    const nextBtn = `<div class="row center q-actions"><button class="btn primary" data-q="next" hidden>${esc(t(i + 1 < n ? "quiz.next" : "quiz.see_result"))} →</button></div>`;
    let answered = false;
    const next = () => { if (answered) resolve(); };
    if (item.type === "pick") {
      box.innerHTML = `<div class="quiz">${head}<div class="q-neck"></div>
        <p class="muted small center">${esc(t(item.mode === "all" ? "quiz.pick_all_hint" : "quiz.pick_tones_hint"))}</p>
        <div class="row center q-actions"><button class="btn" data-q="clear">${esc(t("quiz.clear"))}</button>
          <button class="btn primary" data-q="check">${esc(t("quiz.check"))}</button></div>
        <p class="q-feedback" aria-live="polite"></p>${nextBtn}</div>`;
      const fb = neck(box.querySelector(".q-neck"), { lo: item.frets[0], hi: item.frets[1], selectable: true, label: say(item.prompt) });
      box.querySelector("[data-q=clear]").onclick = () => fb.clear();
      box.querySelector("[data-q=check]").onclick = async () => {
        if (answered) return;
        const sel = fb.selected();
        let r;
        try { r = await api("/api/exercise/check", { json: { token, index: i, answer: sel } }); } catch (e) { feedback(box, false, e.message); return; }
        answered = true;
        fb.lock();
        const chosen = new Set(sel.map(([s, f]) => `${s}:${f}`));
        if (r.mode === "all") {
          const right = new Set(r.answer.map(([s, f]) => `${s}:${f}`));
          fb.set([...right].map(k => k.split(":").map(Number)).map(([s, f]) => ({ string: s, fret: f, kind: chosen.has(`${s}:${f}`) ? "right" : "missed", text: chosen.has(`${s}:${f}`) ? "✓" : "?" }))
            .concat(sel.filter(([s, f]) => !right.has(`${s}:${f}`)).map(([s, f]) => ({ string: s, fret: f, kind: "wrong", text: "✕" }))));
        } else {
          fb.set(sel.map(([s, f]) => ({ string: s, fret: f, kind: r.correct ? "right" : "mark", text: r.correct ? "✓" : "•" })));
        }
        feedback(box, r.correct, r.correct ? t("quiz.right") : t(r.mode === "all" ? "quiz.wrong_pick_all" : "quiz.wrong_pick_tones"));
        box.querySelector("[data-q=check]").disabled = true;
        box.querySelector("[data-q=clear]").disabled = true;
        showNext(box, next);
      };
    } else {
      box.innerHTML = `<div class="quiz">${head}
        <div class="q-choices" role="group" aria-label="${esc(t("quiz.choices"))}">${item.choices.map((c, k) =>
          `<button class="btn q-choice" data-id="${esc(c.id)}"><kbd>${k + 1}</kbd> ${esc(say(c.label))}</button>`).join("")}</div>
        <p class="q-feedback" aria-live="polite"></p>${nextBtn}</div>`;
      const choose = async b => {
        if (answered) return;
        answered = true;
        let r;
        try { r = await api("/api/exercise/check", { json: { token, index: i, answer: b.dataset.id } }); }
        catch (e) { answered = false; feedback(box, false, e.message); return; }
        box.querySelectorAll(".q-choice").forEach(x => {
          x.disabled = true;
          if (x.dataset.id === r.answer) x.classList.add("right");
          else if (x === b) x.classList.add("wrong");
        });
        const right = box.querySelector(`.q-choice[data-id="${CSS.escape(r.answer)}"]`);
        feedback(box, r.correct, r.correct ? t("quiz.right") : t("quiz.wrong_was", { answer: right ? right.textContent.replace(/^\d\s*/, "").trim() : "" }));
        if (r.reveal && onReveal) box.querySelector(".q-feedback").insertAdjacentHTML("afterend", `<div class="q-reveal">${onReveal(r.reveal)}</div>`);
        showNext(box, next);
      };
      box.querySelectorAll(".q-choice").forEach(b => b.onclick = () => choose(b));
      box.onkeydown = e => {
        const k = +e.key;
        if (k >= 1 && k <= item.choices.length && !answered) { e.preventDefault(); choose(box.querySelectorAll(".q-choice")[k - 1]); }
      };
    }
    const rep = box.querySelector("[data-q=replay]");
    if (rep) { rep.onclick = () => play(item); setTimeout(() => !isStopped() && play(item), 250); }
    box.querySelector(".quiz").tabIndex = -1;
    box.querySelector(".quiz").focus();
  });
}

function feedback(box, ok, text) {
  const p = box.querySelector(".q-feedback");
  p.className = "q-feedback " + (ok ? "ok" : "err");
  p.textContent = (ok ? "✓ " : "✕ ") + text;
}

function showNext(box, next) {
  const b = box.querySelector("[data-q=next]");
  b.hidden = false;
  b.onclick = next;
  b.focus();
}
