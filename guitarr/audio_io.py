"""Entradas/salidas de audio: interfaz (sounddevice), WAV simulado y metrónomo."""
from __future__ import annotations

import queue
import re
import sys
import threading
import time
from pathlib import Path

import numpy as np

BLOCK = 256
BUILTIN_HINTS = re.compile(r"macbook|built-?in|internal|micr[oó]fono|microphone|iphone|ipad|"
                           r"airpods|teams|zoom|blackhole|soundflower|aggregate|virtual", re.I)


class AudioError(Exception):
    pass


def _sd():
    try:
        import sounddevice as sd
    except OSError as e:  # PortAudio no disponible
        raise AudioError(f"No pude abrir el sistema de audio: {e}") from e
    return sd


def parse_device(d):
    if d is None or d == "":
        return None
    return int(d) if str(d).lstrip("-").isdigit() else d


def devices() -> dict:
    sd = _sd()
    ins, outs = [], []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            ins.append(dict(index=i, name=d["name"], channels=d["max_input_channels"],
                            samplerate=int(d["default_samplerate"])))
        if d["max_output_channels"] > 0:
            outs.append(dict(index=i, name=d["name"], channels=d["max_output_channels"]))
    return dict(inputs=ins, outputs=outs, suggested=suggest_input(ins))


def suggest_input(inputs: list[dict]) -> int | None:
    """La primera entrada que parece una interfaz de audio (no el micrófono interno)."""
    for d in inputs:
        if not BUILTIN_HINTS.search(d["name"]):
            return d["index"]
    return None


def list_devices() -> None:
    info = devices()
    print("Entradas de audio (usá --device N --channel C):\n")
    for d in info["inputs"]:
        star = "  ← parece tu interfaz" if d["index"] == info["suggested"] else ""
        print(f"  {d['index']:2d}  {d['name']:40s} {d['channels']} canales  {d['samplerate']} Hz{star}")
    print("\nSalidas (para el metrónomo, --output-device N):\n")
    for d in info["outputs"]:
        print(f"  {d['index']:2d}  {d['name']}")
    print("\nTip: `guitarr config --device N --channel C` lo deja guardado.")


class MicSource:
    def __init__(self, device, channel: int = 1, samplerate: int | None = None):
        sd = _sd()
        dev = parse_device(device)
        try:
            info = sd.query_devices(dev, "input")
        except (ValueError, sd.PortAudioError) as e:
            raise AudioError(f"No encontré el dispositivo de entrada '{device}'. Mirá: guitarr devices") from e
        if channel > info["max_input_channels"]:
            raise AudioError(f"'{info['name']}' tiene {info['max_input_channels']} entradas; "
                             f"pediste el canal {channel}.")
        self.sr = int(samplerate or info["default_samplerate"])
        self.name = info["name"]
        self.q: queue.Queue = queue.Queue()
        self.adc0: float | None = None
        self.overflows = 0
        ch = channel - 1

        def cb(indata, frames, t, status):
            if status.input_overflow:
                self.overflows += 1
            if self.adc0 is None:
                st = getattr(self, "stream", None)
                self.adc0 = t.inputBufferAdcTime or (t.currentTime - (st.latency if st else 0.0))
            self.q.put(indata[:, ch].copy())

        try:
            self.stream = sd.InputStream(device=dev, channels=channel, samplerate=self.sr,
                                         blocksize=BLOCK, dtype="float32", latency="low", callback=cb)
        except sd.PortAudioError as e:
            raise AudioError(f"No pude abrir '{self.name}': {e}") from e

    def start(self):
        self.stream.start()

    def stop(self):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


class FileSource:
    """Reproduce un WAV como si fuera la entrada en vivo (para probar sin guitarra)."""

    def __init__(self, path: Path, realtime: bool = True):
        import soundfile as sf

        y, self.sr = sf.read(str(path), dtype="float32", always_2d=True)
        self.y = y.mean(axis=1)
        self.name = f"simulado: {Path(path).name}"
        self.realtime = realtime
        self.q: queue.Queue = queue.Queue()
        self.adc0 = 0.0
        self.overflows = 0
        self._stop = threading.Event()

    def start(self):
        def run():
            t_start = time.perf_counter()
            for i in range(0, len(self.y), BLOCK):
                if self._stop.is_set():
                    break
                self.q.put(self.y[i:i + BLOCK])
                if self.realtime:
                    lag = (i + BLOCK) / self.sr - (time.perf_counter() - t_start)
                    if lag > 0:
                        time.sleep(lag)
            self.q.put(np.zeros(int(self.sr * 0.6), np.float32))  # cola de silencio
            self.q.put(None)

        threading.Thread(target=run, daemon=True).start()

    def stop(self):
        self._stop.set()


class Metronome:
    """Clicks programados en tiempo de entrada (alineados con el reloj del ADC).

    `clicks` es una lista de (tiempo, acento) a la que se le pueden ir agregando
    clicks mientras suena (para loops y cambios de velocidad)."""

    def __init__(self, device, src: MicSource, clicks: list[tuple[float, bool]], volume: float = 1.0):
        sd = _sd()
        dev = parse_device(device)
        try:
            sr = int(sd.query_devices(dev, "output")["default_samplerate"])
        except (ValueError, sd.PortAudioError) as e:
            raise AudioError(f"No encontré la salida '{device}'.") from e
        self.sr, self.src = sr, src
        self.clicks = clicks
        self.idx = 0
        n = int(0.03 * sr)
        env = np.exp(-np.arange(n) / (0.006 * sr))
        tt = np.arange(n) / sr
        self.wave = {True: (0.6 * volume * env * np.sin(2 * np.pi * 1600 * tt)).astype(np.float32),
                     False: (0.4 * volume * env * np.sin(2 * np.pi * 1000 * tt)).astype(np.float32)}

        def cb(outdata, frames, t, status):
            outdata.fill(0)
            if self.src.adc0 is None:
                return
            st = getattr(self, "stream", None)
            dac = t.outputBufferDacTime or (t.currentTime + (st.latency if st else 0.0))
            lo = dac - self.src.adc0
            hi = lo + frames / sr
            j = self.idx
            clicks = self.clicks
            while j < len(clicks) and clicks[j][0] < hi:
                ct, acc = clicks[j]
                w = self.wave[acc]
                off = int(round((ct - lo) * sr))
                a, b = max(0, off), min(frames, off + len(w))
                if b > a:
                    outdata[a:b, 0] += w[a - off:b - off]
                if ct + len(w) / sr < hi:
                    self.idx = j + 1
                j += 1

        try:
            self.stream = sd.OutputStream(device=dev, channels=1, samplerate=sr, blocksize=BLOCK,
                                          dtype="float32", latency="low", callback=cb)
        except sd.PortAudioError as e:
            raise AudioError(f"No pude abrir la salida para el metrónomo: {e}") from e

    def start(self):
        self.stream.start()

    def stop(self):
        try:
            self.stream.stop()
            self.stream.close()
        except Exception:
            pass


def check_platform() -> str | None:
    if sys.platform != "darwin":
        return ("Aviso: la sincronía metrónomo↔entrada está probada en macOS (CoreAudio). "
                "En otros sistemas calibrá la latencia con `guitarr calibrate`.")
    return None
