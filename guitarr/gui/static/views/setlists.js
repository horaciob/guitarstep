// Setlists: charts and songs in the order you'll play them, with a warning wherever the tuning changes.
import { t, tc } from "../lib/i18n.js";
import { $, $$, api, esc, toast } from "../lib/ui.js";
import { readinessRing } from "../lib/chips.js";

let root = null;
const tuningName = id => t(`instrument.t_${id}`, { defaultValue: id });

export async function mount(el, { params = {} }) {
  root = el;
  const [lists, charts, songs] = await Promise.all([api("/api/setlists"), api("/api/charts"), api("/api/songs").catch(() => [])]);
  const open = lists.find(s => s.id === params.id) || null;
  const chartTitle = c => c.mine ? c.title : tc(`charts.${c.id}.title`, c.title);
  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("setlists.title"))}</h1><p class="muted">${esc(t("setlists.subtitle"))}</p></div>
    <form class="panel row wrap" id="newForm">
      <label class="field grow"><span>${esc(t("setlists.new_name"))}</span><input type="text" id="newName" maxlength="80" aria-describedby="newErr"></label>
      <button class="btn primary" type="submit">${esc(t("setlists.create"))}</button>
      <p class="field-error" id="newErr" hidden></p>
    </form>
    <div class="setlist-cards">${lists.map(s => `
      <a class="panel setlist-card${open && open.id === s.id ? " on" : ""}" href="#/setlists?id=${esc(s.id)}">
        <b>${esc(s.name)}</b><small class="muted">${esc(t("setlists.n_items", { count: s.items.length }))}${s.warnings.length ? ` · ⚠ ${esc(t("setlists.n_retunes", { count: s.warnings.length }))}` : ""}</small></a>`).join("")}</div>
    ${open ? `<section class="panel" id="openList" aria-labelledby="openTitle">
      <div class="sec-progress-head"><h2 id="openTitle">${esc(open.name)}</h2>
        <span class="row left">${open.items.length ? `<a class="btn primary" href="#/stage?setlist=${esc(open.id)}">▶ ${esc(t("setlists.stage"))}</a>` : ""}
        <span id="delBox"><button class="btn ghost" id="delList">${esc(t("setlists.delete"))}</button></span></span></div>
      <ol class="setlist-items">${open.items.map((it, i) => {
        const warn = open.warnings.find(w => w.index === i);
        return `${warn ? `<li class="retune" aria-label="${esc(t("setlists.retune", { from: tuningName(warn.from), to: tuningName(warn.to) }))}">⚠ ${esc(t("setlists.retune", { from: tuningName(warn.from), to: tuningName(warn.to) }))}</li>` : ""}
          <li class="setlist-item" data-i="${i}">
            <span class="si-num">${i + 1}</span>
            <span class="si-what"><b>${esc(it.kind === "chart" ? tc(`charts.${it.id}.title`, it.title) : it.title)}</b>
              <small class="muted">${esc(t(`setlists.kind_${it.kind}`))} · ${esc(tuningName(it.tuning))}${it.bpm ? ` · ♩=${it.bpm}` : ""}${it.exists === false ? ` · ${esc(t("setlists.missing"))}` : ""}</small></span>
            ${readinessRing(it.readiness, 40)}
            <span class="si-tools">
              <button class="ib" data-act="up" ${i === 0 ? "disabled" : ""} aria-label="${esc(t("setlists.up"))}">↑</button>
              <button class="ib" data-act="down" ${i === open.items.length - 1 ? "disabled" : ""} aria-label="${esc(t("setlists.down"))}">↓</button>
              <span class="si-del"><button class="ib" data-act="remove" aria-label="${esc(t("setlists.remove"))}">✕</button></span></span>
          </li>`;
      }).join("")}</ol>
      ${open.items.length ? "" : `<p class="muted">${esc(t("setlists.empty"))}</p>`}
      <div class="row wrap">
        <label class="field-inline small">${esc(t("setlists.add_chart"))}
          <select id="addChart"><option value="">—</option>${charts.filter(c => !c.error).map(c => `<option value="${esc(c.id)}">${esc(chartTitle(c))}</option>`).join("")}</select></label>
        ${songs.length ? `<label class="field-inline small">${esc(t("setlists.add_song"))}
          <select id="addSong"><option value="">—</option>${songs.map(s => `<option value="${esc(s.name)}">${esc(s.name)}</option>`).join("")}</select></label>` : ""}
      </div>
    </section>` : lists.length ? `<p class="muted">${esc(t("setlists.pick"))}</p>` : ""}`;

  $("#newForm", el).onsubmit = async ev => {
    ev.preventDefault();
    const err = $("#newErr", el);
    if (!$("#newName", el).value.trim()) { err.textContent = t("setlists.err_empty_name"); err.hidden = false; return; }
    try {
      const s = await api("/api/setlists", { json: { name: $("#newName", el).value } });
      location.hash = `#/setlists?id=${s.id}`;
    } catch (e) { err.textContent = t(`setlists.err_${e.code}`, { defaultValue: e.message }); err.hidden = false; }
  };
  if (!open) return;
  const items = open.items.map(({ kind, id }) => ({ kind, id }));
  const save = async next => {
    try { await api(`/api/setlists/${open.id}`, { method: "PUT", json: { items: next } }); mount(el, { params }); }
    catch (e) { toast(e.message); }
  };
  $$(".setlist-item", el).forEach(li => {
    const i = +li.dataset.i;
    li.querySelector("[data-act=up]").onclick = () => { const n = [...items]; [n[i - 1], n[i]] = [n[i], n[i - 1]]; save(n); };
    li.querySelector("[data-act=down]").onclick = () => { const n = [...items]; [n[i + 1], n[i]] = [n[i], n[i + 1]]; save(n); };
    li.querySelector("[data-act=remove]").onclick = () => {          // confirm in place
      li.querySelector(".si-del").innerHTML = `<span class="small">${esc(t("setlists.remove_confirm"))}</span>
        <button class="btn small danger" data-yes>${esc(t("rig.yes"))}</button><button class="btn small" data-no>${esc(t("rig.no"))}</button>`;
      li.querySelector("[data-yes]").onclick = () => save(items.filter((_, k) => k !== i));
      li.querySelector("[data-no]").onclick = () => mount(el, { params });
    };
  });
  const addC = $("#addChart", el), addS = $("#addSong", el);
  addC.onchange = () => addC.value && save([...items, { kind: "chart", id: addC.value }]);
  if (addS) addS.onchange = () => addS.value && save([...items, { kind: "song", id: addS.value }]);
  $("#delList", el).onclick = () => {
    $("#delBox", el).innerHTML = `<span class="small">${esc(t("setlists.delete_confirm", { name: open.name }))}</span>
      <button class="btn small danger" id="delYes">${esc(t("rig.yes"))}</button><button class="btn small" id="delNo">${esc(t("rig.no"))}</button>`;
    $("#delYes", el).onclick = async () => {
      try { await api(`/api/setlists/${open.id}`, { method: "DELETE" }); location.hash = "#/setlists"; } catch (e) { toast(e.message); }
    };
    $("#delNo", el).onclick = () => mount(el, { params });
  };
}

export function unmount() { root = null; }
