"""Score followers: judge every detected onset against the reference.

  WaitFollower  : waits until you play the next note/chord correctly.
  TempoFollower : every event has its moment on the metronome; judges note and
                  timing. Supports looping and the speed trainer.

Everything that reaches the user is structured: a judgment `detail` is a dict with a
`kind`, and messages are dicts with a stable `code`, `params` and an English `text`.
The web UI translates `code` + `params`; the CLI prints `text`.
"""
from __future__ import annotations

import re

from dataclasses import dataclass, field

import numpy as np

from .core import NOTE_NAMES, Grid, Note, note_name
from .dsp import Detection, chord_template

INTERVALS = {0: "root", 1: "min9", 2: "9th", 3: "min3", 4: "maj3", 5: "4th", 6: "dim5", 7: "5th",
             8: "min6", 9: "6th", 10: "min7", 11: "maj7"}
INTERVAL_TEXT = {"root": "root", "min9": "minor 9th", "9th": "9th", "min3": "minor 3rd", "maj3": "major 3rd",
                 "4th": "4th", "dim5": "diminished 5th", "5th": "5th", "min6": "minor 6th", "6th": "6th",
                 "min7": "minor 7th", "maj7": "major 7th"}


# ---------------------------------------------------------------- details and messages
def describe(d: dict | None) -> str:
    """English text for a judgment detail (used by the CLI and stored reports)."""
    if not d:
        return ""
    k = d.get("kind")
    if k == "legato":
        return "legato"
    if k == "by_chroma":
        return "(by chroma)"
    if k == "chord_ok":
        unheard = f", {'/'.join(d['unheard'])} not heard" if d.get("unheard") else ""
        return f"chord ok ({d['sim']:.2f}{unheard})"
    if k == "chord_wrong":
        parts = [f"missing {m['note']} ({INTERVAL_TEXT[m['interval']]})" for m in d.get("missing", [])]
        parts += [f"extra {n}" for n in d.get("extra", [])]
        if not parts:
            parts.append(f"heard {'/'.join(d.get('heard', []))}")
        return f"chord: {', '.join(parts)} ({d['sim']:.2f})"
    if k == "octave":
        return f"heard {d['played']} (another octave)"
    if k == "wrong_note":
        return f"played {d['played']}"
    if k == "unclear":
        return f"couldn't tell the note: {d['heard']}"
    if k == "missed":
        return "didn't sound"
    if k == "skipped":
        before = d.get("before")
        return "skipped" + (f" (before: {describe(before)})" if before else "")
    return ""


def fmt_dt(dt: float | None) -> str:
    if dt is None:
        return ""
    ms = dt * 1000
    if abs(ms) < 15:
        return "on time"
    return f"{abs(ms):.0f} ms {'late' if ms > 0 else 'early'}"


def _text(code: str, p: dict) -> str:
    if code == "hit":
        s = f"✓ {p['label']}"
        if p.get("dt_ms") is not None:
            s += f"  {fmt_dt(p['dt_ms'] / 1000)}"
        elif p.get("detail"):
            s += f"  {describe(p['detail'])}"
        if p.get("previous_extra"):
            s += f"  (the previous one, {p['previous_extra']}, was extra)"
        return s
    if code == "wrong":
        return f"✗ {describe(p['detail'])} — expected {p['label']}"
    if code == "skip":
        return f"∅ skipped {p['skipped']} · ✓ {p['label']}"
    if code == "extra":
        return f"+ extra note: {p['played']}"
    if code == "pass":
        s = f"↻ pass {p['n']}: {p['score']:.0f}%"
        if p.get("new_speed") is not None:
            s += f" — speed {p['old_speed']:.0%} → {p['new_speed']:.0%}"
        return s
    return code


def message(code: str, **params) -> dict:
    return dict(code=code, params=params, text=_text(code, params))


def is_error(msg: dict | None) -> bool:
    return bool(msg) and msg["code"] in ("wrong", "skip", "extra")


# ---------------------------------------------------------------- events
@dataclass
class Event:
    time: float               # time in the reference
    pitches: list
    tab: list = field(default_factory=list)   # [(string, fret)] aligned with pitches
    status: str = "pending"   # pending | ok | octave | fixed | wrong | missed
    errors: int = 0           # failed attempts before getting it right (wait mode)
    detail: dict | None = None
    dt: float | None = None   # timing deviation (tempo mode)
    due: float = 0.0          # when it should sound (input clock, tempo mode)
    win: float = 0.2          # window to accept an onset for it (tempo mode)
    name: str | None = None   # chord name (charts); otherwise the notes are named
    tentative: tuple | None = None  # provisional error: (t, note) in case it was an extra note

    @property
    def is_chord(self) -> bool:
        return len({p % 12 for p in self.pitches}) > 1

    def label(self) -> str:
        return self.name or "+".join(note_name(p) for p in sorted(self.pitches))

    def reset(self) -> None:
        self.status, self.errors, self.detail, self.dt, self.tentative = "pending", 0, None, None, None


def group_events(notes: list[Note], win: float = 0.035) -> list[Event]:
    evs: list[Event] = []
    for n in sorted(notes, key=lambda n: (n.start, n.pitch)):
        if evs and n.start - evs[-1].time <= win:
            if n.pitch not in evs[-1].pitches:
                evs[-1].pitches.append(n.pitch)
                evs[-1].tab.append((n.string, n.fret))
        else:
            evs.append(Event(n.start, [n.pitch], [(n.string, n.fret)], name=n.label))
    return evs


_ROOTS = dict(C=0, D=2, E=4, F=5, G=7, A=9, B=11)


def chord_root(name: str | None) -> int | None:
    """Pitch class of a chord's bass note: "F#m7" → 6, "C/G" → 7."""
    if not name:
        return None
    part = name.split("/")[-1] if "/" in name else name
    m = re.match(r"([A-G])([#b]?)", part.strip())
    if not m:
        return None
    return (_ROOTS[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]) % 12


def backing_track(events, grid, bar0: float, section_end: float, bar_start: float, speed: float, capo: int = 0):
    """Bass & drums for a chord chart, as (time, sound) on the input clock.
    Drums: kick on 1 (and 3), snare on the backbeats, hi-hat in eighths. Bass: the chord's
    root on 1 (and 3), between E1 and D#2; chord names are relative to the capo, so it's added.
    Sounds: "kick", "snare", "hat", "bass:<midi>"."""
    names = [(e.time, e.name) for e in events if e.name]
    out = []
    k = 0
    for bi, b in enumerate(grid.beats):
        if not (bar0 - 1e-3 <= b < section_end - 1e-3):
            continue
        k = 0 if grid.is_downbeat(bi) else k + 1
        t = bar_start + (b - bar0) / speed
        nxt = grid.beats[bi + 1] if bi + 1 < len(grid.beats) else b + grid.beat_len(b)
        half = (nxt - b) / speed / 2
        strong = k == 0 or (grid.bpb >= 4 and k == grid.bpb // 2)
        out.append((t, "kick" if strong else "snare"))
        out += [(t, "hat"), (t + half, "hat")]
        chord = next((n for tm, n in reversed(names) if tm <= b + 1e-3), names[0][1] if names else None)
        root = chord_root(chord)
        if strong and root is not None:
            out.append((t, f"bass:{28 + (root + capo - 4) % 12}"))
    return sorted(out)


def min_repeat_gap(events: list[Event], speed: float = 1.0) -> float:
    """Smallest gap (s, at the given speed) between consecutive events."""
    if len(events) < 2:
        return 1.0
    return float(np.min(np.diff([e.time for e in events]))) / speed


# ---------------------------------------------------------------- judge
class Judge:
    def __init__(self, transpose: int = 0, chord_thr: float = 0.78, name_shift: int = 0):
        self.transpose = transpose
        self.chord_thr = chord_thr
        self.name_shift = name_shift  # e.g. -capo: name notes by the shape, not the sounding pitch
        self.cents: list[float] = []

    def chord_diff(self, ev: Event, c: np.ndarray) -> tuple[list[int], list[int], list[int]]:
        """Pitch classes (in the reference's tuning) that are missing / extra, and which of
        the extra ones might just be a harmonic (doubtful)."""
        exp = sorted({p % 12 for p in ev.pitches})
        ref_level = max(c[pc] for pc in exp) + 1e-9
        missing = [pc for pc in exp if c[pc] < 0.3 * ref_level]
        harm = set(exp) | {(pc + 7) % 12 for pc in exp}           # 2nd/3rd harmonic: always strong
        root = min(ev.pitches) % 12
        # The bass note's "other third" (major ↔ minor): if it sounds, you probably changed the
        # chord quality. Low threshold: the 5th harmonic leaks ≤0.37 of the level, a played third ≥0.44.
        thirds = {(root + 3) % 12, (root + 4) % 12}
        own = thirds & set(exp)
        # no third (power chords) → no quality to police; with its own third sounding, the other one
        # isn't a swap
        alt = thirds - set(exp) if own and any(pc in missing for pc in own) else set()
        # 5th, 7th, 9th and 11th harmonics of the low strings: "ghost" notes, especially in chords
        # with few strings. They only count when very loud.
        ghost = ({(pc + d) % 12 for pc in exp for d in (4, 10, 2, 6)} | (thirds - set(exp))) - harm - alt
        thr = lambda pc: 0.42 if pc in alt else 0.8 if pc in ghost else 0.5
        outside = [int(pc) for pc in np.argsort(c)[::-1] if pc not in harm][:4]   # 4 strongest outsiders
        extra = [pc for pc in outside if c[pc] > thr(pc) * ref_level]
        return missing, extra, [pc for pc in extra if pc in ghost]

    def similarity(self, ev: Event, det: Detection) -> float:
        return float(np.roll(det.chroma, self.transpose) @ chord_template(ev.pitches))

    def _n(self, pc: int) -> str:
        return NOTE_NAMES[(pc + self.name_shift) % 12]

    def __call__(self, ev: Event, det: Detection) -> tuple[str, dict]:
        if ev.is_chord:
            c = np.roll(det.chroma, self.transpose)  # what you played, in the reference's tuning
            sim = round(float(c @ chord_template(ev.pitches)), 2)
            missing, extra, doubtful = self.chord_diff(ev, c)
            # nothing missing and the "extra" notes may be harmonics: ok, unless it sounds far off
            only_doubtful = not missing and set(extra) <= set(doubtful) and sim >= self.chord_thr - 0.1
            if (sim >= self.chord_thr and not (missing and extra)) or only_doubtful:
                return "ok", dict(kind="chord_ok", sim=sim, unheard=[self._n(pc) for pc in missing])
            # a note is missing and another one sounds in its place (e.g. minor instead of major): wrong
            root = min(ev.pitches)
            return "wrong", dict(kind="chord_wrong", sim=sim,
                                 missing=[dict(note=self._n(pc), interval=INTERVALS[(pc - root) % 12]) for pc in missing],
                                 extra=[self._n(pc) for pc in extra],
                                 heard=[self._n(int(i)) for i in np.argsort(c)[::-1][:3]])
        exp = ev.pitches[0]
        if det.midi is not None:
            m = det.midi + self.transpose
            r = int(round(m - exp))
            if r == 0:
                self.cents.append((m - exp) * 100)
                return "ok", dict(kind="legato") if det.legato else None
            if r % 12 == 0:
                return "octave", dict(kind="octave", played=note_name(int(round(m))))
            return "wrong", dict(kind="wrong_note", played=note_name(int(round(m))))
        if np.argmax(det.chroma) == (exp - self.transpose) % 12:
            return "ok", dict(kind="by_chroma")
        return "wrong", dict(kind="unclear", heard=det.label())

    def tuning(self) -> float | None:
        return float(np.median(self.cents[-30:])) if len(self.cents) >= 3 else None


def pass_score(events: list[Event], extras: int, timing_tol: float) -> float:
    pts = 0.0
    for e in events:
        if e.status in ("ok", "octave"):
            pts += 1.0 if e.dt is None or abs(e.dt) <= timing_tol else 0.5
        elif e.status == "fixed":
            pts += 0.5
    return round(max(0.0, 100 * (pts - 0.5 * extras) / max(1, len(events))), 1)


# ---------------------------------------------------------------- wait mode
class WaitFollower:
    """Waits until you play the current event correctly; tolerates skipping one."""

    mode = "wait"

    def __init__(self, events: list[Event], judge: Judge, loop: bool = False):
        self.events, self.judge, self.loop = events, judge, loop
        self.k = 0
        self.ignore_until = -1.0
        self.passes: list[dict] = []
        self.extras: list[tuple[float, str]] = []
        self.history: list[list[dict]] = []  # events of every finished pass

    @property
    def done(self) -> bool:
        return not self.loop and self.k >= len(self.events)

    def on_detection(self, det: Detection) -> dict | None:
        if self.k >= len(self.events) or det.t < self.ignore_until:
            return None
        ev = self.events[self.k]
        res, detail = self.judge(ev, det)
        if res in ("ok", "octave"):
            ev.status = res if ev.errors == 0 else "fixed"
            if ev.errors == 0:
                ev.detail = detail
            self._advance(det, ev)
            return message("hit", label=ev.label(), detail=detail, dt_ms=None)
        if self.k > 0:
            prev = self.events[self.k - 1]
            if (prev.is_chord or ev.is_chord) and set(prev.pitches) != set(ev.pitches) \
                    and self.judge(prev, det)[0] == "ok" \
                    and self.judge.similarity(prev, det) > self.judge.similarity(ev, det):
                return None  # still strumming the previous chord
        if self.k + 1 < len(self.events):
            nxt = self.events[self.k + 1]
            r2, d2 = self.judge(nxt, det)
            if r2 == "ok":
                ev.status = "missed"
                ev.detail = dict(kind="skipped", before=ev.detail if ev.errors else None)
                nxt.status, nxt.detail = r2, d2
                self.k += 1
                self._advance(det, nxt)
                return message("skip", skipped=ev.label(), label=nxt.label())
        ev.errors += 1
        ev.detail = detail
        return message("wrong", label=ev.label(), detail=detail)

    def _advance(self, det: Detection, ev: Event) -> None:
        self.k += 1
        if ev.is_chord:
            self.ignore_until = det.t + 0.15  # a strum produces several onsets
        if self.k >= len(self.events) and self.loop:
            ok = sum(e.status in ("ok", "octave") for e in self.events)
            self.passes.append(dict(speed=None, score=round(100 * ok / len(self.events), 1)))
            self.history.append(snapshot_events(self.events))
            for e in self.events:
                e.reset()
            self.k = 0

    def tick(self, now: float) -> None:
        pass


# ---------------------------------------------------------------- tempo mode
@dataclass
class Trainer:
    """Speed trainer: speeds up after a clean pass, slows down after a bad one."""
    step: float = 0.05
    target: float = 90.0
    max_speed: float = 1.0
    min_speed: float = 0.3

    def next_speed(self, speed: float, score: float) -> float:
        if score >= self.target:
            speed += self.step
        elif score < self.target - 25:
            speed -= self.step
        return round(float(np.clip(speed, self.min_speed, self.max_speed)), 3)


class TempoFollower:
    """Every event has its moment (on the metronome); judges note and timing."""

    mode = "tempo"

    def __init__(self, events: list[Event], judge: Judge, speed: float, window: float, grid: Grid,
                 loop: bool = False, trainer: Trainer | None = None, count_in: int | None = None,
                 click: bool = True, timing_tol: float = 0.06, count_extras: bool = True):
        self.events, self.judge, self.grid = events, judge, grid
        self.speed, self.window = speed, window
        self.loop, self.trainer, self.click = loop or trainer is not None, trainer, click
        self.count_in = grid.bpb if count_in is None else count_in
        self.timing_tol = timing_tol
        self.count_extras = count_extras  # False when strumming: filler strums aren't mistakes
        self.t0: float | None = None
        self.extras: list[tuple[float, str]] = []
        self.pass_extras = 0
        self.ignore_until = -1.0
        self.passes: list[dict] = []
        self.history: list[list[dict]] = []
        self.clicks: list[tuple[float, bool]] = []  # append-only (read by the metronome)
        self.backing: list[tuple[float, str]] = []  # append-only: (time, sound) for bass & drums (charts)
        self.capo = 0                               # set by the session for charts with a capo
        self.pass_end = np.inf
        self.finished = False
        self.bar0 = grid.bar_time(grid.bar_index(events[0].time))  # start of the first note's bar
        self.section_end = grid.bar_time(grid.bar_index(events[-1].time) + 1)

    # -- scheduling a pass
    def beat_len(self) -> float:
        return self.grid.beat_len(self.events[0].time) / self.speed

    def _set_dues(self, bar_start: float) -> None:
        times = np.array([e.time for e in self.events])
        for i, e in enumerate(self.events):
            e.due = bar_start + (e.time - self.bar0) / self.speed
            gaps = [abs(times[i] - times[j]) for j in (i - 1, i + 1) if 0 <= j < len(times)]
            gap = min(gaps) / self.speed if gaps else 1.0
            e.win = float(min(self.window, max(0.06, 0.5 * gap)))
        last = self.events[-1]
        self.pass_end = max(bar_start + (self.section_end - self.bar0) / self.speed, last.due + last.win)

    def schedule(self, count_start: float) -> None:
        """Schedules count-in + the section, starting at `count_start` (input clock)."""
        bl = self.beat_len()
        bar_start = count_start + self.count_in * bl
        self._set_dues(bar_start)
        self.t0 = self.events[0].due
        clicks = [(count_start + i * bl, i == 0) for i in range(self.count_in)]
        g = self.grid
        for bi, b in enumerate(g.beats):
            if self.bar0 - 1e-3 <= b < self.section_end - 1e-3:
                clicks.append((bar_start + (b - self.bar0) / self.speed, g.is_downbeat(bi)))
        self.clicks.extend(sorted(clicks))
        self.backing.extend(backing_track(self.events, g, self.bar0, self.section_end, bar_start, self.speed, self.capo))

    def start(self, t_first: float) -> None:
        """Without a metronome: your first note sets the start."""
        self._set_dues(t_first - (self.events[0].time - self.bar0) / self.speed)
        self.t0 = t_first

    @property
    def done(self) -> bool:
        return self.finished

    @property
    def k(self) -> int:
        return next((i for i, e in enumerate(self.events) if e.status == "pending"), len(self.events))

    def countdown(self, now: float) -> int | None:
        if self.t0 is None:
            return None
        bar_start = self.events[0].due - (self.events[0].time - self.bar0) / self.speed
        if now >= bar_start:
            return None
        return int(np.ceil((bar_start - now) / self.beat_len()))

    # -- judging
    def _extra(self, det: Detection) -> dict | None:
        if not self.count_extras:
            return None
        self.extras.append((det.t, det.label()))
        self.pass_extras += 1
        return message("extra", played=det.label())

    def on_detection(self, det: Detection) -> dict | None:
        if self.t0 is None or det.t < self.ignore_until:
            return None
        cands = [e for e in self.events
                 if (e.status == "pending" or e.tentative) and abs(det.t - e.due) <= e.win]
        if not cands:
            if self.events[0].due - self.window < det.t < self.pass_end:
                return self._extra(det)
            return None
        cands.sort(key=lambda e: abs(det.t - e.due))
        for e in cands:
            res, detail = self.judge(e, det)
            if res in ("ok", "octave"):
                previous_extra = None
                if e.tentative:  # the previous onset was an extra note, not a mistake on this one
                    if self.count_extras:
                        self.extras.append(e.tentative)
                        self.pass_extras += 1
                        previous_extra = e.tentative[1]
                    e.tentative = None
                e.status, e.detail, e.dt = res, detail, det.t - e.due
                if e.is_chord:
                    self.ignore_until = det.t + 0.15
                return message("hit", label=e.label(), detail=detail, dt_ms=round(e.dt * 1000),
                               previous_extra=previous_extra)
        pend = [e for e in cands if e.status == "pending"]
        if not pend:
            return self._extra(det)
        e = pend[0]
        res, detail = self.judge(e, det)
        e.status, e.detail, e.dt = "wrong", detail, det.t - e.due
        e.tentative = (det.t, det.label())
        return message("wrong", label=e.label(), detail=detail)

    def tick(self, now: float) -> dict | None:
        """`now` = how far the audio has been analyzed. Returns a message when a pass ends."""
        if self.t0 is None or self.finished:
            return None
        for e in self.events:
            if e.tentative and now > e.due + e.win:
                e.tentative = None  # the window closed: the mistake stands
            if e.status == "pending" and now > e.due + e.win:
                e.status, e.detail = "missed", dict(kind="missed")
        if now <= self.pass_end or any(e.status == "pending" for e in self.events):
            return None
        score = pass_score(self.events, self.pass_extras, self.timing_tol)
        self.passes.append(dict(speed=self.speed, score=score))
        self.history.append(snapshot_events(self.events))
        if not self.loop:
            self.finished = True
            return None
        old = self.speed
        if self.trainer:
            self.speed = self.trainer.next_speed(self.speed, score)
        for e in self.events:
            e.reset()
        self.pass_extras = 0
        msg = message("pass", n=len(self.passes), score=score, old_speed=old,
                      new_speed=self.speed if self.speed != old else None)
        if self.click:
            self.schedule(max(now, self.pass_end) + 0.3)
        else:
            self.t0 = None  # re-syncs with your next first note
            self.pass_end = np.inf
        return msg


def snapshot_events(events: list[Event]) -> list[dict]:
    return [dict(time=e.time, label=e.label(), status=e.status, errors=e.errors, detail=e.detail,
                 dt=e.dt) for e in events]
