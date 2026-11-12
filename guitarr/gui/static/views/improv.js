// Improvise: play whatever you like over a backing (bass, drums and the metronome). Every note is heard against
// the chord of the moment and the scale; the server grades the solo and says the one or two things to work on.
import { msgText, t } from "../lib/i18n.js";
import { $, api, esc, instrument, NOTE_NAMES } from "../lib/ui.js";
import { neck } from "../lib/fretboard.js";
import { listen } from "../lib/listen.js";

const SCALES = ["follow", "minor_pentatonic", "major_pentatonic", "blues", "natural_minor", "major", "dorian", "mixolydian"];
const KEYS = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];

let task = null;

export function stopImprov() { if (task) task.stop(); task = null; }

export async function improvise(box) {
  const [prog, backings] = await Promise.all([api("/api/progress"), api("/api/improv/backings")]);
  const BACKINGS = Object.keys(backings);
  const best = id => (prog.improv || {})[id]?.best;
  box.innerHTML = `
    <div class="panel">
      <p class="muted">${esc(t("improv.intro"))}</p>
      <div class="row left wrap">
        <label class="field-inline">${esc(t("improv.backing"))} <select id="iBacking">${BACKINGS.map(b =>
          `<option value="${b}">${esc(t(`improv.backing_${b}`))}${best(b) != null ? ` · ${Math.round(best(b))}` : ""}</option>`).join("")}</select></label>
        <label class="field-inline">${esc(t("improv.key"))} <select id="iKey">${KEYS.map(k => `<option>${k}</option>`).join("")}</select></label>
        <label class="field-inline">${esc(t("improv.scale"))} <select id="iScale">${SCALES.map(s =>
          `<option value="${s}">${esc(t(`improv.scale_${s}`))}</option>`).join("")}</select></label>
        <label class="field-inline">${esc(t("rhythm.bpm"))} <input type="number" id="iBpm" min="40" max="200"></label>
        <label class="field-inline">${esc(t("improv.choruses"))} <select id="iChoruses">${[1, 2, 4].map(n => `<option${n === 2 ? " selected" : ""}>${n}</option>`).join("")}</select></label>
        <label class="check"><input type="checkbox" id="iBand" checked> ${esc(t("improv.band"))}</label>
      </div>
      <p class="muted small" id="iChords"></p>
      <div id="iNeck" class="improv-neck"></div>
      <div class="row center"><button class="btn primary xl" id="iGo">▶ ${esc(t("improv.start"))}</button></div>
      <div class="improv-now" id="iNow" hidden aria-live="polite">
        <div><small class="muted">${esc(t("improv.now"))}</small><b id="iChord">—</b></div>
        <div><small class="muted">${esc(t("improv.next"))}</small><span id="iNext">—</span></div>
        <div class="improv-counts" id="iCounts"></div>
      </div>
      <p class="ex-msg muted center" id="iMsg" aria-live="polite"></p>
      <div id="iOut"></div>
    </div>`;
  const pick = () => {
    const b = backings[$("#iBacking", box).value];
    $("#iKey", box).value = b.key; $("#iScale", box).value = b.scale; $("#iBpm", box).value = b.bpm;
    showScale();
  };
  const showScale = async () => {
    const backing = $("#iBacking", box).value, scale = $("#iScale", box).value, key = $("#iKey", box).value;
    $("#iChords", box).textContent = t("improv.chords", { chords: backings[backing].bars.join(" | ") });
    const nb = $("#iNeck", box);
    if (scale === "follow") { nb.innerHTML = `<p class="muted small">${esc(t("improv.follow_hint"))}</p>`; return; }
    let tones;
    try { tones = (await api(`/api/theory/scale?key=${encodeURIComponent(key)}&name=${scale}`)).notes; } catch { nb.innerHTML = ""; return; }
    const byPc = new Map(tones.map(x => [x.pc, x])), root = tones[0].pc, marks = [];
    instrument.strings.forEach((open, i) => {
      for (let f = 0; f <= 12; f++) {
        const tn = byPc.get((open + f) % 12);
        if (tn) marks.push({ string: i + 1, fret: f, text: tn.note || NOTE_NAMES[tn.pc], kind: tn.pc === root ? "root" : "tone" });
      }
    });
    neck(nb, { lo: 0, hi: 12, marks, label: t("improv.scale_label", { key, scale: t(`improv.scale_${scale}`) }) });
  };
  $("#iBacking", box).onchange = pick;
  $("#iKey", box).onchange = showScale;
  $("#iScale", box).onchange = showScale;
  pick();

  $("#iGo", box).onclick = async () => {
    if (task) { task.stop(); return; }
    const go = $("#iGo", box), msg = $("#iMsg", box), now = $("#iNow", box);
    go.textContent = `■ ${t("lesson.stop")}`;
    msg.className = "ex-msg muted center";
    msg.textContent = t("lesson.wait_count_in");
    $("#iOut", box).innerHTML = "";
    now.hidden = false;
    task = listen({
      improv: { backing: $("#iBacking", box).value, key: $("#iKey", box).value, scale: $("#iScale", box).value,
                bpm: +$("#iBpm", box).value, choruses: +$("#iChoruses", box).value },
      click: true, backing: $("#iBand", box).checked,
    }, {
      onState: s => {
        if (s.countdown) msg.textContent = t("lesson.count_in", { n: s.countdown });
        const im = s.improv;
        if (!im) return;
        $("#iChord", box).textContent = im.chord || "—";
        $("#iNext", box).textContent = im.next || "—";
        $("#iCounts", box).innerHTML = ["chord", "scale", "outside"].map(k =>
          `<span class="improv-c ${k}">${esc(t(`improv.count_${k}`, { n: im.counts[k] }))}</span>`).join("");
      },
      onMessage: m => {
        if (m.code !== "improv") return;
        msg.textContent = msgText(m);
        msg.className = `ex-msg center ${m.params.cls === "outside" ? "err" : "ok"}`;
      },
    });
    try {
      const rep = await task.done;
      now.hidden = true;
      $("#iOut", box).innerHTML = reportHtml(rep);
      msg.className = "ex-msg muted center";
      msg.textContent = rep.award && rep.award.xp ? `+${rep.award.xp} XP${rep.award.record ? ` · ${t("improv.record")}` : ""}` : "";
    } catch (e) { msg.className = "ex-msg err center"; msg.textContent = e.message; now.hidden = true; }
    finally { task = null; go.textContent = `▶ ${t("improv.start")}`; }
  };
}

function reportHtml(rep) {
  const s = rep.summary;
  if (s.score == null) return `<p class="muted center">${esc(t(s.n ? "improv.too_few" : "lesson.not_played", { n: s.n }))}</p>`;
  const stat = (v, l, cls = "") => `<div class="stat ${cls}"><div class="v">${esc(v)}</div><div class="l">${esc(l)}</div></div>`;
  const grade = v => v >= 80 ? "good" : v >= 60 ? "warn" : "bad";
  return `<div class="summary">
      ${stat(Math.round(s.score), t("report.score"), grade(s.score))}
      ${stat(`${s.fits_pct}%`, t("improv.fits"), grade(s.fits_pct))}
      ${s.landing_pct != null ? stat(`${s.landing_pct}%`, t("improv.landing")) : ""}
      ${stat(`${s.space_pct}%`, t("improv.space"))}
      ${stat(t("improv.semitones", { n: s.span }), t("improv.range"))}
      ${stat(s.distinct, t("improv.distinct"))}
    </div>
    <p class="small">${esc(t("improv.counts", s.counts))}</p>
    ${s.tips.length ? `<ul class="improv-tips">${s.tips.map(k => `<li>${esc(t(`improv.tip_${k}`))}</li>`).join("")}</ul>`
      : `<p class="callout small ok">${esc(t("improv.tip_none"))}</p>`}`;
}
