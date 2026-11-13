// Classes (web service): your students and their week, an invitation link, assignments to send; your teachers
// and the assignments they sent you. Joining a class (#/class?join=CODE) first says what the teacher will see.
import { lang, t } from "../lib/i18n.js";
import { $, $$, api, esc, toast } from "../lib/ui.js";
import { fmtHM } from "../lib/plan.js";

let root = null;

const day = iso => new Intl.DateTimeFormat(lang(), { day: "numeric", month: "short" }).format(new Date(iso));
const showErr = (el, e) => { el.textContent = e.message; el.hidden = false; };

export async function mount(el, { params = {} } = {}) {
  root = el;
  const [c, lists] = await Promise.all([api("/api/class"), api("/api/setlists").catch(() => [])]);
  if (root !== el) return;
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("class.title"))}</h1><p class="muted">${esc(t("class.subtitle"))}</p></div>
    <div id="joinBox"></div>
    ${c.inbox.length ? `<section class="panel" aria-labelledby="inboxTitle"><h2 id="inboxTitle">${esc(t("class.inbox"))}</h2>
      <ul class="class-list">${c.inbox.map(a => `<li data-a="${a.id}">
        <div><b>${esc(a.name)}</b> <small class="muted">${esc(t("class.from", { teacher: a.teacher, date: day(a.created_at) }))}
          · ${esc(t("setlists.n_items", { count: a.items }))}</small>${a.note ? `<p class="small">${esc(a.note)}</p>` : ""}</div>
        <span class="row left"><button class="btn small primary" data-accept>${esc(t("class.accept"))}</button>
          <button class="btn small" data-dismiss>${esc(t("class.dismiss"))}</button></span>
        <p class="field-error" hidden></p></li>`).join("")}</ul></section>` : ""}
    <section class="panel" aria-labelledby="stTitle">
      <div class="row-between"><h2 id="stTitle">${esc(t("class.students"))}</h2>
        <button class="btn small" id="inviteBtn">${esc(t("class.invite"))}</button></div>
      <div id="inviteBox" hidden></div>
      ${c.students.length ? `<ul class="class-list">${c.students.map(s => `<li data-s="${esc(s.id)}">
        <div><b>${esc(s.email)}</b>
          <small class="muted">${esc(t("class.week", { time: fmtHM(s.week.minutes), days: s.week.active_days, streak: s.week.streak, songs: s.week.songs }))}
            · ${esc(t("level.label", { n: s.week.level.level }))}</small>
          ${s.sent.length ? `<small class="muted class-sent">${s.sent.map(a => esc(t(`class.sent_${a.state}`, { name: a.name }))).join(" · ")}</small>` : ""}</div>
        <span class="row left"><a class="btn small" href="#/report?student=${esc(s.id)}">${esc(t("class.report"))}</a>
          <button class="btn small" data-send ${lists.length ? "" : "disabled"}>${esc(t("class.send"))}</button>
          <span class="rm"><button class="btn small ghost" data-remove>${esc(t("class.remove"))}</button></span></span>
        <form class="send-form row wrap" hidden>
          <label class="field"><span>${esc(t("class.setlist"))}</span><select name="setlist">${lists.map(l => `<option value="${esc(l.id)}">${esc(l.name)}</option>`).join("")}</select></label>
          <label class="field grow"><span>${esc(t("class.note"))}</span><input name="note" maxlength="2000" placeholder="${esc(t("class.note_hint"))}"></label>
          <button class="btn primary small" type="submit">${esc(t("class.send_it"))}</button>
          <p class="field-error" hidden></p></form></li>`).join("")}</ul>`
        : `<p class="muted">${esc(t(lists.length ? "class.no_students" : "class.no_students_no_lists"))}</p>`}
    </section>
    <section class="panel" aria-labelledby="tcTitle"><h2 id="tcTitle">${esc(t("class.teachers"))}</h2>
      ${c.teachers.length ? `<p class="muted small">${esc(t("class.shared"))}</p><ul class="class-list">${c.teachers.map(tc => `<li data-t="${esc(tc.id)}">
        <div><b>${esc(tc.email)}</b> <small class="muted">${esc(t("class.since", { date: day(tc.joined_at) }))}</small></div>
        <span class="rm"><button class="btn small ghost" data-leave>${esc(t("class.leave"))}</button></span></li>`).join("")}</ul>`
        : `<p class="muted">${esc(t("class.no_teachers"))}</p>`}
    </section>`;
  bind(el);
  if (params.join) showJoin(el, params.join);
}

export function unmount() { root = null; }

const reload = () => root && mount(root, {});

function confirmIn(box, question, onYes) {
  const was = box.innerHTML;
  box.innerHTML = `<span class="small">${esc(question)}</span> <button class="btn small danger" data-yes>${esc(t("rig.yes"))}</button>
    <button class="btn small" data-no>${esc(t("rig.no"))}</button>`;
  box.querySelector("[data-no]").onclick = () => { box.innerHTML = was; bind(root); };
  box.querySelector("[data-yes]").onclick = onYes;
}

function bind(el) {
  $("#inviteBtn", el).onclick = async () => {
    const box = $("#inviteBox", el);
    try {
      const inv = await api("/api/class/invite", { method: "POST" });
      box.hidden = false;
      box.innerHTML = `<p class="small">${esc(t("class.invite_hint", { days: inv.days }))}</p>
        <div class="row"><input class="grow" id="inviteUrl" readonly value="${esc(inv.url)}" aria-label="${esc(t("class.invite"))}">
        <button class="btn small" id="copyInvite">${esc(t("class.copy"))}</button></div>`;
      $("#copyInvite", el).onclick = async () => {
        try { await navigator.clipboard.writeText(inv.url); toast(t("class.copied"), true); } catch { $("#inviteUrl", el).select(); }
      };
    } catch (e) { toast(e.message); }
  };
  $$("[data-s]", el).forEach(li => {
    const id = li.dataset.s, form = $(".send-form", li);
    const send = li.querySelector("[data-send]");
    if (send) send.onclick = () => { form.hidden = !form.hidden; };
    form.onsubmit = async ev => {
      ev.preventDefault();
      const err = $(".field-error", form);
      err.hidden = true;
      try {
        await api(`/api/class/students/${id}/assignments`, { json: { setlist: form.setlist.value, note: form.note.value } });
        toast(t("class.sent"), true);
        reload();
      } catch (e) { showErr(err, e); }
    };
    const rm = $(".rm", li);
    rm.querySelector("[data-remove]").onclick = () => confirmIn(rm, t("class.remove_q"), async () => {
      try { await api(`/api/class/students/${id}`, { method: "DELETE" }); reload(); } catch (e) { toast(e.message); }
    });
  });
  $$("[data-t]", el).forEach(li => {
    const rm = $(".rm", li);
    rm.querySelector("[data-leave]").onclick = () => confirmIn(rm, t("class.leave_q"), async () => {
      try { await api(`/api/class/teachers/${li.dataset.t}`, { method: "DELETE" }); reload(); } catch (e) { toast(e.message); }
    });
  });
  $$("[data-a]", el).forEach(li => {
    const answer = async accept => {
      try {
        const r = await api(`/api/class/assignments/${li.dataset.a}`, { json: { accept } });
        if (accept) toast(t(r.missing_songs && r.missing_songs.length ? "class.accepted_missing" : "class.accepted",
          { name: r.setlist.name, songs: (r.missing_songs || []).join(", ") }), true);
        reload();
      } catch (e) { showErr($(".field-error", li), e); }
    };
    li.querySelector("[data-accept]").onclick = () => answer(true);
    li.querySelector("[data-dismiss]").onclick = () => answer(false);
  });
}

async function showJoin(el, code) {
  const box = $("#joinBox", el);
  let inv;
  try { inv = await api(`/api/class/invite/${encodeURIComponent(code)}`); } catch (e) {
    box.innerHTML = `<div class="panel"><p class="field-error">${esc(e.message)}</p></div>`;
    return;
  }
  if (inv.yours || inv.joined) {
    box.innerHTML = `<div class="panel"><p>${esc(t(inv.yours ? "class.join_yours" : "class.join_already", { teacher: inv.teacher }))}</p></div>`;
    return;
  }
  box.innerHTML = `<section class="panel callout" aria-labelledby="joinTitle"><h2 id="joinTitle">${esc(t("class.join_q", { teacher: inv.teacher }))}</h2>
    <p>${esc(t("class.join_shares"))}</p>
    <div class="row left"><button class="btn primary" id="joinYes">${esc(t("class.join"))}</button>
      <a class="btn" href="#/class">${esc(t("class.not_now"))}</a></div><p class="field-error" id="joinErr" hidden></p></section>`;
  $("#joinYes", el).onclick = async () => {
    try {
      await api("/api/class/join", { json: { code } });
      toast(t("class.joined", { teacher: inv.teacher }), true);
      location.hash = "#/class";
    } catch (e) { showErr($("#joinErr", el), e); }
  };
}
