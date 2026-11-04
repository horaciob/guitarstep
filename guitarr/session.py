"""Sesión en vivo: une fuente de audio, detector, seguidor y metrónomo.

La usan tanto la terminal (tui.py) como la interfaz web (gui/server.py): corre
el loop en `run()` y expone el estado con `snapshot()` (seguro entre hilos).
"""
from __future__ import annotations

import queue
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from . import config
from .audio_io import FileSource, Metronome, MicSource
from .core import Reference
from .dsp import CHROMA_LEN, CHROMA_OFF, HOP, MIN_GAP, NFFT, PITCH_LEN, PITCH_OFF, Detector, Recorder
from .follow import (Judge, TempoFollower, Trainer, WaitFollower, fmt_dt, group_events, min_repeat_gap,
                     pass_score)


@dataclass
class LiveOptions:
    mode: str = "wait"               # wait | tempo
    speed: float = 1.0
    device: str | int | None = None
    channel: int = 1
    output_device: str | int | None = None
    samplerate: int | None = None
    click: bool = True
    count_in: int | None = None
    latency_ms: float = 0.0
    gate_db: float = -50.0
    sensitivity: float = 1.0
    timing_tol: float = 0.06
    window: float = 0.2
    loop: bool = False
    trainer: bool = False
    speed_step: float = 0.05
    target: float = 90.0
    max_speed: float = 1.0
    legato: bool = True
    count_extras: bool = True        # False para cifrados: los rasguidos de relleno no cuentan
    transpose: int = 0
    simulate: Path | None = None
    fast: bool = False
    save_dir: Path = field(default_factory=lambda: config.TAKES_DIR)


class LiveSession:
    def __init__(self, ref: Reference, opts: LiveOptions):
        self.ref, self.opts, self.grid = ref, opts, ref.grid
        self.events = group_events(ref.notes)
        self.judge = Judge(opts.transpose, name_shift=-ref.capo)
        if opts.simulate:
            self.src = FileSource(opts.simulate, realtime=not opts.fast)
        else:
            self.src = MicSource(opts.device, opts.channel, opts.samplerate)
        self.sr = self.src.sr
        self.rec = Recorder(self.sr)
        # en pasajes rápidos achicamos el mínimo entre ataques y el filtro de re-detección
        gap = min_repeat_gap(self.events, opts.speed if opts.mode == "tempo" else 1.0)
        self.det = Detector(self.rec, opts.gate_db, opts.sensitivity,
                            min_gap=float(np.clip(0.6 * gap, 0.035, MIN_GAP)), legato=opts.legato)
        self.repeat_gap = float(np.clip(0.6 * gap, 0.04, 0.1))
        self.use_click = opts.mode == "tempo" and opts.click and not opts.simulate
        if opts.mode == "wait":
            self.follower = WaitFollower(self.events, self.judge, opts.loop)
        else:
            trainer = Trainer(opts.speed_step, opts.target, opts.max_speed) if opts.trainer else None
            self.follower = TempoFollower(self.events, self.judge, opts.speed, opts.window, self.grid,
                                          loop=opts.loop, trainer=trainer, count_in=opts.count_in,
                                          click=self.use_click, timing_tol=opts.timing_tol,
                                          count_extras=opts.count_extras)
        # retardo del análisis: frame del detector + ventana de altura tras el ataque
        need = max(PITCH_OFF + PITCH_LEN, CHROMA_OFF + CHROMA_LEN / self.sr)
        self.analysis_lag = (NFFT + 2 * HOP) / self.sr + need
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self.log: deque = deque(maxlen=12)
        self.last = ""
        self.now = 0.0
        self.running = False
        self.report: dict | None = None
        self.error: str | None = None
        self.started = datetime.now()

    # ------------------------------------------------------------ control
    def stop(self) -> None:
        self._stop.set()

    def _say(self, msg: str | None, t: float, on_message=None) -> None:
        if not msg:
            return
        self.last = msg
        self.log.append((round(t, 2), msg))
        if on_message:
            on_message(t, msg)

    def run(self, on_update=None, on_message=None) -> dict:
        """Loop principal (bloqueante). `on_update()` se llama ~20 veces por segundo."""
        f, det, rec, src = self.follower, self.det, self.rec, self.src
        lat = self.opts.latency_ms / 1000
        metro = None
        prev = None
        self.running = True
        src.start()
        try:
            if self.use_click:
                f.schedule(1.0)  # 1 s para que arranque el audio, después la cuenta de entrada
                metro = Metronome(self.opts.output_device, src, f.clicks)
                metro.start()
            last_ui = 0.0
            ended = False
            while not ended and not self._stop.is_set():
                try:
                    blk = src.q.get(timeout=0.05)
                except queue.Empty:
                    blk = np.zeros(0, np.float32)
                with self.lock:
                    while blk is not None:
                        rec.append(blk)
                        det.update_level(blk)
                        try:
                            blk = src.q.get_nowait()
                        except queue.Empty:
                            break
                    if blk is None:
                        ended = True
                    self.now = rec.n / self.sr
                    for d in det.process():
                        d.t -= lat
                        if prev and d.midi is not None and prev.midi is not None and not d.legato \
                                and round(d.midi) == round(prev.midi) and d.t - prev.t < self.repeat_gap \
                                and d.db <= prev.db + 1:
                            continue  # la misma nota sonando, re-detectada
                        prev = d
                        if f.mode == "tempo" and f.t0 is None:
                            f.start(d.t)  # sin metrónomo: tu primera nota marca el tempo
                        self._say(f.on_detection(d), d.t, on_message)
                    # en el último bloque ya se analizó todo el audio
                    horizon = self.now - lat - (0 if ended else self.analysis_lag)
                    self._say(f.tick(horizon if not ended else self.now + 10), self.now, on_message)
                    if f.done:
                        ended = True
                if on_update and (self.now - last_ui >= 0.05 or ended):
                    last_ui = self.now
                    on_update()
        except KeyboardInterrupt:  # Ctrl+C: terminar normalmente (guardar toma y reporte)
            pass
        except Exception as e:  # que la GUI pueda mostrarlo
            self.error = str(e)
            raise
        finally:
            src.stop()
            if metro:
                metro.stop()
            self.running = False
        saved = None
        if not self.opts.simulate:
            saved = save_take(self.rec, self.opts.save_dir)
        with self.lock:
            self.report = self.build_report(saved)
        return self.report

    # ------------------------------------------------------------ estado
    def snapshot(self, before: int = 6, after: int = 14) -> dict:
        with self.lock:
            f, evs = self.follower, self.events
            k = min(f.k, len(evs) - 1)
            lo, hi = max(0, k - before), min(len(evs), k + after)
            judged = [e for e in evs if e.status != "pending"]
            good = sum(e.status in ("ok", "octave") for e in judged)
            countdown = f.countdown(self.now) if f.mode == "tempo" else None
            bar, beat = self.grid.bar_of(evs[k].time)
            return dict(
                running=self.running, mode=f.mode, source=self.src.name,
                speed=getattr(f, "speed", 1.0), now=round(self.now, 2),
                level_db=round(self.det.level_db, 1), peak=round(self.det.peak, 3),
                clip=self.det.peak >= 0.98, gate_db=self.opts.gate_db, tuning=self.judge.tuning(),
                k=f.k, total=len(evs), bar=bar, beat=round(beat, 2),
                lane=[dict(i=i, label=e.label(), status=e.status, detail=e.detail, tab=e.tab,
                           pitches=e.pitches, time=round(e.time, 3), current=i == f.k,
                           dt=None if e.dt is None else round(e.dt * 1000)) for i, e in enumerate(evs[lo:hi], lo)],
                waiting_first=f.mode == "tempo" and f.t0 is None, countdown=countdown,
                last=self.last, log=list(self.log),
                stats=dict(judged=len(judged), pct=round(100 * good / len(judged)) if judged else None,
                           errors=sum(e.status in ("wrong", "missed") or e.errors > 0 for e in judged),
                           extras=len(getattr(f, "extras", []))),
                passes=list(f.passes), error=self.error, done=self.report is not None,
            )

    def build_report(self, saved: Path | None) -> dict:
        f, grid, opts = self.follower, self.grid, self.opts
        evs = self.events
        judged = [e for e in evs if e.status != "pending"]
        if not judged and f.history:  # cortaste justo al terminar una vuelta: usar la última
            judged = [_Ev(**d) for d in f.history[-1]]
        first = sum(e.status in ("ok", "octave") for e in judged)
        dts = [e.dt for e in judged if e.dt is not None and e.status in ("ok", "octave")]
        issues = []
        for e in judged:
            bar, beat = grid.bar_of(e.time)
            base = dict(t=round(e.time, 3), bar=bar, beat=round(beat, 2), label=e.label())
            if e.status in ("wrong", "missed"):
                issues.append(dict(base, type=e.status, msg=f"{e.label()}: {e.detail}"))
            elif e.status == "fixed":
                issues.append(dict(base, type="fixed",
                                   msg=f"{e.label()}: {e.errors} intento(s) mal antes de acertar (último: {e.detail})"))
            elif f.mode == "tempo" and e.dt is not None and abs(e.dt) > opts.timing_tol:
                issues.append(dict(base, type="timing", msg=f"{e.label()}: {fmt_dt(e.dt)}",
                                   dt_ms=round(e.dt * 1000)))
        # compases: acumulado de todas las vueltas
        bars: dict[int, dict] = {}
        all_passes = list(f.history) + ([[dict(time=e.time, status=e.status, errors=e.errors, dt=e.dt)
                                          for e in evs]] if any(e.status != "pending" for e in evs) else [])
        for p in all_passes:
            for e in p:
                if e["status"] == "pending":
                    continue
                b = grid.bar_index(e["time"])
                d = bars.setdefault(b, dict(bar=b, notes=0, errors=0, timing=0))
                d["notes"] += 1
                if e["status"] in ("wrong", "missed", "fixed") or e["errors"]:
                    d["errors"] += 1
                elif f.mode == "tempo" and e["dt"] is not None and abs(e["dt"]) > opts.timing_tol:
                    d["timing"] += 1
        extras = len(getattr(f, "extras", []))
        tun = self.judge.tuning()
        summary = dict(
            events=len(evs), judged=len(judged), first_try=first,
            first_try_pct=round(100 * first / len(judged), 1) if judged else None,
            fixed=sum(e.status == "fixed" for e in judged),
            wrong=sum(e.status == "wrong" for e in judged),
            missed=sum(e.status == "missed" for e in judged), extras=extras,
            timing_mean_ms=round(1000 * float(np.mean(dts)), 1) if dts else None,
            timing_std_ms=round(1000 * float(np.std(dts)), 1) if dts else None,
            tuning_cents=None if tun is None else round(tun, 1),
            score=None,
        )
        if any(e.status != "pending" for e in evs):
            summary["score"] = pass_score(judged, getattr(f, "pass_extras", 0) if f.mode == "tempo" else 0,
                                          opts.timing_tol)
        elif f.passes:
            summary["score"] = f.passes[-1]["score"]
        return dict(
            kind="live", mode=f.mode, speed=opts.speed, final_speed=getattr(f, "speed", None),
            reference=dict(name=self.ref.name, path=self.ref.path, track=self.ref.track),
            date=self.started.isoformat(timespec="seconds"), summary=summary, passes=list(f.passes),
            issues=issues, bars=[bars[b] for b in sorted(bars)],
            take=str(saved) if saved else None, overflows=self.src.overflows,
            simulated=bool(opts.simulate),
        )


class _Ev:
    """Evento reconstruido desde el historial de una vuelta (para el reporte)."""

    def __init__(self, time, label, status, errors, detail, dt):
        self.time, self._label, self.status, self.errors, self.detail, self.dt = time, label, status, errors, detail, dt

    def label(self) -> str:
        return self._label


def save_take(rec: Recorder, folder: Path) -> Path | None:
    import soundfile as sf

    if rec.n < rec.sr:
        return None
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"toma-{datetime.now():%Y%m%d-%H%M%S}.wav"
    sf.write(path, rec.audio(), rec.sr)
    return path
