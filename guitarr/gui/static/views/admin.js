// The web service's admin page (GUITARR_ADMINS): accounts, space, practice this week, the jobs, and blocking.
import { lang, t } from "../lib/i18n.js";
import { $$, api, esc } from "../lib/ui.js";

let root = null;
const when = iso => iso ? new Intl.DateTimeFormat(lang(), { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(iso)) : "—";

export async function mount(el) {
  root = el;
  let o;
  try { o = await api("/api/admin"); } catch (e) {
    el.innerHTML = `<div class="gl-head"><h1>${esc(t("admin.title"))}</h1></div><div class="panel"><p class="field-error">${esc(e.message)}</p></div>`;
    return;
  }
  if (root !== el) return;
  const T = o.totals, J = o.jobs;
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("admin.title"))}</h1></div>
    <div class="summary">
      <div class="stat"><div class="v">${T.users}</div><div class="l">${esc(t("admin.users"))}${T.blocked ? ` · ${esc(t("admin.n_blocked", { count: T.blocked }))}` : ""}</div></div>
      <div class="stat"><div class="v">${T.active_week}</div><div class="l">${esc(t("admin.active_week"))}</div></div>
      <div class="stat"><div class="v">${T.sessions_week}</div><div class="l">${esc(t("admin.sessions_week"))}</div></div>
      <div class="stat"><div class="v">${T.space_mb} MB</div><div class="l">${esc(t("admin.space"))}</div></div>
    </div>
    <section class="panel"><h2>${esc(t("admin.jobs"))}</h2>
      <p>${esc(t("admin.jobs_line", J))}</p>
      ${o.failed.length ? `<table class="report-table"><tr><th>${esc(t("admin.when"))}</th><th>${esc(t("admin.kind"))}</th><th>${esc(t("admin.user"))}</th><th>${esc(t("admin.error"))}</th></tr>
        ${o.failed.map(f => `<tr><td>${esc(when(f.at))}</td><td>${esc(f.kind)}</td><td>${esc(f.email)}</td>
          <td class="small">${esc((f.error && (f.error.message || f.error.code)) || "")}</td></tr>`).join("")}</table>` : ""}
    </section>
    <section class="panel"><h2>${esc(t("admin.accounts"))}</h2>
      <table class="report-table"><tr><th>${esc(t("admin.user"))}</th><th>${esc(t("admin.last_seen"))}</th><th>${esc(t("admin.sessions"))}</th><th>${esc(t("admin.space_col"))}</th><th><span class="sr-only">${esc(t("admin.actions"))}</span></th></tr>
      ${o.users.map(u => `<tr data-u="${esc(u.id)}"><td>${esc(u.email)}${u.blocked ? ` · <b>${esc(t("admin.blocked"))}</b>` : ""}</td>
        <td>${esc(when(u.last_seen))}</td><td>${u.sessions}</td><td>${u.space_mb} MB</td>
        <td class="blk"><button class="btn small ${u.blocked ? "" : "ghost"}" data-block="${u.blocked ? "0" : "1"}">${esc(t(u.blocked ? "admin.unblock" : "admin.block"))}</button>
          <span class="field-error" hidden></span></td></tr>`).join("")}</table>
    </section>`;
  $$("[data-u]", el).forEach(tr => {
    const cell = tr.querySelector(".blk"), btn = cell.querySelector("button"), blocking = btn.dataset.block === "1";
    const go = async () => {
      try { await api(`/api/admin/users/${tr.dataset.u}`, { json: { blocked: blocking } }); mount(root); } catch (e) {
        const err = cell.querySelector(".field-error"); err.textContent = e.message; err.hidden = false;
      }
    };
    btn.onclick = () => {
      if (!blocking) return go();
      cell.innerHTML = `<span class="small">${esc(t("admin.block_q"))}</span> <button class="btn small danger" data-yes>${esc(t("rig.yes"))}</button>
        <button class="btn small" data-no>${esc(t("rig.no"))}</button><span class="field-error" hidden></span>`;
      cell.querySelector("[data-yes]").onclick = go;
      cell.querySelector("[data-no]").onclick = () => mount(root);
    };
  });
}

export function unmount() { root = null; }
