"""guitarr: te escucha tocar la guitarra y te dice qué erraste.

    guitarr gui                          # interfaz gráfica (en el navegador)
    guitarr live REFERENCIA [opciones]   # en vivo, guitarra enchufada
    guitarr file REFERENCIA TU_TOMA      # toma pre-grabada
    guitarr tune                         # afinador
    guitarr calibrate                    # medir la latencia (se guarda)
    guitarr history [CANCION]            # progreso y compases flojos
    guitarr cancionero [ID]              # cifrados para tocar con escucha (--cifrado ID)
    guitarr progreso                     # nivel, XP, racha, lecciones y acordes dominados
    guitarr devices | tracks ARCHIVO | config | demo

REFERENCIA: MIDI (.mid), Guitar Pro (.gp3/.gp4/.gp5) o audio (.wav/.mp3).
Con audio de una canción completa, usá --separate para aislar la guitarra.
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

from . import config


def _quiet() -> None:
    warnings.filterwarnings("ignore")
    logging.getLogger().setLevel(logging.ERROR)


# ---------------------------------------------------------------- argumentos
def add_reference_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("reference", type=Path, nargs="?", help="MIDI, Guitar Pro o audio de referencia")
    ap.add_argument("--cifrado", help="en vez de un archivo, un cifrado (ver `guitarr cancionero`)")
    ap.add_argument("--track", help="pista (número o parte del nombre; ver `guitarr tracks`)")
    ap.add_argument("--separate", action="store_true", help="aislar guitarra de la referencia con Demucs")
    ap.add_argument("--start-bar", type=int, help="practicar desde este compás")
    ap.add_argument("--end-bar", type=int, help="practicar hasta este compás (inclusive)")
    ap.add_argument("--transpose", type=int, help="semitonos a sumar a lo que tocás (afinación distinta)")
    ap.add_argument("--bpm", type=float, help="tempo de la referencia (si el detector de pulso falla)")
    ap.add_argument("--first-beat", type=float, help="segundo del primer tiempo del compás 1 (con --bpm)")
    ap.add_argument("--beats-per-bar", type=int)
    ap.add_argument("--onset-threshold", type=float, default=0.5)
    ap.add_argument("--frame-threshold", type=float, default=0.3)
    ap.add_argument("--min-amp", type=float, default=0.2, help="descartar notas detectadas más débiles")
    ap.add_argument("--save-preset", action="store_true",
                    help="recordar pista/compases/transposición/modo/velocidad para esta canción")


def add_audio_args(ap: argparse.ArgumentParser, output: bool = True) -> None:
    ap.add_argument("--device", help="entrada de audio (número o nombre; ver `guitarr devices`)")
    ap.add_argument("--channel", type=int, help="canal de entrada de la interfaz (1 = input 1)")
    if output:
        ap.add_argument("--output-device", help="salida para el metrónomo (default: la del sistema)")
    ap.add_argument("--samplerate", type=int, help="default: el del dispositivo")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="guitarr", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("file", help="analizar una toma pre-grabada")
    add_reference_args(f)
    f.add_argument("take", type=Path, help="tu toma (wav/mp3/...)")
    f.add_argument("--onset-tol", type=float, default=0.15, help="tolerancia para emparejar notas (s)")
    f.add_argument("--timing-tol", type=float, default=0.06, help="desvío a partir del cual se marca timing (s)")
    f.add_argument("--smooth", type=float, default=2.0, help="ventana de suavizado del tempo (s)")
    f.add_argument("--dump-midi", type=Path, help="carpeta donde guardar las transcripciones en MIDI")
    f.add_argument("--max-issues", type=int, default=60)
    f.add_argument("--no-history", action="store_true", help="no guardar en el historial")

    lv = sub.add_parser("live", help="tocar en vivo con la guitarra enchufada")
    add_reference_args(lv)
    add_audio_args(lv)
    lv.add_argument("--mode", choices=["wait", "tempo"],
                    help="wait: espera a que toques bien cada nota | tempo: metrónomo y timing")
    lv.add_argument("--speed", type=float, help="velocidad en modo tempo (0.7 = 70%%)")
    lv.add_argument("--no-click", action="store_true", help="modo tempo sin metrónomo (arranca con tu 1ra nota)")
    lv.add_argument("--count-in", type=int, help="tiempos de cuenta de entrada (default: un compás)")
    lv.add_argument("--latency-ms", type=float, help="corrección de latencia (mejor: guitarr calibrate)")
    lv.add_argument("--gate-db", type=float, help="nivel mínimo para considerar una nota (default -50)")
    lv.add_argument("--sensitivity", type=float, help="sensibilidad del detector de ataques (default 1)")
    lv.add_argument("--timing-tol", type=float, default=0.06, help="desvío a partir del cual se marca timing (s)")
    lv.add_argument("--window", type=float, default=0.2, help="ventana máx. para asociar una nota en modo tempo (s)")
    lv.add_argument("--loop", action="store_true", help="repetir la sección al terminar")
    lv.add_argument("--trainer", action="store_true",
                    help="modo tempo en loop: sube la velocidad cuando la vuelta sale limpia")
    lv.add_argument("--speed-step", type=float, default=0.05, help="cuánto sube/baja el entrenador (0.05 = 5%%)")
    lv.add_argument("--target", type=float, default=90, help="puntaje para subir la velocidad (entrenador)")
    lv.add_argument("--max-speed", type=float, default=1.0, help="tope del entrenador")
    lv.add_argument("--no-legato", action="store_true", help="no detectar hammer-ons/pull-offs/slides")
    lv.add_argument("--simulate", type=Path, help="usar un WAV como si fuera la guitarra en vivo (pruebas)")
    lv.add_argument("--fast", action="store_true", help="con --simulate: no esperar tiempo real")
    lv.add_argument("--plain", action="store_true", help="salida de texto simple en vez de pantalla en vivo")
    lv.add_argument("--save-dir", type=Path, help=f"dónde guardar lo que tocaste (default {config.TAKES_DIR})")
    lv.add_argument("--no-history", action="store_true", help="no guardar en el historial")

    t = sub.add_parser("tune", help="afinador")
    add_audio_args(t, output=False)
    t.add_argument("--simulate", type=Path, help="usar un WAV como entrada")

    c = sub.add_parser("calibrate", help="medir la latencia tocando junto al click (se guarda)")
    add_audio_args(c)
    c.add_argument("--bpm", type=float, default=90)

    h = sub.add_parser("history", help="ver progreso y compases flojos")
    h.add_argument("song", nargs="?", help="id de la canción (ver `guitarr history`)")

    cf = sub.add_parser("config", help="ver o guardar la configuración de audio")
    add_audio_args(cf)
    cf.add_argument("--latency-ms", type=float)
    cf.add_argument("--gate-db", type=float)
    cf.add_argument("--sensitivity", type=float)

    g = sub.add_parser("gui", help="abrir la interfaz gráfica en el navegador")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--no-browser", action="store_true")

    cn = sub.add_parser("cancionero", help="cifrados para tocar con escucha (para --cifrado)")
    cn.add_argument("id", nargs="?")
    cn.add_argument("--formato", action="store_true", help="cómo escribir tus propios cifrados")
    sub.add_parser("progreso", help="nivel, XP, racha, lecciones y acordes dominados")

    d = sub.add_parser("demo", help="generar archivos de prueba con errores plantados")
    d.add_argument("--out", type=Path, default=Path("demo"))

    sub.add_parser("devices", help="listar dispositivos de audio")
    tr = sub.add_parser("tracks", help="listar las pistas de un MIDI / Guitar Pro")
    tr.add_argument("file", type=Path)
    return ap


# ---------------------------------------------------------------- resolución de opciones
def resolve_audio(args, log=print) -> dict:
    """Argumentos > config guardada > autodetección."""
    saved = config.load()["audio"]
    out = {}
    for k in config.AUDIO_KEYS:
        v = getattr(args, k, None)
        out[k] = v if v is not None else saved.get(k)
    if out["device"] is None and not getattr(args, "simulate", None):
        try:
            from .audio_io import devices

            info = devices()
            if info["suggested"] is not None:
                out["device"] = info["suggested"]
                name = next(d["name"] for d in info["inputs"] if d["index"] == info["suggested"])
                log(f"Uso la entrada '{name}' (autodetectada; cambiala con --device o `guitarr config`)")
        except Exception:
            pass
    out["channel"] = out["channel"] or 1
    return out


def apply_preset(args, log=print) -> None:
    if args.reference is None:
        return
    preset = config.song_preset(args.reference)
    used = []
    for k in config.SONG_KEYS:
        if hasattr(args, k) and getattr(args, k) is None and k in preset:
            setattr(args, k, preset[k])
            used.append(f"{k}={preset[k]}")
    if used:
        log(f"Preset de {args.reference.name}: {', '.join(used)}")


def ref_options(args):
    from . import catalog
    from .reference import RefOptions, ReferenceError

    chart = None
    if args.cifrado:
        try:
            chart = catalog.get_cifrado(args.cifrado)
        except catalog.CatalogError as e:
            raise ReferenceError(str(e)) from e
    elif args.reference is None:
        raise ReferenceError("Falta la referencia: un archivo (MIDI/GP/audio) o --cifrado ID")
    return RefOptions(path=args.reference, chart=chart, track=args.track, separate=args.separate,
                      start_bar=args.start_bar, end_bar=args.end_bar, bpm=args.bpm,
                      first_beat=args.first_beat or 0.0, beats_per_bar=args.beats_per_bar or 4,
                      onset_threshold=args.onset_threshold, frame_threshold=args.frame_threshold,
                      min_amp=args.min_amp)


def section_of(args) -> dict | None:
    if args.start_bar or args.end_bar:
        return dict(start_bar=args.start_bar, end_bar=args.end_bar)
    return None


# ---------------------------------------------------------------- comandos
def cmd_file(args) -> None:
    from . import history
    from .analysis import FileOptions, analyze_take
    from .reference import load_reference, save_midi
    from .tui import print_file_report

    apply_preset(args)
    ref = load_reference(ref_options(args))
    opts = FileOptions(onset_tol=args.onset_tol, timing_tol=args.timing_tol, smooth=args.smooth,
                       transpose=args.transpose or 0, onset_threshold=args.onset_threshold,
                       frame_threshold=args.frame_threshold, min_amp=args.min_amp)
    result, usr = analyze_take(ref, args.take, opts)
    if args.dump_midi:
        args.dump_midi.mkdir(parents=True, exist_ok=True)
        save_midi(ref.notes, args.dump_midi / "referencia.mid")
        save_midi(usr, args.dump_midi / "toma.mid")
    print_file_report(result, args.max_issues)
    if not args.no_history:
        history.save(result, section_of(args))
        _reward(result["summary"].get("score"))
    if args.save_preset:
        _save_preset(args)


def _reward(score, what: str = "Práctica") -> None:
    from . import progress

    xp = progress.add_practice(score, what)
    if xp:
        d = progress.get()
        lv = d["level"]
        print(f"\n+{xp} XP · nivel {lv['level']} ({lv['title']}) · {d['xp']} XP · 🔥 {d['streak']}")


def _save_preset(args) -> None:
    if args.reference is None:
        print("Los presets son para archivos; los cifrados ya traen sus opciones.")
        return
    p = config.save_song_preset(args.reference, **{k: getattr(args, k, None) for k in config.SONG_KEYS})
    print(f"Preset guardado para {args.reference.name}: {p}")


def cmd_live(args) -> None:
    from . import history
    from .reference import load_reference
    from .session import LiveOptions, LiveSession
    from .tui import print_live_report, render

    apply_preset(args)
    audio = resolve_audio(args)
    ref = load_reference(ref_options(args))
    mode = args.mode or ("tempo" if args.trainer else "wait")
    if args.trainer and mode != "tempo":
        sys.exit("--trainer funciona en modo tempo.")
    opts = LiveOptions(
        mode=mode, speed=args.speed or (0.6 if args.trainer else 1.0),
        device=audio["device"], channel=audio["channel"], output_device=audio["output_device"],
        samplerate=audio["samplerate"], click=not args.no_click, count_in=args.count_in,
        latency_ms=audio["latency_ms"] or 0.0,
        gate_db=audio["gate_db"] if audio["gate_db"] is not None else -50.0,
        sensitivity=audio["sensitivity"] or 1.0, timing_tol=args.timing_tol, window=args.window,
        count_extras=not args.cifrado,
        legato=not args.no_legato and not args.cifrado,
        loop=args.loop, trainer=args.trainer, speed_step=args.speed_step, target=args.target,
        max_speed=args.max_speed, transpose=args.transpose or 0,
        simulate=args.simulate, fast=args.fast, save_dir=args.save_dir or config.TAKES_DIR,
    )
    if not audio["latency_ms"] and not args.simulate and mode == "tempo":
        print("Tip: medí la latencia una vez con `guitarr calibrate` para que el timing sea exacto.")
    sess = LiveSession(ref, opts)
    plain = args.plain or not sys.stdout.isatty()
    live = None
    if plain:
        on_update, on_message = None, lambda t, m: print(f"[{t:6.2f}s]  {m}")
    else:
        from rich.live import Live

        live = Live(render(sess.snapshot()), refresh_per_second=20, screen=False)
        live.__enter__()
        on_update, on_message = (lambda: live.update(render(sess.snapshot()))), None
    try:
        report = sess.run(on_update=on_update, on_message=on_message)
    except KeyboardInterrupt:  # la sesión ya se cerró en el finally de run
        report = sess.report or sess.build_report(None)
    finally:
        if live:
            live.__exit__(None, None, None)
    print_live_report(report, ref.grid, str(args.reference) if args.reference else f"--cifrado {args.cifrado}")
    if not args.no_history and not args.simulate and report["summary"]["judged"]:
        history.save(report, section_of(args))
        _reward(report["summary"].get("score"))
    if args.save_preset:
        args.mode = mode
        _save_preset(args)


def cmd_tune(args) -> None:
    from .audio_io import FileSource, MicSource
    from .tuner import run_tuner_cli

    if args.simulate:
        src = FileSource(args.simulate)
    else:
        a = resolve_audio(args)
        src = MicSource(a["device"], a["channel"], a["samplerate"])
    run_tuner_cli(src)


def cmd_calibrate(args) -> None:
    from .tuner import calibrate

    a = resolve_audio(args)
    print("Calibración: vas a escuchar 4 clicks para agarrar el pulso y después 12 más.\n"
          "Tocá las cuerdas muteadas (un golpe seco con la púa) JUSTO con cada click.\n"
          "Usá auriculares para que el click no entre por el micrófono.\n")
    last = [-1]

    def prog(p):
        if p["beat"] != last[0] and 0 < p["beat"] <= p["total"]:
            last[0] = p["beat"]
            print(f"  {'(pulso)' if p['warmup'] else 'tocá!  '} {p['beat']}/{p['total']}", end="\r", flush=True)

    r = calibrate(a["device"], a["channel"], a["output_device"], bpm=args.bpm, on_progress=prog)
    print("\n\n" + r["message"])
    if r["ok"]:
        config.update_audio(latency_ms=r["latency_ms"])
        print(f"Guardado en {config.CONFIG_PATH}. Ya no hace falta --latency-ms.")


def cmd_config(args) -> None:
    kw = {k: getattr(args, k, None) for k in config.AUDIO_KEYS}
    if any(v is not None for v in kw.values()):
        config.update_audio(**kw)
        print(f"Guardado en {config.CONFIG_PATH}")
    data = config.load()
    print("[audio]")
    for k, v in data["audio"].items():
        print(f"  {k} = {v}")
    if data["songs"]:
        print("\n[presets por canción]")
        for s, p in data["songs"].items():
            print(f"  {s}: {p}")


def cmd_tracks(args) -> None:
    from .reference import list_tracks

    rows = list_tracks(args.file)
    if not rows:
        print("No hay pistas (o el formato no tiene pistas: audio).")
    for r in rows:
        print(f"{r['index']:2d}  {r['name']:30s} {r['kind']:28s} {r['notes']} notas")


def main(argv=None) -> None:
    _quiet()
    args = build_parser().parse_args(argv)
    from .audio_io import AudioError
    from .catalog import CatalogError
    from .reference import ReferenceError

    try:
        if args.cmd == "devices":
            from .audio_io import list_devices
            list_devices()
        elif args.cmd == "tracks":
            cmd_tracks(args)
        elif args.cmd == "live":
            cmd_live(args)
        elif args.cmd == "file":
            cmd_file(args)
        elif args.cmd == "tune":
            cmd_tune(args)
        elif args.cmd == "calibrate":
            cmd_calibrate(args)
        elif args.cmd == "history":
            from .history import print_history
            print_history(args.song)
        elif args.cmd == "config":
            cmd_config(args)
        elif args.cmd == "cancionero":
            from . import catalog
            if args.formato:
                print(catalog.__doc__.split("Formato de cifrado (texto plano):", 1)[1].rstrip())
                print(f"\nGuardalos como .txt en {catalog.user_dir()}")
            else:
                catalog.print_songs(args.id)
        elif args.cmd == "progreso":
            from .progress import print_progress
            print_progress()
        elif args.cmd == "demo":
            from .demo import main as make_demo
            out = make_demo(args.out)
            print("Listo:", *sorted(p.name for p in out.iterdir()))
            print(f"Probá: guitarr file {out}/referencia.mid {out}/toma.wav")
        elif args.cmd == "gui":
            from .gui.server import serve
            serve(args.host, args.port, open_browser=not args.no_browser)
    except (ReferenceError, AudioError, ValueError, CatalogError) as e:
        sys.exit(f"Error: {e}")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
