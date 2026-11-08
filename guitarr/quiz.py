"""Exercises that are drawn fresh every time, and the ones you pass by answering.

- quiz: multiple-choice questions (theory, reading tab, ear training). The server keeps the answers.
- pick: select notes on the fretboard ("every G between frets 2 and 7"); checked by position or pitch class.
- find_note / play_interval: targets you play, graded by the listener like any other exercise.

Prompts and choices are {code, params} so the UI can show them in any language (`quiz.<code>`).
A draw lives in memory until it is finished (or replaced by a newer draw of the same exercise).
"""
from __future__ import annotations

import random
import secrets
import threading

from . import theory as th

_lock = threading.Lock()
_draws: dict[str, dict] = {}                      # token → {lesson, exercise, need, items, answers}
_latest: dict[tuple[str, str], dict] = {}         # (lesson, exercise) → the last listener draw {notes, prompts}
MAX_DRAWS = 64


class QuizError(ValueError):
    pass


def L(code: str, **params) -> dict:
    return dict(code=code, params=params)


# ---------------------------------------------------------------- building blocks
SIMPLE = ["m2", "M2", "m3", "M3", "P4", "A4", "P5", "m6", "M6", "m7", "M7", "P8"]
NATURALS = ["C", "D", "E", "F", "G", "A", "B"]
KEYS = ["C", "G", "D", "A", "E", "F", "Bb", "Eb"]
ENHARMONIC = [("C#", "Db"), ("D#", "Eb"), ("F#", "Gb"), ("G#", "Ab"), ("A#", "Bb"), ("E", "Fb"), ("B", "Cb"), ("E#", "F"), ("B#", "C")]
OPEN_NAMES = {6: "E", 5: "A", 4: "D", 3: "G", 2: "B", 1: "E"}


def _choices(rng: random.Random, answer, pool, n: int = 4, label=lambda x: x):
    """`answer` plus n-1 different options from `pool`, shuffled. Ids are positions, labels what you see."""
    others = [p for p in dict.fromkeys(pool) if p != answer]
    rng.shuffle(others)
    opts = [answer] + others[:n - 1]
    rng.shuffle(opts)
    return [dict(id=str(i), label=label(o)) for i, o in enumerate(opts)], str(opts.index(answer))


def _iv(x):
    return L("iv", name=x)


def _q(prompt: dict, choices, answer: str, **extra) -> dict:
    return dict(type="choice", prompt=prompt, choices=choices, answer=answer, **extra)


# ---------------------------------------------------------------- quiz generators (one question each)
def q_interval_frets(rng, ex):
    pool = ex.get("intervals", SIMPLE)
    iv = rng.choice(pool)
    a = rng.randint(0, 12 - th.INTERVALS[iv][1] if th.INTERVALS[iv][1] <= 12 else 0)
    ch, ans = _choices(rng, iv, pool if len(pool) >= 4 else SIMPLE, label=_iv)
    return _q(L("interval_frets", a=a, b=a + th.INTERVALS[iv][1]), ch, ans)


def q_interval_ear(rng, ex):
    pool = ex.get("intervals", SIMPLE)
    iv = rng.choice(pool)
    root = rng.randint(48, 60)
    ch, ans = _choices(rng, iv, pool, n=min(4, len(pool)), label=_iv)
    return _q(L("interval_ear"), ch, ans, play=[root, root + th.INTERVALS[iv][1]], melodic=True)


def q_enharmonic(rng, ex):
    a, b = rng.choice(ENHARMONIC[:5])
    note, other = (a, b) if rng.random() < 0.5 else (b, a)
    pool = [x for pair in ENHARMONIC[:5] for x in pair] + NATURALS
    ch, ans = _choices(rng, other, [p for p in pool if th.pc(p) != th.pc(note)] + [other])
    return _q(L("enharmonic", note=note), ch, ans)


def q_half_step(rng, ex):
    note = rng.choice(NATURALS)
    whole = rng.random() < 0.5
    target = th.plain_name(th.pc(note) + (2 if whole else 1))
    ch, ans = _choices(rng, target, [th.plain_name(th.pc(note) + k) for k in (1, 2, 3, -1)])
    return _q(L("whole_step" if whole else "half_step", note=note), ch, ans)


def q_tab_read(rng, ex):
    s, f = rng.randint(1, 6), rng.randint(0, 9)
    opts = {(s, f), (7 - s if 7 - s != s else (s % 6) + 1, f), (s, f + 1 if f < 9 else f - 1), ((s % 6) + 1, f)}
    pool = list(opts)
    ch, ans = _choices(rng, (s, f), pool, label=lambda x: L("string_fret", string=x[0], fret=x[1]))
    return _q(L("tab_read"), ch, ans, tab=dict(string=s, fret=f))


def q_open_string(rng, ex):
    s = rng.randint(1, 6)
    ch, ans = _choices(rng, OPEN_NAMES[s], ["E", "A", "D", "G", "B", "C", "F"])
    return _q(L("open_string", string=s), ch, ans)


def q_scale_degree(rng, ex):
    key = rng.choice(ex.get("keys", KEYS))
    name = rng.choice(ex.get("scales", ["major"]))
    sc = th.scale(key, name)
    k = rng.randrange(1, len(sc))
    right = sc[k]["note"]
    letter, acc = th.parse_note(right)
    wrong = []
    for d in (-1, 1):                                    # the same pitch with the wrong letter
        alt = th.LETTERS[(th.LETTERS.index(letter) + d) % 7]
        diff = (th.pc(right) - th.LETTER_PC[alt]) % 12
        diff = diff - 12 if diff > 6 else diff
        if -2 <= diff <= 2:
            wrong.append(th.note_name(alt, diff))
    pool = wrong + [s["note"] for s in sc if s["note"] != right]
    ch, ans = _choices(rng, right, pool)
    return _q(L("scale_degree", key=key, scale=name, degree=sc[k]["degree"]), ch, ans)


def q_relative_minor(rng, ex):
    key = rng.choice(ex.get("keys", KEYS))
    if rng.random() < 0.5:
        right = th.relative_minor(key)
        ch, ans = _choices(rng, right + "m", [th.transpose(key, iv) + "m" for iv in ("M2", "M3", "P4", "P5", "M6", "M7")])
        return _q(L("relative_minor", key=key), ch, ans)
    minor = th.relative_minor(key)
    ch, ans = _choices(rng, key, [th.transpose(minor, iv) for iv in ("m2", "M2", "m3", "P4", "P5", "m6")])
    return _q(L("relative_major", key=minor + "m"), ch, ans)


def q_hear_quality(rng, ex):
    kinds = ex.get("qualities", ["maj", "min"])
    q = rng.choice(kinds)
    root = rng.randint(48, 57)
    pitches = [root + th.INTERVALS[iv][1] for iv in th.CHORDS[q][1]]
    if ex.get("as_scale"):
        name = "major" if q == "maj" else "natural_minor"
        pitches = [root + th.INTERVALS[iv][1] for iv in th.SCALES[name]] + [root + 12]
    ch, ans = _choices(rng, q, kinds, n=len(kinds), label=lambda x: L("quality", q=x))
    return _q(L("hear_scale" if ex.get("as_scale") else "hear_quality"), ch, ans, play=pitches, melodic=bool(ex.get("as_scale")))


def q_mode_color(rng, ex):
    mode = rng.choice(ex.get("modes", list(th.MODE_COLOR)))
    right = th.DEGREE[th.MODE_COLOR[mode]]
    ch, ans = _choices(rng, right, ["#4", "b7", "6", "b2", "b5", "b3", "b6"])
    return _q(L("mode_color", mode=mode), ch, ans)


def _notes(sym):
    return " ".join(t["note"] for t in th.chord(sym)["tones"])


def q_chord_tones(rng, ex):
    root = rng.choice(ex.get("roots", ["C", "G", "D", "A", "E", "F", "Bb"]))
    q = rng.choice(ex.get("qualities", ["maj", "min", "7", "maj7", "m7"]))
    sym = th.chord_symbol(root, q)
    swaps = {"maj": ["min", "aug", "sus4"], "min": ["maj", "dim", "sus2"], "7": ["maj7", "m7", "6"], "maj7": ["7", "m7", "6"],
             "m7": ["m7b5", "7", "mmaj7"], "m7b5": ["m7", "dim7", "7"], "dim7": ["m7b5", "m7", "7"], "sus2": ["sus4", "maj", "min"],
             "sus4": ["sus2", "maj", "7sus4"], "6": ["maj7", "m6", "7"], "m6": ["6", "m7", "min"], "mmaj7": ["m7", "maj7", "m6"],
             "aug": ["maj", "dim", "7"], "dim": ["min", "m7b5", "aug"]}
    pool = [_notes(th.chord_symbol(root, s)) for s in swaps.get(q, ["maj", "min", "7"])]
    ch, ans = _choices(rng, _notes(sym), pool)
    return _q(L("chord_tones", chord=sym), ch, ans)


def _formula(q):
    return " ".join(th.DEGREE[iv] for iv in th.CHORDS[q][1])


def q_chord_formula(rng, ex):
    q = rng.choice(ex.get("qualities", ["maj7", "7", "m7", "m7b5", "dim7"]))
    pool = [_formula(x) for x in ex.get("qualities", []) + ["maj", "min", "7", "maj7", "m7", "m7b5", "dim7", "6", "9", "13", "7b9"] if x != q]
    ch, ans = _choices(rng, _formula(q), pool)
    return _q(L("chord_formula", chord=th.chord_symbol("C", q)), ch, ans)


def q_inversion(rng, ex):
    root = rng.choice(["C", "G", "D", "A", "F", "E"])
    q = rng.choice(["maj", "min"])
    tones = th.chord(th.chord_symbol(root, q))["tones"]
    k = rng.randrange(3)
    sym = th.chord_symbol(root, q)
    ch, ans = _choices(rng, k, [0, 1, 2], n=3,
                       label=lambda x: L("inv", k=x, name=sym + ("" if x == 0 else "/" + tones[x]["note"])))
    return _q(L("inversion", chord=sym, bass=tones[k]["note"]), ch, ans)


def q_roman(rng, ex):
    key = rng.choice(ex.get("keys", KEYS))
    name = ex.get("scale", "major")
    size = ex.get("size", "triads")
    hz = th.harmonize(key, name, size)
    c = rng.choice(hz)
    if rng.random() < 0.5:
        ch, ans = _choices(rng, c["symbol"], [x["symbol"] for x in hz])
        return _q(L("roman", key=key, scale=name, roman=c["roman"]), ch, ans)
    ch, ans = _choices(rng, c["roman"], [x["roman"] for x in hz])
    return _q(L("roman_reverse", key=key, scale=name, chord=c["symbol"]), ch, ans)


def q_pentatonic(rng, ex):
    minor = rng.choice(["A", "E", "D", "G", "B", "C"])
    right = th.transpose(minor, "m3")
    ch, ans = _choices(rng, right, [th.transpose(minor, iv) for iv in ("M2", "P4", "P5", "M3", "m7")])
    return _q(L("pentatonic", key=minor), ch, ans)


def q_symmetric(rng, ex):
    name, n = rng.choice([("whole_tone", 2), ("half_whole", 3), ("whole_half", 3)])
    ch, ans = _choices(rng, n, [1, 2, 3, 4, 5], label=lambda x: L("n_frets", count=x))
    return _q(L("symmetric", scale=name), ch, ans)


def q_bebop(rng, ex):
    key = rng.choice(["G", "C", "F", "D", "A", "Bb"])
    right = th.transpose(key, "M7")
    ch, ans = _choices(rng, right, [th.transpose(key, iv) for iv in ("m7", "m6", "A4", "m2", "M6")])
    return _q(L("bebop_added", key=key), ch, ans)


def q_altered(rng, ex):
    key = rng.choice(["G", "C", "D", "A", "E", "F"])
    ch, ans = _choices(rng, "b9 #9 #11 b13", ["9 11 13", "b9 11 13", "9 #11 13", "b9 #9 11 13"])
    return _q(L("altered_tones", chord=key + "7"), ch, ans)


def q_guide_tones(rng, ex):
    root = rng.choice(["C", "D", "G", "F", "Bb", "A", "E"])
    q = rng.choice(["maj7", "7", "m7"])
    c = th.chord(th.chord_symbol(root, q))
    n = {t["degree"].lstrip("b"): t["note"] for t in c["tones"]}
    right = f"{n['3']} {n['7']}"
    ch, ans = _choices(rng, right, [f"{n['1']} {n['5']}", f"{n['1']} {n['3']}", f"{n['5']} {n['7']}", f"{n['1']} {n['7']}"])
    return _q(L("guide_tones", chord=c["symbol"]), ch, ans)


def q_drop(rng, ex):
    n = rng.choice(ex.get("drops", [2, 3]))
    right = {2: "second", 3: "third"}[n]
    ch, ans = _choices(rng, right, ["top", "second", "third", "bottom"], label=lambda x: L("voice", which=x))
    return _q(L("drop_voice", n=n), ch, ans)


def q_extension(rng, ex):
    root = rng.choice(["C", "G", "D", "F", "Bb", "A"])
    ext, iv = rng.choice([("9", "M9"), ("11", "P11"), ("13", "M13"), ("b9", "m9"), ("#9", "A9"), ("#11", "A11"), ("b13", "m13")])
    right = th.transpose(root, iv)
    pool = [th.transpose(root, x) for x in ("M2", "P4", "M6", "m2", "A2", "A4", "m6", "M3", "P5")]
    ch, ans = _choices(rng, right, pool)
    return _q(L("extension", root=root, ext=ext), ch, ans)


def q_voice_lead(rng, ex):
    key = rng.choice(["C", "F", "G", "Bb", "D", "Eb"])
    ii, v, i = (th.transpose(key, "M2") + "m7", th.transpose(key, "P5") + "7", key + "maj7")
    a, b = rng.choice([(ii, v), (v, i)])
    seventh = th.tone(th.chord(a), "7")["note"]
    third = th.tone(th.chord(b), "3")["note"]
    pool = [t["note"] for t in th.chord(b)["tones"]] + [th.transpose(seventh, "M2")]
    ch, ans = _choices(rng, third, pool)
    return _q(L("voice_lead", a=a, b=b, note=seventh), ch, ans)


def q_tritone_sub(rng, ex):
    root = rng.choice(["G", "C", "D", "A", "E", "F", "Bb"])
    sym = root + "7"
    right = th.tritone_sub(sym)
    pool = [th.transpose(root, iv) + "7" for iv in ("P5", "P4", "M2", "m3", "M6")]
    ch, ans = _choices(rng, right, pool)
    return _q(L("tritone_sub", chord=sym), ch, ans)


def q_shared_tones(rng, ex):
    root = rng.choice(["G", "C", "D", "A", "F"])
    a = th.chord(root + "7")
    n = {t["degree"]: t["note"] for t in a["tones"]}
    right = f"{n['3']} {n['b7']}"
    ch, ans = _choices(rng, right, [f"{n['1']} {n['5']}", f"{n['1']} {n['3']}", f"{n['5']} {n['b7']}"])
    return _q(L("shared_tones", a=a["symbol"], b=th.tritone_sub(a["symbol"])), ch, ans)


def _ii_v_i(key, minor):
    if minor:
        return f"{th.transpose(key, 'M2')}m7b5 – {th.transpose(key, 'P5')}7b9 – {key}m6"
    return f"{th.transpose(key, 'M2')}m7 – {th.transpose(key, 'P5')}7 – {key}maj7"


def q_ii_v_i(rng, ex):
    minor = rng.random() < 0.5 if ex.get("mode") == "both" else ex.get("mode") == "minor"
    key = rng.choice(ex.get("keys", ["C", "F", "G", "Bb", "D", "Eb", "A"]))
    right = _ii_v_i(key, minor)
    pool = [_ii_v_i(key, not minor), _ii_v_i(th.transpose(key, "P5"), minor), _ii_v_i(th.transpose(key, "P4"), minor),
            _ii_v_i(th.transpose(key, "M2"), minor)]
    ch, ans = _choices(rng, right, pool)
    return _q(L("ii_v_i_minor" if minor else "ii_v_i_major", key=key + ("m" if minor else "")), ch, ans)


def q_turnaround(rng, ex):
    key = rng.choice(["C", "F", "G", "Bb", "D"])
    I, ii, iii, V = key + "maj7", th.transpose(key, "M2") + "m7", th.transpose(key, "M3") + "m7", th.transpose(key, "P5") + "7"
    vi, VI = th.transpose(key, "M6") + "m7", th.transpose(key, "M6") + "7"
    forms = {"1": f"{I} – {vi} – {ii} – {V}", "3": f"{iii} – {VI} – {ii} – {V}",
             "x": f"{I} – {th.transpose(key, 'm3')}7 – {ii} – {th.tritone_sub(V)}"}
    which = rng.choice(["1", "3", "x"])
    pool = list(forms.values()) + [f"{I} – {ii} – {vi} – {V}", f"{ii} – {V} – {I} – {vi}"]
    ch, ans = _choices(rng, forms[which], pool)
    return _q(L(f"turnaround_{which}", key=key), ch, ans)


QUIZ = {f.__name__[2:]: f for f in [q_tritone_sub, q_shared_tones, q_ii_v_i, q_turnaround,q_interval_frets, q_interval_ear, q_enharmonic, q_half_step, q_tab_read, q_open_string,
                                     q_scale_degree, q_relative_minor, q_hear_quality, q_mode_color, q_chord_tones,
                                     q_chord_formula, q_inversion, q_roman, q_pentatonic, q_symmetric, q_bebop, q_altered,
                                     q_guide_tones, q_drop, q_extension, q_voice_lead]}


# ---------------------------------------------------------------- pick on the fretboard
def pick_item(rng, ex) -> dict:
    lo, hi = ex.get("frets", [0, 12])
    strings = ex.get("strings", [6, 5, 4, 3, 2, 1])
    what = ex["pick"]
    if what == "note":
        note = rng.choice(ex.get("notes", NATURALS))
        want = {th.pc(note)}
        prompt, mode = L("pick_note", note=note, lo=lo, hi=hi), "all"
    elif what == "degree":
        key = rng.choice(ex.get("keys", KEYS))
        sc = th.scale(key, ex.get("scale", "major"))
        deg = rng.choice([s for s in sc if s["degree"] in ex.get("degrees", ["1", "3", "5"])])
        want = {deg["pc"]}
        prompt, mode = L("pick_degree", degree=deg["degree"], key=key, note=deg["note"], lo=lo, hi=hi), "all"
    elif what == "chord":
        sym = rng.choice(ex.get("chords", ["C", "G", "D", "A", "E", "Am", "Em", "Dm"]))
        want = {t["pc"] for t in th.chord(sym)["tones"]}
        prompt, mode = L("pick_chord", chord=sym, lo=lo, hi=hi), "pcs"
    elif what == "scale":
        key = rng.choice(ex.get("keys", KEYS))
        name = ex.get("scale", "major")
        want = {s["pc"] for s in th.scale(key, name)}
        prompt, mode = L("pick_scale", key=key, scale=name, lo=lo, hi=hi), "all"
    else:
        raise QuizError(f"Unknown pick: {what}")
    expected = sorted((s, f) for s, f, _ in th.positions(want, lo, hi, tuple(strings)))
    return dict(type="pick", prompt=prompt, frets=[lo, hi], strings=strings, mode=mode, want=sorted(want),
                expected=[list(x) for x in expected], need=len(want) if mode == "pcs" else len(expected))


def _check_pick(item: dict, answer) -> bool:
    try:
        sel = {(int(s), int(f)) for s, f in answer}
    except (TypeError, ValueError):
        return False
    lo, hi = item["frets"]
    if any(not (lo <= f <= hi) or s not in item["strings"] for s, f in sel):
        return False
    pcs = {th.fret_pitch(s, f) % 12 for s, f in sel}
    if item["mode"] == "all":
        return sel == {tuple(x) for x in item["expected"]}
    return pcs == set(item["want"])                      # every chord tone at least once, nothing else


# ---------------------------------------------------------------- notes to play (graded by the listener)
def play_items(rng, ex) -> list[dict]:
    n = int(ex.get("count", 5))
    out = []
    if ex["kind"] == "find_note":
        lo, hi = ex.get("frets", [0, 12])
        strings = ex.get("strings", [6, 5])
        notes = ex.get("notes", NATURALS)
        combos = [(s, note) for s in strings for note in notes
                  if any(th.fret_pitch(s, f) % 12 == th.pc(note) for f in range(lo, hi + 1))]
        if not combos:
            raise QuizError("No note of the list fits those strings and frets")
        last = None
        while len(out) < n:
            s, note = rng.choice(combos)
            if (s, note) == last and len(combos) > 1:       # don't ask the same thing twice in a row
                continue
            last = (s, note)
            frets = [f for f in range(lo, hi + 1) if th.fret_pitch(s, f) % 12 == th.pc(note)]
            out.append(dict(prompt=L("find_note", note=note, string=s), notes=[th.fret_pitch(s, frets[0])],
                            reveal=L("found_at", string=s, fret=frets[0])))
    elif ex["kind"] == "tone_row":
        lo, hi = ex.get("frets", [0, 12])
        row = list(range(12))
        rng.shuffle(row)
        ok = th._playable(lo, hi)
        prev = min(ok) + 7
        pitches = []
        for pc in row:
            prev = th._near({pc}, prev, ok)
            pitches.append(prev)
        for s, f, p in th._place(pitches, lo, hi):
            out.append(dict(prompt=L("row_note", note=th.plain_name(p)), notes=[p], reveal=L("found_at", string=s, fret=f)))
    else:
        pool = ex.get("intervals", ["M3", "P5", "P8"])
        while len(out) < n:
            iv = rng.choice(pool)
            s = rng.choice(ex.get("strings", [6, 5]))
            f = rng.randint(*ex.get("frets", [1, 7]))
            root = th.fret_pitch(s, f)
            name = th.plain_name(root)
            target = th.transpose(name, iv)
            out.append(dict(prompt=L("play_interval", root=name, string=s, fret=f, iv=iv), notes=[root, root + th.INTERVALS[iv][1]],
                            reveal=L("interval_is", root=name, iv=iv, note=target)))
    return out


# ---------------------------------------------------------------- the draw lifecycle
def draw(lid: str, ex: dict, need: float, seed: int | None = None) -> dict:
    """A fresh draw for an exercise → what the UI shows (answers stay here)."""
    rng = random.Random(seed if seed is not None else secrets.randbits(32))
    kind, n = ex["kind"], int(ex.get("count", 6))
    if kind == "quiz":
        types = ex["quiz"] if isinstance(ex["quiz"], list) else [ex["quiz"]]
        unknown = [t for t in types if t not in QUIZ]
        if unknown:
            raise QuizError(f"Unknown quiz: {', '.join(unknown)}")
        items = [QUIZ[types[i % len(types)]](rng, ex) for i in range(n)]
    elif kind == "pick":
        items = [pick_item(rng, ex) for _ in range(n)]
    elif kind in ("find_note", "play_interval", "tone_row"):
        items = play_items(rng, ex)
        with _lock:
            _latest[(lid, ex["id"])] = dict(notes=[p for it in items for p in it["notes"]], items=items)
        return dict(kind=kind, items=[dict(prompt=it["prompt"], reveal=it["reveal"], notes=len(it["notes"])) for it in items])
    else:
        raise QuizError(f"Exercise kind '{kind}' isn't drawn")
    token = secrets.token_urlsafe(12)
    with _lock:
        if len(_draws) >= MAX_DRAWS:
            _draws.pop(next(iter(_draws)))
        _draws[token] = dict(lesson=lid, exercise=ex["id"], need=need, items=items, answers={})
    public = [{k: v for k, v in it.items() if k not in ("answer", "expected", "want")} for it in items]
    return dict(kind=kind, token=token, items=public)


def check(token: str, index: int, answer) -> dict:
    """Checks one answer (once: changing it later doesn't count) → {correct, answer}."""
    with _lock:
        d = _draws.get(token)
        if d is None:
            raise QuizError("This quiz expired: start it again")
        if not 0 <= index < len(d["items"]):
            raise QuizError("No such question")
        it = d["items"][index]
        ok = _check_pick(it, answer) if it["type"] == "pick" else str(answer) == it["answer"]
        d["answers"].setdefault(index, ok)
        if it["type"] == "pick":
            return dict(correct=ok, answer=it["expected"] if it["mode"] == "all" else it["want"], mode=it["mode"])
        return dict(correct=ok, answer=it["answer"])


def finish(token: str) -> dict:
    """Ends a quiz → {lesson, exercise, need, score} (unanswered questions count as wrong)."""
    with _lock:
        d = _draws.pop(token, None)
    if d is None:
        raise QuizError("This quiz expired: start it again")
    right = sum(1 for ok in d["answers"].values() if ok)
    return dict(lesson=d["lesson"], exercise=d["exercise"], need=d["need"], score=round(100 * right / len(d["items"]), 1))


def drawn_notes(lid: str, ex: dict) -> list[int]:
    """The notes of the latest draw of a play-it exercise (drawing one if the UI didn't)."""
    with _lock:
        got = _latest.get((lid, ex["id"]))
    if got is None:
        draw(lid, ex, ex.get("min", 80))
        with _lock:
            got = _latest[(lid, ex["id"])]
    return list(got["notes"])
