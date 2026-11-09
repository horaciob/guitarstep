// A song you uploaded: what its file says (tuning, key, tempo, time), your progress per section, videos by
// role, and adding it to a setlist.
import { t } from "../lib/i18n.js";
import { $, api, esc, toast, youtubeSearch } from "../lib/ui.js";
import { renderSections } from "../lib/sections.js";
import { chipsHtml, readinessRing } from "../lib/chips.js";

export async function mount(el, { segs }) {
  const name = decodeURIComponent(segs[0] || "");
  let f;
  try { f = await api(`/api/songs/${encodeURIComponent(name)}/facts`); }
  catch (e) { el.innerHTML = `<div class="gl-head"><h1>${esc(t("song.not_found"))}</h1><p class="muted">${esc(e.message)}</p></div><a class="btn" href="#/practice">← ${esc(t("nav.practice"))}</a>`; return; }
  const lists = await api("/api/setlists").catch(() => []);
  const practice = `#/practice?song=${encodeURIComponent(name)}`;
  el.innerHTML = `
    <a class="btn small" href="#/practice">← ${esc(t("nav.practice"))}</a>
    <div class="gl-head song-head" style="margin-top:12px">
      <div id="songRing"></div>
      <div><h1>${esc(f.title)}</h1>${f.artist ? `<p class="muted">${esc(f.artist)}</p>` : ""}
        ${chipsHtml({ tuning: f.tuning, key: f.key, bpm: f.bpm, time: f.time, capo: f.capo })}</div>
    </div>
    <div class="row left wrap">
      <a class="btn primary" href="${esc(practice)}">${esc(t("charts.play"))}</a>
      ${lists.length ? `<label class="field-inline small">${esc(t("setlists.add_to"))}
        <select id="addTo"><option value="">—</option>${lists.map(s => `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</select></label>`
        : `<a class="btn ghost" href="#/setlists">${esc(t("setlists.create_first"))}</a>`}
    </div>
    <section class="panel sec-progress" id="secProgress" aria-labelledby="secTitle"></section>
    <section class="panel" aria-labelledby="vidTitle">
      <h2 id="vidTitle">${esc(t("song.videos"))}</h2>
      <ul class="tutorias">${["lesson", "backing", "guitar"].map(r => `<li><span class="how-chip">${esc(t(`song.role_${r}`))}</span>
        <a href="${youtubeSearch(f.searches[r])}" target="_blank" rel="noopener">▶ ${esc(f.searches[r])}</a></li>`).join("")}</ul>
      <form class="row" id="vidForm"><label class="field grow"><span>${esc(t("song.pin_label"))}</span>
        <input type="text" id="vidUrl" value="${esc(f.video || "")}" placeholder="https://…" aria-describedby="vidErr"></label>
        <button class="btn small" type="submit">${esc(t("lesson.pin"))}</button></form>
      <p class="field-error" id="vidErr" hidden></p>
      ${f.video ? `<p><a href="${esc(f.video)}" target="_blank" rel="noopener">${esc(t("lesson.pinned_link"))} ↗</a></p>` : ""}
    </section>`;
  renderSections($("#secProgress", el), { base: `/api/songs/${encodeURIComponent(name)}`, practice, queue: `song:${name}`,
    onChange: m => { $("#songRing", el).innerHTML = readinessRing(m); } });
  $("#vidForm", el).onsubmit = async ev => {
    ev.preventDefault();
    const err = $("#vidErr", el), url = $("#vidUrl", el).value.trim();
    if (url && !/^https?:\/\//.test(url)) { err.textContent = t("song.bad_url"); err.hidden = false; return; }
    try { await api(`/api/songs/${encodeURIComponent(name)}/video`, { json: { url: $("#vidUrl", el).value } }); err.hidden = true; mount(el, { segs }); }
    catch (e) { err.textContent = e.code === "bad_url" ? t("song.bad_url") : e.message; err.hidden = false; }
  };
  const add = $("#addTo", el);
  if (add) add.onchange = async () => {
    const s = lists.find(x => x.id === add.value);
    if (!s) return;
    try {
      await api(`/api/setlists/${s.id}`, { method: "PUT", json: { items: [...s.items.map(({ kind, id }) => ({ kind, id })), { kind: "song", id: name }] } });
      toast(t("setlists.added", { name: s.name }), true);
    } catch (e) { toast(e.message); }
    add.value = "";
  };
}
