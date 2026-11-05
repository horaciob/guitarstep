// The tone rig: guitar → pedals → amp → cabinet + mic → effects → looper → master → limiter.
// Runs in the browser (Web Audio) and keeps running while you move around the app, so you can
// practice with your sound. The listener in Python always hears the clean input.
import { api } from "../ui.js";
import { biquad, dbToGain, gainNode, ramp } from "./dsp.js";
import { buildAmp, buildCab, buildGuitar, EFFECTS } from "./effects.js";
import { defaultRig, normalize } from "./presets.js";
import { VirtualGuitar } from "./synth.js";

const WORKLETS = "/static/lib/rig/worklets.js";

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
    this._saveT = setTimeout(() => {
      api("/api/rig/current", { method: "PUT", json: { rig: { rig: this.state, source: this.source, preset: this.preset } } }).catch(() => {});
    }, 600);
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
    this.emit();
  }

  async stop() {
    if (!this.running) return;
    this.running = false;
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
    this.looper = new AudioWorkletNode(c, "rig-looper", { outputChannelCount: [2], processorOptions: { seconds: 90 } });
    this.looper.port.onmessage = e => { this.looperState = e.data; this.emit("looper", e.data); };
    this.inTrim.connect(this.inMeter);
    this.inTrim.connect(this.chainIn);
    this.level = gainNode(c);           // the sound's own level (saved with presets)
    this.chainOut.connect(this.level);
    this.level.connect(this.mix);
    this.level.connect(this.looper).connect(this.mix);
    this.mix.connect(this.mixMeter);
    this.mix.connect(this.master).connect(this.dcBlock).connect(this.limiter).connect(this.outMeter).connect(c.destination);
    this.applyLevels();
  }

  applyLevels() {
    if (!this.ctx) return;
    ramp(this.ctx, this.inTrim.gain, dbToGain(this.state.input.trim));
    ramp(this.ctx, this.master.gain, dbToGain(this.state.master.volume));
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
  async loadIR(file) {
    if (!this.ctx) { await this.ensureCtx(); if (!this.running) await this.ctx.suspend(); }
    const buf = await this.ctx.decodeAudioData(await file.arrayBuffer());
    if (buf.duration > 3) throw new Error("ir_too_long");
    this.irs.set(file.name, buf);
    this.setCab({ ir: file.name, on: true });
  }
  clearIR() { this.setCab({ ir: null }); }

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
window.dispatchEvent(new CustomEvent("guitarr:rig-ready", { detail: rig }));
