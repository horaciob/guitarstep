"""Interfaz gráfica: servidor local (FastAPI) + página web en el navegador.

El audio se sigue procesando en Python (sounddevice, baja latencia); el
navegador solo muestra el estado que llega por WebSocket ~20 veces por segundo.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__, catalog, config, history, progress
from ..audio_io import AudioError, FileSource, MicSource, devices
from ..reference import REFERENCE_EXT, RefOptions, ReferenceError, list_tracks, load_reference

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="guitarr", docs_url=None, redoc_url=None)


@app.middleware("http")
async def revalidate_static(request, call_next):
    """Que el navegador revalide JS/CSS (con ETag) para no quedar con versiones viejas."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.session = None          # LiveSession
        self.thread: threading.Thread | None = None
        self.section: dict | None = None
        self.ctx: dict | None = None     # para qué es la sesión: práctica, ejercicio, acorde, minuto de cambio
        self.final: dict | None = None   # reporte + lo ganado (cuando ya se registró el progreso)
        self.tuner = None
        self.calib: dict = dict(running=False)


S = State()


# ---------------------------------------------------------------- utilidades
def _safe_name(name: str) -> str:
    n = Path(name or "").name
    if not n or n.startswith("."):
        raise HTTPException(400, "Nombre de archivo inválido")
    return n


def song_path(name: str) -> Path:
    p = config.SONGS_DIR / _safe_name(name)
    if not p.exists():
        raise HTTPException(404, f"No encontré la canción '{name}'")
    return p


def take_path(name: str) -> Path:
    p = config.TAKES_DIR / _safe_name(name)
    if not p.exists():
        raise HTTPException(404, f"No encontré la toma '{name}'")
    return p


def audio_settings() -> dict:
    a = dict(config.load()["audio"])
    if a.get("device") is None:
        try:
            a["device"] = devices()["suggested"]
        except AudioError:
            pass
    a.setdefault("channel", 1)
    return a


def ref_options(body: dict) -> tuple[RefOptions, dict]:
    """Arma la referencia pedida y su contexto. Fuentes posibles: archivo subido (song),
    cifrado, acorde suelto, ejercicio de la ruta o minuto de cambio (drill)."""
    common = dict(start_bar=_int(body.get("start_bar")), end_bar=_int(body.get("end_bar")))
    try:
        if body.get("ejercicio"):
            lid, eid = body["ejercicio"]["lesson"], body["ejercicio"]["exercise"]
            opts, mode, speed, need = catalog.exercise_setup(lid, eid)
            ex = catalog.get_exercise(lid, eid)
            return opts, dict(type="exercise", lesson=lid, exercise=eid, min=need, mode=mode, speed=speed,
                              title=ex["title"])
        if body.get("drill"):
            chords = list(body["drill"]["chords"])[:2]
            return RefOptions(chart=catalog.chart_alternating(chords, 60)), dict(
                type="drill", chords=chords, mode="wait", seconds=int(body["drill"].get("seconds", 60)))
        if body.get("acorde"):
            return RefOptions(chart=catalog.chart_from_chord(body["acorde"])), dict(
                type="chord", chord=body["acorde"], mode="wait")
        if body.get("cifrado"):
            return RefOptions(chart=catalog.get_cifrado(body["cifrado"]), **common), dict(type="practice", chart=True)
    except catalog.CatalogError as e:
        raise HTTPException(404, str(e))
    if not body.get("song"):
        raise HTTPException(400, "Elegí una canción")
    return RefOptions(
        path=song_path(body["song"]), track=body.get("track") or None,
        bpm=_float(body.get("bpm")), first_beat=_float(body.get("first_beat")) or 0.0,
        beats_per_bar=_int(body.get("beats_per_bar")) or 4, separate=bool(body.get("separate")), **common,
    ), dict(type="practice")


def ref_from(body: dict):
    opts, _ = ref_options(body)
    return load_reference(opts, log=lambda m: None)


def _int(v):
    return int(v) if v not in (None, "", "null") else None


def _float(v):
    return float(v) if v not in (None, "", "null") else None


def _section(body: dict) -> dict | None:
    sb, eb = _int(body.get("start_bar")), _int(body.get("end_bar"))
    return dict(start_bar=sb, end_bar=eb) if sb or eb else None


# ---------------------------------------------------------------- páginas
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/takes/{name}")
def get_take(name: str):
    return FileResponse(take_path(name), media_type="audio/wav")


# ---------------------------------------------------------------- aprender: acordes, cifrados, ruta, progreso
def _catalog_errors(fn, *a):
    try:
        return fn(*a)
    except catalog.CatalogError as e:
        raise HTTPException(400, str(e))


@app.get("/api/acordes")
def api_acordes():
    mastered = progress.get()["chords"]
    return dict(groups=catalog.chord_groups(), chords=catalog.chords(), mastered=mastered)


@app.get("/api/cifrados")
def api_cifrados():
    return catalog.cifrados()


@app.get("/api/cifrados/{cid}")
def api_cifrado(cid: str):
    try:
        text, mine = catalog.cifrado_text(cid)
        return dict(id=cid, text=text, mine=mine, chart=catalog.parse_cifrado(text, cid))
    except catalog.CatalogError as e:
        raise HTTPException(404, str(e))


@app.post("/api/cifrados/validar")
def api_cifrado_validar(body: dict):
    try:
        c = catalog.parse_cifrado(body.get("text", ""), "vista-previa")
        return dict(ok=not c["missing"], chart=c, error=(f"No conozco: {', '.join(c['missing'])}" if c["missing"] else None))
    except catalog.CatalogError as e:
        return dict(ok=False, error=str(e))


@app.post("/api/cifrados")
def api_cifrado_guardar(body: dict):
    cid = body.get("id")
    if cid:
        cid = catalog.slug(cid)
    return _catalog_errors(catalog.save_cifrado, body.get("text", ""), cid)


@app.delete("/api/cifrados/{cid}")
def api_cifrado_borrar(cid: str):
    _catalog_errors(catalog.delete_cifrado, cid)
    return dict(ok=True)


@app.get("/api/ruta")
def api_ruta():
    p = progress.get()
    levels = []
    for lvl in catalog.ruta()["levels"]:
        ls = []
        for x in lvl["lessons"]:
            exs = [dict(e, best=p["exercises"].get(f"{x['id']}/{e['id']}"),
                        passed=p["exercises"].get(f"{x['id']}/{e['id']}", -1) >= e.get("min", 80))
                   for e in x["exercises"]]
            ls.append(dict(x, exercises=exs, done=x["id"] in p["lessons"], pinned=p["tutorias"].get(x["id"])))
        levels.append(dict(lvl, lessons=ls))
    nxt = next((x for lv in levels for x in lv["lessons"] if not x["done"]), None)
    return dict(levels=levels, next=nxt and dict(id=nxt["id"], title=nxt["title"]))


@app.get("/api/progreso")
def api_progreso():
    return progress.get()


@app.post("/api/progreso/acorde")
def api_progreso_acorde(body: dict):
    via = body.get("via")
    if via not in ("oido", "camara") or catalog.get_chord(body.get("chord", "")) is None:
        raise HTTPException(400, "Acorde o vía inválidos")
    return progress.chord_mastered(body["chord"], via)


@app.post("/api/progreso/tutoria")
def api_progreso_tutoria(body: dict):
    url = (body.get("url") or "").strip() or None
    if url and not url.startswith(("https://", "http://")):
        raise HTTPException(400, "Pegá un link que empiece con https://")
    _catalog_errors(catalog.get_lesson, body.get("lesson", ""))
    return progress.pin_tutoria(body["lesson"], url)


# ---------------------------------------------------------------- estado / config
@app.get("/api/status")
def status():
    return dict(version=__version__, home=str(config.HOME),
                live=bool(S.session and S.session.running), tuner=S.tuner is not None)


@app.get("/api/devices")
def api_devices():
    try:
        return devices()
    except AudioError as e:
        return dict(inputs=[], outputs=[], suggested=None, error=str(e))


@app.get("/api/config")
def get_config():
    return dict(audio=audio_settings(), saved=config.load()["audio"], path=str(config.CONFIG_PATH))


@app.post("/api/config")
def set_config(body: dict):
    audio = {k: body.get(k) for k in config.AUDIO_KEYS}
    for k in ("channel", "samplerate"):
        audio[k] = _int(audio[k])
    for k in ("latency_ms", "gate_db", "sensitivity"):
        audio[k] = _float(audio[k])
    for k in ("device", "output_device"):
        if audio[k] in ("", None):
            audio[k] = None
        elif str(audio[k]).lstrip("-").isdigit():
            audio[k] = int(audio[k])
    data = config.load()
    for k, v in audio.items():
        if v is None:
            data["audio"].pop(k, None)
        else:
            data["audio"][k] = v
    config.save(data)
    return get_config()


# ---------------------------------------------------------------- canciones
@app.get("/api/songs")
def songs():
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    presets = config.load()["songs"]
    out = []
    for p in sorted(config.SONGS_DIR.iterdir(), key=lambda p: -p.stat().st_mtime):
        if p.suffix.lower() in REFERENCE_EXT:
            out.append(dict(name=p.name, ext=p.suffix.lower(), preset=presets.get(p.name, {})))
    return out


@app.post("/api/songs")
async def upload_song(file: UploadFile = File(...)):
    name = _safe_name(file.filename)
    if Path(name).suffix.lower() not in REFERENCE_EXT:
        raise HTTPException(400, "Formato no soportado: subí MIDI, Guitar Pro o audio")
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.SONGS_DIR / name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return dict(name=name)


@app.post("/api/demo")
def make_demo():
    from ..demo import main as demo_main

    out = demo_main(config.HOME / "demo")
    config.SONGS_DIR.mkdir(parents=True, exist_ok=True)
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(out / "referencia.mid", config.SONGS_DIR / "demo-referencia.mid")
    shutil.copy(out / "toma.wav", config.TAKES_DIR / "demo-toma.wav")
    return dict(song="demo-referencia.mid", take="demo-toma.wav")


@app.get("/api/songs/{name}/tracks")
def tracks(name: str):
    try:
        return list_tracks(song_path(name))
    except Exception as e:
        raise HTTPException(400, str(e))


@app.post("/api/preview")
def preview(body: dict):
    try:
        ref = ref_from(body)
    except ReferenceError as e:
        raise HTTPException(400, str(e))
    g = ref.grid
    last_bar = g.bar_index(max(n.start for n in ref.notes))
    first_bar = g.bar_index(ref.notes[0].start)
    return dict(
        name=ref.name, track=ref.track, tuning=ref.tuning, first_bar=first_bar, last_bar=last_bar,
        notes=[dict(s=round(n.start, 3), e=round(n.end, 3), p=n.pitch, string=n.string, fret=n.fret, label=n.label)
               for n in ref.notes],
        downbeats=[round(g.bar_time(b), 3) for b in range(first_bar, last_bar + 2)],
        bpm=round(60 / g.beat_len(ref.notes[0].start), 1),
    )


@app.post("/api/presets")
def save_preset(body: dict):
    song = _safe_name(body.pop("song"))
    kw = {k: body.get(k) for k in config.SONG_KEYS}
    for k in ("transpose", "start_bar", "end_bar", "beats_per_bar"):
        kw[k] = _int(kw[k])
    for k in ("speed", "bpm", "first_beat"):
        kw[k] = _float(kw[k])
    kw["track"] = kw["track"] or None
    data = config.load()
    data["songs"][song] = {k: v for k, v in kw.items() if v is not None}
    config.save(data)
    return data["songs"][song]


# ---------------------------------------------------------------- tomas / análisis
@app.get("/api/takes")
def takes():
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    return [dict(name=p.name, size=p.stat().st_size, mtime=p.stat().st_mtime)
            for p in sorted(config.TAKES_DIR.glob("*.wav"), key=lambda p: -p.stat().st_mtime)]


@app.post("/api/takes")
async def upload_take(file: UploadFile = File(...)):
    name = _safe_name(file.filename)
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    dest = config.TAKES_DIR / name
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return dict(name=name)


@app.post("/api/analyze")
def analyze(options: str = Form(...), take: UploadFile | None = File(None)):
    from ..analysis import FileOptions, analyze_take

    body = json.loads(options)
    if take is not None and take.filename:
        up = upload_take_sync(take)
        tpath = take_path(up)
    else:
        tpath = take_path(body["take"])
    try:
        ref = ref_from(body)
        msgs = []
        res, _ = analyze_take(ref, tpath, FileOptions(
            transpose=_int(body.get("transpose")) or 0,
            timing_tol=(_float(body.get("timing_tol_ms")) or 60) / 1000), log=msgs.append)
    except (ReferenceError, ValueError) as e:
        raise HTTPException(400, str(e))
    res["messages"] = [m.strip() for m in msgs if m.strip().startswith("⚠")]
    res["take_name"] = tpath.name
    history.save(res, _section(body))
    res["award"] = dict(xp=progress.add_practice(res["summary"].get("score"), "Análisis de toma"))
    return res


def upload_take_sync(file: UploadFile) -> str:
    name = _safe_name(file.filename)
    config.TAKES_DIR.mkdir(parents=True, exist_ok=True)
    with open(config.TAKES_DIR / name, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return name


# ---------------------------------------------------------------- en vivo
@app.post("/api/live/start")
def live_start(body: dict):
    from ..session import LiveOptions, LiveSession

    with S.lock:
        if S.session and S.session.running:
            raise HTTPException(409, "Ya hay una sesión en curso")
        if S.tuner:
            S.tuner.stop()
        ropts, ctx = ref_options(body)
        try:
            ref = load_reference(ropts, log=lambda m: None)
        except ReferenceError as e:
            raise HTTPException(400, str(e))
        a = audio_settings()
        sim = take_path(body["simulate"]) if body.get("simulate") else None
        mode = ctx.get("mode") or body.get("mode", "wait")
        speed = ctx.get("speed") or _float(body.get("speed")) or 1.0
        chart = ropts.chart is not None
        opts = LiveOptions(
            mode=mode, speed=speed,
            device=a.get("device"), channel=a.get("channel") or 1, output_device=a.get("output_device"),
            samplerate=a.get("samplerate"), click=body.get("click", True),
            count_in=_int(body.get("count_in")), latency_ms=a.get("latency_ms") or 0.0,
            gate_db=a["gate_db"] if a.get("gate_db") is not None else -50.0,
            sensitivity=a.get("sensitivity") or 1.0, loop=bool(body.get("loop")) and ctx["type"] == "practice",
            trainer=bool(body.get("trainer")) and mode == "tempo" and ctx["type"] == "practice",
            speed_step=(_float(body.get("speed_step")) or 5) / 100, target=_float(body.get("target")) or 90,
            max_speed=(_float(body.get("max_speed")) or 100) / 100,
            legato=body.get("legato", not chart) and not chart,
            count_extras=not chart, transpose=_int(body.get("transpose")) or 0,
            simulate=sim, fast=bool(body.get("fast")) and sim is not None,
        )
        try:
            sess = LiveSession(ref, opts)
        except AudioError as e:
            raise HTTPException(400, str(e))
        S.session, S.section, S.ctx, S.final = sess, _section(body), ctx, None

        def run():
            try:
                rep = sess.run()
                if ctx["type"] == "practice" and rep["summary"]["judged"] and not opts.simulate:
                    history.save(rep, S.section)
                rep["award"] = progress.on_session(ctx, rep)
                rep["context"] = ctx
                S.final = rep
            except Exception as e:  # queda en sess.error para la UI
                sess.error = sess.error or str(e)

        S.thread = threading.Thread(target=run, daemon=True)
        S.thread.start()
        if ctx["type"] == "drill":  # el minuto de cambio se corta solo
            threading.Timer(ctx["seconds"] + 1.5, sess.stop).start()
    return dict(ok=True, events=len(sess.events), context=ctx,
                grid_bpm=round(60 / ref.grid.beat_len(ref.notes[0].start), 1))


@app.post("/api/live/stop")
def live_stop():
    sess, th = S.session, S.thread
    if not sess:
        raise HTTPException(404, "No hay sesión")
    sess.stop()
    if th:
        th.join(5)
    return dict(report=S.final or sess.report, error=sess.error)


@app.get("/api/live/state")
def live_state():
    if not S.session:
        return dict(active=False)
    return dict(active=True, state=S.session.snapshot(), report=S.final, context=S.ctx)


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    sent = None
    try:
        while True:
            sess = S.session
            if sess is not None:
                await ws.send_json(dict(type="state", state=sess.snapshot(), context=S.ctx))
                if S.final is not None and sent is not S.final:
                    sent = S.final
                    await ws.send_json(dict(type="report", report=S.final))
                if sess.error and not sess.running:
                    await ws.send_json(dict(type="error", error=sess.error))
            await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError):
        pass


# ---------------------------------------------------------------- afinador
@app.websocket("/ws/tuner")
async def ws_tuner(ws: WebSocket):
    from ..tuner import Tuner

    await ws.accept()
    if S.session and S.session.running:
        await ws.send_json(dict(error="Pará la práctica para usar el afinador."))
        await ws.close()
        return
    try:
        sim = ws.query_params.get("simulate")
        a = audio_settings()
        src = FileSource(take_path(sim)) if sim else MicSource(a.get("device"), a.get("channel") or 1,
                                                                a.get("samplerate"))
    except (AudioError, HTTPException) as e:
        await ws.send_json(dict(error=getattr(e, "detail", None) or str(e)))
        await ws.close()
        return
    tuner = Tuner(src)
    S.tuner = tuner
    th = threading.Thread(target=tuner.run, daemon=True)
    th.start()
    try:
        await ws.send_json(dict(source=src.name))
        while th.is_alive():
            await ws.send_json(tuner.reading)
            await asyncio.sleep(0.05)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        tuner.stop()
        if S.tuner is tuner:
            S.tuner = None


# ---------------------------------------------------------------- calibración
@app.post("/api/calibrate")
def calibrate_start(body: dict | None = None):
    from ..tuner import calibrate

    if S.calib.get("running"):
        raise HTTPException(409, "Ya se está calibrando")
    if S.session and S.session.running:
        raise HTTPException(409, "Pará la práctica primero")
    a = audio_settings()
    bpm = _float((body or {}).get("bpm")) or 90
    S.calib = dict(running=True, beat=0, total=16, warmup=True, result=None)

    def prog(p):
        S.calib.update(p)

    def run():
        try:
            r = calibrate(a.get("device"), a.get("channel") or 1, a.get("output_device"), bpm=bpm,
                          on_progress=prog)
            if r["ok"]:
                config.update_audio(latency_ms=r["latency_ms"])
        except Exception as e:
            r = dict(ok=False, message=str(e))
        S.calib.update(running=False, result=r)

    threading.Thread(target=run, daemon=True).start()
    return S.calib


@app.get("/api/calibrate")
def calibrate_state():
    return S.calib


# ---------------------------------------------------------------- historial
@app.get("/api/history")
def api_history():
    return history.songs()


@app.get("/api/history/{sid}")
def api_history_song(sid: str):
    sid = _safe_name(sid)
    sessions = history.load_sessions(sid)
    if not sessions:
        raise HTTPException(404, "Sin sesiones")
    light = [dict(file=s["file"], date=s.get("date"), kind=s.get("kind"), score=history.session_score(s),
                  speed=s.get("final_speed") or s.get("speed"), section=s.get("section"),
                  mode=s.get("mode"), summary=s.get("summary"), passes=s.get("passes", []))
             for s in sessions]
    ref = sessions[-1].get("reference", {})
    rpath = ref.get("path", "") or ""
    if rpath.startswith("cifrado:"):
        song = rpath
    else:
        song = Path(rpath).name if rpath and (config.SONGS_DIR / Path(rpath).name).exists() else None
    return dict(id=sid, reference=ref, song=song,
                sessions=light, problem_bars=history.problem_bars(sessions))


# ---------------------------------------------------------------- arranque
def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    import uvicorn

    url = f"http://{host}:{port}/"
    print(f"guitarr {__version__} — abrí {url}  (Ctrl+C para salir)")
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
