"""Modo archivo: transcribe una toma, la alinea con la referencia y lista los errores."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .core import Note, Reference, note_name, shifted
from .reference import Log, transcribe

FPS = 20  # resolución temporal de la alineación (frames/seg)


@dataclass
class FileOptions:
    onset_tol: float = 0.15
    timing_tol: float = 0.06
    smooth: float = 2.0
    transpose: int = 0
    onset_threshold: float = 0.5
    frame_threshold: float = 0.3
    min_amp: float = 0.2


# ---------------------------------------------------------------- alineación
def note_chroma(notes: list[Note], length: float) -> np.ndarray:
    """Cromagrama sintético a partir de notas, con énfasis en el ataque."""
    T = int(np.ceil(length * FPS)) + 2
    C = np.full((12, T), 1e-3)
    for n in notes:
        a = max(0, int(n.start * FPS))
        b = min(max(a + 1, int(n.end * FPS)), T)
        C[n.pitch % 12, a:b] += np.exp(-np.arange(b - a) / (0.3 * FPS))
    return C


def align(ref: list[Note], usr: list[Note], smooth_s: float, subseq: bool = False) -> np.ndarray:
    """Tabla tiempo_usuario -> tiempo_referencia vía DTW.

    El mapeo se suaviza para que absorba cambios de tempo globales/lentos pero
    NO los adelantos/atrasos puntuales, que es lo que queremos reportar.
    Con `subseq`, la referencia (p.ej. una sección) se ubica dentro de una toma
    más larga, y lo que queda fuera se extrapola con el tempo medio.
    """
    import librosa

    end = max(max(n.end for n in ref), max(n.end for n in usr))
    Cr, Cu = note_chroma(ref, end), note_chroma(usr, end)
    _, wp = librosa.sequence.dtw(X=Cr, Y=Cu, metric="cosine", subseq=subseq)
    T = Cu.shape[1]
    cnt = np.bincount(wp[:, 1], minlength=T).astype(float)
    tot = np.bincount(wp[:, 1], weights=wp[:, 0], minlength=T)
    u_idx = np.arange(T)
    ok = cnt > 0
    u_ok, r_ok = u_idx[ok], tot[ok] / cnt[ok]
    ref_of_u = np.interp(u_idx, u_ok, r_ok)
    if subseq and len(u_ok) > 1:
        slope = (r_ok[-1] - r_ok[0]) / (u_ok[-1] - u_ok[0])
        pre, post = u_idx < u_ok[0], u_idx > u_ok[-1]
        ref_of_u[pre] = r_ok[0] + (u_idx[pre] - u_ok[0]) * slope
        ref_of_u[post] = r_ok[-1] + (u_idx[post] - u_ok[-1]) * slope
    w = max(1, int(smooth_s * FPS)) | 1
    pad = np.pad(ref_of_u, w // 2, mode="reflect", reflect_type="odd")  # extrapola lineal en bordes
    ref_of_u = np.convolve(pad, np.ones(w) / w, mode="valid")
    return np.stack([u_idx / FPS, ref_of_u / FPS])


def refine_alignment(ref: list[Note], usr: list[Note], pairs, window: float) -> np.ndarray | None:
    """Recalcula el mapeo de tempo con regresión lineal local sobre los ataques de
    las notas bien emparejadas. Los ataques son anclas mucho más confiables que el
    sustain, y una sola nota fuera de tiempo apenas mueve la recta."""
    ok = [(usr[j].start, ref[i].start) for i, j, k in pairs if k == "ok"]
    if len(ok) < 4:
        return None
    u, r = np.array(ok).T
    order = np.argsort(u)
    u, r = u[order], r[order]
    grid_t = np.arange(0, max(n.end for n in usr) + 1, 1 / FPS)
    out = np.empty_like(grid_t)
    for idx, t in enumerate(grid_t):
        w = window
        lo, hi = np.searchsorted(u, [t - w, t + w])
        while hi - lo < 4:  # agrandar ventana si hay pocas anclas
            w *= 1.5
            lo, hi = np.searchsorted(u, [t - w, t + w])
        a, b = np.polyfit(u[lo:hi], r[lo:hi], 1)
        out[idx] = a * t + b
    return np.stack([grid_t, out])


def warp(notes: list[Note], table: np.ndarray) -> list[Note]:
    f = lambda t: float(np.interp(t, table[0], table[1]))
    return [Note(f(n.start), f(n.end), n.pitch, n.amp) for n in notes]


def initial_shift(ref: list[Note], usr: list[Note], look: int = 6) -> float:
    """Desfase inicial robusto: ignora ruidos antes de empezar (una cuerda al aire,
    un golpe) buscando entre las primeras notas tuyas la que coincide con el
    arranque de la referencia y a la que le sigue la 2da nota de la referencia."""
    r0 = ref[0].pitch % 12
    r1 = next((n.pitch % 12 for n in ref if n.start > ref[0].start + 0.03), None)
    for k, n in enumerate(usr[:look]):
        if n.pitch % 12 != r0:
            continue
        nxt = [m.pitch % 12 for m in usr[k + 1:k + 4]]
        if r1 is None or r1 in nxt:
            return n.start - ref[0].start
    return usr[0].start - ref[0].start


# ---------------------------------------------------------------- comparación
def onset_tolerances(ref: list[Note], tol: float) -> np.ndarray:
    """Tolerancia por nota: no más de ~60% de la distancia al ataque vecino, así
    en pasajes rápidos una nota no se empareja con la de al lado."""
    starts = np.array([n.start for n in ref])
    uniq = np.unique(np.round(starts, 2))
    if len(uniq) < 2:
        return np.full(len(ref), tol)
    gaps = np.diff(uniq)
    gap_of = np.empty(len(uniq))
    gap_of[0], gap_of[-1] = gaps[0], gaps[-1]
    gap_of[1:-1] = np.minimum(gaps[:-1], gaps[1:])
    idx = np.clip(np.searchsorted(uniq, np.round(starts, 2)), 0, len(uniq) - 1)
    return np.clip(0.6 * gap_of[idx], 0.06, tol)


def match(ref: list[Note], usr: list[Note], tol: float):
    """Empareja notas en 3 pasadas: misma nota, misma nota otra octava, nota distinta."""
    order = np.argsort([n.start for n in usr], kind="stable")
    u_starts = np.array([usr[j].start for j in order])
    tols = onset_tolerances(ref, tol)
    used_r, used_u, pairs = set(), set(), []
    passes = [
        ("ok", lambda a, b: a == b),
        ("octava", lambda a, b: a % 12 == b % 12),
        ("nota", lambda a, b: True),
    ]
    for kind, cond in passes:
        cands = []
        for i, r in enumerate(ref):
            if i in used_r:
                continue
            lo, hi = np.searchsorted(u_starts, [r.start - tols[i], r.start + tols[i]])
            for jj in range(lo, hi):
                j = int(order[jj])
                if j not in used_u and cond(r.pitch, usr[j].pitch):
                    cands.append((abs(usr[j].start - r.start), i, j))
        for _, i, j in sorted(cands):
            if i not in used_r and j not in used_u:
                used_r.add(i)
                used_u.add(j)
                pairs.append((i, j, kind))
    missing = [i for i in range(len(ref)) if i not in used_r]
    extra = [j for j in range(len(usr)) if j not in used_u]
    return pairs, missing, extra


def suggest_transpose(ref: list[Note], usr: list[Note]) -> int:
    def hist(ns):
        h = np.bincount([n.pitch % 12 for n in ns],
                        weights=[n.end - n.start for n in ns], minlength=12)
        return h / (np.linalg.norm(h) + 1e-9)

    hr, hu = hist(ref), hist(usr)
    scores = np.array([hr @ np.roll(hu, k) for k in range(12)])
    k = int(np.argmax(scores))
    if k != 0 and scores[k] > 1.15 * scores[0]:
        return k if k <= 6 else k - 12
    return 0


# ---------------------------------------------------------------- análisis completo
def _align_and_match(ref: list[Note], usr: list[Note], opts: FileOptions):
    # toma bastante más larga que la referencia: ubicar la referencia adentro (subsecuencia)
    subseq = len(usr) > 1.3 * len(ref)
    shift = usr[0].start - ref[0].start if subseq else initial_shift(ref, usr)
    usr = [shifted(n, -shift) for n in usr]
    table = align(ref, usr, opts.smooth, subseq=subseq)
    usr_w = warp(usr, table)
    pairs, missing, extra = match(ref, usr_w, opts.onset_tol)
    table2 = refine_alignment(ref, usr, pairs, opts.smooth)
    if table2 is not None:
        usr_w = warp(usr, table2)
        pairs, missing, extra = match(ref, usr_w, opts.onset_tol)
    ok_pairs = [(i, j) for i, j, k2 in pairs if k2 == "ok"]
    tempo_ratio = 1.0
    if len(ok_pairs) >= 2:  # pendiente tiempo_ref / tiempo_usuario
        tempo_ratio = float(np.polyfit([usr[j].start for _, j in ok_pairs],
                                       [ref[i].start for i, _ in ok_pairs], 1)[0])
    return usr_w, pairs, missing, extra, tempo_ratio


def compare(reference: Reference, usr: list[Note], opts: FileOptions, log: Log = print) -> dict:
    section, grid = reference.notes, reference.grid
    if not usr:
        raise ValueError("No se detectaron notas en tu toma.")
    n_detected = len(usr)
    k = suggest_transpose(section, usr)
    if opts.transpose:
        usr = [shifted(n, dp=opts.transpose) for n in usr]
    elif k:
        log(f"\n⚠️  Parece que tu toma está {-k:+d} semitonos respecto de la referencia "
            f"(¿afinación distinta?). Probá con --transpose {k}\n")

    # Si practicaste una sección pero la toma parece la canción entera, alinear contra
    # la canción entera (mucho más robusto en riffs que se repiten) y reportar la sección.
    ref = section
    full = reference.all_notes
    if full and abs(len(usr) - len(full)) < abs(len(usr) - len(section)):
        ref = full
    usr_w, pairs, missing, extra, tempo_ratio = _align_and_match(ref, usr, opts)

    lo = section[0].start - 0.02
    hi = max(n.start for n in section) + 0.02
    in_sec = lambda t: lo <= t <= hi
    margin_hi = max(n.end for n in section) + 0.5

    ref_status = {}  # índice ref -> estado (solo dentro de la sección)
    usr_status = ["outside"] * len(usr_w)
    issues, dts = [], []

    def add(t, kind, msg, **kw):
        bar, beat = grid.bar_of(t)
        issues.append(dict(t=round(t, 3), bar=bar, beat=round(beat, 2), type=kind, msg=msg, **kw))

    for i, j, kind in pairs:
        r, u = ref[i], usr_w[j]
        if not in_sec(r.start):
            continue
        dt = u.start - r.start
        if kind == "ok":
            dts.append(dt)
            st = "ok"
            if abs(dt) > opts.timing_tol:
                st = "timing"
                add(r.start, "timing", f"⏱  {note_name(r.pitch):4s} {'tarde' if dt > 0 else 'adelantada'} "
                                       f"{abs(dt) * 1000:.0f} ms", pitch=r.pitch, dt_ms=round(dt * 1000))
        elif kind == "octava":
            st = "octave"
            add(r.start, "octave", f"↕  {note_name(r.pitch):4s} detectada en otra octava "
                                   f"({note_name(u.pitch)}) — puede ser error de detección",
                pitch=r.pitch, user_pitch=u.pitch)
        else:
            st = "wrong"
            add(r.start, "wrong", f"✗  tocaste {note_name(u.pitch):4s} en vez de {note_name(r.pitch)}",
                pitch=r.pitch, user_pitch=u.pitch)
        ref_status[i] = usr_status[j] = st
    matched_ok = {i for i, _, k2 in pairs if k2 == "ok"}
    for i in missing:
        r = ref[i]
        if not in_sec(r.start):
            continue
        # octava de otra nota del mismo acorde que sí sonó: casi seguro tapada por su armónico
        if any(abs(ref[x].start - r.start) < 0.03 and ref[x].pitch % 12 == r.pitch % 12 for x in matched_ok):
            ref_status[i] = "masked"
            continue
        ref_status[i] = "missing"
        add(r.start, "missing", f"∅  faltó {note_name(r.pitch)}", pitch=r.pitch)
    n_extra = 0
    for j in extra:
        t = usr_w[j].start
        if not lo - 0.5 <= t <= margin_hi:  # fuera de la sección practicada
            continue
        n_extra += 1
        usr_status[j] = "extra"
        add(t, "extra", f"+  nota de más: {note_name(usr_w[j].pitch)}", user_pitch=usr_w[j].pitch)
    issues.sort(key=lambda x: x["t"])

    # por compás
    bars: dict[int, dict] = {}
    for n in section:
        b = grid.bar_index(n.start)
        bars.setdefault(b, dict(bar=b, notes=0, errors=0, timing=0))["notes"] += 1
    for it in issues:
        d = bars.setdefault(it["bar"], dict(bar=it["bar"], notes=0, errors=0, timing=0))
        d["timing" if it["type"] == "timing" else "errors"] += 1

    st = list(ref_status.values())
    n_ok = st.count("ok") + st.count("timing")
    n_timing = st.count("timing")
    n_sec = len(section)
    summary = dict(
        ref_notes=n_sec, user_notes=n_detected, tempo_ratio=round(tempo_ratio, 3),
        correct=n_ok, correct_pct=round(100 * n_ok / n_sec, 1), timing_loose=n_timing,
        wrong=st.count("wrong"), missing=st.count("missing"), masked=st.count("masked"), extra=n_extra,
        timing_mean_ms=round(1000 * float(np.mean(dts)), 1) if dts else None,
        timing_std_ms=round(1000 * float(np.std(dts)), 1) if dts else None,
        score=round(100 * max(0, n_ok - 0.5 * n_timing - 0.5 * n_extra) / n_sec, 1),
    )
    sec_idx = [i for i, n in enumerate(ref) if in_sec(n.start)]
    t_lo, t_hi = lo - 1.0, margin_hi + 0.5
    return dict(
        kind="file", summary=summary, transpose_suggestion=k, issues=issues,
        bars=[bars[b] for b in sorted(bars)],
        roll=dict(ref=[[round(ref[i].start, 3), round(ref[i].end, 3), ref[i].pitch, ref_status.get(i, "ok")]
                       for i in sec_idx],
                  user=[[round(n.start, 3), round(n.end, 3), n.pitch, s] for n, s in zip(usr_w, usr_status)
                        if t_lo <= n.start <= t_hi]),
        downbeats=[round(grid.bar_time(b), 3) for b in range(1, grid.bar_index(max(n.start for n in section)) + 2)],
    )


def analyze_take(reference: Reference, take: Path, opts: FileOptions, log: Log = print) -> tuple[dict, list[Note]]:
    log(f"[transcribiendo] tu toma: {Path(take).name}")
    usr = transcribe(Path(take), opts.onset_threshold, opts.frame_threshold, opts.min_amp)
    result = compare(reference, usr, opts, log)
    result["take"] = str(take)
    result["reference"] = dict(name=reference.name, path=reference.path, track=reference.track)
    return result, usr
