"""Seguidores de partitura: juzgan cada ataque detectado contra la referencia.

  WaitFollower  : espera a que toques bien la nota/acorde siguiente.
  TempoFollower : cada evento tiene su momento según el metrónomo; juzga nota y
                  timing. Soporta loop y entrenador de velocidad.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .core import NOTE_NAMES, Grid, Note, note_name
from .dsp import Detection, chord_template

INTERVAL_NAMES = {0: "tónica", 1: "9na menor", 2: "9na", 3: "3ra menor", 4: "3ra", 5: "4ta",
                  6: "5ta disminuida", 7: "5ta", 8: "6ta menor", 9: "6ta", 10: "7ma", 11: "7ma mayor"}


@dataclass
class Event:
    time: float               # tiempo en la referencia
    pitches: list
    tab: list = field(default_factory=list)   # [(cuerda, traste)] alineado con pitches
    status: str = "pending"   # pending | ok | octave | fixed | wrong | missed
    errors: int = 0           # intentos fallidos antes de acertar (modo espera)
    detail: str = ""
    dt: float | None = None   # desvío de timing (modo tempo)
    due: float = 0.0          # cuándo debe sonar (reloj de entrada, modo tempo)
    win: float = 0.2          # ventana para asociarle un ataque (modo tempo)
    name: str | None = None   # nombre del acorde (cifrados); si no, se nombran las notas
    tentative: tuple | None = None  # error provisorio: (t, nota) por si era una nota de más

    @property
    def is_chord(self) -> bool:
        return len({p % 12 for p in self.pitches}) > 1

    def label(self) -> str:
        return self.name or "+".join(note_name(p) for p in sorted(self.pitches))

    def reset(self) -> None:
        self.status, self.errors, self.detail, self.dt, self.tentative = "pending", 0, "", None, None


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


def min_repeat_gap(events: list[Event], speed: float = 1.0) -> float:
    """Distancia mínima (s, a la velocidad dada) entre eventos consecutivos."""
    if len(events) < 2:
        return 1.0
    return float(np.min(np.diff([e.time for e in events]))) / speed


class Judge:
    def __init__(self, transpose: int = 0, chord_thr: float = 0.78, name_shift: int = 0):
        self.transpose = transpose
        self.chord_thr = chord_thr
        self.name_shift = name_shift  # p.ej. -capo: nombrar las notas según la forma, no la altura real
        self.cents: list[float] = []

    def chord_diff(self, ev: Event, c: np.ndarray) -> tuple[list[int], list[int], list[int]]:
        """Clases de altura (en la afinación de la referencia) que faltan / sobran, y cuáles
        de las que sobran podrían ser solo un 5to armónico (dudosas)."""
        exp = sorted({p % 12 for p in ev.pitches})
        ref_level = max(c[pc] for pc in exp) + 1e-9
        missing = [pc for pc in exp if c[pc] < 0.3 * ref_level]
        harm = set(exp) | {(pc + 7) % 12 for pc in exp}           # 2do/3er armónico: siempre fuertes
        root = min(ev.pitches) % 12
        # la "otra 3ra" del bajo (mayor ↔ menor): si suena, es probable que hayas cambiado la calidad.
        # Umbral bajo: el 5to armónico se filtra ≤0.37 del nivel, una 3ra tocada da ≥0.44.
        thirds = {(root + 3) % 12, (root + 4) % 12}
        own = thirds & set(exp)
        # sin 3ra (quintas) no hay calidad que vigilar; con su 3ra sonando, la otra no es un cambio
        alt = thirds - set(exp) if own and any(pc in missing for pc in own) else set()
        # 5to, 7mo, 9no y 11vo armónico de las cuerdas graves: notas "fantasma", sobre todo en
        # acordes de pocas cuerdas. Solo cuentan si suenan muy fuerte.
        ghost = ({(pc + d) % 12 for pc in exp for d in (4, 10, 2, 6)} | (thirds - set(exp))) - harm - alt
        thr = lambda pc: 0.42 if pc in alt else 0.8 if pc in ghost else 0.5
        outside = [int(pc) for pc in np.argsort(c)[::-1] if pc not in harm][:4]   # las 4 más fuertes de afuera
        extra = [pc for pc in outside if c[pc] > thr(pc) * ref_level]
        return missing, extra, [pc for pc in extra if pc in ghost]

    def similarity(self, ev: Event, det: Detection) -> float:
        return float(np.roll(det.chroma, self.transpose) @ chord_template(ev.pitches))

    def _n(self, pc: int) -> str:
        return NOTE_NAMES[(pc + self.name_shift) % 12]

    def chord_text(self, ev: Event, missing: list[int], extra: list[int], c: np.ndarray) -> str:
        root = min(ev.pitches)
        parts = [f"faltó {self._n(pc)} ({INTERVAL_NAMES[(pc - root) % 12]})" for pc in missing]
        parts += [f"sobró {self._n(pc)}" for pc in extra]
        if not parts:
            parts.append(f"sonó {'/'.join(self._n(i) for i in np.argsort(c)[::-1][:3])}")
        return "acorde: " + ", ".join(parts)

    def __call__(self, ev: Event, det: Detection) -> tuple[str, str]:
        if ev.is_chord:
            c = np.roll(det.chroma, self.transpose)  # lo que tocaste, llevado a la afinación de la referencia
            sim = float(c @ chord_template(ev.pitches))
            missing, extra, doubtful = self.chord_diff(ev, c)
            # no falta nada y lo que "sobra" puede ser un armónico: ok, si el parecido no es malo
            only_doubtful = not missing and set(extra) <= set(doubtful) and sim >= self.chord_thr - 0.1
            if (sim >= self.chord_thr and not (missing and extra)) or only_doubtful:
                note = f", no se escuchó {'/'.join(self._n(pc) for pc in missing)}" if missing else ""
                return "ok", f"acorde ok ({sim:.2f}{note})"
            # falta una nota y suena otra en su lugar (p.ej. menor en vez de mayor): error
            return "wrong", f"{self.chord_text(ev, missing, extra, c)} ({sim:.2f})"
        exp = ev.pitches[0]
        if det.midi is not None:
            m = det.midi + self.transpose
            r = int(round(m - exp))
            if r == 0:
                self.cents.append((m - exp) * 100)
                return "ok", "legato" if det.legato else ""
            if r % 12 == 0:
                return "octave", f"sonó {note_name(int(round(m)))} (otra octava)"
            return "wrong", f"tocaste {note_name(int(round(m)))}"
        if np.argmax(det.chroma) == (exp - self.transpose) % 12:
            return "ok", "(por croma)"
        return "wrong", f"no se entendió la nota: {det.label()}"

    def tuning(self) -> float | None:
        return float(np.median(self.cents[-30:])) if len(self.cents) >= 3 else None


def fmt_dt(dt: float | None) -> str:
    if dt is None:
        return ""
    ms = dt * 1000
    if abs(ms) < 15:
        return "a tiempo"
    return f"{abs(ms):.0f} ms {'tarde' if ms > 0 else 'adelantado'}"


def pass_score(events: list[Event], extras: int, timing_tol: float) -> float:
    pts = 0.0
    for e in events:
        if e.status in ("ok", "octave"):
            pts += 1.0 if e.dt is None or abs(e.dt) <= timing_tol else 0.5
        elif e.status == "fixed":
            pts += 0.5
    return round(max(0.0, 100 * (pts - 0.5 * extras) / max(1, len(events))), 1)


class WaitFollower:
    """Espera a que toques bien el evento actual; tolera saltearse uno."""

    mode = "wait"

    def __init__(self, events: list[Event], judge: Judge, loop: bool = False):
        self.events, self.judge, self.loop = events, judge, loop
        self.k = 0
        self.ignore_until = -1.0
        self.passes: list[dict] = []
        self.extras: list[tuple[float, str]] = []
        self.history: list[list[dict]] = []  # eventos de cada vuelta terminada

    @property
    def done(self) -> bool:
        return not self.loop and self.k >= len(self.events)

    def on_detection(self, det: Detection) -> str | None:
        if self.k >= len(self.events) or det.t < self.ignore_until:
            return None
        ev = self.events[self.k]
        res, detail = self.judge(ev, det)
        if res in ("ok", "octave"):
            ev.status = res if ev.errors == 0 else "fixed"
            if ev.errors == 0:
                ev.detail = detail
            msg = f"✓ {ev.label()}" + (f"  {detail}" if detail else "")
            self._advance(det, ev)
            return msg
        if self.k > 0:
            prev = self.events[self.k - 1]
            if (prev.is_chord or ev.is_chord) and set(prev.pitches) != set(ev.pitches) \
                    and self.judge(prev, det)[0] == "ok" \
                    and self.judge.similarity(prev, det) > self.judge.similarity(ev, det):
                return None  # seguís rasgueando el acorde anterior
        if self.k + 1 < len(self.events):
            nxt = self.events[self.k + 1]
            r2, d2 = self.judge(nxt, det)
            if r2 == "ok":
                ev.status = "missed"
                ev.detail = "salteada" + (f" (antes: {ev.detail})" if ev.errors else "")
                nxt.status, nxt.detail = r2, d2
                self.k += 1
                self._advance(det, nxt)
                return f"∅ salteaste {ev.label()} · ✓ {nxt.label()}"
        ev.errors += 1
        ev.detail = detail
        return f"✗ {detail} — esperaba {ev.label()}"

    def _advance(self, det: Detection, ev: Event) -> None:
        self.k += 1
        if ev.is_chord:
            self.ignore_until = det.t + 0.15  # el rasgueo genera varios ataques
        if self.k >= len(self.events) and self.loop:
            ok = sum(e.status in ("ok", "octave") for e in self.events)
            self.passes.append(dict(speed=None, score=round(100 * ok / len(self.events), 1)))
            self.history.append(snapshot_events(self.events))
            for e in self.events:
                e.reset()
            self.k = 0

    def tick(self, now: float) -> None:
        pass


@dataclass
class Trainer:
    """Entrenador de velocidad: sube si la vuelta salió limpia, baja si salió mal."""
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
    """Cada evento tiene su momento (según metrónomo); juzga nota y timing."""

    mode = "tempo"

    def __init__(self, events: list[Event], judge: Judge, speed: float, window: float, grid: Grid,
                 loop: bool = False, trainer: Trainer | None = None, count_in: int | None = None,
                 click: bool = True, timing_tol: float = 0.06, count_extras: bool = True):
        self.events, self.judge, self.grid = events, judge, grid
        self.speed, self.window = speed, window
        self.loop, self.trainer, self.click = loop or trainer is not None, trainer, click
        self.count_in = grid.bpb if count_in is None else count_in
        self.timing_tol = timing_tol
        self.count_extras = count_extras  # False al rasguear: los rasguidos de relleno no son errores
        self.t0: float | None = None
        self.extras: list[tuple[float, str]] = []
        self.pass_extras = 0
        self.ignore_until = -1.0
        self.passes: list[dict] = []
        self.history: list[list[dict]] = []
        self.clicks: list[tuple[float, bool]] = []  # solo se agregan (lo lee el metrónomo)
        self.pass_end = np.inf
        self.finished = False
        self.bar0 = grid.bar_time(grid.bar_index(events[0].time))  # inicio del compás de la 1ra nota
        self.section_end = grid.bar_time(grid.bar_index(events[-1].time) + 1)

    # -- programación de una vuelta
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
        """Programa cuenta de entrada + la sección, empezando en `count_start` (reloj de entrada)."""
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

    def start(self, t_first: float) -> None:
        """Sin metrónomo: tu primera nota marca el arranque."""
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

    # -- juicio
    def on_detection(self, det: Detection) -> str | None:
        if self.t0 is None or det.t < self.ignore_until:
            return None
        cands = [e for e in self.events
                 if (e.status == "pending" or e.tentative) and abs(det.t - e.due) <= e.win]
        if not cands:
            if not self.count_extras:
                return None
            if self.events[0].due - self.window < det.t < self.pass_end:
                self.extras.append((det.t, det.label()))
                self.pass_extras += 1
                return f"+ nota de más: {det.label()}"
            return None
        cands.sort(key=lambda e: abs(det.t - e.due))
        for e in cands:
            res, detail = self.judge(e, det)
            if res in ("ok", "octave"):
                fix = ""
                if e.tentative:  # lo anterior era una nota de más, no un error en ésta
                    if self.count_extras:
                        self.extras.append(e.tentative)
                        self.pass_extras += 1
                        fix = f"  (la anterior, {e.tentative[1]}, fue de más)"
                    e.tentative = None
                e.status, e.detail, e.dt = res, detail, det.t - e.due
                if e.is_chord:
                    self.ignore_until = det.t + 0.15
                return f"✓ {e.label()}  {fmt_dt(e.dt)}{fix}"
        pend = [e for e in cands if e.status == "pending"]
        if not pend:
            if not self.count_extras:
                return None
            self.extras.append((det.t, det.label()))
            self.pass_extras += 1
            return f"+ nota de más: {det.label()}"
        e = pend[0]
        res, detail = self.judge(e, det)
        e.status, e.detail, e.dt = "wrong", detail, det.t - e.due
        e.tentative = (det.t, det.label())
        return f"✗ {detail} — esperaba {e.label()}"

    def tick(self, now: float) -> str | None:
        """`now` = hasta dónde ya se analizó el audio. Devuelve un mensaje al cerrar una vuelta."""
        if self.t0 is None or self.finished:
            return None
        for e in self.events:
            if e.tentative and now > e.due + e.win:
                e.tentative = None  # se cerró la ventana: el error queda firme
            if e.status == "pending" and now > e.due + e.win:
                e.status, e.detail = "missed", "no sonó"
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
        msg = f"↻ vuelta {len(self.passes)}: {score:.0f}%"
        if self.speed != old:
            msg += f" — velocidad {old:.0%} → {self.speed:.0%}"
        if self.click:
            self.schedule(max(now, self.pass_end) + 0.3)
        else:
            self.t0 = None  # se re-sincroniza con tu próxima primera nota
            self.pass_end = np.inf
        return msg


def snapshot_events(events: list[Event]) -> list[dict]:
    return [dict(time=e.time, label=e.label(), status=e.status, errors=e.errors, detail=e.detail,
                 dt=e.dt) for e in events]
