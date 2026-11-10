// Reading text aloud with the browser's own voices (no download, works offline on most systems).
import { lang, t } from "./i18n.js";
import { esc } from "./ui.js";

export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;

// Spanish: a Latin American voice first (es-AR, then es-419 / es-US / es-MX), then any Spanish one.
const PREFER = { es: ["es-AR", "es-419", "es-US", "es-MX", "es-ES"], en: ["en-US", "en-GB"] };
function voiceFor(code) {
  const voices = speechSynthesis.getVoices();
  const base = code.split("-")[0];
  for (const want of PREFER[base] || []) {
    const v = voices.find(x => x.lang.replace("_", "-").toLowerCase() === want.toLowerCase());
    if (v) return v;
  }
  return voices.find(x => x.lang.toLowerCase().startsWith(base)) || null;
}

let playing = null;           // the button whose text is being read

function reset(btn) {
  if (!btn) return;
  btn.setAttribute("aria-pressed", "false");
  btn.textContent = "🔊";
  btn.title = t("speak.read");
  btn.setAttribute("aria-label", t("speak.read"));
}

export function stopSpeaking() {
  if (!canSpeak()) return;
  const b = playing;
  playing = null;
  speechSynthesis.cancel();
  reset(b);
}

/** Reads `text` aloud, or stops if this button is already reading. */
export function toggleSpeak(btn, text) {
  if (!canSpeak()) return;
  if (playing === btn) { stopSpeaking(); return; }
  stopSpeaking();
  const u = new SpeechSynthesisUtterance(text);
  const code = lang();
  u.lang = code.startsWith("es") ? "es-AR" : code;
  const v = voiceFor(code);
  if (v) { u.voice = v; u.lang = v.lang; }
  u.rate = 0.95;
  u.onend = u.onerror = () => { if (playing === btn) { playing = null; reset(btn); } };
  playing = btn;
  btn.setAttribute("aria-pressed", "true");
  btn.textContent = "⏹";
  btn.title = t("speak.stop");
  btn.setAttribute("aria-label", t("speak.stop"));
  speechSynthesis.speak(u);
}

/** HTML for a read-aloud button (nothing when the browser has no voices). */
export function speakButton(extra = "") {
  if (!canSpeak()) return "";
  return `<button type="button" class="btn small ghost speak-btn" data-speak ${extra} aria-pressed="false" title="${esc(t("speak.read"))}" aria-label="${esc(t("speak.read"))}">🔊</button>`;
}

/** Plain text of an element, as a voice should read it (one sentence per list item). */
export function readable(el) {
  if (!el) return "";
  const items = [...el.querySelectorAll("li")];
  const parts = items.length ? items.map(li => li.textContent) : [el.textContent];
  return parts.map(x => x.replace(/🔊|⏹|📖/g, "").replace(/\s+/g, " ").trim()).filter(Boolean)
    .map(x => /[.!?:]$/.test(x) ? x : x + ".").join(" ");
}
