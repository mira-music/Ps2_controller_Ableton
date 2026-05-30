#!/usr/bin/env python3
"""
================================================================================
  analyze_diagnostics.py — Post-Session Diagnostics Analyzer CLI
================================================================================
  Standalone command-line tool for analyzing a past FX Machine session's
  diagnostics output.

  Usage:
      python analyze_diagnostics.py                 # default location
      python analyze_diagnostics.py --file PATH     # specific JSONL file
      python analyze_diagnostics.py --no-rotated    # current file only
      python analyze_diagnostics.py --json          # output raw JSON

  Reads logs/diagnostics.jsonl (and any rotated backups by default),
  aggregates all session data, prints a human-readable report.

  Use this AFTER closing the FX Machine app to see what happened during
  your session — which functions were slow, what OSC traffic peaked,
  which warnings fired, etc.

  Exit codes:
      0 — analysis ran successfully
      1 — no data found (jsonl file missing or empty)
      2 — error during analysis
================================================================================
"""

import sys
import json
import argparse
import datetime
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════
#  ANSI COLORS (Windows 10+ native support)
# ═══════════════════════════════════════════════════════════════════════════

try:
    import ctypes
    ctypes.windll.kernel32.SetConsoleMode(
        ctypes.windll.kernel32.GetStdHandle(-11), 7
    )
except Exception:
    pass


class C:
    OK   = "\033[92m"
    WARN = "\033[93m"
    FAIL = "\033[91m"
    INFO = "\033[96m"
    DIM  = "\033[90m"
    BOLD = "\033[1m"
    END  = "\033[0m"


# ═══════════════════════════════════════════════════════════════════════════
#  FORMATTING HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def fmt_ts(ts: float) -> str:
    """Format Unix timestamp as readable date/time."""
    if not ts:
        return "?"
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def fmt_bytes(n: int) -> str:
    """Format byte count as human-readable size."""
    if n >= 1024 * 1024:
        return f"{n / (1024*1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def header(title: str):
    print(f"\n{C.BOLD}{C.INFO}━━━ {title} ━━━{C.END}")


def section_line(label: str, value: str, color=""):
    pad = max(0, 30 - len(label))
    print(f"  {label}{' ' * pad} {color}{value}{C.END}")


# ═══════════════════════════════════════════════════════════════════════════
#  REPORT SECTIONS
# ═══════════════════════════════════════════════════════════════════════════

def print_session_summary(session: dict):
    header("SESSION OVERVIEW")
    section_line("Start time", fmt_ts(session.get("start_time")))
    section_line("End time", fmt_ts(session.get("end_time")))
    section_line("Duration", session.get("duration_str", "?"))
    section_line("Summaries written", str(session.get("summary_count", 0)))
    section_line("Outliers logged", str(session.get("outlier_count", 0)))
    section_line("Warnings (cumulative)", str(session.get("warning_count_total", 0)))
    section_line("Diagnostics overhead", f"{session.get('total_overhead_ms', 0):.1f} ms")
    section_line(
        "Clean shutdown",
        "✓ yes" if session.get("session_was_clean") else "✗ NO (app may have crashed)",
        C.OK if session.get("session_was_clean") else C.WARN,
    )


def print_system_resources(sys_data: dict):
    header("SYSTEM RESOURCES")
    if sys_data.get("empty"):
        print(f"  {C.DIM}No system data available (psutil missing or no samples){C.END}")
        return

    if not sys_data.get("psutil_available"):
        print(f"  {C.DIM}psutil not installed — CPU/RAM data unavailable{C.END}")
        return

    print(f"  CPU usage  (across {sys_data.get('sample_count', 0)} summaries):")
    print(f"    min  {sys_data.get('cpu_min', 0):5.1f}%   "
          f"avg  {sys_data.get('cpu_avg', 0):5.1f}%   "
          f"p95  {sys_data.get('cpu_p95', 0):5.1f}%   "
          f"max  {sys_data.get('cpu_max', 0):5.1f}%")

    print(f"\n  Memory usage:")
    print(f"    min  {sys_data.get('memory_min', 0):6.1f} MB   "
          f"max  {sys_data.get('memory_max', 0):6.1f} MB")

    growth = sys_data.get("memory_growth_total", 0)
    rate   = sys_data.get("memory_growth_per_min", 0)
    growth_color = C.WARN if abs(rate) > 1.0 else C.OK
    print(f"    growth {growth_color}{growth:+.1f} MB total"
          f" ({rate:+.2f} MB/min){C.END}")

    if "thread_count_min" in sys_data:
        print(f"\n  Thread count: "
              f"{sys_data['thread_count_min']}–{sys_data['thread_count_max']}")


def print_thread_health(threads: dict):
    header("THREAD HEALTH (whole session)")
    if not threads:
        print(f"  {C.DIM}No thread data{C.END}")
        return

    for name in sorted(threads.keys()):
        t = threads[name]
        if t["target_hz"] <= 0:
            continue  # skip threads with no target (auto-registered unknowns)

        status_color = C.OK
        if t["was_stalled"]:
            status_color = C.FAIL
            status_icon = "✗ STALLED"
        elif t["unhealthy_pct"] > 25:
            status_color = C.FAIL
            status_icon = f"✗ {t['unhealthy_pct']:.0f}% unhealthy"
        elif t["unhealthy_pct"] > 5:
            status_color = C.WARN
            status_icon = f"⚠ {t['unhealthy_pct']:.0f}% unhealthy"
        else:
            status_icon = f"✓ {t['unhealthy_pct']:.0f}% unhealthy"

        worst_at = ""
        if t.get("worst_actual_hz_at"):
            worst_at = f"  (worst at {fmt_ts(t['worst_actual_hz_at'])})"

        print(f"  {status_color}{status_icon:18}{C.END}  "
              f"{name:12} target {t['target_hz']:6.1f} Hz   "
              f"avg {t['avg_actual_hz']:6.1f} Hz   "
              f"worst {t.get('worst_actual_hz', 0) or 0:6.1f} Hz{worst_at}")


def print_top_functions(fn_perf: dict):
    header("TOP FUNCTIONS BY TOTAL TIME")
    top = fn_perf.get("top_by_cumulative_time", [])
    if not top:
        print(f"  {C.DIM}No function timing data{C.END}")
        return

    print(f"  {C.BOLD}{'function':40} {'calls':>9} {'total':>11} {'avg':>9} {'p99':>9}{C.END}")
    print(f"  {'─' * 80}")
    for fn in top:
        if fn.get("count", 0) == 0:
            continue
        name = fn["name"]
        if len(name) > 40:
            name = "…" + name[-39:]
        print(f"  {name:40} "
              f"{fn['count']:9d} "
              f"{fn['total_ms']:10.1f}ms "
              f"{fn['avg_ms']:8.2f}ms "
              f"{fn.get('recent_p99_ms', 0):8.2f}ms")


def print_worst_p99(fn_perf: dict):
    header("WORST p99 LATENCIES (slowest functions overall)")
    worst = fn_perf.get("top_by_worst_p99", [])
    if not worst:
        print(f"  {C.DIM}No data{C.END}")
        return

    for fn in worst[:10]:
        max_ms = fn.get("recent_max_ms", 0)
        p99 = fn.get("recent_p99_ms", 0)
        color = C.FAIL if max_ms > 100 else (C.WARN if max_ms > 50 else "")
        print(f"  {color}{fn['name'][-50:]:50}  "
              f"p99 {p99:6.2f}ms  max {max_ms:6.2f}ms{C.END}")


def print_outliers(fn_perf: dict):
    header("OUTLIER FUNCTIONS (most slow-call occurrences)")
    by_fn = fn_perf.get("outliers_by_function", {})
    total = fn_perf.get("outliers_total", 0)
    if not by_fn:
        print(f"  {C.DIM}No outliers logged this session{C.END}")
        return
    print(f"  {C.DIM}{total} outlier(s) total{C.END}")
    for name, count in list(by_fn.items())[:15]:
        print(f"  {name[-50:]:50}  {count:5d} slow call(s)")


def print_osc_traffic(osc: dict):
    header("OSC TRAFFIC")
    if osc.get("empty"):
        print(f"  {C.DIM}No OSC data{C.END}")
        return

    section_line("Total outbound", f"{osc['total_sends']:,} messages "
                                    f"({fmt_bytes(osc['total_send_bytes'])})")
    section_line("Total inbound",  f"{osc['total_receives']:,} messages "
                                    f"({fmt_bytes(osc['total_recv_bytes'])})")
    section_line("Unique send addresses", str(osc.get("unique_send_addresses", 0)))
    section_line("Unique recv addresses", str(osc.get("unique_recv_addresses", 0)))
    section_line("Peak send rate", f"{osc.get('peak_send_rate', 0):.1f} msg/s "
                                    f"at {fmt_ts(osc.get('peak_send_at'))}")
    section_line("Peak recv rate", f"{osc.get('peak_recv_rate', 0):.1f} msg/s "
                                    f"at {fmt_ts(osc.get('peak_recv_at'))}")

    top_send = osc.get("top_senders", [])
    if top_send:
        print(f"\n  {C.BOLD}Top outbound addresses:{C.END}")
        for s in top_send[:10]:
            print(f"    {s['address'][:52]:52}  {s['count_total']:6d} total  "
                  f"peak {s.get('max_per_sec_observed', 0):5.1f}/s")

    top_recv = osc.get("top_receivers", [])
    if top_recv:
        print(f"\n  {C.BOLD}Top inbound addresses:{C.END}")
        for s in top_recv[:10]:
            print(f"    {s['address'][:52]:52}  {s['count_total']:6d} total  "
                  f"peak {s.get('max_per_sec_observed', 0):5.1f}/s")


def print_counters(counters: dict):
    header("EVENT COUNTERS")
    if not counters:
        print(f"  {C.DIM}No counter data{C.END}")
        return
    # Filter zero counters
    nonzero = {k: v for k, v in counters.items() if v["total"] > 0}
    if not nonzero:
        print(f"  {C.DIM}All counters at zero{C.END}")
        return

    sorted_counters = sorted(nonzero.items(), key=lambda x: -x[1]["total"])
    for name, data in sorted_counters[:20]:
        print(f"  {name:40} {int(data['total']):8d} total  "
              f"({data['rate_per_min']:6.1f}/min)")


def print_warnings(warnings: dict):
    header("WARNINGS SUMMARY")
    total = warnings.get("total_warnings", 0)
    if total == 0:
        print(f"  {C.OK}✓ No warnings fired during this session{C.END}")
        return

    print(f"  {C.WARN}Total warnings: {total}{C.END}\n")

    most_common = warnings.get("most_common_warnings", [])
    if most_common:
        print(f"  {C.BOLD}Most common warning patterns:{C.END}")
        for pattern, count in most_common[:10]:
            print(f"    {C.WARN}{count:5d}× {pattern}{C.END}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze a FX Machine diagnostics session log."
    )
    parser.add_argument(
        "--file", type=Path,
        default=Path("logs") / "diagnostics.jsonl",
        help="Path to .jsonl file (default: logs/diagnostics.jsonl)",
    )
    parser.add_argument(
        "--no-rotated", action="store_true",
        help="Only analyze the current file, ignore rotated backups",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw analysis dict as JSON instead of pretty-printing",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    jsonl_path = args.file.resolve()

    print(f"\n{C.BOLD}{C.INFO}╔{'═' * 62}╗{C.END}")
    print(f"{C.BOLD}{C.INFO}║{' ' * 7}FX MACHINE — DIAGNOSTICS SESSION ANALYZER{' ' * 13}║{C.END}")
    print(f"{C.BOLD}{C.INFO}╚{'═' * 62}╝{C.END}\n")

    print(f"  {C.DIM}Source : {jsonl_path}{C.END}")
    print(f"  {C.DIM}Rotated backups: {'excluded' if args.no_rotated else 'included if present'}{C.END}\n")

    if not jsonl_path.exists():
        print(f"{C.FAIL}❌ No diagnostics file found at {jsonl_path}{C.END}\n")
        print(f"   Run the app with diagnostics.enabled = true in TOML")
        print(f"   to generate a session log, then re-run this analyzer.\n")
        sys.exit(1)

    try:
        from src.diagnostics.analyzer import analyze_full_session
    except Exception as e:
        print(f"{C.FAIL}❌ Cannot import analyzer: {e}{C.END}\n")
        sys.exit(2)

    try:
        report = analyze_full_session(
            jsonl_path,
            include_rotated=not args.no_rotated,
        )
    except Exception as e:
        print(f"{C.FAIL}❌ Analysis failed: {e}{C.END}\n")
        import traceback
        traceback.print_exc()
        sys.exit(2)

    events_loaded = report.get("events_loaded", 0)
    if events_loaded == 0:
        print(f"{C.FAIL}❌ No events found in JSONL file{C.END}\n")
        sys.exit(1)

    print(f"  {C.OK}✓ Loaded {events_loaded:,} event records{C.END}")

    # JSON output mode
    if args.json:
        print("\n" + json.dumps(report, indent=2, default=str))
        sys.exit(0)

    # Pretty-print mode
    print_session_summary(report["session"])
    print_system_resources(report["system_resources"])
    print_thread_health(report["thread_health"])
    print_top_functions(report["function_perf"])
    print_worst_p99(report["function_perf"])
    print_outliers(report["function_perf"])
    print_osc_traffic(report["osc_traffic"])
    print_counters(report["counters"])
    print_warnings(report["warnings"])

    print(f"\n{C.BOLD}{'━' * 64}{C.END}")
    print(f"{C.DIM}  Analysis complete. Run again after your next session "
          f"to track changes.{C.END}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()