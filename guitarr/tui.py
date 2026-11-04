"""Salida en terminal: pantalla en vivo (rich) y reportes en texto."""
from __future__ import annotations

import numpy as np

from .core import Grid

STATUS_STYLE = {"pending": "white", "ok": "bold green", "octave": "yellow", "fixed": "green",
                "wrong": "bold red", "missed": "red"}
STATUS_ICON = {"pending": " ", "ok": "✓", "octave": "↕", "fixed": "↻", "wrong": "✗", "missed": "∅",
               "timing": "⏱"}


def tab_label(e: dict) -> str:
    tab = [t for t in e.get("tab", []) if t and t[0]]
    if not tab:
        return ""
    return " ".join(f"{s}·{f}" for s, f in sorted(tab))


def render(s: dict):
    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    head = Text()
    head.append("🎸 guitarr  ", style="bold")
    head.append(f"modo {'espera' if s['mode'] == 'wait' else 'tempo ' + format(s['speed'], '.0%')}  ")
    head.append(f"{s['source']}\n", style="dim")
    head.append(f"compás {s['bar']} tiempo {s['beat']:.2f}   nota {min(s['k'] + 1, s['total'])}/{s['total']}")

    lvl = Text("\nnivel ")
    n = int(np.clip((s["level_db"] + 60) / 60, 0, 1) * 30)
    lvl.append("█" * n, style="green" if s["peak"] < 0.9 else "red")
    lvl.append("░" * (30 - n), style="dim")
    lvl.append(f" {s['level_db']:5.0f} dB")
    if s["clip"]:
        lvl.append("  ¡CLIPEA! bajá la ganancia", style="bold red")
    elif s["level_db"] < s["gate_db"] and s["now"] > 1:
        lvl.append("  (muy bajo / sin señal)", style="yellow")
    if s["tuning"] is not None:
        lvl.append(f"   afinación {s['tuning']:+.0f} cents", style="yellow" if abs(s["tuning"]) > 15 else "dim")

    lane = Text("\n")
    tabs = Text("\n", style="dim")
    for e in s["lane"]:
        lab = e["label"]
        tl = tab_label(e)
        width = max(len(lab), len(tl)) + 2
        if e["current"]:
            lane.append(f"[{lab:^{width - 2}}]", style="bold black on yellow")
        else:
            lane.append(f"{STATUS_ICON[e['status']]}{lab:<{width - 1}}", style=STATUS_STYLE[e["status"]])
        tabs.append(f" {tl:<{width - 1}}")
        lane.append("  ")
        tabs.append("  ")

    extra = Text()
    if s["mode"] == "tempo":
        if s["waiting_first"]:
            extra.append("\nArrancá cuando quieras: el tempo se sincroniza con tu primera nota", style="cyan")
        elif s["countdown"]:
            extra.append(f"\nCuenta: {s['countdown']}...", style="bold cyan")

    last = s["last"] or "Tocá la primera nota..."
    lastt = Text("\n" + last, style="bold red" if last.startswith(("✗", "∅", "+")) else "bold green")

    st = s["stats"]
    stats = Text("\n", style="dim")
    if st["pct"] is not None:
        stats.append(f"aciertos {st['pct']}%  ·  ")
    stats.append(f"errores {st['errors']}")
    if st["extras"]:
        stats.append(f"  ·  de más {st['extras']}")
    if s["passes"]:
        stats.append("  ·  vueltas: " + ", ".join(
            f"{p['score']:.0f}%" + (f"@{p['speed']:.0%}" if p.get("speed") else "") for p in s["passes"][-5:]))
    stats.append("\nCtrl+C para terminar")
    parts = [head, lvl, lane, tabs] + ([extra] if extra.plain else []) + [lastt, stats]
    return Panel(Group(*parts), border_style="cyan")


def print_live_report(r: dict, grid: Grid | None = None, ref_path: str | None = None) -> None:
    sm = r["summary"]
    print("\n================ RESULTADO (en vivo) ================")
    if not sm["judged"]:
        print("No llegaste a tocar ninguna nota de la referencia.")
    else:
        print(f"Notas tocadas          : {sm['judged']}/{sm['events']}")
        print(f"Bien al primer intento : {sm['first_try']} ({sm['first_try_pct']:.0f}%)")
        if r["mode"] == "wait":
            print(f"Corregidas tras error  : {sm['fixed']}")
        print(f"Equivocadas            : {sm['wrong']}")
        print(f"Salteadas / no sonaron : {sm['missed']}")
        if r["mode"] == "tempo":
            if sm["timing_mean_ms"] is not None:
                ms = sm["timing_mean_ms"]
                desc = "a tiempo" if abs(ms) < 15 else f"{abs(ms):.0f} ms {'tarde' if ms > 0 else 'adelantado'}"
                print(f"Timing promedio        : {desc} (desvío ±{sm['timing_std_ms']:.0f} ms)")
            print(f"Notas de más           : {sm['extras']}")
        if sm["score"] is not None:
            print(f"Puntaje                : {sm['score']:.0f}/100")
        if r["passes"]:
            print("Vueltas                : " + ", ".join(
                f"{p['score']:.0f}%" + (f" @{p['speed']:.0%}" if p.get("speed") else "") for p in r["passes"]))
        if sm["tuning_cents"] is not None and abs(sm["tuning_cents"]) > 15:
            print(f"Afinación              : {sm['tuning_cents']:+.0f} cents — conviene afinar (guitarr tune)")
    if r.get("overflows"):
        print(f"⚠️  Se perdieron {r['overflows']} bloques de audio (CPU ocupada).")
    print("=====================================================\n")
    for it in r["issues"]:
        icon = STATUS_ICON.get(it["type"], "·")
        print(f"compás {it['bar']:3d} tiempo {it['beat']:4.2f} ({it['t']:6.2f}s)  {icon}  {it['msg']}")
    if r.get("take"):
        print(f"\nTu toma quedó guardada en {r['take']}\n"
              f"Para un análisis más fino: guitarr file {ref_path or r['reference']['path']} {r['take']}")


def print_file_report(r: dict, max_issues: int = 60) -> None:
    sm = r["summary"]
    print("\n================ RESULTADO ================")
    print(f"Notas en la referencia : {sm['ref_notes']}")
    print(f"Notas detectadas tuyas : {sm['user_notes']}")
    print(f"Tu tempo vs referencia : {100 * sm['tempo_ratio']:.0f}%")
    print(f"Correctas              : {sm['correct']} ({sm['correct_pct']:.0f}%)  "
          f"[de ésas, {sm['timing_loose']} con timing flojo]")
    print(f"Nota equivocada        : {sm['wrong']}")
    print(f"Faltantes              : {sm['missing']}"
          + (f"  (+{sm['masked']} octavas de acorde no detectables, ignoradas)" if sm["masked"] else ""))
    print(f"De más                 : {sm['extra']}")
    if sm["timing_mean_ms"] is not None:
        ms = sm["timing_mean_ms"]
        tend = "a tiempo" if abs(ms) < 15 else ("tendés a ir atrás" if ms > 0 else "tendés a apurarte")
        print(f"Timing                 : {tend} ({ms:+.0f} ms, desvío ±{sm['timing_std_ms']:.0f} ms)")
    print(f"Puntaje                : {sm['score']:.0f}/100")
    print("===========================================\n")
    issues = r["issues"]
    for it in issues[:max_issues]:
        print(f"compás {it['bar']:3d} tiempo {it['beat']:4.2f} ({it['t']:6.2f}s)  {it['msg']}")
    if len(issues) > max_issues:
        print(f"... y {len(issues) - max_issues} más (--max-issues)")
