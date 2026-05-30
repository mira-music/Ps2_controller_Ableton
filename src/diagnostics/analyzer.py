"""
================================================================================
  src/diagnostics/analyzer.py — Post-Session Analysis Module
================================================================================
  Reads a previously-written diagnostics.jsonl file and produces aggregate
  reports across the entire session. Used both by the standalone CLI tool
  (analyze_diagnostics.py in the project root) and potentially by future
  in-app "show me the last 5 minutes" features.

  What it analyzes:
    1. Session summary
       - Start time, end time, total duration
       - Total summaries written
       - Total outliers logged
       - Diagnostics overhead

    2. Top performance offenders
       - Functions by total cumulative time
       - Functions by worst p99 latency
       - Functions with most outliers
       - Time-binned analysis: "filter_freq spent X ms in minute 3"

    3. OSC traffic patterns
       - Most active addresses (sends + receives)
       - Peak burst rates and when they occurred
       - Total bytes sent/received

    4. System resource trends
       - CPU usage over time (min/avg/max/p95 per minute)
       - Memory growth trajectory
       - Thread count stability

    5. Event counter totals
       - Cumulative counts of every tracked event
       - Rate breakdowns

    6. Warnings summary
       - All warnings that fired during the session
       - Frequency of each warning type
       - Time clustering (was 80% of warnings in the first 5 minutes?)

    7. Thread health
       - Per-thread health over the entire session
       - Identifies threads that struggled at specific times

  Input format:
    JSONL = JSON Lines. Each line is one JSON object. The reporter writes
    several event types:
      {"type": "session_start", ...}
      {"type": "summary", ...}      ← the bulk of records
      {"type": "outlier", ...}
      {"type": "session_end", ...}

  Memory:
    The analyzer reads the entire file into memory. A 5 MB JSONL file
    (the rotation limit) is roughly 50,000 summary records or 200,000
    outlier records — fits easily in RAM. For very long sessions split
    across multiple rotated files, the analyzer can read all of them.

  Output:
    Returns dicts and lists. The standalone CLI tool formats these for
    terminal display. Future GUI tools could consume the same data.
================================================================================
"""

import json
import time
import statistics
from pathlib import Path
from collections import defaultdict, Counter
from typing import Optional, Iterator


# ═══════════════════════════════════════════════════════════════════════════
#  LOADING + PARSING
# ═══════════════════════════════════════════════════════════════════════════

def load_jsonl_file(path: Path) -> list[dict]:
    """
    Read a JSONL file and return a list of parsed event dicts.

    Malformed lines are logged to stderr and skipped — we never raise
    just because one line in the middle is corrupted (could happen if
    the app crashed mid-write).

    Args:
        path: Path to the .jsonl file (or a rotated backup like .jsonl.1)

    Returns:
        List of dicts, each one record from the file.
        Empty list if the file doesn't exist or is empty.
    """
    if not path.exists():
        return []

    events = []
    line_num = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line_num += 1
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError as e:
                    # Don't raise — corrupt lines are individually skipped
                    import sys
                    print(
                        f"[analyzer] {path.name} line {line_num}: "
                        f"JSON parse error ({e}), skipping",
                        file=sys.stderr,
                    )
    except Exception as e:
        import sys
        print(f"[analyzer] cannot read {path}: {e}", file=sys.stderr)
        return []

    return events


def load_all_rotated_files(base_path: Path) -> list[dict]:
    """
    Load the main .jsonl plus all rotated backups, oldest first.

    Rotation naming (matches the Reporter): the current file is
    `diagnostics.jsonl`. As it rolls over, it becomes `diagnostics.jsonl.1`,
    `.2`, etc. Higher numbers are OLDER. So to get chronological order
    we load .10, .9, ..., .2, .1, then the current file.

    Args:
        base_path: e.g. logs/diagnostics.jsonl

    Returns:
        List of all events from all files, in chronological order.
    """
    events = []
    # Oldest-first ordering: highest .N down to .1, then the base file
    for i in range(10, 0, -1):
        rotated = base_path.with_suffix(base_path.suffix + f".{i}")
        if rotated.exists():
            events.extend(load_jsonl_file(rotated))
    # The base file is the newest
    events.extend(load_jsonl_file(base_path))
    return events


def filter_events_by_type(events: list[dict], event_type: str) -> list[dict]:
    """Filter a list of events to just those matching the given type."""
    return [e for e in events if e.get("type") == event_type]


# ═══════════════════════════════════════════════════════════════════════════
#  SESSION-LEVEL ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_session(events: list[dict]) -> dict:
    """
    Top-level session summary: when did it run, how long, how many records.

    Returns dict with:
        start_time, end_time, duration_s, duration_str
        summary_count, outlier_count, warning_count_total
        total_overhead_ms_reported
        session_was_clean (i.e. session_end event present)
    """
    starts = filter_events_by_type(events, "session_start")
    ends   = filter_events_by_type(events, "session_end")
    summaries = filter_events_by_type(events, "summary")
    outliers  = filter_events_by_type(events, "outlier")

    start_ts = starts[0]["timestamp"] if starts else None
    end_ts = ends[-1]["timestamp"] if ends else None

    # If the session didn't end cleanly, derive end_ts from last summary
    if end_ts is None and summaries:
        end_ts = summaries[-1]["timestamp"]
    if start_ts is None and summaries:
        start_ts = summaries[0]["timestamp"]

    duration_s = (end_ts - start_ts) if (start_ts and end_ts) else 0

    # Final overhead from session_end record if present, else from last summary
    if ends:
        overhead_ns = ends[-1].get("overhead_ns_total", 0)
        total_overhead_ms = overhead_ns / 1_000_000.0
    elif summaries:
        total_overhead_ms = summaries[-1].get("diag_overhead_ms", 0)
    else:
        total_overhead_ms = 0

    # Count warnings across all summaries
    warning_count = 0
    for s in summaries:
        warning_count += len(s.get("warnings", []))

    return {
        "start_time":           start_ts,
        "end_time":             end_ts,
        "duration_s":           duration_s,
        "duration_str":         _fmt_duration(duration_s),
        "summary_count":        len(summaries),
        "outlier_count":        len(outliers),
        "warning_count_total":  warning_count,
        "total_overhead_ms":    total_overhead_ms,
        "session_was_clean":    len(ends) > 0,
        "total_event_count":    len(events),
    }


def _fmt_duration(seconds: float) -> str:
    """Format duration as 'Xh Ym Zs'."""
    s = int(seconds)
    h, m, sec = s // 3600, (s % 3600) // 60, s % 60
    if h > 0:
        return f"{h}h {m}m {sec}s"
    if m > 0:
        return f"{m}m {sec}s"
    return f"{sec}s"


# ═══════════════════════════════════════════════════════════════════════════
#  FUNCTION PERFORMANCE ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_function_performance(events: list[dict],
                                  top_n: int = 15) -> dict:
    """
    Aggregate function timing data across all summary records.

    Each summary contains a "top_functions_by_total_time" list with stats
    that are CUMULATIVE since startup. So the LAST summary has the most
    complete picture of total time spent in each function.

    We also analyze outliers separately — each outlier is one slow call
    with a timestamp, useful for time-clustering.

    Returns dict with:
        top_by_cumulative_time:  list of dicts, biggest time consumers
        top_by_worst_p99:        list of dicts, latency outliers
        outliers_by_function:    dict {func_name: count}
        outliers_total:          int
    """
    summaries = filter_events_by_type(events, "summary")
    outliers  = filter_events_by_type(events, "outlier")

    result = {
        "top_by_cumulative_time": [],
        "top_by_worst_p99":       [],
        "outliers_by_function":   {},
        "outliers_total":         len(outliers),
    }

    if summaries:
        last_summary = summaries[-1]

        top_total = last_summary.get("top_functions_by_total_time", [])
        result["top_by_cumulative_time"] = top_total[:top_n]

        # For p99, we want functions with the WORST single-call max
        # across the whole session, not just the last summary's window.
        # Best approximation from summary data alone: track the highest
        # recent_max_ms seen for each function across all summaries.
        worst_max_by_fn: dict[str, dict] = {}
        for s in summaries:
            for fn in s.get("top_functions_by_p99", []):
                name = fn["name"]
                current_max = fn.get("recent_max_ms", 0)
                if name not in worst_max_by_fn or current_max > worst_max_by_fn[name]["recent_max_ms"]:
                    worst_max_by_fn[name] = dict(fn)

        # Sort by recent_max_ms descending
        sorted_worst = sorted(
            worst_max_by_fn.values(),
            key=lambda x: x.get("recent_max_ms", 0),
            reverse=True,
        )
        result["top_by_worst_p99"] = sorted_worst[:top_n]

    # Count outliers per function
    outlier_counts: dict[str, int] = Counter()
    for o in outliers:
        fn = o.get("function", "?")
        outlier_counts[fn] += 1
    result["outliers_by_function"] = dict(outlier_counts.most_common(top_n))

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  OSC TRAFFIC ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_osc_traffic(events: list[dict], top_n: int = 10) -> dict:
    """
    Aggregate OSC traffic patterns across the session.

    The last summary's totals represent the entire session (since the
    underlying tracker is cumulative). Per-address rate history is in
    the summary records.

    Returns dict with:
        total_sends, total_receives, total_send_bytes, total_recv_bytes
        top_senders:     list of address+stats dicts
        top_receivers:   list of address+stats dicts
        peak_send_rate:  highest send rate seen + when
        peak_recv_rate:  highest recv rate seen + when
        unique_send_addresses, unique_recv_addresses
    """
    summaries = filter_events_by_type(events, "summary")
    if not summaries:
        return {"empty": True}

    last = summaries[-1]
    last_osc = last.get("osc", {})

    result = {
        "total_sends":            last_osc.get("total_sends", 0),
        "total_receives":         last_osc.get("total_receives", 0),
        "total_send_bytes":       last_osc.get("total_send_bytes", 0),
        "total_recv_bytes":       last_osc.get("total_recv_bytes", 0),
        "unique_send_addresses":  last_osc.get("unique_send_addresses", 0),
        "unique_recv_addresses":  last_osc.get("unique_recv_addresses", 0),
        "top_senders":            last.get("osc_top_senders", [])[:top_n],
        "top_receivers":          last.get("osc_top_receivers", [])[:top_n],
    }

    # Find peak rates across all summaries
    peak_send_rate = 0.0
    peak_send_at = 0.0
    peak_recv_rate = 0.0
    peak_recv_at = 0.0

    for s in summaries:
        osc = s.get("osc", {})
        srate = osc.get("send_rate_per_sec", 0)
        rrate = osc.get("recv_rate_per_sec", 0)
        if srate > peak_send_rate:
            peak_send_rate = srate
            peak_send_at = s.get("timestamp", 0)
        if rrate > peak_recv_rate:
            peak_recv_rate = rrate
            peak_recv_at = s.get("timestamp", 0)

    result["peak_send_rate"] = peak_send_rate
    result["peak_send_at"]   = peak_send_at
    result["peak_recv_rate"] = peak_recv_rate
    result["peak_recv_at"]   = peak_recv_at

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  SYSTEM RESOURCE ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_system_resources(events: list[dict]) -> dict:
    """
    Track CPU/RAM trajectory across the session.

    Computes min/avg/max/p95 of CPU and memory across all summaries,
    plus growth rate (MB per minute) for memory.

    Returns dict with:
        cpu_min, cpu_avg, cpu_max, cpu_p95
        memory_min, memory_max, memory_growth_total, memory_growth_per_min
        thread_count_min, thread_count_max
        psutil_available
    """
    summaries = filter_events_by_type(events, "summary")
    if not summaries:
        return {"empty": True}

    cpu_samples = []
    mem_samples = []
    thread_samples = []

    for s in summaries:
        sys_data = s.get("system", {})
        if sys_data.get("psutil_available"):
            cpu = sys_data.get("avg_cpu_percent", -1)
            mem = sys_data.get("avg_memory_mb", -1)
            if cpu >= 0:
                cpu_samples.append(cpu)
            if mem >= 0:
                mem_samples.append(mem)
        tc = sys_data.get("avg_thread_count", 0)
        if tc > 0:
            thread_samples.append(tc)

    if not cpu_samples and not mem_samples:
        return {"empty": True, "psutil_available": False}

    result = {
        "psutil_available": True,
        "sample_count":     len(summaries),
    }

    if cpu_samples:
        cpu_sorted = sorted(cpu_samples)
        result["cpu_min"] = cpu_sorted[0]
        result["cpu_avg"] = sum(cpu_samples) / len(cpu_samples)
        result["cpu_max"] = cpu_sorted[-1]
        result["cpu_p95"] = cpu_sorted[min(len(cpu_sorted) - 1, int(len(cpu_sorted) * 0.95))]

    if mem_samples:
        result["memory_min"] = min(mem_samples)
        result["memory_max"] = max(mem_samples)
        # Growth: last reading minus first reading
        result["memory_growth_total"] = mem_samples[-1] - mem_samples[0]
        # Rate: total growth divided by session duration in minutes
        first_ts = summaries[0].get("timestamp", 0)
        last_ts  = summaries[-1].get("timestamp", 0)
        duration_min = (last_ts - first_ts) / 60.0 if last_ts > first_ts else 1.0
        result["memory_growth_per_min"] = result["memory_growth_total"] / duration_min

    if thread_samples:
        result["thread_count_min"] = min(thread_samples)
        result["thread_count_max"] = max(thread_samples)

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  EVENT COUNTER ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_counters(events: list[dict]) -> dict:
    """
    Get final counter totals from the last summary.
    Returns: {counter_name: {total, rate_per_min, ...}}
    """
    summaries = filter_events_by_type(events, "summary")
    if not summaries:
        return {}

    last = summaries[-1]
    counters_list = last.get("counters", [])

    result = {}
    for c in counters_list:
        result[c["name"]] = {
            "total":         c.get("total", 0),
            "rate_per_min":  c.get("rate_per_min", 0),
            "rate_per_sec":  c.get("rate_per_sec", 0),
        }

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  WARNINGS ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_warnings(events: list[dict]) -> dict:
    """
    Aggregate all warnings across the session.

    Counts how often each warning text appeared (after stripping the
    variable portion like specific numbers). Provides "warning fingerprint"
    grouping so you can see if the same problem fired 100 times vs once.

    Returns dict with:
        total_warnings:          int
        warnings_by_summary:     list[(timestamp, warning_count)]
        most_common_warnings:    list[(fingerprint, count)]
        full_warning_log:        list[(timestamp, warning_text)]
    """
    summaries = filter_events_by_type(events, "summary")

    full_log = []
    warning_counts: Counter = Counter()
    warnings_per_summary = []

    for s in summaries:
        ts = s.get("timestamp", 0)
        warnings = s.get("warnings", [])
        warnings_per_summary.append((ts, len(warnings)))
        for w in warnings:
            full_log.append((ts, w))
            # Fingerprint: collapse variable numbers to make grouping work
            # e.g. "CPU avg 12.3% > threshold 25.0%" → "CPU avg X% > threshold X%"
            fingerprint = _fingerprint_warning(w)
            warning_counts[fingerprint] += 1

    return {
        "total_warnings":         len(full_log),
        "warnings_by_summary":    warnings_per_summary,
        "most_common_warnings":   warning_counts.most_common(20),
        "full_warning_log":       full_log,
    }


def _fingerprint_warning(text: str) -> str:
    """
    Collapse numeric variations in a warning string so similar warnings
    group together.

    "CPU avg 12.3% > threshold 25.0%" → "CPU avg X% > threshold X%"
    "Thread 'ui' missing 12.5%..."    → "Thread 'X' missing X%..."
    """
    import re
    # Replace numbers (incl decimals and signs) with X
    text = re.sub(r"[-+]?\d+\.?\d*", "X", text)
    # Replace quoted strings with 'X'
    text = re.sub(r"'[^']*'", "'X'", text)
    return text


# ═══════════════════════════════════════════════════════════════════════════
#  THREAD HEALTH ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════

def analyze_thread_health(events: list[dict]) -> dict:
    """
    Per-thread health stats across the session.

    For each thread, computes:
      - Average actual_hz across all summaries
      - Worst (lowest) actual_hz seen and when
      - Percentage of summaries where the thread was unhealthy
      - Whether the thread was ever stalled (no ticks for >5s)
    """
    summaries = filter_events_by_type(events, "summary")
    if not summaries:
        return {}

    # Group per-thread observations
    per_thread: dict[str, dict] = defaultdict(lambda: {
        "target_hz":         0,
        "actual_hz_samples": [],
        "worst_hz":          None,
        "worst_hz_at":       0,
        "unhealthy_periods": 0,
        "total_periods":     0,
        "was_stalled":       False,
    })

    for s in summaries:
        threads = s.get("threads", [])
        for t in threads:
            name = t["name"]
            entry = per_thread[name]
            entry["target_hz"] = t.get("target_hz", 0)
            entry["total_periods"] += 1

            hz = t.get("actual_hz", 0)
            if hz > 0:
                entry["actual_hz_samples"].append(hz)
                if entry["worst_hz"] is None or hz < entry["worst_hz"]:
                    entry["worst_hz"] = hz
                    entry["worst_hz_at"] = s.get("timestamp", 0)

            # If the thread was in unhealthy_threads this period, count it
            for u in s.get("unhealthy_threads", []):
                if u["name"] == name:
                    entry["unhealthy_periods"] += 1
                    break

            # Stall check
            for st in s.get("stalled_threads", []):
                if st["name"] == name:
                    entry["was_stalled"] = True
                    break

    # Compute summary stats
    result = {}
    for name, entry in per_thread.items():
        samples = entry["actual_hz_samples"]
        avg_hz = sum(samples) / len(samples) if samples else 0
        unhealthy_pct = (entry["unhealthy_periods"] / entry["total_periods"]) * 100 if entry["total_periods"] > 0 else 0

        result[name] = {
            "target_hz":           entry["target_hz"],
            "avg_actual_hz":       avg_hz,
            "worst_actual_hz":     entry["worst_hz"],
            "worst_actual_hz_at":  entry["worst_hz_at"],
            "unhealthy_periods":   entry["unhealthy_periods"],
            "total_periods":       entry["total_periods"],
            "unhealthy_pct":       unhealthy_pct,
            "was_stalled":         entry["was_stalled"],
        }

    return result


# ═══════════════════════════════════════════════════════════════════════════
#  COMPLETE ANALYSIS REPORT
# ═══════════════════════════════════════════════════════════════════════════

def analyze_full_session(jsonl_path: Path,
                          include_rotated: bool = True) -> dict:
    """
    One-call complete analysis. Returns everything in a single dict
    that the CLI tool can format for display.

    Args:
        jsonl_path: path to the .jsonl file
        include_rotated: also load .jsonl.1, .jsonl.2 etc. for full history

    Returns:
        Master dict containing all sub-analyses.
    """
    if include_rotated:
        events = load_all_rotated_files(jsonl_path)
    else:
        events = load_jsonl_file(jsonl_path)

    return {
        "events_loaded":      len(events),
        "source_file":        str(jsonl_path),
        "included_rotated":   include_rotated,
        "session":            analyze_session(events),
        "function_perf":      analyze_function_performance(events),
        "osc_traffic":        analyze_osc_traffic(events),
        "system_resources":   analyze_system_resources(events),
        "counters":           analyze_counters(events),
        "warnings":           analyze_warnings(events),
        "thread_health":      analyze_thread_health(events),
    }