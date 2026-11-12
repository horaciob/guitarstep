// A song you uploaded: what its file says (tuning, key, tempo, time), your progress per section, videos by
// role, and adding it to a setlist.
import { t } from "../lib/i18n.js";
import { $, api, esc, toast, youtubeSearch } from "../lib/ui.js";
import { renderSections } from "../lib/sections.js";
import { chipsHtml, readinessRing } from "../lib/chips.js";
import { slowPlayer } from "../lib/slowplayer.js";

const AUDIO = /\.(wav|mp3|flac|ogg|m4a|aiff?)$/i;
let slow = null;

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
    <section class="panel" aria-labelledby="slowTitle"><h2 id="slowTitle">${esc(t("slow.title"))}</h2>
      ${AUDIO.test(name) ? `<p class="muted small">${esc(t("song.slow_hint"))}</p>` : ""}<div id="slowBox"></div></section>
    <section class="panel song-theory" id="songTheory" aria-labelledby="thTitle"><h2 id="thTitle">${esc(t("songtheory.title"))}</h2>
      <p class="muted">${esc(t("songtheory.loading"))}</p></section>
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
  if (slow) slow.stop();
  slow = slowPlayer($("#slowBox", el), AUDIO.test(name) ? { src: `/api/songs/${encodeURIComponent(name)}/audio` } : {});
  api(`/api/songs/${encodeURIComponent(name)}/theory`).then(a => theoryPanel($("#songTheory", el), a))
    .catch(e => { $("#songTheory", el).innerHTML = `<h2 id="thTitle">${esc(t("songtheory.title"))}</h2><p class="muted">${esc(e.message)}</p>`; });
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

/** The song's theory: key, the chords of the key (how many bars each), chords from outside, the progression that
 * repeats most and a bar-by-bar reading. Every count is written out; nothing relies on color. */
function theoryPanel(box, a) {
  const head = `<h2 id="thTitle">${esc(t("songtheory.title"))}</h2>`;
  if (a.empty) { box.innerHTML = `${head}<p class="muted">${esc(t("songtheory.empty"))}</p>`; return; }
  const keyName = k => t(`songtheory.key_${k.mode}`, { root: k.root });
  const job = j => j ? t(`quiz.fn_${j}`) : t("songtheory.outside_key");
  const scale = s => `${s.root} ${t(`quiz.scale_${s.scale}`)}`;
  const p = a.progression;
  box.innerHTML = `${head}
    <p class="th-key"><b>${esc(keyName(a.key))}</b> <span class="muted small">${esc(t("songtheory.or", { key: keyName(a.second) }))}</span></p>
    <h3>${esc(t("songtheory.field"))}</h3>
    <div class="th-field">${a.field.map(c => `<div class="th-cell${c.bars ? " used" : ""}"><small>${esc(c.roman)}</small><b>${esc(c.chord)}</b>
      <span class="muted small">${esc(t(`quiz.fn_${c.job}`))}</span><span class="small">${esc(c.bars ? t("songtheory.bars", { count: c.bars }) : t("songtheory.unused"))}</span></div>`).join("")}</div>
    ${a.outside.length ? `<h3>${esc(t("songtheory.outside"))}</h3><div class="chips">${a.outside.map(u =>
      `<span class="chip"><b>${esc(u.chord)}</b> · ${esc(u.roman)} · ${esc(t("songtheory.bars", { count: u.bars }))}</span>`).join("")}</div>` : ""}
    <h3>${esc(t("songtheory.progression"))}</h3>
    ${p ? `<p class="th-prog"><b>${esc(p.chords.join(" – "))}</b> <span class="muted">(${esc(p.romans.join(" – "))})</span>
      <span class="small muted">· ${esc(t("songtheory.prog_where", { count: p.count, bar: p.bar }))}</span></p>` : `<p class="muted">${esc(t("songtheory.no_prog"))}</p>`}
    <details><summary>${esc(t("songtheory.by_bar"))}</summary>
      <div class="table-wrap"><table class="th-bars"><thead><tr><th>${esc(t("songtheory.bar"))}</th><th>${esc(t("songtheory.chord"))}</th>
        <th>${esc(t("songtheory.degree"))}</th><th>${esc(t("songtheory.job"))}</th><th>${esc(t("songtheory.resting"))}</th><th>${esc(t("songtheory.scales"))}</th></tr></thead>
      <tbody>${a.bars.map(b => b.chord ? `<tr><td>${b.bar}</td><td><b>${esc(b.chord)}</b></td><td>${esc(b.roman)}</td><td>${esc(job(b.job))}</td>
        <td>${b.resting ? esc(t("songtheory.rest_note", b.resting)) : "–"}</td><td>${esc(b.scales.map(scale).join(" · ") || "–")}</td></tr>`
        : `<tr><td>${b.bar}</td><td colspan="5" class="muted">${esc(t("songtheory.no_chord"))}</td></tr>`).join("")}</tbody></table></div>
    </details>
    <p class="muted small">${esc(t("songtheory.caveat"))}</p>`;
}

export function unmount() {
  if (slow) slow.stop();
  slow = null;
}
