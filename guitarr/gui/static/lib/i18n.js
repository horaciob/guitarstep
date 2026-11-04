// Internationalization with i18next. English is the default and the source of truth;
// other languages live in /static/locales/<lang>.json. Learning content (chords, course,
// charts) is authored in English in the data files; translations of that content live in
// the "content" namespace of each locale and fall back to the English data.
import i18next from "../vendor/i18next/i18next.js";

export const LANGS = { en: "English", es: "Español" };
const KEY = "guitarr.lang";

function savedLang() {
  try { return localStorage.getItem(KEY); } catch { return null; }
}

export async function initI18n() {
  const lng = LANGS[savedLang()] ? savedLang() : "en";
  const load = async l => (await fetch(`/static/locales/${l}.json`)).json();
  const resources = { en: await load("en") };
  if (lng !== "en") resources[lng] = await load(lng);
  await i18next.init({
    lng, fallbackLng: "en", resources, defaultNS: "ui", ns: ["ui", "content"],
    // Rendering code escapes with esc() or uses textContent, and *_html keys only get
    // pre-escaped values, so i18next must not escape again.
    interpolation: { escapeValue: false },
    returnEmptyString: false,
  });
  document.documentElement.lang = lng;
  return i18next;
}

export const t = (key, opts) => i18next.t(key, opts);
export const lang = () => i18next.language || "en";

export function setLang(l) {
  try { localStorage.setItem(KEY, l); } catch { /* storage unavailable */ }
  location.reload();
}

/** Translates static markup: data-i18n (text), data-i18n-html, data-i18n-placeholder, data-i18n-title. */
export function applyDom(root = document) {
  root.querySelectorAll("[data-i18n]").forEach(el => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-html]").forEach(el => { el.innerHTML = t(el.dataset.i18nHtml, { interpolation: { escapeValue: false } }); });
  root.querySelectorAll("[data-i18n-placeholder]").forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  root.querySelectorAll("[data-i18n-title]").forEach(el => { el.title = t(el.dataset.i18nTitle); });
}

/** Translated learning content, falling back to the English value from the data file. */
export function tc(path, fallback) {
  const opts = { ns: "content", defaultValue: fallback };
  if (Array.isArray(fallback)) opts.returnObjects = true;
  return i18next.t(path, opts);
}

// ------------------------------------------------------------------ backend messages
/** Text for a judgment detail (`kind` + fields), see guitarr/follow.py. */
export function detailText(d) {
  if (!d) return "";
  switch (d.kind) {
    case "legato": return t("detail.legato");
    case "by_chroma": return t("detail.by_chroma");
    case "chord_ok": return d.unheard && d.unheard.length
      ? t("detail.chord_ok_unheard", { sim: d.sim.toFixed(2), notes: d.unheard.join("/") })
      : t("detail.chord_ok", { sim: d.sim.toFixed(2) });
    case "chord_wrong": {
      const parts = (d.missing || []).map(m => t("detail.missing_note", { note: m.note, interval: t(`interval.${m.interval}`) }));
      (d.extra || []).forEach(n => parts.push(t("detail.extra_note", { note: n })));
      if (!parts.length) parts.push(t("detail.heard", { notes: (d.heard || []).join("/") }));
      return t("detail.chord_wrong", { parts: parts.join(", "), sim: d.sim.toFixed(2), interpolation: { escapeValue: false } });
    }
    case "octave": return t("detail.octave", { note: d.played });
    case "wrong_note": return t("detail.wrong_note", { note: d.played });
    case "unclear": return t("detail.unclear", { heard: d.heard });
    case "missed": return t("detail.missed");
    case "skipped": return d.before ? t("detail.skipped_before", { before: detailText(d.before), interpolation: { escapeValue: false } }) : t("detail.skipped");
    default: return "";
  }
}

export function dtText(ms) {
  if (ms == null) return "";
  if (Math.abs(ms) < 15) return t("timing.on_time");
  return t(ms > 0 ? "timing.late" : "timing.early", { ms: Math.abs(Math.round(ms)) });
}

/** Text for a live message `{code, params, text}`. */
export function msgText(m) {
  if (!m) return "";
  const p = m.params || {};
  const raw = { interpolation: { escapeValue: false } };
  switch (m.code) {
    case "hit": {
      let s = `✓ ${p.label}`;
      if (p.dt_ms != null) s += `  ${dtText(p.dt_ms)}`;
      else if (p.detail) s += `  ${detailText(p.detail)}`;
      if (p.previous_extra) s += `  ${t("msg.previous_extra", { note: p.previous_extra, ...raw })}`;
      return s;
    }
    case "wrong": return `✗ ${t("msg.wrong", { detail: detailText(p.detail), label: p.label, ...raw })}`;
    case "skip": return `∅ ${t("msg.skip", { skipped: p.skipped, label: p.label, ...raw })}`;
    case "extra": return `+ ${t("msg.extra", { note: p.played, ...raw })}`;
    case "pass": return `↻ ${p.new_speed != null
      ? t("msg.pass_speed", { n: p.n, score: Math.round(p.score), from: Math.round(p.old_speed * 100), to: Math.round(p.new_speed * 100) })
      : t("msg.pass", { n: p.n, score: Math.round(p.score) })}`;
    default: return m.text || "";
  }
}

export const msgIsError = m => !!m && ["wrong", "skip", "extra"].includes(m.code);

/** Text for a report issue (live or file mode). */
export function issueText(it) {
  const raw = { interpolation: { escapeValue: false } };
  switch (it.type) {
    case "wrong":
      if (it.detail) return `${it.label}: ${detailText(it.detail)}`;
      return t("issue.played_instead", { played: noteOf(it.user_pitch), expected: noteOf(it.pitch), ...raw });
    case "missed": return `${it.label}: ${detailText(it.detail)}`;
    case "missing": return t("issue.missing", { note: noteOf(it.pitch) });
    case "extra": return t("issue.extra", { note: noteOf(it.user_pitch) });
    case "octave": return t("issue.octave", { note: noteOf(it.pitch), heard: noteOf(it.user_pitch) });
    case "fixed": return t("issue.fixed", { label: it.label, n: it.attempts, last: detailText(it.detail), ...raw });
    case "timing": return `${it.label || noteOf(it.pitch)}: ${dtText(it.dt_ms)}`;
    default: return it.msg || "";
  }
}

const NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
const noteOf = p => p == null ? "?" : NAMES[((p % 12) + 12) % 12] + (Math.floor(p / 12) - 1);

/** Text for a progress event `{code, params}` (see guitarr/progress.py). */
export function eventText(e) {
  const p = e.params || {};
  const raw = { interpolation: { escapeValue: false } };
  switch (e.code) {
    case "exercise_passed": return t("event.exercise_passed", { title: tc(`exercises.${p.lesson}/${p.exercise}`, p.exercise), ...raw });
    case "lesson_completed": return t("event.lesson_completed", { title: tc(`lessons.${p.lesson}.title`, p.lesson), ...raw });
    case "chord_mastered": return t(p.via === "camera" ? "event.chord_camera" : "event.chord_ear", { chord: p.chord });
    case "drill": return t("event.drill", { chords: String(p.chords).replace("-", " ↔ "), n: p.changes });
    case "take_analysis": return t("event.take_analysis", { score: Math.round(p.score) });
    case "practice": return t("event.practice", { name: p.name || "", score: Math.round(p.score), ...raw });
    default: return e.code;
  }
}

/** Error text from an API error detail `{code, message}` (or a plain string). */
export function errorText(detail) {
  if (!detail) return t("errors.generic");
  if (typeof detail === "string") return detail;
  return t(`errors.${detail.code}`, { defaultValue: detail.message });
}
