// Listening to a recording slower without changing its pitch, with an A–B loop to repeat a passage.
// The audio is the song's own file, or one you open from your computer (it stays in the browser).
import { t } from "./i18n.js";
import { $, esc } from "./ui.js";

const SPEEDS = [0.5, 0.6, 0.7, 0.75, 0.8, 0.9, 1];
const fmt = s => s == null ? "—" : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}.${Math.floor((s % 1) * 10)}`;

/** Mounts the player in `box`. src: a URL to start with (or none: open a file). Returns { stop }. */
export function slowPlayer(box, { src = "", allowFile = true } = {}) {
  let a = null, b = null, raf = 0, objectUrl = "";
  box.innerHTML = `
    ${allowFile ? `<label class="field"><span>${esc(t("slow.open"))}</span><input type="file" accept="audio/*" id="slowFile"></label>
      <p class="muted small">${esc(t("slow.local"))}</p>` : ""}
    <audio id="slowAudio" controls preload="metadata"${src ? ` src="${esc(src)}"` : ""}></audio>
    <div class="row left wrap slow-controls">
      <label class="field-inline small">${esc(t("slow.speed"))}
        <select id="slowSpeed">${SPEEDS.map(s => `<option value="${s}"${s === 1 ? " selected" : ""}>${Math.round(s * 100)}%</option>`).join("")}</select></label>
      <button class="btn small" id="slowA" type="button">${esc(t("slow.set_a"))}</button>
      <button class="btn small" id="slowB" type="button">${esc(t("slow.set_b"))}</button>
      <label class="check small"><input type="checkbox" id="slowLoop"> ${esc(t("slow.loop"))}</label>
      <button class="btn small ghost" id="slowClear" type="button">${esc(t("slow.clear"))}</button>
      <span class="mono small" id="slowAB" aria-live="polite"></span>
    </div>
    <p class="muted small">${esc(t("slow.hint"))}</p>`;
  const audio = $("#slowAudio", box), loop = $("#slowLoop", box);
  const keep = () => { audio.preservesPitch = true; audio.playbackRate = +$("#slowSpeed", box).value; };
  const show = () => {
    $("#slowAB", box).textContent = t("slow.ab", { a: fmt(a), b: fmt(b) });
    loop.disabled = a == null || b == null;
    if (loop.disabled) loop.checked = false;
  };
  const tick = () => {                       // timeupdate fires only ~4 times a second: too coarse for a loop
    if (loop.checked && a != null && b != null && audio.currentTime >= b) audio.currentTime = a;
    raf = requestAnimationFrame(tick);
  };
  audio.addEventListener("play", () => { keep(); cancelAnimationFrame(raf); raf = requestAnimationFrame(tick); });
  audio.addEventListener("pause", () => cancelAnimationFrame(raf));
  audio.addEventListener("loadedmetadata", keep);
  $("#slowSpeed", box).onchange = keep;
  $("#slowA", box).onclick = () => { a = audio.currentTime; if (b != null && b <= a) b = null; show(); };
  $("#slowB", box).onclick = () => {
    const now = audio.currentTime;
    if (a == null || now <= a) return;
    b = now; loop.checked = true; show();
    audio.currentTime = a;
  };
  loop.onchange = () => { if (loop.checked && a != null) audio.currentTime = a; };
  $("#slowClear", box).onclick = () => { a = b = null; show(); };
  const file = $("#slowFile", box);
  if (file) file.onchange = () => {
    const f = file.files[0];
    if (!f) return;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(f);
    audio.src = objectUrl; a = b = null; show();
  };
  show();
  return {
    stop() {
      cancelAnimationFrame(raf); audio.pause();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    },
  };
}
