// Search everything from anywhere: Ctrl+K (⌘K on a Mac) opens a box that finds pages, tools, lessons, chords,
// charts, your songs and the rig's sounds. Arrows move, Enter goes, Escape closes.
import { t, tc } from "./i18n.js";
import { $, api, esc } from "./ui.js";
import { fold, matcher, rank } from "./search.js";

const PAGES = ["home", "plan", "course", "chords", "practice", "charts", "setlists", "rig", "tuner", "tools", "analyze", "history", "settings", "report"];
const TOOLS = ["metronome", "warmup", "rhythm", "strums", "drill", "ear", "improv", "neck", "random", "slow", "fretboard", "finder"];
const TOOL_KEY = { rhythm: "rhythm_tab", strums: "strums_tab", ear: "ear_tab", random: "random_tab", warmup: "warmup_tab", slow: "slow_tab", improv: "improv_tab", neck: "neck_tab" };
const MAX = 40;
let items = null, dlg = null, sel = 0, shown = [];

async function load() {
  const [course, chords, charts, songs, presets] = await Promise.all([
    api("/api/course").catch(() => null), api("/api/chords").catch(() => null), api("/api/charts").catch(() => []),
    api("/api/songs").catch(() => []), import("./rig/presets.js").catch(() => null)]);
  const out = [];
  const add = (kind, name, href, extra = "") => out.push({ kind, name, href, q: fold(`${name} ${extra}`), r: fold(name) });
  for (const p of PAGES) add("page", t(p === "report" ? "report_week.open" : `nav.${p}`), `#/${p}`);
  for (const k of TOOLS) add("tool", t(`tools.${TOOL_KEY[k] || k}`), `#/tools?tab=${k}`, t("nav.tools"));
  if (course) for (const lv of [...course.levels, ...(course.optional || [])]) for (const ls of lv.lessons)
    if (!ls.recap) add("lesson", tc(`lessons.${ls.id}.title`, ls.title), `#/lesson/${encodeURIComponent(ls.id)}`, `${tc(`levels.${lv.id}.title`, lv.title)} ${ls.title}`);
  if (chords) for (const c of chords.chords) add("chord", c.id, `#/chords?chord=${encodeURIComponent(c.id)}`, tc(`chords.${c.id}.name`, c.name || ""));
  for (const c of charts) if (!c.error) add("chart", c.mine ? c.title : tc(`charts.${c.id}.title`, c.title), `#/practice?chart=${encodeURIComponent(c.id)}`, c.artist || "");
  for (const s of songs) add("song", s.name, `#/song/${encodeURIComponent(s.name)}`);
  if (presets) {
    for (const id of Object.keys(presets.FACTORY)) add("sound", t(`rig.preset.${id}`), `#/rig?preset=${id}`);
    for (const id of Object.keys(presets.ARTISTS)) {
      const info = presets.ARTIST_INFO[id] || {};
      add("sound", t(`rig.preset.${id}`), `#/rig?preset=${id}`, [info.artist, ...(info.bands || []), ...(info.also || [])].join(" "));
    }
  }
  return out;
}

function render() {
  const q = $("#palInput", dlg).value;
  const m = matcher(q, items.map(x => x.q));
  shown = m.words.length ? items.filter(x => m.test(x.q)).map(x => [rank(m.words, [x.r, x.q]), x]).sort((a, b) => a[0] - b[0]).map(([, x]) => x).slice(0, MAX)
    : items.filter(x => x.kind === "page");
  sel = Math.min(sel, Math.max(0, shown.length - 1));
  const list = $("#palList", dlg);
  list.innerHTML = shown.map((x, i) => `<li role="option" id="pal-${i}" aria-selected="${i === sel}" data-i="${i}" class="${i === sel ? "on" : ""}">
      <span>${esc(x.name)}</span><small class="muted">${esc(t(`palette.kind_${x.kind}`))}</small></li>`).join("")
    || `<li class="muted" aria-disabled="true">${esc(t("palette.none", { q }))}</li>`;
  $("#palInput", dlg).setAttribute("aria-activedescendant", shown.length ? `pal-${sel}` : "");
  const on = $(`#pal-${sel}`, dlg);
  if (on) on.scrollIntoView({ block: "nearest" });
  list.querySelectorAll("[data-i]").forEach(li => li.onclick = () => go(shown[+li.dataset.i]));
}

function go(x) {
  if (!x) return;
  dlg.close();
  location.hash = x.href;
}

export async function openPalette() {
  if (!dlg) {
    dlg = document.createElement("dialog");
    dlg.className = "palette";
    dlg.setAttribute("aria-label", t("palette.title"));
    dlg.innerHTML = `<input type="search" id="palInput" role="combobox" aria-expanded="true" aria-controls="palList" aria-autocomplete="list"
        placeholder="${esc(t("palette.placeholder"))}" autocomplete="off" spellcheck="false">
      <ul id="palList" role="listbox" aria-label="${esc(t("palette.results"))}"></ul>
      <p class="muted small palette-keys">${esc(t("palette.keys"))}</p>`;
    document.body.append(dlg);
    dlg.addEventListener("click", e => { if (e.target === dlg) dlg.close(); });       // a click outside closes it
    const input = $("#palInput", dlg);
    input.oninput = () => { sel = 0; if (items) render(); };
    input.onkeydown = e => {
      if (!items) return;
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(sel + 1, shown.length - 1); render(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(sel - 1, 0); render(); }
      else if (e.key === "Enter") { e.preventDefault(); go(shown[sel]); }
    };
  }
  const input = $("#palInput", dlg);
  input.value = ""; sel = 0;
  $("#palList", dlg).innerHTML = "";
  dlg.showModal();
  input.focus();
  items = items || await load();                  // what you type meanwhile is kept and searched once it's loaded
  render();
}

/** The data (lessons, charts, songs) may change: load it again next time. */
export function stalePalette() { items = null; }
