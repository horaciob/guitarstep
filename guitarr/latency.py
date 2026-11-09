"""Is it you or the system? Latency bookkeeping and a verdict on a take's timing.

Two ways to measure the delay between the click and what the input hears:
- "loopback": a cable from the metronome output into an input. Nobody plays, so it's the system alone
  (output + input latency, plus the detector's bias). This is the correction to apply.
- "play": you hit muted strings on the clicks. That's the system *plus your habit* (most people land
  a little ahead of a click). Used as the correction only when there's no loopback measurement;
  with one, the difference is your own tendency and is shown, not hidden.

What was measured, how and with which devices lives in config.toml's [latency] table, so the UI can
warn when you changed the input or the metronome output since.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np

from . import config

STEADY_SPREAD_MS = 50      # this regular, an offset is mechanical rather than human
BIG_OFFSET_MS = 60
SLIGHT_OFFSET_MS = 25
UNSTEADY_SPREAD_MS = 70
MIN_HITS = 4


def info() -> dict:
    return dict(config.load().get("latency", {}))


def record(method: str, measured_ms: float, spread_ms: float, input_name: str | None, output_name: str | None) -> dict:
    """Saves a measurement and decides the correction to apply (returns {applied_ms, tendency_ms, ...})."""
    data = config.load()
    lat = dict(data.get("latency", {}))
    same = lat.get("input") == input_name and lat.get("output") == output_name
    now = datetime.now().isoformat(timespec="seconds")
    if method == "loopback":
        lat.update(method="loopback", system_ms=measured_ms, system_spread_ms=spread_ms, input=input_name,
                   output=output_name, at=now)
        if not same:
            lat.pop("play_ms", None)
        applied = measured_ms
    else:
        lat.update(play_ms=measured_ms, play_spread_ms=spread_ms, play_at=now)
        if lat.get("system_ms") is not None and same:
            applied = lat["system_ms"]                     # keep the system's number; the rest is you
        else:
            lat.update(method="play", input=input_name, output=output_name, at=now)
            lat.pop("system_ms", None)
            applied = measured_ms
    data["latency"] = lat
    data["audio"]["latency_ms"] = applied
    config.save(data)
    return status(input_name, output_name)


def status(input_name: str | None, output_name: str | None) -> dict:
    """What's applied, how it was measured, your tendency, and warnings about the current setup."""
    lat = info()
    applied = config.load()["audio"].get("latency_ms")
    tendency = None
    if lat.get("system_ms") is not None and lat.get("play_ms") is not None:
        tendency = round(lat["play_ms"] - lat["system_ms"], 1)
    warnings = []
    if input_name and output_name and input_name != output_name:
        warnings.append(dict(code="two_devices", params=dict(input=input_name, output=output_name)))
    if lat.get("input") and (lat.get("input") != input_name or lat.get("output") != output_name):
        warnings.append(dict(code="devices_changed", params=dict(input=lat.get("input"), output=lat.get("output"))))
    if not lat and not applied:
        warnings.append(dict(code="never_measured", params={}))
    elif applied is not None and abs(applied) > 200:      # a whole beat off: it matched the wrong click
        warnings.append(dict(code="too_large", params=dict(ms=applied)))
    elif applied is not None and applied < 0 and lat.get("method") != "loopback":
        warnings.append(dict(code="negative", params=dict(ms=applied)))
    return dict(applied_ms=applied, method=lat.get("method"), at=lat.get("at"), input=lat.get("input"),
                current_input=input_name, current_output=output_name,
                output=lat.get("output"), system_ms=lat.get("system_ms"), play_ms=lat.get("play_ms"),
                tendency_ms=tendency, warnings=warnings)


def verdict(timing_ms: list[float], method: str | None = None) -> dict | None:
    """Reads a take's hits (ms, − early / + late) as: on time, a bit early/late, unsteady, or a steady offset —
    which, unless the latency was measured with a cable, is more likely the system than your hand."""
    x = np.asarray([v for v in timing_ms if v is not None], float)
    if len(x) < MIN_HITS:
        return None
    med = float(np.median(x))
    spread = float(np.std(x))
    p = dict(ms=round(abs(med)), signed_ms=round(med), spread=round(spread), n=int(len(x)),
             dir="early" if med < 0 else "late", measured=method or "none")
    if abs(med) >= BIG_OFFSET_MS and spread <= STEADY_SPREAD_MS:
        return dict(code="steady_you" if method == "loopback" else "steady_system", params=p)
    if spread > UNSTEADY_SPREAD_MS:
        return dict(code="unsteady", params=p)
    if abs(med) >= SLIGHT_OFFSET_MS:
        return dict(code="slight", params=p)
    return dict(code="on_time", params=p)
