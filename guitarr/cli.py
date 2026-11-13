"""guitarr: listens to you play guitar and tells you what you got wrong.

    guitarr gui                          # web UI (in your browser)
    guitarr live REFERENCE [options]     # live, guitar plugged in
    guitarr file REFERENCE YOUR_TAKE     # pre-recorded take
    guitarr tune                         # tuner
    guitarr calibrate                    # measure the latency (saved)
    guitarr history [SONG]               # progress and weakest bars
    guitarr charts [ID]                  # chord charts to play with listening (--chart ID)
    guitarr progress                     # level, XP, streak, lessons and mastered chords
    guitarr devices | tracks FILE | config | demo

REFERENCE: MIDI (.mid), Guitar Pro (.gp3/.gp4/.gp5) or audio (.wav/.mp3).
For a full-mix audio reference, use --separate to isolate the guitar.
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


# ---------------------------------------------------------------- arguments
def add_reference_args(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("reference", type=Path, nargs="?", help="MIDI, Guitar Pro or audio reference")
    ap.add_argument("--chart", help="use a chord chart instead of a file (see `guitarr charts`)")
    ap.add_argument("--track", help="track (number or part of its name; see `guitarr tracks`)")
    ap.add_argument("--separate", action="store_true", help="isolate the guitar in the reference with Demucs")
    ap.add_argument("--start-bar", type=int, help="practice from this bar")
    ap.add_argument("--end-bar", type=int, help="practice up to this bar (inclusive)")
    ap.add_argument("--transpose", type=int, help="semitones added to what you play (different tuning)")
    ap.add_argument("--bpm", type=float, help="reference tempo (if beat tracking fails)")
    ap.add_argument("--first-beat", type=float, help="second of the first beat of bar 1 (with --bpm)")
    ap.add_argument("--beats-per-bar", type=int)
    ap.add_argument("--onset-threshold", type=float, default=0.5)
    ap.add_argument("--frame-threshold", type=float, default=0.3)
    ap.add_argument("--min-amp", type=float, default=0.2, help="drop weaker detected notes")
    ap.add_argument("--save-preset", action="store_true",
                    help="remember track/bars/transpose/mode/speed for this song")


def add_audio_args(ap: argparse.ArgumentParser, output: bool = True) -> None:
    ap.add_argument("--device", help="audio input (number or name; see `guitarr devices`)")
    ap.add_argument("--channel", type=int, help="interface input channel (1 = input 1)")
    if output:
        ap.add_argument("--output-device", help="output for the metronome (default: system output)")
    ap.add_argument("--samplerate", type=int, help="default: the device's")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="guitarr", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("file", help="analyze a pre-recorded take")
    add_reference_args(f)
    f.add_argument("take", type=Path, help="your take (wav/mp3/...)")
    f.add_argument("--onset-tol", type=float, default=0.15, help="tolerance to match notes (s)")
    f.add_argument("--timing-tol", type=float, default=0.06, help="deviation flagged as a timing issue (s)")
    f.add_argument("--smooth", type=float, default=2.0, help="tempo smoothing window (s)")
    f.add_argument("--dump-midi", type=Path, help="folder to save the transcriptions as MIDI")
    f.add_argument("--max-issues", type=int, default=60)
    f.add_argument("--no-history", action="store_true", help="don't save to the history")

    lv = sub.add_parser("live", help="play live with your guitar plugged in")
    add_reference_args(lv)
    add_audio_args(lv)
    lv.add_argument("--mode", choices=["wait", "tempo"],
                    help="wait: waits until each note is right | tempo: metronome and timing")
    lv.add_argument("--speed", type=float, help="tempo-mode speed (0.7 = 70%%)")
    lv.add_argument("--no-click", action="store_true", help="tempo mode without a metronome (starts on your 1st note)")
    lv.add_argument("--count-in", type=int, help="count-in beats (default: one bar)")
    lv.add_argument("--latency-ms", type=float, help="latency correction (better: guitarr calibrate)")
    lv.add_argument("--gate-db", type=float, help="minimum level to consider a note (default -50)")
    lv.add_argument("--sensitivity", type=float, help="onset detector sensitivity (default 1)")
    lv.add_argument("--timing-tol", type=float, default=0.06, help="deviation flagged as a timing issue (s)")
    lv.add_argument("--window", type=float, default=0.2, help="max window to match a note in tempo mode (s)")
    lv.add_argument("--loop", action="store_true", help="repeat the section when it ends")
    lv.add_argument("--trainer", action="store_true",
                    help="looped tempo mode: speeds up after a clean pass")
    lv.add_argument("--speed-step", type=float, default=0.05, help="trainer speed step (0.05 = 5%%)")
    lv.add_argument("--target", type=float, default=90, help="score needed to speed up (trainer)")
    lv.add_argument("--max-speed", type=float, default=1.0, help="trainer speed cap")
    lv.add_argument("--no-legato", action="store_true", help="don't detect hammer-ons/pull-offs/slides")
    lv.add_argument("--simulate", type=Path, help="use a WAV as if it were the live guitar (testing)")
    lv.add_argument("--fast", action="store_true", help="with --simulate: don't wait in real time")
    lv.add_argument("--plain", action="store_true", help="plain text output instead of the live screen")
    lv.add_argument("--save-dir", type=Path, help=f"where to save what you played (default {config.TAKES_DIR})")
    lv.add_argument("--no-history", action="store_true", help="don't save to the history")

    t = sub.add_parser("tune", help="tuner")
    add_audio_args(t, output=False)
    t.add_argument("--simulate", type=Path, help="use a WAV as the input")

    c = sub.add_parser("calibrate", help="measure the latency by playing along with the click (saved)")
    add_audio_args(c)
    c.add_argument("--bpm", type=float, default=90)

    h = sub.add_parser("history", help="progress and weakest bars")
    h.add_argument("song", nargs="?", help="song id (see `guitarr history`)")

    cf = sub.add_parser("config", help="show or save the audio settings")
    add_audio_args(cf)
    cf.add_argument("--latency-ms", type=float)
    cf.add_argument("--gate-db", type=float)
    cf.add_argument("--sensitivity", type=float)

    g = sub.add_parser("gui", help="open the web UI in your browser")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--host", default="127.0.0.1")
    g.add_argument("--no-browser", action="store_true")

    ch = sub.add_parser("charts", help="chord charts to play with listening (for --chart)")
    ch.add_argument("id", nargs="?")
    ch.add_argument("--format", action="store_true", help="how to write your own charts")
    sub.add_parser("progress", help="level, XP, streak, lessons and mastered chords")

    d = sub.add_parser("demo", help="generate test files with planted mistakes")
    d.add_argument("--out", type=Path, default=Path("demo"))

    jc = sub.add_parser("judge-check", help="measure the chord judge on your own recordings (see guitarr/judgecheck.py)")
    jc.add_argument("folder", type=Path, help="a folder with one subfolder per chord asked (G/ok-1.wav, G/Em-1.wav…)")
    jc.add_argument("--json", action="store_true", help="print the result as JSON")
    db = sub.add_parser("db", help="web service database: schema migrations (needs GUITARR_DATABASE_URL)")
    db.add_argument("action", choices=["migrate", "status", "new"])
    db.add_argument("name", nargs="?", help="for new: what the migration does, e.g. add_setlists")
    us = sub.add_parser("user", help="web service: a sign-in link printed here (no mail server needed); new accounts are created")
    us.add_argument("action", choices=["link"])
    us.add_argument("email")
    sub.add_parser("worker", help="web service: run the slow jobs (transcriptions, take analysis); any number of them")
    sub.add_parser("devices", help="list audio devices")
    tr = sub.add_parser("tracks", help="list the tracks of a MIDI / Guitar Pro file")
    tr.add_argument("file", type=Path)
    return ap


# ---------------------------------------------------------------- option resolution
def resolve_audio(args, log=print) -> dict:
    """Arguments > saved settings > auto-detection."""
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
                log(f"Using input '{name}' (auto-detected; change it with --device or `guitarr config`)")
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
        log(f"Preset for {args.reference.name}: {', '.join(used)}")


def ref_options(args):
    from . import catalog
    from .reference import RefOptions, ReferenceError

    chart = None
    if args.chart:
        try:
            chart = catalog.get_chart(args.chart)
        except catalog.CatalogError as e:
            raise ReferenceError(str(e)) from e
    elif args.reference is None:
        raise ReferenceError("Missing reference: a file (MIDI/GP/audio) or --chart ID")
    return RefOptions(path=args.reference, chart=chart, track=args.track, separate=args.separate,
                      start_bar=args.start_bar, end_bar=args.end_bar, bpm=args.bpm,
                      first_beat=args.first_beat or 0.0, beats_per_bar=args.beats_per_bar or 4,
                      onset_threshold=args.onset_threshold, frame_threshold=args.frame_threshold,
                      min_amp=args.min_amp)


def section_of(args) -> dict | None:
    if args.start_bar or args.end_bar:
        return dict(start_bar=args.start_bar, end_bar=args.end_bar)
    return None


# ---------------------------------------------------------------- commands
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
        save_midi(ref.notes, args.dump_midi / "reference.mid")
        save_midi(usr, args.dump_midi / "take.mid")
    print_file_report(result, args.max_issues)
    if not args.no_history:
        history.save(result, section_of(args))
        _reward(result["summary"].get("score"), "take_analysis")
    if args.save_preset:
        _save_preset(args)


def _reward(score, code: str = "practice", **params) -> None:
    from . import progress

    xp = progress.add_practice(score, code, **params)
    if xp:
        d = progress.get()
        lv = d["level"]
        print(f"\n+{xp} XP · level {lv['level']} ({lv['title']}) · {d['xp']} XP · 🔥 {d['streak']}")


def _save_preset(args) -> None:
    if args.reference is None:
        print("Presets are for files; charts already carry their own settings.")
        return
    p = config.save_song_preset(args.reference, **{k: getattr(args, k, None) for k in config.SONG_KEYS})
    print(f"Preset saved for {args.reference.name}: {p}")


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
        sys.exit("--trainer works in tempo mode.")
    opts = LiveOptions(
        mode=mode, speed=args.speed or (0.6 if args.trainer else 1.0),
        device=audio["device"], channel=audio["channel"], output_device=audio["output_device"],
        samplerate=audio["samplerate"], click=not args.no_click, count_in=args.count_in,
        latency_ms=audio["latency_ms"] or 0.0,
        gate_db=audio["gate_db"] if audio["gate_db"] is not None else -50.0,
        sensitivity=audio["sensitivity"] or 1.0, timing_tol=args.timing_tol, window=args.window,
        count_extras=not args.chart,
        legato=not args.no_legato and not args.chart,
        loop=args.loop, trainer=args.trainer, speed_step=args.speed_step, target=args.target,
        max_speed=args.max_speed, transpose=args.transpose or 0,
        simulate=args.simulate, fast=args.fast, save_dir=args.save_dir or config.TAKES_DIR,
    )
    if not audio["latency_ms"] and not args.simulate and mode == "tempo":
        print("Tip: measure the latency once with `guitarr calibrate` for accurate timing.")
    sess = LiveSession(ref, opts)
    plain = args.plain or not sys.stdout.isatty()
    live = None
    if plain:
        on_update, on_message = None, lambda t, m: print(f"[{t:6.2f}s]  {m['text']}")
    else:
        from rich.live import Live

        live = Live(render(sess.snapshot()), refresh_per_second=20, screen=False)
        live.__enter__()
        on_update, on_message = (lambda: live.update(render(sess.snapshot()))), None
    try:
        report = sess.run(on_update=on_update, on_message=on_message)
    except KeyboardInterrupt:  # the session already closed in run()'s finally
        report = sess.report or sess.build_report(None)
    finally:
        if live:
            live.__exit__(None, None, None)
    print_live_report(report, ref.grid, str(args.reference) if args.reference else f"--chart {args.chart}")
    if not args.no_history and not args.simulate and report["summary"]["judged"]:
        history.save(report, section_of(args))
        _reward(report["summary"].get("score"), name=ref.name)
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
    print("Calibration: you'll hear 4 clicks to catch the pulse, then 12 more.\n"
          "Hit the muted strings (a short pick stroke) EXACTLY on every click.\n"
          "Use headphones so the click doesn't leak into the input.\n")
    last = [-1]

    def prog(p):
        if p["beat"] != last[0] and 0 < p["beat"] <= p["total"]:
            last[0] = p["beat"]
            print(f"  {'(pulse)' if p['warmup'] else 'play!  '} {p['beat']}/{p['total']}", end="\r", flush=True)

    r = calibrate(a["device"], a["channel"], a["output_device"], bpm=args.bpm, on_progress=prog)
    print("\n\n" + r["message"])
    if r["ok"]:
        config.update_audio(latency_ms=r["latency_ms"])
        print(f"Saved to {config.CONFIG_PATH}. --latency-ms is no longer needed.")


def cmd_config(args) -> None:
    kw = {k: getattr(args, k, None) for k in config.AUDIO_KEYS}
    if any(v is not None for v in kw.values()):
        config.update_audio(**kw)
        print(f"Saved to {config.CONFIG_PATH}")
    data = config.load()
    print("[audio]")
    for k, v in data["audio"].items():
        print(f"  {k} = {v}")
    if data["songs"]:
        print("\n[song presets]")
        for s, p in data["songs"].items():
            print(f"  {s}: {p}")


def cmd_tracks(args) -> None:
    from .reference import list_tracks

    rows = list_tracks(args.file)
    if not rows:
        print("No tracks (or the format has no tracks: audio).")
    for r in rows:
        print(f"{r['index']:2d}  {r['name']:30s} {r['kind']:28s} {r['notes']} notes")


def cmd_db(args) -> None:
    from . import db
    from .db import migrate
    if args.action == "new":
        print(f"Created {migrate.new(args.name or '')}")
        return
    if not db.enabled():
        raise ValueError("Set GUITARR_DATABASE_URL, e.g. postgresql://guitarr:guitarr@localhost:5432/guitarr")
    import psycopg
    try:
        if args.action == "migrate":
            done = migrate.migrate(db.url())
            print(f"{len(done)} migration(s) applied" if done else "Up to date")
        else:
            for m in migrate.status(db.url()):
                print(f"{m['version']:04d}  {m['name']:<32} {m['applied_at'] or 'pending'}")
    except psycopg.Error as e:
        raise ValueError(f"Database: {e}") from e


def cmd_user(args) -> None:
    from . import accounts, db
    from .db import migrate
    email = accounts.normalize_email(args.email)
    if not db.enabled():
        raise ValueError("Set GUITARR_DATABASE_URL: accounts live in the web service's database")
    import psycopg
    try:
        if migrate.pending(db.url()):
            raise ValueError("The database needs migrations first: run guitarr db migrate")
        link = accounts.console_link(email)
    except psycopg.Error as e:
        raise ValueError(f"Database: {e}") from e
    print(f"Sign-in link for {email} (open it within {accounts.LINK_MINUTES} minutes; it works once):")
    print(link)


def cmd_worker() -> None:
    from . import db, jobs
    from .db import migrate
    if not db.enabled():
        raise ValueError("Set GUITARR_DATABASE_URL: the worker takes its jobs from the web service's database")
    if migrate.pending(db.url()):
        raise ValueError("The database needs migrations first: run guitarr db migrate")
    import signal
    import threading
    from .gui import server  # noqa: F401 - registers the job handlers
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):        # docker stop: finish the job at hand, then quit
        signal.signal(sig, lambda *_: stop.set())
    print("[guitarr] worker ready", flush=True)
    jobs.work(stop)
    print("[guitarr] worker stopped", flush=True)


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
        elif args.cmd == "charts":
            from . import catalog
            if args.format:
                print(catalog.__doc__.split("Chart format (plain text):", 1)[1].rstrip())
                print(f"\nSave them as .txt files in {catalog.user_dir()}")
            else:
                catalog.print_charts(args.id)
        elif args.cmd == "progress":
            from .progress import print_progress
            print_progress()
        elif args.cmd == "demo":
            from .demo import main as make_demo
            out = make_demo(args.out)
            print("Done:", *sorted(p.name for p in out.iterdir()))
            print(f"Try: guitarr file {out}/reference.mid {out}/take.wav")
        elif args.cmd == "judge-check":
            import json

            from .judgecheck import print_report, run
            if not args.folder.is_dir():
                raise ValueError(f"{args.folder} is not a folder")
            r = run(args.folder, log=print)
            print(json.dumps(r, indent=1)) if args.json else print_report(r)
        elif args.cmd == "db":
            cmd_db(args)
        elif args.cmd == "user":
            cmd_user(args)
        elif args.cmd == "worker":
            cmd_worker()
        elif args.cmd == "gui":
            from .gui.server import serve
            serve(args.host, args.port, open_browser=not args.no_browser)
    except (ReferenceError, AudioError, ValueError, CatalogError) as e:
        sys.exit(f"Error: {e}")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
