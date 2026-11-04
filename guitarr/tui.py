"""Terminal output: live screen (rich) and text reports."""
from __future__ import annotations

import numpy as np

from .core import Grid
from .follow import is_error

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
    head.append(f"{'wait mode' if s['mode'] == 'wait' else 'tempo ' + format(s['speed'], '.0%')}  ")
    head.append(f"{s['source']}\n", style="dim")
    head.append(f"bar {s['bar']} beat {s['beat']:.2f}   note {min(s['k'] + 1, s['total'])}/{s['total']}")

    lvl = Text("\nlevel ")
    n = int(np.clip((s["level_db"] + 60) / 60, 0, 1) * 30)
    lvl.append("█" * n, style="green" if s["peak"] < 0.9 else "red")
    lvl.append("░" * (30 - n), style="dim")
    lvl.append(f" {s['level_db']:5.0f} dB")
    if s["clip"]:
        lvl.append("  CLIPPING! lower the gain", style="bold red")
    elif s["level_db"] < s["gate_db"] and s["now"] > 1:
        lvl.append("  (too low / no signal)", style="yellow")
    if s["tuning"] is not None:
        lvl.append(f"   tuning {s['tuning']:+.0f} cents", style="yellow" if abs(s["tuning"]) > 15 else "dim")

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
            extra.append("\nStart whenever you want: the tempo syncs to your first note", style="cyan")
        elif s["countdown"]:
            extra.append(f"\nCount-in: {s['countdown']}...", style="bold cyan")

    last = s["last"]
    lastt = Text("\n" + (last["text"] if last else "Play the first note..."),
                 style="bold red" if is_error(last) else "bold green")

    st = s["stats"]
    stats = Text("\n", style="dim")
    if st["pct"] is not None:
        stats.append(f"hits {st['pct']}%  ·  ")
    stats.append(f"mistakes {st['errors']}")
    if st["extras"]:
        stats.append(f"  ·  extra {st['extras']}")
    if s["passes"]:
        stats.append("  ·  passes: " + ", ".join(
            f"{p['score']:.0f}%" + (f"@{p['speed']:.0%}" if p.get("speed") else "") for p in s["passes"][-5:]))
    stats.append("\nCtrl+C to finish")
    parts = [head, lvl, lane, tabs] + ([extra] if extra.plain else []) + [lastt, stats]
    return Panel(Group(*parts), border_style="cyan")


def print_live_report(r: dict, grid: Grid | None = None, ref_path: str | None = None) -> None:
    sm = r["summary"]
    print("\n================ RESULT (live) ================")
    if not sm["judged"]:
        print("You didn't play any note of the reference.")
    else:
        print(f"Notes played           : {sm['judged']}/{sm['events']}")
        print(f"Right on the first try : {sm['first_try']} ({sm['first_try_pct']:.0f}%)")
        if r["mode"] == "wait":
            print(f"Fixed after a mistake  : {sm['fixed']}")
        print(f"Wrong                  : {sm['wrong']}")
        print(f"Skipped / not played   : {sm['missed']}")
        if r["mode"] == "tempo":
            if sm["timing_mean_ms"] is not None:
                ms = sm["timing_mean_ms"]
                desc = "on time" if abs(ms) < 15 else f"{abs(ms):.0f} ms {'late' if ms > 0 else 'early'}"
                print(f"Average timing         : {desc} (spread ±{sm['timing_std_ms']:.0f} ms)")
            print(f"Extra notes            : {sm['extras']}")
        if sm["score"] is not None:
            print(f"Score                  : {sm['score']:.0f}/100")
        if r["passes"]:
            print("Passes                 : " + ", ".join(
                f"{p['score']:.0f}%" + (f" @{p['speed']:.0%}" if p.get("speed") else "") for p in r["passes"]))
        if sm["tuning_cents"] is not None and abs(sm["tuning_cents"]) > 15:
            print(f"Tuning                 : {sm['tuning_cents']:+.0f} cents — tune up (guitarr tune)")
    if r.get("overflows"):
        print(f"⚠️  {r['overflows']} audio blocks were dropped (busy CPU).")
    print("===============================================\n")
    for it in r["issues"]:
        icon = STATUS_ICON.get(it["type"], "·")
        print(f"bar {it['bar']:3d} beat {it['beat']:4.2f} ({it['t']:6.2f}s)  {icon}  {it['msg']}")
    if r.get("take"):
        print(f"\nYour take was saved to {r['take']}\n"
              f"For a finer analysis: guitarr file {ref_path or r['reference']['path']} {r['take']}")


def print_file_report(r: dict, max_issues: int = 60) -> None:
    sm = r["summary"]
    print("\n================ RESULT ================")
    print(f"Notes in the reference : {sm['ref_notes']}")
    print(f"Notes detected (yours) : {sm['user_notes']}")
    print(f"Your tempo vs reference: {100 * sm['tempo_ratio']:.0f}%")
    print(f"Correct                : {sm['correct']} ({sm['correct_pct']:.0f}%)  "
          f"[{sm['timing_loose']} of them with loose timing]")
    print(f"Wrong note             : {sm['wrong']}")
    print(f"Missing                : {sm['missing']}"
          + (f"  (+{sm['masked']} undetectable chord octaves, ignored)" if sm["masked"] else ""))
    print(f"Extra                  : {sm['extra']}")
    if sm["timing_mean_ms"] is not None:
        ms = sm["timing_mean_ms"]
        tend = "on time" if abs(ms) < 15 else ("you tend to drag" if ms > 0 else "you tend to rush")
        print(f"Timing                 : {tend} ({ms:+.0f} ms, spread ±{sm['timing_std_ms']:.0f} ms)")
    print(f"Score                  : {sm['score']:.0f}/100")
    print("========================================\n")
    issues = r["issues"]
    for it in issues[:max_issues]:
        print(f"bar {it['bar']:3d} beat {it['beat']:4.2f} ({it['t']:6.2f}s)  {it['msg']}")
    if len(issues) > max_issues:
        print(f"... and {len(issues) - max_issues} more (--max-issues)")
