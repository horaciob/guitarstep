// The rig sound that suits a lesson, chart or song, one click away (it loads the sound; the rig stays off until you
// turn it on), and a picker to choose one for a song.
import { t } from "./i18n.js";
import { $, esc, toast } from "./ui.js";
import { rig } from "./rig/engine.js";
import { ARTISTS, FACTORY, factory } from "./rig/presets.js";

export async function toneSuggestion(box, id) {
  if (!box) return;
  if (!id || !factory(id)) { box.innerHTML = ""; box.hidden = true; return; }
  box.hidden = false;
  await rig.load();
  const name = t(`rig.preset.${id}`), using = rig.preset && rig.preset.kind === "factory" && rig.preset.id === id && !rig.preset.edited;
  box.innerHTML = `🎛 ${esc(t("lesson.tone", { name }))} ${using
    ? `<span class="pill ok">✓ ${esc(t("lesson.tone_using"))}</span>`
    : `<button class="btn small" type="button" data-tone-load>${esc(t("lesson.tone_load"))}</button>`} <a class="small" href="#/rig">${esc(t("lesson.tone_rig"))}</a>`;
  const b = $("[data-tone-load]", box);
  if (b) b.onclick = () => {
    rig.loadState(factory(id), { kind: "factory", id });
    toast(t(rig.running ? "lesson.tone_loaded_on" : "lesson.tone_loaded_off", { name }), true);
    toneSuggestion(box, id);
  };
}

/** <option>s of every sound: favorites first, then the factory sounds and the artist tones, alphabetically. */
export async function toneOptions(selected = "") {
  await rig.load();
  const name = id => t(`rig.preset.${id}`);
  const favs = (rig.favorites || []).filter(id => factory(id));
  const sorted = ids => ids.sort((a, b) => name(a).localeCompare(name(b)));
  const opt = id => `<option value="${id}"${id === selected ? " selected" : ""}>${esc(name(id))}</option>`;
  return `<option value="">${esc(t("song.tone_none"))}</option>
    ${favs.length ? `<optgroup label="★ ${esc(t("rig.favorites"))}">${favs.map(opt).join("")}</optgroup>` : ""}
    <optgroup label="${esc(t("rig.factory"))}">${sorted(Object.keys(FACTORY)).map(opt).join("")}</optgroup>
    <optgroup label="${esc(t("rig.artists_title"))}">${sorted(Object.keys(ARTISTS)).map(opt).join("")}</optgroup>`;
}
