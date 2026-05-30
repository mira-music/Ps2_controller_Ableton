#!/usr/bin/env python3
"""
================================================================================
  analyze_diagnostics.py — Post-Session Diagnostics Analyzer CLI
================================================================================
  Standalone tool that reads a previously-written diagnostics.jsonl file
  and produces a complete performance report.

  Usage:
      python analyze_diagnostics.py                 # default location
      python analyze_diagnostics.py --file PATH     # specific JSONL file
      python analyze_diagnostics.py --no-rotated    # current file only
      python analyze_diagnostics.py --no-save       # don't write report file
      python analyze_diagnostics.py --json          # output raw JSON
      python analyze_diagnostics.py --no-pause      # don't wait for key on exit

  Behavior in v1.0.0:
      - Auto-writes the report to logs/session_analysis_TIMESTAMP.txt
        so the user has a permanent audit trail to share with developers.
      - Pauses for "press any key to exit" so the console doesn't close
        before the user can read the report (when run via double-click).
      - Detects script vs frozen (.exe) mode and adjusts paths accordingly.

  When built as Analyze_Session.exe via build.py, this is the tool end
  users run after a performance to see how their session went, or to
  send the report to the developer for support.

  Exit codes:
      0 = analysis completed successfully
      1 = no data found (JSONL file missing or empty)
      2 = error during analysis
================================================================================
"""

import sys
import os
import json
import argparse
import datetime
import time
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
#  VERSION DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def detect_version() -> str:
    """
    Try to detect FX Machine version from src/config.py.
    Returns version string or 'unknown'.
    """
    try:
        # Detect script vs frozen
        if getattr(sys, 'frozen', False):
            # Running as .exe
            base = Path(sys.executable).parent
        else:
            # Running as script
            base = Path(__file__).resolve().parent

        config_path = base / "src" / "config.py"
        if not config_path.is_file():
            return "unknown"

        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("VERSION") and "=" in line:
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        value = value.split("#")[0].strip()
                        value = value.strip('"').strip("'")
                        if value:
                            return value
        return "unknown"
    except Exception:
        return "unknown"


# ═══════════════════════════════════════════════════════════════════════════
#  PATH DETECTION (handles script vs frozen .exe mode)
# ═══════════════════════════════════════════════════════════════════════════

def get_base_dir() -> Path:
    """
    Get the base directory for log/config paths.
    Script mode: project root
    Frozen mode: folder containing the .exe
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).resolve().parent


def get_default_jsonl_path() -> Path:
    """Get the default location for the diagnostics JSONL file."""
    return get_base_dir() / "logs" / "diagnostics.jsonl"


def get_report_output_path() -> Path:
    """
    Get the path where the analysis report will be saved.
    Format: logs/session_analysis_YYYY-MM-DD_HH-MM.txt
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
    return get_base_dir() / "logs" / f"session_analysis_{timestamp}.txt"


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


def fmt_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym Zs'."""
    s = int(seconds)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h > 0:
        return f"{h}h {m}m {sec}s"
    if m > 0:
        return f"{m}m {sec}s"
    return f"{sec}s"


# ═══════════════════════════════════════════════════════════════════════════
#  REPORT BUILDER
# ═══════════════════════════════════════════════════════════════════════════
#
#  The report is built as a list of strings. Each line is printed to the
#  console AND optionally written to the output file. This dual-output
#  pattern means console color codes can be stripped for the file version.
# ═══════════════════════════════════════════════════════════════════════════

class ReportBuilder:
    """
    Accumulates report lines for dual output (console with colors,
    file without colors).
    """

    def __init__(self):
        self.lines: list[str] = []

    def add(self, line: str = ""):
        """Add a line to the report. Prints to console immediately."""
        self.lines.append(line)
        print(line)

    def header(self, title: str):
        """Section header."""
        line = f"\n{C.BOLD}{C.INFO}━━━ {title} ━━━{C.END}"
        self.lines.append(line)
        print(line)

    def label_value(self, label: str, value: str, color: str = ""):
        """A 'Label : value' line."""
        pad = max(0, 30 - len(label))
        line = f"  {label}{' ' * pad} {color}{value}{C.END}"
        self.lines.append(line)
        print(line)

    def info(self, msg: str):
        line = f"  {C.INFO}ℹ{C.END} {msg}"
        self.lines.append(line)
        print(line)

    def get_text(self, strip_colors: bool = True) -> str:
        """Get the complete report as a single string."""
        text = "\n".join(self.lines)
        if strip_colors:
            text = strip_ansi_codes(text)
        return text


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI color codes for plain-text file output."""
    import re
    pattern = re.compile(r'\x1b\[[0-9;]*m')
    return pattern.sub('', text)


# ═══════════════════════════════════════════════════════════════════════════
#  REPORT SECTIONS
# ═══════════════════════════════════════════════════════════════════════════

def print_banner(report: ReportBuilder, version: str):
    """Print the tool banner."""
    line1 = f"\n{C.BOLD}{C.INFO}╔{'═' * 62}╗{C.END}"
    line2 = f"{C.BOLD}{C.INFO}║{' ' * 6}FX MACHINE — DIAGNOSTICS SESSION ANALYZER{' ' * 14}║{C.END}"
    line3 = f"{C.BOLD}{C.INFO}╚{'═' * 62}╝{C.END}"

    report.lines.extend([line1, line2, line3])
    print(line1)
    print(line2)
    print(line3)

    report.add(f"\n  {C.DIM}FX Machine version : v{version}{C.END}")
    report.add(f"  {C.DIM}Analysis generated : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{C.END}")


def print_session_summary(report: ReportBuilder, session: dict):
    report.header("SESSION OVERVIEW")
    report.label_value("Start time", fmt_ts(session.get("start_time")))
    report.label_value("End time", fmt_ts(session.get("end_time")))
    report.label_value("Duration", session.get("duration_str", "?"))
    report.label_value("Summaries written", str(session.get("summary_count", 0)))
    report.label_value("Outliers logged", str(session.get("outlier_count", 0)))
    report.label_value("Warnings (cumulative)", str(session.get("warning_count_total", 0)))
    report.label_value("Diagnostics overhead", f"{session.get('total_overhead_ms', 0):.1f} ms")

    clean = session.get("session_was_clean", False)
    report.label_value(
        "Clean shutdown",
        "✓ yes" if clean else "✗ NO (app may have crashed)",
        C.OK if clean else C.WARN,
    )


def print_system_resources(report: ReportBuilder, sys_data: dict):
    report.header("SYSTEM RESOURCES")

    if sys_data.get("empty"):
        report.add(f"  {C.DIM}No system data available{C.END}")
        return

    if not sys_data.get("psutil_available"):
        report.add(f"  {C.DIM}psutil not installed — CPU/RAM data unavailable{C.END}")
        return

    report.add(f"  CPU usage  (across {sys_data.get('sample_count', 0)} summaries):")
    report.add(f"    min  {sys_data.get('cpu_min', 0):5.1f}%   "
               f"avg  {sys_data.get('cpu_avg', 0):5.1f}%   "
               f"p95  {sys_data.get('cpu_p95', 0):5.1f}%   "
               f"max  {sys_data.get('cpu_max', 0):5.1f}%")

    report.add(f"\n  Memory usage:")
    report.add(f"    min  {sys_data.get('memory_min', 0):6.1f} MB   "
               f"max  {sys_data.get('memory_max', 0):6.1f} MB")

    growth = sys_data.get("memory_growth_total", 0)
    rate   = sys_data.get("memory_growth_per_min", 0)
    growth_color = C.WARN if abs(rate) > 1.0 else C.OK
    report.add(f"    growth {growth_color}{growth:+.1f} MB total"
               f" ({rate:+.2f} MB/min){C.END}")

    if "thread_count_min" in sys_data:
        report.add(f"\n  Thread count: "
                   f"{sys_data['thread_count_min']}–{sys_data['thread_count_max']}")


def print_thread_health(report: ReportBuilder, threads: dict):
    report.header("THREAD HEALTH (whole session)")

    if not threads:
        report.add(f"  {C.DIM}No thread data{C.END}")
        return

    for name in sorted(threads.keys()):
        t = threads[name]
        if t["target_hz"] <= 0:
            continue

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
            status_color = C.OK
            status_icon = f"✓ {t['unhealthy_pct']:.0f}% unhealthy"

        worst_at = ""
        if t.get("worst_actual_hz_at"):
            worst_at = f"  (worst at {fmt_ts(t['worst_actual_hz_at'])})"

        report.add(f"  {status_color}{status_icon:18}{C.END}  "
                   f"{name:12} target {t['target_hz']:6.1f} Hz   "
                   f"avg {t['avg_actual_hz']:6.1f} Hz   "
                   f"worst {t.get('worst_actual_hz', 0) or 0:6.1f} Hz{worst_at}")


def print_top_functions(report: ReportBuilder, fn_perf: dict):
    report.header("TOP FUNCTIONS BY TOTAL TIME")

    top = fn_perf.get("top_by_cumulative_time", [])
    if not top:
        report.add(f"  {C.DIM}No function timing data{C.END}")
        return

    report.add(f"  {C.BOLD}{'function':40} {'calls':>9} {'total':>11} {'avg':>9} {'p99':>9}{C.END}")
    report.add(f"  {'─' * 80}")

    for fn in top:
        if fn.get("count", 0) == 0:
            continue
        name = fn["name"]
        if len(name) > 40:
            name = "…" + name[-39:]
        report.add(f"  {name:40} "
                   f"{fn['count']:9d} "
                   f"{fn['total_ms']:10.1f}ms "
                   f"{fn['avg_ms']:8.2f}ms "
                   f"{fn.get('recent_p99_ms', 0):8.2f}ms")


def print_worst_p99(report: ReportBuilder, fn_perf: dict):
    report.header("WORST p99 LATENCIES (slowest functions overall)")

    worst = fn_perf.get("top_by_worst_p99", [])
    if not worst:
        report.add(f"  {C.DIM}No data{C.END}")
        return

    for fn in worst[:10]:
        max_ms = fn.get("recent_max_ms", 0)
        p99 = fn.get("recent_p99_ms", 0)
        color = C.FAIL if max_ms > 100 else (C.WARN if max_ms > 50 else "")
        report.add(f"  {color}{fn['name'][-50:]:50}  "
                   f"p99 {p99:6.2f}ms  max {max_ms:6.2f}ms{C.END}")


def print_outliers(report: ReportBuilder, fn_perf: dict):
    report.header("OUTLIER FUNCTIONS (most slow-call occurrences)")

    by_fn = fn_perf.get("outliers_by_function", {})
    total = fn_perf.get("outliers_total", 0)

    if not by_fn:
        report.add(f"  {C.DIM}No outliers logged this session{C.END}")
        return

    report.add(f"  {C.DIM}{total} outlier(s) total{C.END}")
    for name, count in list(by_fn.items())[:15]:
        report.add(f"  {name[-50:]:50}  {count:5d} slow call(s)")


def print_osc_traffic(report: ReportBuilder, osc: dict):
    report.header("OSC TRAFFIC")

    if osc.get("empty"):
        report.add(f"  {C.DIM}No OSC data{C.END}")
        return

    report.label_value("Total outbound", f"{osc['total_sends']:,} messages "
                       f"({fmt_bytes(osc['total_send_bytes'])})")
    report.label_value("Total inbound", f"{osc['total_receives']:,} messages "
                       f"({fmt_bytes(osc['total_recv_bytes'])})")
    report.label_value("Unique send addresses", str(osc.get("unique_send_addresses", 0)))
    report.label_value("Unique recv addresses", str(osc.get("unique_recv_addresses", 0)))
    report.label_value("Peak send rate", f"{osc.get('peak_send_rate', 0):.1f} msg/s "
                       f"at {fmt_ts(osc.get('peak_send_at'))}")
    report.label_value("Peak recv rate", f"{osc.get('peak_recv_rate', 0):.1f} msg/s "
                       f"at {fmt_ts(osc.get('peak_recv_at'))}")

    top_send = osc.get("top_senders", [])
    if top_send:
        report.add(f"\n  {C.BOLD}Top outbound addresses:{C.END}")
        for s in top_send[:10]:
            report.add(f"    {s['address'][:52]:52}  {s['count_total']:6d} total  "
                       f"peak {s.get('max_per_sec_observed', 0):5.1f}/s")

    top_recv = osc.get("top_receivers", [])
    if top_recv:
        report.add(f"\n  {C.BOLD}Top inbound addresses:{C.END}")
        for s in top_recv[:10]:
            report.add(f"    {s['address'][:52]:52}  {s['count_total']:6d} total  "
                       f"peak {s.get('max_per_sec_observed', 0):5.1f}/s")


def print_counters(report: ReportBuilder, counters: dict):
    report.header("EVENT COUNTERS")

    if not counters:
        report.add(f"  {C.DIM}No counter data{C.END}")
        return

    nonzero = {k: v for k, v in counters.items() if v["total"] > 0}
    if not nonzero:
        report.add(f"  {C.DIM}All counters at zero{C.END}")
        return

    sorted_counters = sorted(nonzero.items(), key=lambda x: -x[1]["total"])
    for name, data in sorted_counters[:20]:
        report.add(f"  {name:40} {int(data['total']):8d} total  "
                   f"({data['rate_per_min']:6.1f}/min)")


def print_warnings(report: ReportBuilder, warnings: dict):
    report.header("WARNINGS SUMMARY")

    total = warnings.get("total_warnings", 0)
    if total == 0:
        report.add(f"  {C.OK}✓ No warnings fired during this session{C.END}")
        return

    report.add(f"  {C.WARN}Total warnings: {total}{C.END}\n")

    most_common = warnings.get("most_common_warnings", [])
    if most_common:
        report.add(f"  {C.BOLD}Most common warning patterns:{C.END}")
        for pattern, count in most_common[:10]:
            report.add(f"    {C.WARN}{count:5d}× {pattern}{C.END}")


def print_footer(report: ReportBuilder, report_file: Path | None):
    """Print the closing footer with file location and developer note."""
    report.add(f"\n{C.BOLD}{'━' * 64}{C.END}")
    report.add(f"{C.DIM}  Analysis complete.{C.END}")

    if report_file:
        report.add(f"\n  {C.BOLD}This report was saved to:{C.END}")
        report.add(f"    {report_file}")
        report.add(f"\n  {C.DIM}You can re-read this file later or share it with the{C.END}")
        report.add(f"  {C.DIM}developer for support. The file is plain text and safe to email.{C.END}")


# ═══════════════════════════════════════════════════════════════════════════
#  FILE OUTPUT
# ═══════════════════════════════════════════════════════════════════════════

def save_report_to_file(report: ReportBuilder, output_path: Path) -> bool:
    """
    Save the report to a text file with ANSI codes stripped.
    Returns True on success, False on failure.
    """
    try:
        # Ensure logs/ folder exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the report (color codes stripped for plain text)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report.get_text(strip_colors=True))
            f.write("\n")

        return True
    except Exception as e:
        print(f"\n  {C.WARN}⚠ Could not save report to file: {e}{C.END}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  PAUSE FOR USER
# ═══════════════════════════════════════════════════════════════════════════

def wait_for_user_keypress():
    """
    Wait for the user to press any key before exiting.
    Important when the .exe is double-clicked — without this, the console
    window closes immediately after the report is printed.
    """
    print(f"\n{C.DIM}  Press any key to exit...{C.END}", end="", flush=True)
    try:
        # Try Windows-specific msvcrt first
        import msvcrt
        msvcrt.getch()
    except ImportError:
        # Fallback for non-Windows (won't happen for .exe but useful for testing)
        try:
            input()
        except (EOFError, KeyboardInterrupt):
            pass
    print()


# ═══════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Analyze an FX Machine diagnostics session log.",
    )
    parser.add_argument(
        "--file", type=Path, default=None,
        help="Path to .jsonl file (default: logs/diagnostics.jsonl)",
    )
    parser.add_argument(
        "--no-rotated", action="store_true",
        help="Only analyze the current file, ignore rotated backups",
    )
    parser.add_argument(
        "--no-save", action="store_true",
        help="Don't write the analysis report to a file",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON instead of pretty-printed text",
    )
    parser.add_argument(
        "--no-pause", action="store_true",
        help="Don't wait for keypress on exit (useful in scripts)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    version = detect_version()

    # Resolve JSONL path
    jsonl_path = args.file if args.file else get_default_jsonl_path()
    jsonl_path = jsonl_path.resolve()

    # Build the report
    report = ReportBuilder()
    print_banner(report, version)

    report.add(f"\n  {C.DIM}Source : {jsonl_path}{C.END}")
    report.add(f"  {C.DIM}Rotated backups: {'excluded' if args.no_rotated else 'included if present'}{C.END}")

    # Check JSONL file exists
    if not jsonl_path.exists():
        print(f"\n{C.FAIL}❌ No diagnostics file found at {jsonl_path}{C.END}")
        print(f"\n  Possible reasons:")
        print(f"    - The app was never run with diagnostics enabled")
        print(f"    - You're looking in the wrong folder")
        print(f"    - The log was deleted")
        print(f"\n  To enable diagnostics:")
        print(f"    Edit config/active.toml and set [diagnostics] enabled = true")
        print(f"    Then run FX Machine and use it for a few minutes")
        print(f"    Close the app cleanly, then run this analyzer again\n")

        if not args.no_pause:
            wait_for_user_keypress()
        sys.exit(1)

    # Load and analyze
    try:
        from src.diagnostics.analyzer import analyze_full_session
    except Exception as e:
        print(f"\n{C.FAIL}❌ Cannot import analyzer: {e}{C.END}\n")
        if not args.no_pause:
            wait_for_user_keypress()
        sys.exit(2)

    try:
        result = analyze_full_session(
            jsonl_path,
            include_rotated=not args.no_rotated,
        )
    except Exception as e:
        print(f"\n{C.FAIL}❌ Analysis failed: {e}{C.END}\n")
        import traceback
        traceback.print_exc()
        if not args.no_pause:
            wait_for_user_keypress()
        sys.exit(2)

    events_loaded = result.get("events_loaded", 0)
    if events_loaded == 0:
        print(f"\n{C.FAIL}❌ No events found in JSONL file{C.END}")
        print(f"\n  The file exists but is empty. The diagnostics layer didn't")
        print(f"  write anything. This usually means:")
        print(f"    - Diagnostics was enabled but the app crashed before writing data")
        print(f"    - The app was closed within a few seconds of starting\n")
        if not args.no_pause:
            wait_for_user_keypress()
        sys.exit(1)

    report.add(f"  {C.OK}✓ Loaded {events_loaded:,} event records{C.END}")

    # JSON output mode (no file save, no pause)
    if args.json:
        print("\n" + json.dumps(result, indent=2, default=str))
        sys.exit(0)

    # Pretty-print all sections
    print_session_summary(report, result["session"])
    print_system_resources(report, result["system_resources"])
    print_thread_health(report, result["thread_health"])
    print_top_functions(report, result["function_perf"])
    print_worst_p99(report, result["function_perf"])
    print_outliers(report, result["function_perf"])
    print_osc_traffic(report, result["osc_traffic"])
    print_counters(report, result["counters"])
    print_warnings(report, result["warnings"])

    # Save to file (unless --no-save)
    report_file = None
    if not args.no_save:
        report_file = get_report_output_path()
        if save_report_to_file(report, report_file):
            print_footer(report, report_file)
        else:
            print_footer(report, None)
    else:
        print_footer(report, None)

    # Wait for user (unless --no-pause)
    if not args.no_pause:
        wait_for_user_keypress()

    sys.exit(0)


if __name__ == "__main__":
    main()