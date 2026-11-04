// Chord dictionary: diagrams, sound and "check by ear".
import { msgText, t, tc } from "../lib/i18n.js";
import { $, $$, api, bindChordSvg, chordSvg, esc, strum, toast } from "../lib/ui.js";
import { listen } from "../lib/listen.js";
import { icon } from "../lib/icons.js";

let task = null;

export async function mount(el, { params }) {
  const data = await api("/api/chords");
  let group = params.group || "all", q = "";
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("chords.title"))}</h1>
      <p class="muted">${t("chords.subtitle_html")}</p></div>
    <div class="toolbar">
      <div class="seg" id="groups"></div>
      <input type="search" id="q" placeholder="${esc(t("chords.search"))}" aria-label="${esc(t("chords.search"))}">
      <a class="btn" href="#/camera">${icon("camera", 16)} ${esc(t("chords.camera_link"))}</a>
    </div>
    <div class="chord-grid" id="grid"></div>`;
  const groups = [{ id: "all", name: t("chords.all") }, ...data.groups.map(g => ({ id: g.id, name: tc(`groups.${g.id}`, g.name) }))];
  $("#groups", el).innerHTML = groups.map(g => `<button data-g="${g.id}">${esc(g.name)}</button>`).join("");

  const render = () => {
    $$("#groups button", el).forEach(b => b.classList.toggle("active", b.dataset.g === group));
    const list = data.chords.filter(c => (group === "all" || c.group === group) &&
      (!q || (c.id + " " + c.name + " " + tc(`chords.${c.id}.name`, c.name) + " " + c.group).toLowerCase().includes(q)));
    $("#grid", el).innerHTML = list.map(c => {
      const m = data.mastered[c.id] || {};
      const badges = (m.ear ? `<span class="pill ok" title="${esc(t("chords.mastered_ear"))}">🎧</span>` : "") +
                     (m.camera ? `<span class="pill ok" title="${esc(t("chords.mastered_camera"))}">◉</span>` : "");
      return `<article class="chord-card${m.ear || m.camera ? " mastered" : ""}" data-id="${esc(c.id)}">
        <header><b>${esc(c.id)}</b><span class="muted">${esc(tc(`chords.${c.id}.name`, c.name))}</span>${badges}</header>
        <div class="diagram">${chordSvg(c, { size: 112 })}</div>
        <div class="chord-notes muted">${c.notes.join(" · ")}</div>
        <p class="chord-tip">${esc(tc(`chords.${c.id}.tip`, c.tip))}</p>
        <div class="row">
          <button class="btn small" data-act="strum" title="${esc(t("chords.listen_hint"))}" aria-label="${esc(t("chords.listen_hint"))}">▶</button>
          <button class="btn small primary" data-act="check">${esc(t("chords.check"))}</button>
          <a class="btn small" href="#/camera?chord=${encodeURIComponent(c.id)}" title="${esc(t("chords.posture_hint"))}">${esc(t("chords.posture"))}</a>
        </div>
        <div class="check-status muted" aria-live="polite"></div>
      </article>`;
    }).join("") || `<p class="muted">${esc(t("chords.none"))}</p>`;
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
  if (task) return toast(t("chords.busy"));
  const st = $(".check-status", card), btn = $("[data-act=check]", card);
  btn.disabled = true;
  st.className = "check-status";
  st.innerHTML = `<span class="spinner"></span> ${esc(t("chords.strum_now", { chord: ch.id }))}`;
  task = listen({ chord: ch.id, mode: "wait", legato: false }, {
    timeoutS: 25,
    onMessage: m => { if (m.code === "wrong") st.textContent = `${msgText(m)} — ${t("chords.try_again")}`; },
  });
  try {
    const rep = await task.done;
    const ok = rep.award && rep.award.passed;
    st.className = "check-status " + (ok ? "ok" : "err");
    st.textContent = ok ? t("chords.heard_ok", { chord: ch.id }) + (rep.award.xp ? ` +${rep.award.xp} XP` : "")
      : t("chords.not_heard", { chord: ch.id });
    if (ok) {
      data.mastered[ch.id] = { ...(data.mastered[ch.id] || {}), ear: true };
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
