"""Contenido para aprender: diccionario de acordes, cifrados y ruta de aprendizaje.

- guitarr/data/acordes.json   : digitaciones (6ta→1ra, -1 = no suena)
- guitarr/data/cifrados/*.txt : ejercicios incluidos, en el formato de texto de abajo
- ~/.guitarr/cifrados/*.txt   : tus cifrados
- guitarr/data/ruta.json      : niveles → lecciones → ejercicios que se aprueban tocando

Formato de cifrado (texto plano):

    titulo: Pop en Sol
    bpm: 90
    compas: 4/4          # opcional (4/4)
    capo: 2              # opcional
    rasgueo: D.DU.UDU    # opcional: D abajo, U arriba, . nada (una casilla por corchea)
    nota: un consejo     # opcional

    [Verso]
    G | D | Em | C       # un compás por barra; "C G" = dos acordes en un compás
    G | % | Em | -       # % repite el acorde anterior, - es un compás sin tocar
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from . import config

DATA_DIR = Path(__file__).parent / "data"
OPEN_STRINGS = [40, 45, 50, 55, 59, 64]  # 6ta ... 1ra
HEADER_KEYS = {"titulo", "artista", "nivel", "bpm", "compas", "capo", "rasgueo", "nota"}


class CatalogError(Exception):
    pass


# ---------------------------------------------------------------- acordes
@lru_cache(maxsize=None)
def _chords_data() -> dict:
    return json.loads((DATA_DIR / "acordes.json").read_text(encoding="utf-8"))


def chord_groups() -> list[dict]:
    return _chords_data()["groups"]


def chords() -> list[dict]:
    return _chords_data()["chords"]


def get_chord(cid: str) -> dict | None:
    return next((c for c in chords() if c["id"] == cid), None)


def chord_pitches(chord: dict, capo: int = 0) -> list[int]:
    return [OPEN_STRINGS[i] + capo + f for i, f in enumerate(chord["frets"]) if f is not None and f >= 0]


# ---------------------------------------------------------------- cifrados
def user_dir() -> Path:
    return config.HOME / "cifrados"


def slug(text: str) -> str:
    s = re.sub(r"[^\w\-]+", "-", text.lower(), flags=re.UNICODE).strip("-")
    return s[:60] or "cifrado"


def parse_cifrado(text: str, cid: str = "cifrado") -> dict:
    """Texto → cifrado (dict). Errores con número de línea."""
    meta: dict = {}
    bars: list[dict] = []
    section = None
    prev = None
    unknown: list[str] = []
    for ln, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^([a-záéíóú]+)\s*:\s*(.*)$", line, re.I)
        if m and m.group(1).lower() in HEADER_KEYS and "|" not in line:
            meta[m.group(1).lower()] = m.group(2).strip()
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            section = m.group(1).strip()
            continue
        bpb = _beats_per_bar(meta.get("compas", "4/4"), ln)
        for cell in [c.strip() for c in line.split("|")]:
            if not cell:
                continue
            names = cell.split()
            per = bpb / len(names)
            for name in names:
                if name == "%":
                    if prev is None:
                        raise CatalogError(f"Línea {ln}: '%' sin un acorde antes")
                    name = prev
                if name in ("-", "NC", "N.C."):
                    bars.append(dict(chord=None, beats=per, frets=[], section=section))
                else:
                    ch = get_chord(name)
                    if ch is None and name not in unknown:
                        unknown.append(name)
                    bars.append(dict(chord=name, beats=per, frets=ch["frets"] if ch else [], section=section))
                    prev = name
                section = None
    if not bars:
        raise CatalogError("El cifrado no tiene compases (líneas con acordes separados por |).")
    try:
        bpm = float(meta.get("bpm", 90))
        capo = int(meta.get("capo", 0) or 0)
        level = int(meta.get("nivel", 0) or 0)
    except ValueError as e:
        raise CatalogError(f"Encabezado inválido: {e}") from e
    if not 20 <= bpm <= 300:
        raise CatalogError("bpm tiene que estar entre 20 y 300")
    return dict(id=cid, title=meta.get("titulo") or cid, artist=meta.get("artista"), bpm=bpm,
                beats_per_bar=_beats_per_bar(meta.get("compas", "4/4"), 0), capo=capo, level=level,
                strum=meta.get("rasgueo", ""), note=meta.get("nota", ""), bars=bars, missing=unknown)


def _beats_per_bar(compas: str, ln: int) -> int:
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", compas or "4/4")
    if not m or not 1 <= int(m.group(1)) <= 12:
        raise CatalogError(f"Línea {ln}: compás inválido '{compas}' (p.ej. 4/4, 3/4, 6/8)")
    return int(m.group(1))


def _cifrado_files() -> dict[str, tuple[Path, bool]]:
    out = {p.stem: (p, False) for p in sorted((DATA_DIR / "cifrados").glob("*.txt"))}
    if user_dir().exists():
        out.update({p.stem: (p, True) for p in sorted(user_dir().glob("*.txt"))})
    return out


def cifrados() -> list[dict]:
    rows = []
    for cid, (p, mine) in _cifrado_files().items():
        try:
            c = parse_cifrado(p.read_text(encoding="utf-8"), cid)
        except CatalogError as e:
            rows.append(dict(id=cid, title=cid, mine=mine, error=str(e)))
            continue
        chords_used = list(dict.fromkeys(b["chord"] for b in c["bars"] if b["chord"]))
        rows.append(dict(id=cid, title=c["title"], artist=c["artist"], level=c["level"], bpm=c["bpm"],
                         capo=c["capo"], beats_per_bar=c["beats_per_bar"], strum=c["strum"], note=c["note"],
                         chords=chords_used, bars=len(c["bars"]), missing=c["missing"], mine=mine))
    rows.sort(key=lambda r: (r.get("mine", False), r.get("level") or 0, r["id"]))
    return rows


def cifrado_text(cid: str) -> tuple[str, bool]:
    f = _cifrado_files().get(cid)
    if f is None:
        raise CatalogError(f"No encontré el cifrado '{cid}' (ver: guitarr cancionero)")
    return f[0].read_text(encoding="utf-8"), f[1]


def get_cifrado(cid: str) -> dict:
    text, _ = cifrado_text(cid)
    return parse_cifrado(text, cid)


def save_cifrado(text: str, cid: str | None = None) -> dict:
    c = parse_cifrado(text, cid or "nuevo")
    if c["missing"]:
        raise CatalogError(f"No conozco estos acordes: {', '.join(c['missing'])} (mirá el diccionario)")
    cid = cid or slug(c["title"])
    builtin = (DATA_DIR / "cifrados" / f"{cid}.txt").exists()
    if builtin:
        cid = f"{cid}-mio"
    user_dir().mkdir(parents=True, exist_ok=True)
    (user_dir() / f"{cid}.txt").write_text(text.strip() + "\n", encoding="utf-8")
    return dict(id=cid, title=c["title"])


def delete_cifrado(cid: str) -> None:
    f = _cifrado_files().get(cid)
    if f is None or not f[1]:
        raise CatalogError("Solo se pueden borrar tus propios cifrados.")
    f[0].unlink()


def chart_from_chord(cid: str, times: int = 1) -> dict:
    ch = get_chord(cid)
    if ch is None:
        raise CatalogError(f"No conozco el acorde '{cid}'")
    return dict(id=f"acorde-{cid}", title=ch["id"], bpm=60, beats_per_bar=1, capo=0,
                bars=[dict(chord=cid, beats=1, frets=ch["frets"]) for _ in range(times)])


def chart_alternating(names: list[str], times: int) -> dict:
    bars = []
    for _ in range(times):
        for n in names:
            ch = get_chord(n)
            if ch is None:
                raise CatalogError(f"No conozco el acorde '{n}'")
            bars.append(dict(chord=n, beats=1, frets=ch["frets"]))
    return dict(id="cambio-" + "-".join(names), title=" ↔ ".join(names), bpm=60, beats_per_bar=1, capo=0, bars=bars)


# ---------------------------------------------------------------- ruta de aprendizaje
@lru_cache(maxsize=None)
def ruta() -> dict:
    return json.loads((DATA_DIR / "ruta.json").read_text(encoding="utf-8"))


def lessons() -> list[dict]:
    return [ls for lvl in ruta()["levels"] for ls in lvl["lessons"]]


def get_lesson(lid: str) -> dict:
    ls = next((x for x in lessons() if x["id"] == lid), None)
    if ls is None:
        raise CatalogError(f"No existe la lección '{lid}'")
    return ls


def get_exercise(lid: str, eid: str) -> dict:
    ex = next((e for e in get_lesson(lid)["exercises"] if e["id"] == eid), None)
    if ex is None:
        raise CatalogError(f"No existe el ejercicio '{eid}' en '{lid}'")
    return ex


def exercise_setup(lid: str, eid: str):
    """→ (RefOptions, modo, velocidad, puntaje mínimo) para escuchar un ejercicio."""
    from .reference import RefOptions

    ex = get_exercise(lid, eid)
    kind = ex["kind"]
    if kind == "notas":
        return RefOptions(notes=list(ex["notes"])), "wait", 1.0, ex.get("min", 80)
    if kind == "acorde":
        return RefOptions(chart=chart_from_chord(ex["chord"], ex.get("times", 4))), "wait", 1.0, ex.get("min", 75)
    if kind == "cambio":
        return RefOptions(chart=chart_alternating(ex["chords"], ex.get("times", 4))), "wait", 1.0, ex.get("min", 75)
    if kind == "cifrado":
        return RefOptions(chart=get_cifrado(ex["cifrado"])), "tempo", ex.get("speed", 1.0), ex.get("min", 80)
    raise CatalogError(f"Tipo de ejercicio desconocido: {kind}")


# ---------------------------------------------------------------- terminal
def print_songs(cid: str | None = None) -> None:
    if cid is None:
        print("Cifrados (tocalos con: guitarr live --cifrado ID --mode tempo):\n")
        for c in cifrados():
            if c.get("error"):
                print(f"  {c['id']:26s} ⚠️  {c['error']}")
                continue
            tag = "  (tuyo)" if c["mine"] else ""
            capo = f" capo {c['capo']}" if c["capo"] else ""
            print(f"  {c['id']:26s} {c['title']}  ♩={c['bpm']:g}{capo}  [{' '.join(c['chords'])}]{tag}")
        print(f"\nTus cifrados van en {user_dir()} (formato: ver `guitarr cancionero --formato`)")
        return
    c = get_cifrado(cid)
    print(f"{c['title']}  ♩={c['bpm']:g}  {c['beats_per_bar']}/4" + (f"  capo {c['capo']}" if c["capo"] else "")
          + (f"  rasgueo {c['strum']}" if c["strum"] else ""))
    if c["note"]:
        print(f"  {c['note']}")
    line: list[str] = []
    acc = 0.0
    for b in c["bars"]:
        if b.get("section"):
            if line:
                print("  " + " | ".join(line))
                line = []
            print(f"\n[{b['section']}]")
        name = b["chord"] or "-"
        if acc and line:
            line[-1] += f" {name}"
        else:
            line.append(name)
        acc = (acc + b["beats"]) % c["beats_per_bar"]
    if line:
        print("  " + " | ".join(line))
