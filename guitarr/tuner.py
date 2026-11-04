"""Afinador (reusa el YIN del modo en vivo) y calibración de latencia."""
from __future__ import annotations

import queue
import threading
from collections import deque

import numpy as np

from .core import STANDARD_TUNING, note_name
from .dsp import db, yin

STRING_NAMES = {64: "1ra (E4)", 59: "2da (B3)", 55: "3ra (G3)", 50: "4ta (D3)", 45: "5ta (A2)", 40: "6ta (E2)"}


class Tuner:
    def __init__(self, src, gate_db: float = -55.0, a4: float = 440.0):
        self.src, self.sr = src, src.sr
        self.gate_db = gate_db
        self.a4 = a4
        self.buf = np.zeros(4096, np.float32)
        self.hist: deque = deque(maxlen=5)
        self.reading: dict = dict(note=None, level_db=-120.0)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def _analyze(self) -> dict:
        lvl = db(self.buf[-2048:])
        if lvl < self.gate_db:
            self.hist.clear()
            return dict(note=None, level_db=round(lvl, 1))
        m, conf = yin(self.buf, self.sr, fmin=60.0, fmax=1400.0, thresh=0.15)
        if m is None or conf < 0.85:
            return dict(note=None, level_db=round(lvl, 1))
        m += 12 * np.log2(440.0 / self.a4)
        if self.hist and abs(m - np.median(self.hist)) > 0.6:
            self.hist.clear()  # cambió de cuerda
        self.hist.append(m)
        mm = float(np.median(self.hist))
        p = int(round(mm))
        nearest = min(STANDARD_TUNING, key=lambda s: abs(s - mm))
        return dict(note=note_name(p), midi=round(mm, 2), cents=round((mm - p) * 100, 1),
                    freq=round(self.a4 * 2 ** ((mm - 69) / 12), 2), level_db=round(lvl, 1),
                    string=STRING_NAMES[nearest] if abs(nearest - mm) < 0.75 else None,
                    string_cents=round((mm - nearest) * 100, 1) if abs(nearest - mm) < 0.75 else None)

    def run(self, on_reading=None, every: float = 0.04) -> None:
        self.src.start()
        acc = 0
        try:
            while not self._stop.is_set():
                try:
                    blk = self.src.q.get(timeout=0.1)
                except queue.Empty:
                    continue
                if blk is None:
                    break
                n = len(blk)
                self.buf = np.concatenate([self.buf[n:], blk]) if n < len(self.buf) else blk[-len(self.buf):]
                acc += n
                if acc >= every * self.sr:
                    acc = 0
                    self.reading = self._analyze()
                    if on_reading:
                        on_reading(self.reading)
        finally:
            self.src.stop()


def tuner_bar(cents: float, width: int = 41) -> str:
    pos = int(np.clip(round(cents / 50 * (width // 2)), -(width // 2), width // 2)) + width // 2
    return "".join("┃" if i == pos else ("│" if i == width // 2 else "─") for i in range(width))


def run_tuner_cli(src) -> None:
    from rich.live import Live
    from rich.panel import Panel
    from rich.text import Text

    tuner = Tuner(src)

    def view(r: dict):
        t = Text()
        t.append("🎸 afinador  ", style="bold")
        t.append(f"{src.name}\n\n", style="dim")
        if r.get("note") is None:
            t.append("Tocá una cuerda al aire...\n", style="cyan")
        else:
            c = r["cents"]
            ok = abs(c) <= 5
            t.append(f"{r['note']:>4s}  ", style="bold green" if ok else "bold yellow")
            t.append(f"{c:+5.1f} cents   {r['freq']:.1f} Hz\n")
            t.append(tuner_bar(c) + "\n", style="green" if ok else "yellow")
            t.append("bemol" + " " * 31 + "sostenido\n", style="dim")
            if r.get("string"):
                sc = r["string_cents"]
                hint = "✓ afinada" if abs(sc) <= 5 else ("subí" if sc < 0 else "bajá")
                t.append(f"\ncuerda {r['string']}: {sc:+.0f} cents → {hint}", style="bold")
        t.append(f"\n\nnivel {r.get('level_db', -120):.0f} dB   Ctrl+C para salir", style="dim")
        return Panel(t, border_style="cyan")

    with Live(view(tuner.reading), refresh_per_second=20) as live:
        th = threading.Thread(target=tuner.run, kwargs=dict(on_reading=lambda r: live.update(view(r))),
                              daemon=True)
        th.start()
        try:
            while th.is_alive():
                th.join(0.2)
        except KeyboardInterrupt:
            tuner.stop()
            th.join(1)


# ---------------------------------------------------------------- calibración de latencia
def calibrate(device, channel: int, output_device=None, bpm: float = 90, beats: int = 12,
              warmup: int = 4, on_progress=None, stop_event: threading.Event | None = None) -> dict:
    """Suena un click; tocás cuerdas muteadas junto con cada click. La mediana del
    desvío (ataque detectado − click) es la latencia total de ida y vuelta + el
    sesgo del detector. Las primeras `warmup` son para agarrar el pulso."""
    from .audio_io import Metronome, MicSource
    from .dsp import Detector, Recorder

    src = MicSource(device, channel)
    rec = Recorder(src.sr)
    det = Detector(rec, gate_db=-55, legato=False)
    beat = 60 / bpm
    t_first = 1.0
    clicks = [(t_first + i * beat, i % 4 == 0) for i in range(warmup + beats)]
    metro = Metronome(output_device, src, clicks)
    onsets: list[float] = []
    src.start()
    metro.start()
    end_t = clicks[-1][0] + 0.8
    try:
        while rec.n / src.sr < end_t and not (stop_event and stop_event.is_set()):
            try:
                blk = src.q.get(timeout=0.1)
            except queue.Empty:
                continue
            rec.append(blk)
            for d in det.process():
                onsets.append(d.t)
            if on_progress:
                now = rec.n / src.sr
                k = int((now - t_first) / beat)
                on_progress(dict(beat=k + 1, total=warmup + beats, warmup=k < warmup))
    finally:
        metro.stop()
        src.stop()
    offs = []
    for ct, _ in clicks[warmup:]:
        near = [o - ct for o in onsets if -0.15 <= o - ct <= 0.35]
        if near:
            offs.append(min(near, key=abs))
    if len(offs) < beats // 2:
        return dict(ok=False, hits=len(offs), message="No detecté suficientes golpes. Subí la ganancia "
                                                      "o tocá más fuerte, sin distorsión.")
    offs = np.array(offs)
    med = float(np.median(offs))
    spread = float(np.median(np.abs(offs - med)))
    return dict(ok=True, latency_ms=round(1000 * med, 1), spread_ms=round(1000 * spread, 1), hits=len(offs),
                message=f"Latencia {1000 * med:.0f} ms (±{1000 * spread:.0f} ms, {len(offs)} golpes)")
