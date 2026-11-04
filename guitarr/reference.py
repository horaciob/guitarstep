"""Carga de referencias (MIDI, Guitar Pro, audio) y transcripción audio→notas con caché."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import subprocess
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import config
from .core import STANDARD_TUNING, Grid, Note, Reference

MIDI_EXT = {".mid", ".midi"}
GP_EXT = {".gp3", ".gp4", ".gp5", ".gtp"}
AUDIO_EXT = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aif", ".aiff"}
REFERENCE_EXT = MIDI_EXT | GP_EXT | AUDIO_EXT

Log = Callable[[str], None]


class ReferenceError(Exception):
    """Error de usuario al cargar la referencia (mensaje listo para mostrar)."""


@dataclass
class RefOptions:
    path: Path | None = None
    track: str | None = None
    separate: bool = False
    start_bar: int | None = None
    end_bar: int | None = None
    bpm: float | None = None
    first_beat: float = 0.0
    beats_per_bar: int = 4
    onset_threshold: float = 0.5
    frame_threshold: float = 0.3
    min_amp: float = 0.2
    chart: dict | None = None       # cifrado de acordes, en vez de un archivo
    notes: list[int] | None = None  # secuencia de notas MIDI (ejercicios de la ruta)

    @property
    def tx(self) -> dict:
        return dict(onset_threshold=self.onset_threshold, frame_threshold=self.frame_threshold,
                    min_amp=self.min_amp)


def file_hash(path: Path, *extra) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    h.update(repr(extra).encode())
    return h.hexdigest()[:16]


# ---------------------------------------------------------------- transcripción (basic-pitch)
HARMONIC_INTERVALS = {12, 19, 24, 28, 31, 36}  # 2do..8vo armónico en semitonos


def clean_notes(notes: list[Note], win: float = 0.05) -> list[Note]:
    """Quita los dos artefactos típicos de la transcripción de guitarra:

    - armónicos: nota débil que arranca junto con una más grave y fuerte, a un
      intervalo armónico (octava, 12va, 2 octavas...).
    - resonancia: la nota anterior que sigue sonando y se re-detecta como nota
      corta y débil justo en el ataque de la siguiente.

    O(n·k) con k = notas en la ventana: usa búsqueda binaria sobre los ataques.
    """
    notes = sorted(notes, key=lambda n: (n.start, n.pitch))
    starts = np.array([n.start for n in notes])
    by_pitch: dict[int, list[Note]] = {}
    for n in notes:
        by_pitch.setdefault(n.pitch, []).append(n)
    keep = []
    for i, n in enumerate(notes):
        lo = int(np.searchsorted(starts, n.start - win, side="left"))
        hi = int(np.searchsorted(starts, n.start + win, side="right"))
        stronger = [notes[j] for j in range(lo, hi) if j != i and notes[j].amp > n.amp]
        drop = any((n.pitch - m.pitch) in HARMONIC_INTERVALS and n.amp < 0.65 * m.amp for m in stronger)
        if not drop and stronger:
            drop = any(abs(p.end - n.start) < 0.08 and p.start < n.start - win for p in by_pitch[n.pitch])
        if not drop:
            keep.append(n)
    return keep


def _quiet_import_basic_pitch():
    root = logging.getLogger()
    lvl = root.level
    root.setLevel(logging.ERROR)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from basic_pitch import ICASSP_2022_MODEL_PATH
            from basic_pitch.inference import predict
    finally:
        root.setLevel(lvl)
    return predict, ICASSP_2022_MODEL_PATH


def transcribe(path: Path, onset_threshold: float = 0.5, frame_threshold: float = 0.3,
               min_amp: float = 0.2, use_cache: bool = True) -> list[Note]:
    path = Path(path)
    key = file_hash(path, "tx-v1", onset_threshold, frame_threshold)
    cache = config.CACHE_DIR / "transcripciones" / f"{key}.json"
    raw = None
    if use_cache and cache.exists():
        try:
            raw = json.loads(cache.read_text())
        except (OSError, json.JSONDecodeError):
            raw = None
    if raw is None:
        predict, model = _quiet_import_basic_pitch()
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():  # CoreML imprime debug
            warnings.simplefilter("ignore")
            _, _, events = predict(
                str(path), model,
                onset_threshold=onset_threshold, frame_threshold=frame_threshold,
                minimum_note_length=60,       # ms
                minimum_frequency=75,         # ~D2, por debajo de la 6ta en Drop D
                maximum_frequency=1400,       # ~F6, traste 24 de la 1ra
                melodia_trick=True,
            )
        raw = [[float(s), float(e), int(p), float(a)] for s, e, p, a, *_ in events]
        if use_cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(raw))
    notes = [Note(s, e, p, a) for s, e, p, a in raw if a >= min_amp]
    return clean_notes(notes)


def separate_guitar(path: Path, log: Log = print) -> Path:
    """Aísla la guitarra con Demucs (modelo de 6 stems), con caché por contenido."""
    outdir = config.CACHE_DIR / "separado" / file_hash(path)
    out = outdir / "htdemucs_6s" / path.stem / "guitar.wav"
    if out.exists():
        log(f"[demucs] uso la separación guardada: {out}")
        return out
    log(f"[demucs] separando guitarra de {path.name} (puede tardar)...")
    try:
        subprocess.run([sys.executable, "-m", "demucs", "-n", "htdemucs_6s", "--two-stems", "guitar",
                        "-o", str(outdir), str(path)], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise ReferenceError("Falló Demucs. ¿Está instalado? pip install demucs") from e
    log(f"[demucs] guitarra aislada: {out}")
    return out


def audio_grid(path: Path) -> Grid:
    key = file_hash(path, "beats-v1")
    cache = config.CACHE_DIR / "pulsos" / f"{key}.json"
    if cache.exists():
        beats = json.loads(cache.read_text())
    else:
        import librosa

        y, sr = librosa.load(str(path), sr=22050, mono=True)
        _, b = librosa.beat.beat_track(y=y, sr=sr, units="time")
        beats = [float(x) for x in b]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(beats))
    return Grid(beats, 4)


def save_midi(notes: list[Note], path: Path) -> None:
    import pretty_midi

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=25)
    inst.notes = [pretty_midi.Note(int(np.clip(n.amp * 127, 1, 127)), n.pitch, n.start, n.end)
                  for n in notes]
    pm.instruments.append(inst)
    pm.write(str(path))


# ---------------------------------------------------------------- tablatura
def assign_tab(notes: list[Note], tuning: list[int] = STANDARD_TUNING, max_fret: int = 22,
               win: float = 0.035) -> None:
    """Elige cuerda/traste para las notas que no lo traen, intentando no mover
    mucho la mano (heurística greedy: la nota más aguda del acorde va primero)."""
    hand = 5.0
    i = 0
    notes_sorted = sorted(notes, key=lambda n: (n.start, -n.pitch))
    while i < len(notes_sorted):
        j = i
        while j < len(notes_sorted) and notes_sorted[j].start - notes_sorted[i].start <= win:
            j += 1
        group = notes_sorted[i:j]
        used = {n.string for n in group if n.string}
        frets = []
        for n in sorted(group, key=lambda n: -n.pitch):
            if n.string:
                if n.fret:
                    frets.append(n.fret)
                continue
            best = None
            for s, open_p in enumerate(tuning, start=1):
                f = n.pitch - open_p
                if s in used or not 0 <= f <= max_fret:
                    continue
                cost = 1.5 if f == 0 else abs(f - hand) + 0.05 * f
                if best is None or cost < best[0]:
                    best = (cost, s, f)
            if best:
                n.string, n.fret = best[1], best[2]
                used.add(best[1])
                if best[2]:
                    frets.append(best[2])
        if frets:
            hand = 0.6 * hand + 0.4 * float(np.mean(frets))
        i = j


# ---------------------------------------------------------------- MIDI
def _midi_instruments(pm):
    return [i for i in pm.instruments if not i.is_drum and i.notes]


def _pick(items, track: str | None, name_of, is_guitar, path: Path, log: Log):
    if track is not None:
        sel = [x for k, x in enumerate(items) if track == str(k) or track.lower() in (name_of(x) or "").lower()]
        if not sel:
            raise ReferenceError(f"No encontré la pista '{track}'. Mirá las pistas con: guitarr tracks {path}")
        return sel[0]
    if len(items) > 1:
        guitars = [x for x in items if is_guitar(x)] or items
        log(f"⚠️  El archivo tiene {len(items)} pistas; uso '{name_of(guitars[0]) or 'sin nombre'}'. "
            f"Elegí otra con --track (ver: guitarr tracks {path})")
        return guitars[0]
    return items[0]


def load_midi(path: Path, track: str | None = None, log: Log = print) -> Reference:
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(path))
    insts = _midi_instruments(pm)
    if not insts:
        raise ReferenceError("El MIDI no tiene pistas con notas.")
    inst = _pick(insts, track, lambda i: i.name, lambda i: 24 <= i.program <= 31, path, log)
    notes = sorted((Note(n.start, n.end, n.pitch, n.velocity / 127) for n in inst.notes),
                   key=lambda n: (n.start, n.pitch))
    beats = pm.get_beats()
    downs = pm.get_downbeats()
    bar_starts = np.unique(np.clip(np.searchsorted(beats, downs - 1e-6), 0, len(beats) - 1))
    sigs = pm.time_signature_changes
    bpb = sigs[-1].numerator if sigs else 4
    grid = Grid(beats, bpb, bar_starts)
    assign_tab(notes)
    return Reference(notes, grid, name=path.stem, path=str(path), track=inst.name or track)


# ---------------------------------------------------------------- Guitar Pro
def _gp_tracks(song):
    return [t for t in song.tracks if not t.isPercussionTrack]


def load_gp(path: Path, track: str | None = None, log: Log = print) -> Reference:
    """Guitar Pro 3-5: trae cuerda y traste reales. Las repeticiones se leen tal cual
    están escritas (sin desplegarlas)."""
    import guitarpro

    try:
        song = guitarpro.parse(str(path))
    except Exception as e:  # formato inválido / versión no soportada
        raise ReferenceError(f"No pude leer el archivo Guitar Pro: {e}") from e
    tracks = _gp_tracks(song)
    if not tracks:
        raise ReferenceError("El archivo no tiene pistas de guitarra.")
    tr = _pick(tracks, track, lambda t: t.name, lambda t: len(t.strings) in (6, 7, 8), path, log)

    # mapa de tempo (ticks -> segundos) con los cambios de tempo de todas las pistas
    changes = {0: float(song.tempo)}
    t0 = song.measureHeaders[0].start if song.measureHeaders else 0
    for t in song.tracks:
        for m in t.measures:
            for v in m.voices:
                for b in v.beats:
                    mt = b.effect.mixTableChange
                    if mt is not None and mt.tempo is not None and mt.tempo.value > 0:
                        changes[b.start - t0] = float(mt.tempo.value)
    ticks = np.array(sorted(changes))
    bpms = np.array([changes[k] for k in ticks])
    secs = np.concatenate([[0.0], np.cumsum(np.diff(ticks) * 60 / (bpms[:-1] * 960))])

    def sec(tick: float) -> float:
        tick -= t0
        i = int(np.searchsorted(ticks, tick, side="right") - 1)
        i = max(i, 0)
        return float(secs[i] + (tick - ticks[i]) * 60 / (bpms[i] * 960))

    beats, bar_starts = [], []
    for h in song.measureHeaders:
        bar_starts.append(len(beats))
        unit = h.timeSignature.denominator.time
        for k in range(h.timeSignature.numerator):
            beats.append(sec(h.start + k * unit))
    last = song.measureHeaders[-1] if song.measureHeaders else None
    if last is not None:
        beats.append(sec(last.end))
    tuning = [s.value for s in tr.strings]
    capo = int(getattr(tr, "offset", 0) or 0)

    notes: list[Note] = []
    open_by_string: dict[int, Note] = {}
    for m in tr.measures:
        for v in m.voices:
            for b in v.beats:
                if b.start is None:
                    continue
                s_t = sec(b.start)
                for n in b.notes:
                    dur_ticks = b.duration.time * (n.durationPercent or 1.0)
                    e_t = sec(b.start + dur_ticks)
                    if n.type == guitarpro.NoteType.tie and n.string in open_by_string:
                        open_by_string[n.string].end = e_t
                        continue
                    if n.type != guitarpro.NoteType.normal:
                        continue
                    note = Note(s_t, e_t, int(n.realValue) + capo, n.velocity / 127, n.string, n.value)
                    notes.append(note)
                    open_by_string[n.string] = note
    if not notes:
        raise ReferenceError(f"La pista '{tr.name}' no tiene notas.")
    notes.sort(key=lambda n: (n.start, n.pitch))
    bpb = last.timeSignature.numerator if last is not None else 4
    grid = Grid(beats, bpb, bar_starts)
    return Reference(notes, grid, name=song.title or path.stem, path=str(path), track=tr.name,
                     tuning=[t + capo for t in tuning])


# ---------------------------------------------------------------- cifrados (cancionero)
OPEN_STRINGS = [40, 45, 50, 55, 59, 64]  # cuerda 6 ... cuerda 1


def load_chart(chart: dict) -> Reference:
    """Referencia a partir de un cifrado: un rasguido al principio de cada acorde.

        {"title": "...", "bpm": 118, "beats_per_bar": 4, "capo": 2,
         "bars": [{"chord": "G", "beats": 4, "frets": [3, 2, 0, 0, 0, 3]}, ...]}

    `frets` va de la 6ta a la 1ra cuerda (-1 o null = no suena), relativo al capo.
    """
    try:
        bpm = float(chart.get("bpm") or 90)
        bpb = int(chart.get("beats_per_bar") or 4)
        capo = int(chart.get("capo") or 0)
        bars = chart["bars"]
    except (KeyError, TypeError, ValueError) as e:
        raise ReferenceError(f"Cifrado inválido: {e}") from e
    beat = 60 / bpm
    t = 0.0
    notes: list[Note] = []
    for b in bars:
        dur = float(b.get("beats") or bpb) * beat
        frets = b.get("frets") or []
        for i, f in enumerate(frets[:6]):
            if f is None or f < 0:
                continue
            notes.append(Note(t, t + dur * 0.95, OPEN_STRINGS[i] + capo + int(f), 0.8, 6 - i, int(f), b.get("chord")))
        t += dur
    if not notes:
        raise ReferenceError("El cifrado no tiene acordes con digitación conocida.")
    grid = Grid.from_bpm(bpm, 0.0, bpb, t + 10)
    return Reference(sorted(notes, key=lambda n: (n.start, n.pitch)), grid, name=chart.get("title") or "cifrado",
                     path=f"cifrado:{chart.get('id') or chart.get('title') or 'cifrado'}", capo=capo)
    # la tab va relativa al capo, así que las cuerdas se rotulan con la afinación estándar


def load_note_sequence(pitches: list[int], bpm: float = 60) -> Reference:
    """Notas sueltas, una por tiempo (para tocar en modo espera)."""
    beat = 60 / bpm
    notes = [Note(k * beat, (k + 0.9) * beat, int(p), 0.8) for k, p in enumerate(pitches)]
    if not notes:
        raise ReferenceError("El ejercicio no tiene notas.")
    assign_tab(notes)
    return Reference(notes, Grid.from_bpm(bpm, 0.0, 4, len(notes) * beat + 10), name="ejercicio", path="ejercicio")


# ---------------------------------------------------------------- listados / entrada principal
def list_tracks(path: Path) -> list[dict]:
    path = Path(path)
    ext = path.suffix.lower()
    out = []
    if ext in MIDI_EXT:
        import pretty_midi

        pm = pretty_midi.PrettyMIDI(str(path))
        for k, i in enumerate(_midi_instruments(pm)):
            kind = "guitarra" if 24 <= i.program <= 31 else pretty_midi.program_to_instrument_name(i.program)
            out.append(dict(index=k, name=i.name or "(sin nombre)", kind=kind, notes=len(i.notes)))
    elif ext in GP_EXT:
        import guitarpro

        song = guitarpro.parse(str(path))
        for k, t in enumerate(_gp_tracks(song)):
            n = sum(len(b.notes) for m in t.measures for v in m.voices for b in v.beats)
            out.append(dict(index=k, name=t.name, kind=f"{len(t.strings)} cuerdas", notes=n))
    return out


def load_reference(opts: RefOptions, log: Log = print) -> Reference:
    if opts.chart is not None:
        return _slice(load_chart(opts.chart), opts, log)
    if opts.notes is not None:
        return load_note_sequence(opts.notes)
    if opts.path is None:
        raise ReferenceError("Falta la referencia.")
    path = Path(opts.path)
    if not path.exists():
        raise ReferenceError(f"No existe el archivo {path}")
    ext = path.suffix.lower()
    if ext in MIDI_EXT:
        ref = load_midi(path, opts.track, log)
    elif ext in GP_EXT:
        ref = load_gp(path, opts.track, log)
    elif ext in AUDIO_EXT:
        src = separate_guitar(path, log) if opts.separate else path
        log(f"[transcribiendo] referencia: {src.name}")
        notes = transcribe(src, **opts.tx)
        assign_tab(notes)
        ref = Reference(notes, audio_grid(src), name=path.stem, path=str(path))
    else:
        raise ReferenceError(f"Formato no soportado: {ext} (usá MIDI, Guitar Pro o audio)")
    if opts.bpm:
        ref.grid = Grid.from_bpm(opts.bpm, opts.first_beat, opts.beats_per_bar, ref.end + 10)
    return _slice(ref, opts, log)


def _slice(ref: Reference, opts: RefOptions, log: Log) -> Reference:
    if opts.start_bar or opts.end_bar:
        t0 = ref.grid.bar_time(opts.start_bar or 1)
        t1 = ref.grid.bar_time(opts.end_bar + 1) if opts.end_bar else np.inf
        ref.all_notes = ref.notes
        ref.notes = [n for n in ref.notes if t0 - 0.02 <= n.start < t1 - 0.02]
        log(f"Practicando compases {opts.start_bar or 1}–{opts.end_bar or 'fin'} ({len(ref.notes)} notas)")
    if not ref.notes:
        raise ReferenceError("La referencia no tiene notas (¿rango de compases vacío?).")
    return ref
