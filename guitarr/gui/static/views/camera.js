// Camera: detects your hand (MediaPipe) and checks whether you fret the chord in the right places.
// Calibration: 4 clicks on the neck (nut and fret 5, on the 1st and 6th strings). With that, each
// fingertip is mapped to (string, fret) using the real fret spacing.
import { t, tc } from "../lib/i18n.js";
import { $, api, chordSvg, esc, strum, toast } from "../lib/ui.js";
import { listen } from "../lib/listen.js";

const VENDOR = "/static/vendor";
const TIPS = { 1: 8, 2: 12, 3: 16, 4: 20 };           // fingertip landmark of each finger
const CAL_STEPS = ["camera.cal_nut_1", "camera.cal_nut_6", "camera.cal_f5_1", "camera.cal_f5_6"];
const F5 = 1 - 2 ** (-5 / 12);
const KEY = "guitarr.camera";

let stream = null, raf = 0, landmarker = null, earTask = null;

function loadCfg() {
  try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; }
}
function saveCfg(c) {
  try { localStorage.setItem(KEY, JSON.stringify(c)); } catch { /* storage unavailable */ }
}

// ------------------------------------------------------------------ neck geometry
function bilinear(q, u, v) {   // q = [A, B, C, D] = nut·1st, nut·6th, fret5·1st, fret5·6th
  const [A, B, C, D] = q;
  const x = (1 - u) * ((1 - v) * A.x + v * B.x) + u * ((1 - v) * C.x + v * D.x);
  const y = (1 - u) * ((1 - v) * A.y + v * B.y) + u * ((1 - v) * C.y + v * D.y);
  return { x, y };
}

/** Image point → (u along the neck, v across the strings), via Newton's method. */
export function inverse(q, p) {
  let u = 0.5, v = 0.5;
  for (let it = 0; it < 12; it++) {
    const P = bilinear(q, u, v), e = 1e-4;
    const Pu = bilinear(q, u + e, v), Pv = bilinear(q, u, v + e);
    const a = (Pu.x - P.x) / e, b = (Pv.x - P.x) / e, c = (Pu.y - P.y) / e, d = (Pv.y - P.y) / e;
    const det = a * d - b * c;
    if (Math.abs(det) < 1e-12) break;
    const rx = p.x - P.x, ry = p.y - P.y;
    u += (d * rx - b * ry) / det;
    v += (-c * rx + a * ry) / det;
  }
  return { u, v };
}

export const uOfFret = n => (1 - 2 ** (-n / 12)) / F5;
export function fretOfU(u) {
  if (u <= 0) return 0;
  const r = u * F5;
  if (r >= 0.999) return 99;
  return Math.ceil(-12 * Math.log2(1 - r) - 1e-6);   // the finger sits between fret n-1 and n
}

function targetsOf(ch) {
  const out = [];
  ch.frets.forEach((f, i) => {
    if (f > 0) {
      const finger = ch.fingers[i] || 0, s = 6 - i;
      const barre = ch.barre && finger === 1 && f === ch.barre.fret;
      out.push({ string: s, fret: f, finger, barre });
    }
  });
  // a barre is checked with a single point: the index finger on its fret
  let barreSeen = false;
  return out.filter(tg => {
    if (!tg.barre) return true;
    if (barreSeen) return false;
    barreSeen = true;
    return true;
  });
}

// ------------------------------------------------------------------ view
export async function mount(el, { params }) {
  const data = await api("/api/chords");
  const cfg = loadCfg();
  let chord = data.chords.find(c => c.id === (params.chord || cfg.chord)) || data.chords[0];
  let calib = cfg.calib && cfg.calib.length === 4 ? cfg.calib : null, calStep = -1, mirror = cfg.mirror ?? true;
  let hold = 0, lastT = 0, done = false;
  const finger = n => t(`camera.finger_${n}`);

  el.innerHTML = `
    <div class="gl-head"><h1>${esc(t("camera.title"))}</h1>
      <p class="muted">${esc(t("camera.subtitle"))}</p></div>
    <div class="cam-layout">
      <div class="panel cam-stage">
        <div class="cam-box" id="box"><video id="video" playsinline muted></video><canvas id="overlay"></canvas>
          <div class="cam-msg" id="camMsg">${esc(t("camera.off"))}</div></div>
        <div class="row" style="margin-top:12px">
          <button class="btn primary" id="camBtn">${esc(t("camera.turn_on"))}</button>
          <button class="btn" id="calBtn" disabled>${esc(t(calib ? "camera.recalibrate" : "camera.calibrate"))}</button>
          <label class="check"><input type="checkbox" id="mirror" ${mirror ? "checked" : ""}> ${esc(t("camera.mirror"))}</label>
        </div>
      </div>
      <div class="stack">
        <div class="panel">
          <label class="field"><span>${esc(t("camera.chord"))}</span><select id="chord">${data.chords.map(c => `<option value="${esc(c.id)}">${esc(c.id)} — ${esc(tc(`chords.${c.id}.name`, c.name))}</option>`).join("")}</select></label>
          <div class="diagram" id="diag"></div>
          <ul class="finger-list" id="fingers"></ul>
          <div class="holdbar"><i id="hold"></i></div>
          <div class="ex-msg muted" id="verdict">${esc(t("camera.hold"))}</div>
          <button class="btn small" id="earBtn" hidden>${esc(t("camera.now_strum"))}</button>
        </div>
      </div>
    </div>`;
  const video = $("#video", el), canvas = $("#overlay", el), g = canvas.getContext("2d"), msg = $("#camMsg", el);
  const sel = $("#chord", el);
  sel.value = chord.id;

  const showChord = () => {
    $("#diag", el).innerHTML = chordSvg(chord, { size: 140 });
    hold = 0; done = false;
    $("#earBtn", el).hidden = true;
    $("#verdict", el).textContent = t("camera.hold");
    $("#verdict", el).className = "ex-msg muted";
  };
  sel.onchange = () => { chord = data.chords.find(c => c.id === sel.value); saveCfg({ ...loadCfg(), chord: chord.id }); showChord(); };
  showChord();
  $("#box", el).classList.toggle("mirror", mirror);
  $("#mirror", el).onchange = e => { mirror = e.target.checked; $("#box", el).classList.toggle("mirror", mirror); saveCfg({ ...loadCfg(), mirror }); };

  // calibration: clicks on the video (in normalized, un-mirrored video coordinates)
  const calPrompt = k => t("camera.click_on", { where: t(CAL_STEPS[k]) });
  $("#calBtn", el).onclick = () => { calStep = 0; calib = []; msg.hidden = false; msg.textContent = calPrompt(0); };
  canvas.addEventListener("click", e => {
    if (calStep < 0) return;
    const r = canvas.getBoundingClientRect();
    let x = (e.clientX - r.left) / r.width;
    if (mirror) x = 1 - x;
    calib.push({ x, y: (e.clientY - r.top) / r.height });
    calStep++;
    if (calStep < 4) msg.textContent = calPrompt(calStep);
    else { calStep = -1; msg.hidden = true; saveCfg({ ...loadCfg(), calib }); toast(t("camera.calibrated"), true); }
  });

  $("#earBtn", el).onclick = async () => {
    const v = $("#verdict", el);
    v.textContent = t("chords.strum_now", { chord: chord.id });
    earTask = listen({ chord: chord.id, mode: "wait", legato: false }, { timeoutS: 20 });
    try {
      const rep = await earTask.done;
      const ok = rep.award && rep.award.passed;
      v.className = "ex-msg " + (ok ? "ok" : "err");
      v.textContent = ok ? t("camera.both_ok", { chord: chord.id }) : t("camera.not_clean");
    } catch (e) { v.textContent = e.message; } finally { earTask = null; }
  };

  $("#camBtn", el).onclick = async () => {
    if (stream) { stopCamera(); $("#camBtn", el).textContent = t("camera.turn_on"); msg.hidden = false; msg.textContent = t("camera.off"); return; }
    try {
      msg.textContent = t("camera.asking");
      stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
      video.srcObject = stream;
      await video.play();
      $("#box", el).style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;  // the canvas matches the image
      $("#camBtn", el).textContent = t("camera.turn_off");
      $("#calBtn", el).disabled = false;
      msg.textContent = t("camera.loading");
      landmarker = landmarker || await createLandmarker();
      msg.hidden = !!calib;
      if (!calib) msg.textContent = t("camera.calibrate_now");
      loop();
    } catch (e) {
      msg.hidden = false;
      msg.textContent = e.name === "NotAllowedError" ? t("camera.no_permission") : t("camera.open_failed", { error: e.message });
      stopCamera();
    }
  };

  function loop() {
    if (!stream) return;
    raf = requestAnimationFrame(loop);
    if (video.readyState < 2) return;
    if (canvas.width !== video.videoWidth) { canvas.width = video.videoWidth; canvas.height = video.videoHeight; }
    const now = performance.now(), dt = lastT ? (now - lastT) / 1000 : 0;
    lastT = now;
    const res = landmarker.detectForVideo(video, now);
    const W = canvas.width, H = canvas.height;
    g.clearRect(0, 0, W, H);
    if (calStep >= 0) calib.forEach(p => dot(g, p.x * W, p.y * H, 7, "#f4b740"));
    if (!calib || calib.length < 4 || calStep >= 0) return;
    drawNeck(g, calib, W, H);
    const targets = targetsOf(chord);
    let best = { hits: new Set(), tips: [] };
    for (const hand of res.landmarks || []) {
      const tips = Object.entries(TIPS).map(([f, li]) => {
        const p = hand[li], { u, v } = inverse(calib, p);
        return { finger: +f, x: p.x, y: p.y, fret: fretOfU(u), string: 1 + Math.round(v * 5), inside: v > -0.15 && v < 1.15 && u > -0.05 };
      });
      const hits = new Set();
      targets.forEach((tg, k) => {
        if (tips.some(tp => tp.inside && tp.fret === tg.fret && (tg.barre || tp.string === tg.string))) hits.add(k);
      });
      if (hits.size >= best.hits.size) best = { hits, tips };
    }
    targets.forEach((tg, k) => {
      const c = bilinear(calib, (uOfFret(tg.fret - 1) + uOfFret(tg.fret)) / 2, (tg.string - 1) / 5);
      ring(g, c.x * W, c.y * H, 14, best.hits.has(k) ? "#37c98b" : "rgba(255,255,255,.7)");
    });
    best.tips.forEach(tp => dot(g, tp.x * W, tp.y * H, 6, tp.inside ? "#5aa8ff" : "rgba(255,255,255,.35)"));
    $("#fingers", el).innerHTML = targets.map((tg, k) => {
      const where = tg.barre ? t("camera.barre_at", { fret: tg.fret }) : t("camera.string_fret", { string: tg.string, fret: tg.fret });
      return `<li class="${best.hits.has(k) ? "ok" : ""}">${best.hits.has(k) ? "✓" : "○"} ${esc(where)}${tg.finger ? ` <span class="muted">(${esc(finger(tg.finger))})</span>` : ""}</li>`;
    }).join("");
    const all = targets.length && best.hits.size === targets.length;
    hold = all ? hold + dt : Math.max(0, hold - dt * 2);      // grace margin if it moves for an instant
    $("#hold", el).style.width = `${Math.min(100, hold * 100)}%`;
    if (hold >= 1 && !done) {
      done = true;
      $("#verdict", el).className = "ex-msg ok";
      $("#verdict", el).textContent = t("camera.posture_ok", { chord: chord.id });
      $("#earBtn", el).hidden = false;
      strum(chord);
      api("/api/progress/chord", { json: { chord: chord.id, via: "camera" } })
        .then(r => { if (r.xp) toast(t("camera.xp", { xp: r.xp, chord: chord.id }), true); window.dispatchEvent(new CustomEvent("guitarr:progress")); })
        .catch(() => {});
    }
  }
}

async function createLandmarker() {
  const { FilesetResolver, HandLandmarker } = await import(`${VENDOR}/tasks-vision/vision_bundle.mjs`);
  const files = await FilesetResolver.forVisionTasks(`${VENDOR}/mediapipe/wasm`);
  const opts = d => ({ baseOptions: { modelAssetPath: `${VENDOR}/mediapipe/hand_landmarker.task`, delegate: d },
                       runningMode: "VIDEO", numHands: 2 });
  try { return await HandLandmarker.createFromOptions(files, opts("GPU")); }
  catch { return await HandLandmarker.createFromOptions(files, opts("CPU")); }
}

function drawNeck(g, q, W, H) {
  g.lineWidth = 1.5;
  for (let n = 0; n <= 12; n++) {
    const a = bilinear(q, uOfFret(n), 0), b = bilinear(q, uOfFret(n), 1);
    g.strokeStyle = n === 0 ? "rgba(244,183,64,.9)" : n === 5 ? "rgba(244,183,64,.6)" : "rgba(255,255,255,.25)";
    g.beginPath(); g.moveTo(a.x * W, a.y * H); g.lineTo(b.x * W, b.y * H); g.stroke();
  }
  for (let s = 0; s < 6; s++) {
    const a = bilinear(q, 0, s / 5), b = bilinear(q, uOfFret(12), s / 5);
    g.strokeStyle = "rgba(255,255,255,.18)";
    g.beginPath(); g.moveTo(a.x * W, a.y * H); g.lineTo(b.x * W, b.y * H); g.stroke();
  }
}
const dot = (g, x, y, r, c) => { g.fillStyle = c; g.beginPath(); g.arc(x, y, r, 0, 7); g.fill(); };
const ring = (g, x, y, r, c) => { g.strokeStyle = c; g.lineWidth = 3; g.beginPath(); g.arc(x, y, r, 0, 7); g.stroke(); };

function stopCamera() {
  cancelAnimationFrame(raf);
  if (stream) stream.getTracks().forEach(tr => tr.stop());
  stream = null;
}

export function unmount() {
  stopCamera();
  if (earTask) { earTask.stop(); earTask = null; }
}
