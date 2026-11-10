// The teaching method in the lesson view: the five steps, understanding vs playing, and the glossary.
// Everything shown here is computed on the server (see _lesson_flow in gui/server.py); this only draws it.
import { lang, t, tc } from "./i18n.js";
import { api, esc, escRe } from "./ui.js";

/** discover → understand → guided → independent → apply, each with a number and a word (and ✓ when done). */
export function stepperHtml(flow) {
  const cur = flow.findIndex(s => !s.done);
  return `<ol class="stepper" aria-label="${esc(t("flow.label"))}">${flow.map((s, i) => `
    <li class="${s.done ? "done" : i === cur ? "cur" : ""}" ${i === cur ? 'aria-current="step"' : ""}>
      <span class="st-num">${s.done ? "✓" : i + 1}</span><span class="st-txt"><b>${esc(t(`flow.${s.step}`))}</b>
      <small>${esc(t(`flow.${s.step}_hint`))}</small></span></li>`).join("")}</ol>`;
}

/** Two separate meters: what you understood (answered) and what you played (heard by the listener). */
export function metersHtml(ls) {
  const m = (icon, key, { done, total }) => total ? `<span class="meter-chip"><span>${icon} ${esc(t(key, { done, total }))}</span>
    <span class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${done}" aria-label="${esc(t(key, { done, total }))}"><i style="width:${Math.round(100 * done / total)}%"></i></span></span>` : "";
  return `<div class="meters-row">${m("🧠", "flow.understood", ls.understood)}${m("🎸", "flow.played", ls.played)}</div>`;
}

// ------------------------------------------------------------------ glossary
let glossary = null;

/** {id: {term, aliases, text}} in the current language (Spanish from the locale, English from the server). */
export async function loadGlossary() {
  if (!glossary) {
    try { glossary = (await api("/api/glossary")).terms; } catch { glossary = {}; }
  }
  const out = {};
  for (const [id, g] of Object.entries(glossary)) {
    out[id] = { term: tc(`glossary.${id}.term`, g.term), aliases: tc(`glossary.${id}.aliases`, g.aliases) || [], text: tc(`glossary.${id}.text`, g.text) };
  }
  return out;
}


/** HTML for a text with the first mention of each glossary term turned into a button (once per `used` set). */
export function linkTerms(text, terms, used) {
  const words = [];
  for (const [id, g] of Object.entries(terms)) for (const w of [g.term, ...g.aliases]) if (w) words.push([w, id]);
  words.sort((a, b) => b[0].length - a[0].length);                 // longer names first ("major scale" before "scale")
  if (!words.length) return esc(text);
  const re = new RegExp(`(^|[^\\p{L}])(${words.map(([w]) => escRe(w)).join("|")})(?![\\p{L}])`, "giu");
  let out = "", last = 0, m;
  while ((m = re.exec(text))) {
    const word = m[2], start = m.index + m[1].length;
    const id = words.find(([w]) => w.toLocaleLowerCase(lang()) === word.toLocaleLowerCase(lang()))?.[1];
    out += esc(text.slice(last, start));
    if (id && !used.has(id)) {
      used.add(id);
      out += `<button type="button" class="term" data-term="${esc(id)}" aria-haspopup="dialog">${esc(word)}</button>`;
    } else out += esc(word);
    last = start + word.length;
  }
  return out + esc(text.slice(last));
}

/** Opens the glossary dialog for a term (or a list of terms), without leaving the page. */
export function openTerms(dlg, terms, ids) {
  dlg.innerHTML = `<form method="dialog" class="dlg-head"><h2>${esc(ids.length === 1 ? terms[ids[0]].term : t("flow.concepts"))}</h2>
      <button class="btn small ghost" value="close" aria-label="${esc(t("rig.close"))}">✕</button></form>
    ${ids.map(id => `<div class="term-def">${ids.length > 1 ? `<h3>${esc(terms[id].term)}</h3>` : ""}<p>${esc(terms[id].text)}</p></div>`).join("")}`;
  dlg.showModal();
}
