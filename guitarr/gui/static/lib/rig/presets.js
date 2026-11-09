// Rig state helpers and factory presets.
import { ampDefaults, EFFECTS } from "./effects.js";

let n = 0;
export const uid = () => `fx${Date.now().toString(36)}${(n++).toString(36)}`;

export function effectDefaults(type) {
  return Object.fromEntries(EFFECTS[type].params.map(p => [p.id, p.def]));
}

export function makeEffect(type, params = {}, on = true) {
  return { uid: uid(), type, on, params: { ...effectDefaults(type), ...params } };
}

export function defaultRig() {
  return {
    v: 1,
    input: { trim: 0 },
    guitar: { type: "as_is", pickup: 0.5 },
    pedals: [makeEffect("gate", {}, false), makeEffect("overdrive", {}, false)],
    amp: { type: "crunch", on: true, params: ampDefaults("crunch") },
    cab: { type: "c2x12_open", on: true },
    mic: { type: "dynamic", position: 0.3, distance: 0.2, room: 0.1 },
    post: [makeEffect("delay", {}, false), makeEffect("reverb", { mix: 2.5 }, true)],
    master: { volume: -12 },
    level: 0,
  };
}

/** Fills in anything missing (older saves, hand-edited files, new parameters). */
export function normalize(r) {
  const d = defaultRig();
  if (!r || typeof r !== "object") return d;
  const fx = list => (Array.isArray(list) ? list : []).filter(e => e && EFFECTS[e.type])
    .map(e => ({ uid: e.uid || uid(), type: e.type, on: e.on !== false, params: { ...effectDefaults(e.type), ...(e.params || {}) } }));
  const ampType = r.amp && r.amp.type;
  return {
    v: 1,
    input: { ...d.input, ...(r.input || {}) },
    guitar: { ...d.guitar, ...(r.guitar || {}) },
    pedals: r.pedals ? fx(r.pedals) : d.pedals,
    amp: ampType ? { type: ampType, on: r.amp.on !== false, params: { ...ampDefaults(ampType), ...(r.amp.params || {}) } } : d.amp,
    cab: { ...d.cab, ...(r.cab || {}) },
    mic: { ...d.mic, ...(r.mic || {}) },
    post: r.post ? fx(r.post) : d.post,
    master: { ...d.master, ...(r.master || {}) },
    level: typeof r.level === "number" ? r.level : 0,
  };
}

const amp = (type, params = {}) => ({ type, on: true, params: { ...ampDefaults(type), ...params } });
const fx = (type, params) => makeEffect(type, params);

/** Factory presets (names in the locale files: rig.preset.<id>). Built fresh each time. */
export const FACTORY = {
  clean_sparkle: () => ({ level: -6, guitar: { type: "single_coil", pickup: 0.4 }, pedals: [fx("compressor", { sustain: 4, blend: 7 })], amp: amp("clean", { gain: 3, treble: 6.5, presence: 6 }),
    cab: { type: "c2x12_open", on: true }, mic: { type: "condenser", position: 0.35, distance: 0.3, room: 0.15 }, post: [fx("chorus", { mix: 4 }), fx("reverb", { type: "hall", mix: 2.5 })] }),
  blues_crunch: () => ({ guitar: { type: "humbucker", pickup: 0.7 }, pedals: [fx("overdrive", { drive: 3.5, tone: 5.5, level: 6 })], amp: amp("tweed", { gain: 5 }),
    cab: { type: "c1x12_open", on: true }, mic: { type: "dynamic", position: 0.3, distance: 0.15, room: 0.1 }, post: [fx("reverb", { type: "room", decay: 1, mix: 2.5 })] }),
  classic_rock: () => ({ level: -3, guitar: { type: "humbucker", pickup: 0.85 }, pedals: [fx("boost", { boost: 4 })], amp: amp("crunch", { gain: 7, mid: 6.5 }),
    cab: { type: "c4x12_closed", on: true }, mic: { type: "dynamic", position: 0.25, distance: 0.1, room: 0.05 }, post: [fx("delay", { time: 320, feedback: 2.5, mix: 2, mode: "analog" })] }),
  modern_metal: () => ({ guitar: { type: "humbucker", pickup: 1 }, pedals: [fx("gate", { threshold: -50 }), fx("overdrive", { drive: 0.5, tone: 6, level: 8 })], amp: amp("high_gain", { gain: 7.5, mid: 3.5, bass: 6, presence: 6.5 }),
    cab: { type: "c4x12_closed", on: true }, mic: { type: "dynamic", position: 0.2, distance: 0.05, room: 0 }, post: [] }),
  smooth_lead: () => ({ level: -3, guitar: { type: "humbucker", pickup: 0.2 }, pedals: [fx("compressor", { sustain: 6 })], amp: amp("lead", { gain: 7.5 }),
    cab: { type: "c4x12_closed", on: true }, mic: { type: "dynamic_large", position: 0.4, distance: 0.2, room: 0.1 }, post: [fx("delay", { time: 440, feedback: 4, mix: 3, mode: "tape" }), fx("reverb", { type: "plate", mix: 2.5 })] }),
  ambient: () => ({ level: -3, guitar: { type: "single_coil", pickup: 0.2 }, pedals: [fx("compressor", { sustain: 5 })], amp: amp("clean", { gain: 2.5, treble: 5.5 }),
    cab: { type: "c2x12_open", on: true }, mic: { type: "condenser", position: 0.5, distance: 0.5, room: 0.3 }, post: [fx("chorus", { mix: 3, rate: 0.4 }), fx("delay", { time: 620, feedback: 6, mix: 4 }), fx("reverb", { type: "hall", decay: 6, mix: 5 })] }),
  funk: () => ({ level: -6, guitar: { type: "single_coil", pickup: 0.6 }, pedals: [fx("compressor", { sustain: 6, attack: 4 }), fx("wah", { mode: "auto", sensitivity: 6, resonance: 7 })], amp: amp("clean", { gain: 3, mid: 5 }),
    cab: { type: "c2x12_open", on: true }, mic: { type: "dynamic", position: 0.35, distance: 0.2, room: 0.05 }, post: [] }),
  surf: () => ({ level: -5, guitar: { type: "single_coil", pickup: 1 }, pedals: [], amp: amp("clean", { gain: 4, treble: 7, bass: 4 }),
    cab: { type: "c2x12_open", on: true }, mic: { type: "dynamic", position: 0.2, distance: 0.2, room: 0.1 }, post: [fx("tremolo", { rate: 6, depth: 5 }), fx("reverb", { type: "spring", decay: 2.5, mix: 5 })] }),
  sixties_fuzz: () => ({ guitar: { type: "p90", pickup: 0.8 }, pedals: [fx("fuzz", { fuzz: 8, tone: 6 })], amp: amp("chime", { gain: 3.5 }),
    cab: { type: "c2x12_open", on: true }, mic: { type: "ribbon", position: 0.3, distance: 0.3, room: 0.2 }, post: [fx("vibrato", { rate: 5, depth: 3 })] }),
  jazz_box: () => ({ level: 1, guitar: { type: "hollow", pickup: 0 }, pedals: [], amp: amp("jazz"),
    cab: { type: "c1x15", on: true }, mic: { type: "ribbon", position: 0.4, distance: 0.3, room: 0.15 }, post: [fx("reverb", { type: "room", decay: 1.2, mix: 2 })] }),
  acoustic_stage: () => ({ level: -12, guitar: { type: "acoustic", pickup: 0.5 }, pedals: [fx("compressor", { sustain: 3 }), fx("eq", { b200: -2, b3200: 2 })], amp: amp("acoustic"),
    cab: { type: "direct", on: true }, mic: { type: "condenser", position: 0.5, distance: 0, room: 0 }, post: [fx("reverb", { type: "hall", mix: 2.5 })] }),
  twelve_shimmer: () => ({ level: 2, guitar: { type: "twelve_string", pickup: 0.5 }, pedals: [fx("compressor", { sustain: 4 })], amp: amp("chime", { gain: 4, treble: 6 }),
    cab: { type: "c2x12_open", on: true }, mic: { type: "condenser", position: 0.4, distance: 0.3, room: 0.2 }, post: [fx("chorus", { mix: 3 }), fx("reverb", { type: "plate", mix: 3 })] }),
  octave_bass: () => ({ level: -18, guitar: { type: "as_is", pickup: 0.5 }, pedals: [fx("octaver", { dry: 4, oct1: 8 }), fx("compressor", { sustain: 4 })], amp: amp("bass"),
    cab: { type: "c4x10_bass", on: true }, mic: { type: "dynamic_large", position: 0.3, distance: 0.2, room: 0 }, post: [] }),
};

const off = (type, params) => makeEffect(type, params, false);

/** Artist-inspired tones: each player's best-known sound approximated with generic gear (names: rig.preset.<id>). */
export const ARTISTS = {
  gilmour_lead: () => ({ level: -11, guitar: { type: "single_coil", pickup: 0.9 }, pedals: [fx("compressor", { sustain: 5, blend: 8 }), fx("fuzz", { fuzz: 6, tone: 4, level: 6 })],
    amp: amp("clean", { gain: 5, bass: 5, mid: 5.5, treble: 6, presence: 5.5, master: 6 }), cab: { type: "c4x12_closed", on: true },
    mic: { type: "dynamic", position: 0.35, distance: 0.2, room: 0.15 }, post: [fx("delay", { time: 460, feedback: 4, mix: 3, mode: "tape" }), fx("reverb", { type: "hall", decay: 3, mix: 2.5 })] }),
  gilmour_clean: () => ({ level: -6, guitar: { type: "single_coil", pickup: 0.35 }, pedals: [fx("compressor", { sustain: 5, blend: 7 })],
    amp: amp("clean", { gain: 3.5, treble: 6, presence: 5.5 }), cab: { type: "c4x12_closed", on: true },
    mic: { type: "condenser", position: 0.4, distance: 0.3, room: 0.2 }, post: [fx("rotary", { speed: "slow", depth: 4, mix: 4 }), fx("delay", { time: 380, feedback: 3, mix: 2.5, mode: "analog" }), fx("reverb", { type: "hall", decay: 3.5, mix: 3 })] }),
  slash_lead: () => ({ level: -3, guitar: { type: "humbucker", pickup: 0.2 }, pedals: [off("wah", { mode: "manual", pedal: 6, resonance: 6 })],
    amp: amp("lead", { gain: 7.5, bass: 5, mid: 6.5, treble: 5.5, presence: 5.5 }), cab: { type: "c4x12_closed", on: true },
    mic: { type: "dynamic", position: 0.3, distance: 0.15, room: 0.1 }, post: [fx("delay", { time: 420, feedback: 2.5, mix: 2, mode: "analog" }), fx("reverb", { type: "plate", decay: 1.5, mix: 1.5 })] }),
  srv_texas: () => ({ level: -17, guitar: { type: "single_coil", pickup: 0.3 }, pedals: [fx("overdrive", { drive: 2, tone: 6, level: 8 })],
    amp: amp("clean", { gain: 6, bass: 5, mid: 4.5, treble: 6.5, presence: 6, master: 7 }), cab: { type: "c2x10", on: true },
    mic: { type: "dynamic", position: 0.3, distance: 0.15, room: 0.1 }, post: [fx("reverb", { type: "spring", decay: 1.8, mix: 2.5 })] }),
  hendrix_vibe: () => ({ level: -3, guitar: { type: "single_coil", pickup: 0.5 }, pedals: [fx("fuzz", { fuzz: 7.5, tone: 6, level: 6 }), off("wah", { mode: "manual", pedal: 5 })],
    amp: amp("crunch", { gain: 6, mid: 6, treble: 6 }), cab: { type: "c4x12_closed", on: true },
    mic: { type: "dynamic", position: 0.3, distance: 0.2, room: 0.15 }, post: [fx("phaser", { rate: 1.2, depth: 6, mix: 5, stages: "4" }), fx("reverb", { type: "room", decay: 1.2, mix: 2 })] }),
  hendrix_octave: () => ({ level: -3, guitar: { type: "single_coil", pickup: 0.2 }, pedals: [fx("octave_fuzz", { fuzz: 7, tone: 6, level: 5 })],
    amp: amp("crunch", { gain: 6.5, mid: 6 }), cab: { type: "c4x12_closed", on: true },
    mic: { type: "dynamic", position: 0.3, distance: 0.2, room: 0.15 }, post: [fx("reverb", { type: "room", decay: 1.2, mix: 2 })] }),
  page_riff: () => ({ level: -3, guitar: { type: "humbucker", pickup: 0.9 }, pedals: [fx("boost", { boost: 5, tilt: 1 })],
    amp: amp("crunch", { gain: 6.5, mid: 6, treble: 6.5, presence: 6 }), cab: { type: "c4x12_closed", on: true },
    mic: { type: "dynamic", position: 0.3, distance: 0.35, room: 0.35 }, post: [fx("delay", { time: 110, feedback: 1, mix: 1.5, mode: "tape" })] }),
  clapton_woman: () => ({ level: -3, guitar: { type: "humbucker", pickup: 0 }, pedals: [],
    amp: amp("crunch", { gain: 7.5, bass: 5.5, mid: 7, treble: 2.5, presence: 3.5 }), cab: { type: "c4x12_closed", on: true },
    mic: { type: "dynamic", position: 0.4, distance: 0.2, room: 0.15 }, post: [fx("reverb", { type: "room", decay: 1, mix: 1.5 })] }),
  clapton_strat: () => ({ level: -1, guitar: { type: "single_coil", pickup: 0.5 }, pedals: [fx("compressor", { sustain: 3, blend: 6 }), fx("eq", { b800: 3 })],
    amp: amp("tweed", { gain: 4.5, mid: 6.5 }), cab: { type: "c2x12_open", on: true },
    mic: { type: "dynamic", position: 0.35, distance: 0.2, room: 0.1 }, post: [fx("chorus", { rate: 0.6, depth: 3, mix: 2 }), fx("reverb", { type: "plate", mix: 2 })] }),
  bb_king: () => ({ level: 0, guitar: { type: "humbucker", pickup: 0.6 }, pedals: [],
    amp: amp("clean", { gain: 4.5, bass: 4, mid: 6, treble: 6.5, presence: 5.5 }), cab: { type: "c2x12_open", on: true },
    mic: { type: "dynamic", position: 0.3, distance: 0.2, room: 0.15 }, post: [fx("reverb", { type: "plate", decay: 1.6, mix: 2.5 })] }),
  knopfler_clean: () => ({ level: -9, guitar: { type: "single_coil", pickup: 0.55 }, pedals: [fx("compressor", { sustain: 6, blend: 8 })],
    amp: amp("clean", { gain: 4, mid: 5.5, treble: 6 }), cab: { type: "c2x12_open", on: true },
    mic: { type: "condenser", position: 0.35, distance: 0.25, room: 0.15 }, post: [fx("chorus", { rate: 0.5, depth: 2.5, mix: 2 }), fx("reverb", { type: "plate", mix: 2.5 })] }),
  angus_crunch: () => ({ level: -3, guitar: { type: "humbucker", pickup: 1 }, pedals: [],
    amp: amp("crunch", { gain: 5.5, mid: 6.5, treble: 6.5, presence: 6, master: 7 }), cab: { type: "c4x12_closed", on: true },
    mic: { type: "dynamic", position: 0.25, distance: 0.15, room: 0.2 }, post: [] }),
  santana_sustain: () => ({ level: -3, guitar: { type: "humbucker", pickup: 0.15 }, pedals: [],
    amp: amp("lead", { gain: 7, bass: 5, mid: 7, treble: 5, presence: 5 }), cab: { type: "c1x12_open", on: true },
    mic: { type: "dynamic_large", position: 0.35, distance: 0.2, room: 0.1 }, post: [fx("delay", { time: 380, feedback: 3, mix: 2.5, mode: "analog" }), fx("reverb", { type: "plate", mix: 2.5 })] }),
};

export function factory(id) {
  const f = FACTORY[id] || ARTISTS[id];
  return f ? normalize({ ...defaultRig(), ...f() }) : defaultRig();
}
