"""Tuner (reuses the live-mode YIN) and latency calibration."""
from __future__ import annotations

import queue
import threading
from collections import deque

import numpy as np

from .core import STANDARD_TUNING, note_name
from .dsp import db, yin

class Tuner:
    def __init__(self, src, gate_db: float = -55.0, a4: float = 440.0, tuning: list[int] | None = None,
                 hum_hz: int | None = None):
        from .signalcheck import hum_filter

        self.src, self.sr = src, src.sr
        self.hum = hum_filter(src.sr, hum_hz)
        self.tuning = list(tuning or STANDARD_TUNING)        # string 1 … n
        self.fmin = min(60.0, 0.8 * 440 * 2 ** ((min(self.tuning) - 69) / 12))   # low enough for a bass
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
        m, conf = yin(self.buf, self.sr, fmin=self.fmin, fmax=1400.0, thresh=0.15)
        if m is None or conf < 0.85:
            return dict(note=None, level_db=round(lvl, 1))
        m += 12 * np.log2(440.0 / self.a4)
        if self.hist and abs(m - np.median(self.hist)) > 0.6:
            self.hist.clear()  # switched strings
        self.hist.append(m)
        mm = float(np.median(self.hist))
        p = int(round(mm))
        nearest = min(self.tuning, key=lambda s: abs(s - mm))
        near = abs(nearest - mm) < 0.75
        return dict(note=note_name(p), midi=round(mm, 2), cents=round((mm - p) * 100, 1),
                    freq=round(self.a4 * 2 ** ((mm - 69) / 12), 2), level_db=round(lvl, 1),
                    string=self.tuning.index(nearest) + 1 if near else None,
                    string_note=note_name(nearest) if near else None,
                    string_cents=round((mm - nearest) * 100, 1) if near else None)

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
                if self.hum is not None:
                    blk = self.hum(blk)
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
        t.append("🎸 tuner  ", style="bold")
        t.append(f"{src.name}\n\n", style="dim")
        if r.get("note") is None:
            t.append("Play an open string...\n", style="cyan")
        else:
            c = r["cents"]
            ok = abs(c) <= 5
            t.append(f"{r['note']:>4s}  ", style="bold green" if ok else "bold yellow")
            t.append(f"{c:+5.1f} cents   {r['freq']:.1f} Hz\n")
            t.append(tuner_bar(c) + "\n", style="green" if ok else "yellow")
            t.append("flat" + " " * 33 + "sharp\n", style="dim")
            if r.get("string"):
                sc = r["string_cents"]
                hint = "✓ in tune" if abs(sc) <= 5 else ("tune up" if sc < 0 else "tune down")
                t.append(f"\nstring {r['string']} ({r['string_note']}): {sc:+.0f} cents → {hint}", style="bold")
        t.append(f"\n\nlevel {r.get('level_db', -120):.0f} dB   Ctrl+C to quit", style="dim")
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


# ---------------------------------------------------------------- latency calibration
def _save_cable_test(x: np.ndarray, sr: int) -> None:
    """Keeps the last cable test's recording (cache/cable-test.wav), to check what came back."""
    import soundfile as sf
    from . import config
    try:
        config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        sf.write(config.CACHE_DIR / "cable-test.wav", x, sr)
    except OSError:
        pass


def _tone_index(x: np.ndarray, sr: int, t: float, tones) -> int | None:
    """Which of `tones` sounds just after `t` (s), or None if none of them is clearly there."""
    a = max(0, int((t - 0.002) * sr))
    seg = x[a:a + int(0.02 * sr)]
    if len(seg) < 64:
        return None
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg)), 8192))
    f = float(np.argmax(spec)) * sr / 8192
    i = int(np.argmin([abs(f / ft - 1) for ft in tones]))
    return i if abs(f / tones[i] - 1) < 0.08 else None


def calibrate(device, channel: int, output_device=None, bpm: float = 90, beats: int = 12,
              warmup: int = 4, on_progress=None, stop_event: threading.Event | None = None,
              loopback: bool = False) -> dict:
    """A click plays; you hit muted strings together with every click. The median of the
    offset (detected onset − click) is the total round-trip latency plus the detector's
    bias. The first `warmup` clicks are for catching the pulse.

    loopback=True: a cable takes the metronome output back into `channel`, and nobody plays, so the
    offset is the system alone, and it's very regular. Each click has its own tone (cycling
    takeclick.LOOP_TONES), and a returning click only counts if it has the tone of the one that left,
    so it's never paired with its neighbour. It can be slightly negative: the clicks are placed using
    the latencies the driver reports, so what's left is the driver's error."""
    from .audio_io import Metronome, MicSource
    from .dsp import Detector, Recorder

    src = MicSource(device, channel)
    rec = Recorder(src.sr)
    det = Detector(rec, gate_db=-60 if loopback else -55, legato=False)
    if loopback:
        warmup, bpm = 1, max(bpm, 120)
    beat = 60 / bpm
    t_first = 1.0
    from .takeclick import LOOP_TONES
    tones = dict(enumerate(LOOP_TONES)) if loopback else None
    clicks = [(t_first + i * beat, i % len(LOOP_TONES) if loopback else i % 4 == 0) for i in range(warmup + beats)]
    metro = Metronome(output_device, src, clicks, tones=tones)
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
    if loopback:
        tone_of = {o: _tone_index(rec.audio(), src.sr, o, LOOP_TONES) for o in onsets}
    for ct, key in clicks[warmup:]:
        if loopback:          # its own tone, so up to a second late (the same tone comes back every 4 beats)
            near = [o - ct for o in onsets if -0.25 <= o - ct <= 1.0 and tone_of[o] == key]
        else:
            near = [o - ct for o in onsets if -0.15 <= o - ct <= 0.35]
        if near:
            offs.append(min(near, key=abs))
    if loopback:
        _save_cable_test(rec.audio(), src.sr)
    if len(offs) < beats // 2:
        if loopback:
            x = rec.audio()
            peak = round(float(20 * np.log10(np.max(np.abs(x)) + 1e-9)), 1) if len(x) else -120.0
            heard = sum(1 for o in onsets if o >= t_first - 0.1)
            diag = dict(hits=len(offs), heard=heard, peak_db=peak, channel=channel)
            if heard:
                return dict(ok=False, code="loop_other_sound", **diag,
                            message=f"Input {channel} heard {heard} sounds, but none was a returning click.")
            return dict(ok=False, code="no_loop", **diag,
                        message=f"Input {channel} heard nothing (peak {peak} dB). Check the cable, the input and its gain.")
        return dict(ok=False, code="too_few_hits", hits=len(offs),
                    message="Not enough hits detected. Raise the gain or play harder, without distortion.")
    offs = np.array(offs)
    med = float(np.median(offs))
    spread = float(np.median(np.abs(offs - med)))
    if loopback and spread > 0.004:                     # a cable is exact: a wobbly result means it heard something else
        return dict(ok=False, code="loop_unsteady", hits=len(offs), spread_ms=round(1000 * spread, 1),
                    message="The returning clicks were irregular. Turn off direct monitoring and lower the input gain.")
    return dict(ok=True, code="ok", method="loopback" if loopback else "play",
                latency_ms=round(1000 * med, 1), spread_ms=round(1000 * spread, 1), hits=len(offs),
                message=f"Latency {1000 * med:.0f} ms (±{1000 * spread:.0f} ms, {len(offs)} hits)")
