"""Tipos básicos: notas, nombres y la grilla de compases."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
STANDARD_TUNING = [64, 59, 55, 50, 45, 40]  # cuerda 1 (E4) ... cuerda 6 (E2)


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    amp: float = 1.0
    string: int | None = None   # 1 = la más aguda
    fret: int | None = None
    label: str | None = None    # nombre del acorde al que pertenece (cifrados)


def note_name(p: int) -> str:
    return f"{NOTE_NAMES[p % 12]}{p // 12 - 1}"


def shifted(n: Note, dt: float = 0.0, dp: int = 0) -> Note:
    return Note(n.start + dt, n.end + dt, n.pitch + dp, n.amp, n.string, n.fret, n.label)


# ---------------------------------------------------------------- grilla de compases
class Grid:
    """Convierte segundos (en tiempo de la referencia) a compás/tiempo.

    `beats` son los tiempos de cada pulso; `bar_starts` los índices de pulso donde
    empieza cada compás (soporta cambios de compás). Fuera del rango conocido se
    extrapola con el último/primer pulso y compás, así que nunca falla.
    """

    def __init__(self, beats, beats_per_bar: int = 4, bar_starts=None):
        b = np.asarray(beats, dtype=float)
        if len(b) == 0:
            b = np.array([0.0])
        if len(b) < 2:  # sin información de tempo: asumimos 120 bpm
            b = b[0] + np.arange(2) * 0.5
        self.beats = b
        if bar_starts is None or len(bar_starts) == 0:
            bar_starts = np.arange(0, len(b), max(1, beats_per_bar))
        self.bar_starts = np.asarray(bar_starts, dtype=int)
        nums = np.diff(self.bar_starts).tolist()
        last = int(beats_per_bar if not nums else nums[-1])
        self.bar_nums = [int(x) for x in nums] + [last]
        self.bpb = self.bar_nums[0]

    # -- pulsos
    def beat_pos(self, t: float) -> float:
        """Índice de pulso fraccional (extrapolado fuera de rango)."""
        b = self.beats
        if t < b[0]:
            return (t - b[0]) / (b[1] - b[0])
        if t > b[-1]:
            return len(b) - 1 + (t - b[-1]) / (b[-1] - b[-2])
        return float(np.interp(t, b, np.arange(len(b))))

    def beat_time(self, k: float) -> float:
        b = self.beats
        if k < 0:
            return float(b[0] + k * (b[1] - b[0]))
        if k > len(b) - 1:
            return float(b[-1] + (k - len(b) + 1) * (b[-1] - b[-2]))
        return float(np.interp(k, np.arange(len(b)), b))

    def beat_len(self, t: float | None = None) -> float:
        if t is None:
            return float(np.median(np.diff(self.beats)))
        k = self.beat_pos(t)
        return self.beat_time(k + 0.5) - self.beat_time(k - 0.5)

    # -- compases
    def bar_of(self, t: float) -> tuple[int, float]:
        """(compás 1-based, tiempo 1-based fraccional)."""
        k = round(self.beat_pos(t), 3)  # evita "tiempo 5.00" por redondeo
        bs = self.bar_starts
        if k < bs[0]:
            n0 = self.bar_nums[0]
            rel = k - bs[0]
            bar = math.floor(rel / n0) + 1
            return bar, rel - (bar - 1) * n0 + 1
        i = int(np.searchsorted(bs, k, side="right") - 1)
        if i == len(bs) - 1:  # último compás conocido y más allá
            n = self.bar_nums[-1]
            rel = k - bs[-1]
            extra = int(rel // n)
            return i + 1 + extra, rel - extra * n + 1
        return i + 1, k - bs[i] + 1

    def bar_index(self, t: float) -> int:
        return self.bar_of(t)[0]

    def bar_time(self, bar: int) -> float:
        """Segundo en que empieza el compás `bar` (1 = primero)."""
        bs = self.bar_starts
        if bar <= 1:
            k = bs[0] + (bar - 1) * self.bar_nums[0]
        elif bar - 1 < len(bs):
            k = bs[bar - 1]
        else:
            k = bs[-1] + (bar - len(bs)) * self.bar_nums[-1]
        return self.beat_time(float(k))

    def beats_in_bar(self, bar: int) -> int:
        if bar < 1:
            return self.bar_nums[0]
        return self.bar_nums[min(bar - 1, len(self.bar_nums) - 1)]

    def is_downbeat(self, beat_idx: int) -> bool:
        if beat_idx < self.bar_starts[0]:
            return (self.bar_starts[0] - beat_idx) % self.bar_nums[0] == 0
        if beat_idx >= self.bar_starts[-1]:
            return (beat_idx - self.bar_starts[-1]) % self.bar_nums[-1] == 0
        return bool(np.any(self.bar_starts == beat_idx))

    def n_bars(self, until: float) -> int:
        return self.bar_index(until)

    def locate(self, t: float) -> str:
        bar, beat = self.bar_of(t)
        return f"compás {bar:3d} tiempo {beat:4.2f} ({t:6.2f}s)"

    def short(self, t: float) -> str:
        bar, beat = self.bar_of(t)
        return f"compás {bar} tiempo {beat:.2f}"

    @classmethod
    def from_bpm(cls, bpm: float, first_beat: float, beats_per_bar: int, until: float) -> "Grid":
        n = int((max(until, 1.0) - first_beat) * bpm / 60) + 2 * beats_per_bar + 2
        return cls(first_beat + np.arange(max(n, 2)) * 60 / bpm, beats_per_bar)


@dataclass
class Reference:
    notes: list[Note]
    grid: Grid
    name: str = ""
    path: str = ""
    track: str | None = None
    tuning: list[int] = field(default_factory=lambda: list(STANDARD_TUNING))
    all_notes: list[Note] | None = None   # la canción completa, si `notes` es una sección
    capo: int = 0                          # cifrados con capo: la tab y los nombres van relativos

    @property
    def end(self) -> float:
        return max((n.end for n in self.notes), default=0.0)
