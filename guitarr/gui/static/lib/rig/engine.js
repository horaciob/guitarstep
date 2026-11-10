// The tone rig: guitar → pedals → amp → cabinet + mic → effects → looper → master → limiter.
// Runs in the browser (Web Audio) and keeps running while you move around the app, so you can
// practice with your sound. The listener in Python always hears the clean input.
import { api, instrument } from "../ui.js";
import { biquad, dbToGain, gainNode, ramp } from "./dsp.js";
import { buildAmp, buildCab, buildGuitar, EFFECTS } from "./effects.js";
import { defaultRig, normalize } from "./presets.js";
import { VirtualGuitar } from "./synth.js";
import { detectPitch, noteOf } from "./pitch.js";

const WORKLETS = "/static/lib/rig/worklets.js";
const MAX_RECORD_S = 600;           // 10 minutes of stereo 16-bit ≈ 115 MB in memory

class Rig extends EventTarget {
  constructor() {
    super();
    this.state = defaultRig();
    this.source = { kind: "input", deviceId: "", label: "", channel: 1, voice: "electric_single", riff: "open_chords", bpm: null };
    this.preset = null;          // {kind: "factory"|"user", id, name} of the last loaded preset
    this.ctx = null; this.running = false; this.loaded = false;
    this.mods = { fx: new Map() };
    this.irs = new Map();        // impulse responses loaded this session: name → AudioBuffer
    this.looperState = { state: "empty", pos: 0, len: 0, max: 90 };
    this.inputs = [];
  }

  emit(type = "change", detail = null) { this.dispatchEvent(new CustomEvent(type, { detail })); }

  // ---------------------------------------------------------------- persistence
  async load() {
    if (this.loaded) return;
    this.loaded = true;
    try {
      const d = await api("/api/rig");
      this.userPresets = d.presets;
      if (d.current) {
        this.state = normalize(d.current.rig || d.current);
        if (d.current.source) Object.assign(this.source, d.current.source);
        this.preset = d.current.preset || null;
      }
    } catch { this.userPresets = []; }
    this.emit();
  }
  save() {
    clearTimeout(this._saveT);
    this._savePending = true;
    this._saveT = setTimeout(() => this.flush(), 600);
  }
  /** Sends a pending save now; also on page close/reload, so the last change isn't lost. */
  flush() {
    if (!this._savePending) return;
    clearTimeout(this._saveT);
    this._savePending = false;
    fetch("/api/rig/current", {
      method: "PUT", keepalive: true, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rig: { rig: this.state, source: this.source, preset: this.preset } }),
    }).catch(() => {});
  }
  async refreshPresets() {
    try { this.userPresets = (await api("/api/rig")).presets; } catch { /* offline */ }
    this.emit();
  }

  // ---------------------------------------------------------------- start / stop
  async start() {
    if (this.running) return;
    await this.ensureCtx();
    await this.ctx.resume();
    try {
      await this.connectSource();
    } catch (e) {
      await this.ctx.suspend();
      throw e;
    }
    this.running = true;
    this.rebuild(true);
    this.startFreePlay();
    this.emit();
  }

  // ---------------------------------------------------------------- recording your sound (with every effect)
  startRecording() {
    if (!this.running || this.recording) return;
    this.recChunks = []; this.recFrames = 0;
    this.recording = { started: performance.now() };
    this.recorder.port.postMessage("start");
    this.emit();
  }
  onRecordBlock([l, r]) {
    if (!this.recording) return;
    const n = l.length, pcm = new Int16Array(n * 2);
    for (let i = 0; i < n; i++) {
      pcm[2 * i] = Math.max(-1, Math.min(1, l[i])) * 32767;
      pcm[2 * i + 1] = Math.max(-1, Math.min(1, r[i])) * 32767;
    }
    this.recChunks.push(pcm);
    this.recFrames += n;
    if (this.recFrames >= this.ctx.sampleRate * MAX_RECORD_S) this.stopRecording();
  }
  /** Stops and returns the take as a 16-bit stereo WAV blob. */
  stopRecording() {
    if (!this.recording) return null;
    this.recorder.port.postMessage("stop");
    this.recording = null;
    const data = this.recChunks, frames = this.recFrames, sr = this.ctx.sampleRate;
    this.recChunks = [];
    const head = new DataView(new ArrayBuffer(44)), str = (o, s) => [...s].forEach((ch, i) => head.setUint8(o + i, ch.charCodeAt(0)));
    str(0, "RIFF"); head.setUint32(4, 36 + frames * 4, true); str(8, "WAVE"); str(12, "fmt ");
    head.setUint32(16, 16, true); head.setUint16(20, 1, true); head.setUint16(22, 2, true); head.setUint32(24, sr, true);
    head.setUint32(28, sr * 4, true); head.setUint16(32, 4, true); head.setUint16(34, 16, true); str(36, "data");
    head.setUint32(40, frames * 4, true);
    this.lastTake = frames ? new Blob([head, ...data], { type: "audio/wav" }) : null;
    this.lastTakeSeconds = frames / sr;
    this.emit();
    return this.lastTake;
  }
  recordingSeconds() { return this.recording ? (performance.now() - this.recording.started) / 1000 : 0; }

  // ---------------------------------------------------------------- tuner (mutes the output, like a pedal tuner)
  setTuning(on) {
    this.tuning = !!on;
    this.applyLevels();
    this.emit();
  }
  /** Current pitch of the input, or null. */
  pitch() {
    if (!this.running || !this.tunerAn) return null;
    const buf = new Float32Array(this.tunerAn.fftSize);
    this.tunerAn.getFloatTimeDomainData(buf);
    const lowest = 440 * 2 ** ((Math.min(...instrument.strings) - 69) / 12);     // a bass goes down to 41 Hz
    const f = detectPitch(buf, this.ctx.sampleRate, { minHz: Math.min(70, 0.8 * lowest) });
    return f ? { freq: f, ...noteOf(f, 440, instrument.strings) } : null;
  }

  // ---------------------------------------------------------------- MIDI expression pedal
  /** Asks the browser for MIDI access and listens to every input. */
  async connectMidi() {
    if (!navigator.requestMIDIAccess) throw new Error("no_midi");
    this.midiAccess = this.midiAccess || await navigator.requestMIDIAccess();
    const attach = () => this.midiAccess.inputs.forEach(inp => { inp.onmidimessage = e => this.onMidi(e.data); });
    attach();
    this.midiAccess.onstatechange = attach;
    this.emit();
    return [...this.midiAccess.inputs.values()].map(i => i.name);
  }
  learnMidi(on = true) { this.midiLearning = on; this.emit(); }
  setMidiTarget(target) { this.source.midi = { ...(this.source.midi || {}), target }; this.save(); this.emit(); }
  /** Targets an expression pedal can move: the volume, or any knob in the chain. */
  midiTargets() {
    const out = [{ id: "master", type: "master" }];
    for (const where of ["pedals", "post"]) {
      for (const e of this.state[where]) {
        for (const p of EFFECTS[e.type].params) if (p.type !== "choice") out.push({ id: `${e.uid}:${p.id}`, type: e.type, param: p.id });
      }
    }
    return out;
  }
  onMidi(data) {
    const [status, cc, value] = data;
    if ((status & 0xf0) !== 0xb0) return;                     // control change only
    if (this.midiLearning) {
      this.source.midi = { ...(this.source.midi || {}), cc };
      this.midiLearning = false;
      this.save();
      this.emit("midi", { learned: cc });
      this.emit();
      return;
    }
    const m = this.source.midi;
    if (!m || m.cc !== cc || !m.target) return;
    const v = value / 127;
    if (m.target === "master") {
      this.state.master.volume = Math.round((-40 + 40 * v) * 2) / 2;
      this.applyLevels();
      this.save();
      this.emit("param", { target: "master", value: this.state.master.volume });
      return;
    }
    const [uidv, param] = m.target.split(":");
    const f = this.find(uidv);
    const spec = f && EFFECTS[f.e.type].params.find(p => p.id === param);
    if (!spec) return;
    const val = spec.min + (spec.max - spec.min) * v;
    this.setEffectParam(uidv, param, val);
    this.emit("param", { target: m.target, value: val });
  }

  // ---------------------------------------------------------------- free play → practice plan
  /** With your real guitar in, time with signal counts as free play (pauses over 8 s don't). */
  startFreePlay() {
    clearInterval(this._freeT);
    this._freeAcc = 0; this._lastSignal = 0; this._freeSince = Date.now();
    this._freeT = setInterval(() => {
      if (!this.running || this.source.kind !== "input") return;
      const now = performance.now();
      if (this.levels().input > -45) this._lastSignal = now;
      if (this._lastSignal && now - this._lastSignal <= 8000) this._freeAcc += 0.5;
      if (this._freeAcc >= 30) this.flushFreePlay();
    }, 500);
  }
  flushFreePlay() {
    const seconds = Math.round(this._freeAcc || 0);
    const window_s = Math.max(seconds, (Date.now() - (this._freeSince || Date.now())) / 1000);   // the server leaves out time a lesson was listening
    this._freeAcc = 0; this._freeSince = Date.now();
    if (seconds < 1) return;
    fetch("/api/plan/free", { method: "POST", keepalive: true, headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ seconds, window_s }) })
      .then(() => window.dispatchEvent(new CustomEvent("guitarr:plan-refresh"))).catch(() => {});
  }

  async stop() {
    if (!this.running) return;
    if (this.recording) this.stopRecording();
    this.running = false;
    clearInterval(this._freeT);
    this.flushFreePlay();
    this.disconnectSource();
    if (this.ctx) await this.ctx.suspend();
    this.emit();
  }

  async ensureCtx() {
    if (this.ctx) return;
    const ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive" });
    await ctx.audioWorklet.addModule(WORKLETS);
    this.ctx = ctx;
    this.buildFixed();
  }

  buildFixed() {
    const c = this.ctx;
    this.inTrim = gainNode(c);
    this.inMeter = c.createAnalyser(); this.inMeter.fftSize = 1024;
    this.chainIn = gainNode(c);
    this.chainOut = gainNode(c);
    this.mix = gainNode(c);
    this.mixMeter = c.createAnalyser(); this.mixMeter.fftSize = 1024;      // before the master volume
    this.master = gainNode(c);
    this.dcBlock = biquad(c, "highpass", 20);
    this.limiter = c.createDynamicsCompressor();
    this.limiter.threshold.value = -6; this.limiter.knee.value = 0; this.limiter.ratio.value = 20;
    this.limiter.attack.value = 0.002; this.limiter.release.value = 0.1;
    this.outMeter = c.createAnalyser(); this.outMeter.fftSize = 1024;
    this.recorder = new AudioWorkletNode(c, "rig-recorder", { numberOfOutputs: 0 });
    this.recorder.port.onmessage = e => this.onRecordBlock(e.data);
    this.looper = new AudioWorkletNode(c, "rig-looper", { outputChannelCount: [2], processorOptions: { seconds: 90 } });
    this.looper.port.onmessage = e => { this.looperState = e.data; this.emit("looper", e.data); };
    this.tunerAn = c.createAnalyser(); this.tunerAn.fftSize = 4096;
    this.inTrim.connect(this.tunerAn);
    this.inTrim.connect(this.inMeter);
    this.inTrim.connect(this.chainIn);
    this.level = gainNode(c);           // the sound's own level (saved with presets)
    this.chainOut.connect(this.level);
    this.level.connect(this.mix);
    this.level.connect(this.looper).connect(this.mix);
    this.mix.connect(this.mixMeter);
    this.mix.connect(this.master).connect(this.dcBlock).connect(this.limiter).connect(this.outMeter).connect(c.destination);
    this.limiter.connect(this.recorder);
    this.applyLevels();
  }

  applyLevels() {
    if (!this.ctx) return;
    ramp(this.ctx, this.inTrim.gain, dbToGain(this.state.input.trim));
    ramp(this.ctx, this.master.gain, this.tuning ? 0 : dbToGain(this.state.master.volume));
    ramp(this.ctx, this.level.gain, dbToGain(this.state.level || 0));
  }

  // ---------------------------------------------------------------- sources
  async listInputs() {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      this.inputs = all.filter(d => d.kind === "audioinput" && d.deviceId !== "default" && d.deviceId !== "communications");
    } catch { this.inputs = []; }
    return this.inputs;
  }

  /** Picks the browser input that matches the input saved for the listener (same interface). */
  async guessDevice() {
    try {
      const [cfg, dv] = await Promise.all([api("/api/config"), api("/api/devices")]);
      const a = cfg.audio, d = dv.inputs.find(x => x.index === a.device || x.name === a.device);
      if (a.channel) this.source.channel = a.channel;
      if (!d) return;
      const name = d.name.toLowerCase();
      const hit = this.inputs.find(i => i.label && (i.label.toLowerCase().includes(name) || name.includes(i.label.toLowerCase().replace(/\s*\(.*\)$/, ""))));
      if (hit) { this.source.deviceId = hit.deviceId; this.source.label = hit.label; }
    } catch { /* keep the browser default */ }
  }

  async connectSource() {
    this.disconnectSource();
    if (this.source.kind === "virtual") {
      this.vg = new VirtualGuitar(this.ctx, this.inTrim);
      this.vg.setVoice(this.source.voice);
      this.vg.setRiff(this.source.riff);
      if (this.source.bpm) this.vg.setTempo(this.source.bpm);
      this.vg.start();
      return;
    }
    const want = Math.max(2, this.source.channel || 1);
    const constraints = id => ({ audio: {
      ...(id ? { deviceId: { exact: id } } : {}),
      echoCancellation: false, noiseSuppression: false, autoGainControl: false,
      channelCount: { ideal: want }, latency: { ideal: 0.003 } } });
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia(constraints(this.source.deviceId)); }
    catch (e) {
      if (!this.source.deviceId || e.name === "NotAllowedError") throw e;
      stream = await navigator.mediaDevices.getUserMedia(constraints(null));     // the saved device is gone
      this.source.deviceId = "";
    }
    const firstTime = !this.inputs.length;
    await this.listInputs();
    if (firstTime && !this.source.deviceId) {
      await this.guessDevice();
      if (this.source.deviceId && stream.getAudioTracks()[0].getSettings().deviceId !== this.source.deviceId) {
        stream.getTracks().forEach(tr => tr.stop());
        stream = await navigator.mediaDevices.getUserMedia(constraints(this.source.deviceId));
      }
    }
    const track = stream.getAudioTracks()[0], st = track.getSettings();
    if (!this.source.label) this.source.label = track.label;
    this.stream = stream;
    this.srcNode = this.ctx.createMediaStreamSource(stream);
    const nch = st.channelCount || this.srcNode.channelCount || 1;
    this.channels = nch;
    const ch = Math.min(this.source.channel || 1, nch) - 1;
    this.splitter = this.ctx.createChannelSplitter(Math.max(1, nch));
    this.srcNode.connect(this.splitter);
    this.splitter.connect(this.inTrim, ch);
    this.inputLatency = st.latency || 0;
  }

  disconnectSource() {
    if (this.vg) { this.vg.dispose(); this.vg = null; }
    if (this.stream) { this.stream.getTracks().forEach(tr => tr.stop()); this.stream = null; }
    for (const n of [this.srcNode, this.splitter]) if (n) try { n.disconnect(); } catch { /* gone */ }
    this.srcNode = this.splitter = null;
  }

  async setSource(patch) {
    const before = { ...this.source };
    Object.assign(this.source, patch);
    this.save();
    if (this.running) {
      const needsReconnect = ["kind", "deviceId", "channel"].some(k => k in patch && patch[k] !== before[k]);
      if (needsReconnect) {
        try { await this.connectSource(); }
        catch (e) { Object.assign(this.source, before); await this.connectSource().catch(() => {}); this.emit(); throw e; }
      } else if (this.vg) {
        if ("voice" in patch) this.vg.setVoice(patch.voice);
        if ("riff" in patch) this.vg.setRiff(patch.riff);
        if ("bpm" in patch) this.vg.setTempo(patch.bpm);
      }
    }
    this.emit();
  }

  playVirtual(on) {
    if (!this.vg) return;
    if (on) this.vg.start(); else this.vg.stop();
    this.emit();
  }

  // ---------------------------------------------------------------- the chain
  /** Recreates the modules and reconnects them (after a structural change), with a short fade. */
  rebuild(immediate = false) {
    if (!this.ctx || !this.running) return;
    const ir = this.state.cab.ir;
    if (ir && !this.irs.has(ir)) {          // a saved IR: decode it first (once), then build
      this.ensureIR(ir).then(ok => { if (!ok) this.state.cab.ir = null; this.rebuild(immediate); });
      return;
    }
    const token = (this._rb = (this._rb || 0) + 1);
    const go = () => {
      if (token !== this._rb) return;
      this.teardown();
      const c = this.ctx, s = this.state, mods = [];
      this.mods.guitar = buildGuitar(c, s.guitar.type, s.guitar.pickup);
      mods.push(this.mods.guitar);
      for (const e of s.pedals) if (e.on) mods.push(this.fx(e));
      if (s.amp.on) { this.mods.amp = buildAmp(c, s.amp.type, s.amp.params); mods.push(this.mods.amp); }
      if (s.cab.on) { this.mods.cab = buildCab(c, s.cab.type, s.mic, this.irs.get(s.cab.ir) || null); mods.push(this.mods.cab); }
      for (const e of s.post) if (e.on) mods.push(this.fx(e));
      let last = this.chainIn;
      for (const m of mods) { last.connect(m.input); last = m.output; }
      last.connect(this.chainOut);
      ramp(c, this.chainOut.gain, 1, 0.04);
    };
    if (immediate) { this.chainOut.gain.value = 0; go(); return; }
    ramp(this.ctx, this.chainOut.gain, 0, 0.015);
    setTimeout(go, 25);
  }

  fx(e) {
    const m = EFFECTS[e.type].build(this.ctx, { ...e.params });
    this.mods.fx.set(e.uid, m);
    return m;
  }

  teardown() {
    try { this.chainIn.disconnect(); } catch { /* ok */ }
    const all = [this.mods.guitar, this.mods.amp, this.mods.cab, ...this.mods.fx.values()].filter(Boolean);
    for (const m of all) {
      try { m.output.disconnect(); } catch { /* ok */ }
      try { m.dispose(); } catch { /* ok */ }
    }
    this.mods = { fx: new Map() };
  }

  // ---------------------------------------------------------------- edits (all save + emit)
  changed(structural) {
    this.preset = this.preset ? { ...this.preset, edited: true } : null;
    if (structural) this.rebuild();
    this.save();
    this.emit();
  }

  find(uidv) {
    for (const where of ["pedals", "post"]) {
      const i = this.state[where].findIndex(e => e.uid === uidv);
      if (i >= 0) return { where, i, e: this.state[where][i] };
    }
    return null;
  }
  addEffect(where, effect, index = null) {
    const list = this.state[where];
    list.splice(index == null ? list.length : index, 0, effect);
    this.changed(true);
  }
  removeEffect(uidv) {
    const f = this.find(uidv);
    if (!f) return;
    this.state[f.where].splice(f.i, 1);
    this.changed(true);
  }
  moveEffect(uidv, where, index) {
    const f = this.find(uidv);
    if (!f) return;
    this.state[f.where].splice(f.i, 1);
    const list = this.state[where];
    list.splice(Math.max(0, Math.min(index, list.length)), 0, f.e);
    this.changed(true);
  }
  toggleEffect(uidv) {
    const f = this.find(uidv);
    if (!f) return;
    f.e.on = !f.e.on;
    this.changed(true);
  }
  setEffectParam(uidv, k, v) {
    const f = this.find(uidv);
    if (!f) return;
    f.e.params[k] = v;
    const m = this.mods.fx.get(uidv);
    if (m) m.set(k, v);
    this.changed(false);
  }
  setGuitar(patch) {
    const typeChanged = "type" in patch && patch.type !== this.state.guitar.type;
    Object.assign(this.state.guitar, patch);
    if (!typeChanged && this.mods.guitar && "pickup" in patch) this.mods.guitar.set("pickup", patch.pickup);
    this.changed(typeChanged);
  }
  setAmp(patch) {
    const structural = ("type" in patch && patch.type !== this.state.amp.type) || "on" in patch;
    Object.assign(this.state.amp, patch);
    this.changed(structural);
  }
  setAmpParam(k, v) {
    this.state.amp.params[k] = v;
    if (this.mods.amp) this.mods.amp.set(k, v);
    this.changed(false);
  }
  setCab(patch) {
    Object.assign(this.state.cab, patch);
    this.changed(true);
  }
  setMic(patch) {
    const structural = "type" in patch;
    Object.assign(this.state.mic, patch);
    if (!structural && this.mods.cab) Object.entries(patch).forEach(([k, v]) => this.mods.cab.set(k, v));
    this.changed(structural);
  }
  setLevel(which, db) {
    if (which === "input") this.state.input.trim = db;
    else if (which === "level") this.state.level = db;
    else this.state.master.volume = db;
    this.applyLevels();
    if (which === "level") this.preset = this.preset ? { ...this.preset, edited: true } : null;
    this.save();
    this.emit();
  }
  /** Uploads an impulse response to ~/.guitarr/irs and uses it. */
  async loadIR(file) {
    const fd = new FormData();
    fd.append("file", file);
    const saved = await api("/api/rig/irs", { method: "POST", body: fd });
    await this.ensureIR(saved.name, await file.arrayBuffer());
    this.setCab({ ir: saved.name, on: true });
    return saved.name;
  }
  /** Decodes a saved impulse response (once per session). */
  async ensureIR(name, bytes = null) {
    if (!name || this.irs.has(name)) return true;
    if (!this.ctx) { await this.ensureCtx(); if (!this.running) await this.ctx.suspend(); }
    try {
      const data = bytes || await (await fetch(`/api/rig/irs/${encodeURIComponent(name)}`)).arrayBuffer();
      this.irs.set(name, await this.ctx.decodeAudioData(data));
      return true;
    } catch { return false; }
  }
  useIR(name) { this.setCab({ ir: name, on: true }); }
  clearIR() { this.setCab({ ir: null }); }
  async listIRs() { try { return await api("/api/rig/irs"); } catch { return []; } }
  async deleteIR(name) {
    await api(`/api/rig/irs/${encodeURIComponent(name)}`, { method: "DELETE" });
    this.irs.delete(name);
    if (this.state.cab.ir === name) this.clearIR();
  }

  /** Loads a preset or saved sound. Your listening volume and input trim stay as they are. */
  loadState(rigState, preset) {
    const keep = { input: this.state.input, master: this.state.master };
    this.state = { ...normalize(JSON.parse(JSON.stringify(rigState))), ...keep };
    this.preset = preset;
    this.applyLevels();
    this.rebuild();
    this.save();
    this.emit();
  }

  // ---------------------------------------------------------------- looper, meters
  loop(cmd) { if (this.looper && this.running) this.looper.port.postMessage(cmd); }

  levels() {
    const peak = an => {
      if (!an || !this.running) return -120;
      const a = new Float32Array(an.fftSize);
      an.getFloatTimeDomainData(a);
      let p = 0;
      for (const v of a) p = Math.max(p, Math.abs(v));
      return p > 0 ? 20 * Math.log10(p) : -120;
    };
    return { input: peak(this.inMeter), sound: peak(this.mixMeter), output: peak(this.outMeter), reduction: this.limiter ? this.limiter.reduction : 0 };
  }

  latencyMs() {
    if (!this.ctx) return null;
    return Math.round(((this.ctx.baseLatency || 0) + (this.ctx.outputLatency || 0) + (this.inputLatency || 0)) * 1000);
  }
}

export const rig = new Rig();
window.addEventListener("pagehide", () => { rig.flush(); rig.flushFreePlay(); });
window.dispatchEvent(new CustomEvent("guitarr:rig-ready", { detail: rig }));
