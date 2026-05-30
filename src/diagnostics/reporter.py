"""
================================================================================
  src/diagnostics/reporter.py — Diagnostics Log Writer
================================================================================
  Periodically writes human-readable summary blocks to a text log file
  and machine-readable per-event records to a JSONL file.

  Two outputs, two purposes:

    1. Text log (logs/diagnostics.log)
       Periodic summary blocks every cfg.DIAG_SUMMARY_INTERVAL_S seconds.
       Designed for humans to skim during/after a session.

    2. JSONL log (logs/diagnostics.jsonl)
       One JSON object per line. Every summary snapshot writes a record;
       outliers and warnings also write individual records. Designed for
       post-session analysis with pandas / Excel / custom tools.

  Why direct file writes instead of Python's logging module:
    Earlier versions used logging.getLogger() + RotatingFileHandler. This
    caused multi-write duplication when logger handlers accumulated across
    process lifetimes or when Unicode multi-line messages got fragmented.
    Direct file writes give us complete control: one write call = one
    block in the file. No formatter, no propagation, no handler stacking.

  Rotation:
    Both files rotate at 5 MB with 10 backups, manually managed (no
    dependency on logging.handlers.RotatingFileHandler).

  Background thread:
    A daemon thread named "diag.reporter" wakes every summary_interval_s,
    computes the summary, writes both formats, and goes back to sleep.

  Self-measurement:
    The reporter wraps its own work in diag.time_diag_overhead() so the
    diag_overhead_ns counter reflects reporter cost too.

  Shutdown:
    stop() sets an event flag. The thread checks it on each sleep wake.
    Reporter writes one final summary on shutdown via write_final_summary().
================================================================================
"""

import time
import threading
import json
from pathlib import Path
from typing import Optional

from src.config_loader import cfg
from src.diagnostics import diag


# ═══════════════════════════════════════════════════════════════════════════
#  PATH HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_path(path_str: str) -> Path:
    """
    Resolve a possibly-relative path against the project base dir.
    Handles both script mode and PyInstaller frozen mode.
    """
    import sys
    p = Path(path_str)
    if p.is_absolute():
        return p

    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        # diagnostics/reporter.py → diagnostics → src → project_root
        base = Path(__file__).resolve().parent.parent.parent

    return base / p


# ═══════════════════════════════════════════════════════════════════════════
#  REPORTER
# ═══════════════════════════════════════════════════════════════════════════

class Reporter:
    """
    Writes summary blocks to text log and per-event records to JSONL log.

    Both outputs use direct file handles (no Python logging module). This
    eliminates handler-stacking duplication that occurred when the
    diagnostics layer was re-installed across multiple process lifetimes
    or when multi-line Unicode messages were fragmented by formatters.

    Public API:
        start()                  — begin background reporting thread
        stop()                   — signal thread to exit + write final summary
        write_summary_now()      — write one summary immediately (sync)
        write_final_summary()    — write shutdown summary (called by stop())
        write_jsonl_event(...)   — log one arbitrary event to JSONL
        close()                  — flush + close file handles
    """

    def __init__(self,
                 log_path: str,
                 jsonl_path: str,
                 summary_interval_s: float = 10.0):
        self._log_path           = _resolve_path(log_path)
        self._jsonl_path         = _resolve_path(jsonl_path)
        self._summary_interval_s = summary_interval_s

        # Ensure parent directories exist
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)

        # ── Text log: direct file handle with manual rotation ────────────
        # Lock guards all writes to the text file. We do NOT use the
        # Python logging module because earlier versions caused multi-write
        # duplication issues with our multi-line Unicode summary blocks.
        self._text_lock   = threading.Lock()
        self._text_handle = None
        self._open_text_log()

        # ── JSONL: direct file handle, same approach ─────────────────────
        self._jsonl_lock   = threading.Lock()
        self._jsonl_handle = None
        self._open_jsonl()

        # Track outlier dump timestamps so we can compute deltas
        # between summary blocks.
        self._last_summary_at: float = 0.0

        # Threading
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ─── Setup ──────────────────────────────────────────────────────────

    def _open_text_log(self):
        """
        Open the text log for appending in line-buffered mode.

        Rotates the file first if it already exceeds 5 MB. Line-buffered
        mode (buffering=1) means writes flush to disk on each newline,
        which makes the log usable for live tail-style monitoring during
        a session without needing explicit flush() calls.
        """
        try:
            if self._log_path.exists() and self._log_path.stat().st_size > 5 * 1024 * 1024:
                self._rotate_text_log()
            self._text_handle = open(
                self._log_path, "a", encoding="utf-8", buffering=1
            )
        except Exception as e:
            print(f"[diag.reporter] cannot open text log file: {e}")
            self._text_handle = None

    def _rotate_text_log(self):
        """
        Rotate text log: rename current to .1, shift older backups up,
        delete the oldest if we have more than 10 backups.

        Naming: diagnostics.log → diagnostics.log.1 → diagnostics.log.2 etc.
        """
        try:
            max_backups = 10
            for i in range(max_backups - 1, 0, -1):
                src = self._log_path.with_suffix(self._log_path.suffix + f".{i}")
                dst = self._log_path.with_suffix(self._log_path.suffix + f".{i+1}")
                if src.exists():
                    try:
                        if dst.exists():
                            dst.unlink()
                        src.rename(dst)
                    except Exception:
                        pass
            new_first = self._log_path.with_suffix(self._log_path.suffix + ".1")
            if new_first.exists():
                new_first.unlink()
            self._log_path.rename(new_first)
        except Exception as e:
            print(f"[diag.reporter] text log rotation failed: {e}")

    def _open_jsonl(self):
        """Open the JSONL file for appending. Rotates if too large."""
        try:
            if self._jsonl_path.exists() and self._jsonl_path.stat().st_size > 5 * 1024 * 1024:
                self._rotate_jsonl()
            # Line-buffered append mode
            self._jsonl_handle = open(
                self._jsonl_path, "a", encoding="utf-8", buffering=1
            )
        except Exception as e:
            print(f"[diag.reporter] cannot open JSONL file: {e}")
            self._jsonl_handle = None

    def _rotate_jsonl(self):
        """Rotate the JSONL file: rename current to .1, shift others up."""
        try:
            max_backups = 10
            for i in range(max_backups - 1, 0, -1):
                src = self._jsonl_path.with_suffix(self._jsonl_path.suffix + f".{i}")
                dst = self._jsonl_path.with_suffix(self._jsonl_path.suffix + f".{i+1}")
                if src.exists():
                    try:
                        if dst.exists():
                            dst.unlink()
                        src.rename(dst)
                    except Exception:
                        pass
            new_first = self._jsonl_path.with_suffix(self._jsonl_path.suffix + ".1")
            if new_first.exists():
                new_first.unlink()
            self._jsonl_path.rename(new_first)
        except Exception as e:
            print(f"[diag.reporter] JSONL rotation failed: {e}")

    # ─── Direct write helpers ───────────────────────────────────────────

    def _write_text(self, text: str):
        """
        Write a string directly to the text log file.

        Thread-safe via _text_lock. Appends a trailing newline if absent
        so consecutive _write_text calls don't run together on one line.

        Checks file size after each write and rotates if needed. Rotation
        is cheap (one stat() call) compared to the write itself.

        If the text handle is None (e.g. file couldn't be opened at startup
        or was closed by shutdown), silently no-ops rather than raising.
        """
        if self._text_handle is None:
            return
        try:
            with self._text_lock:
                # Re-check inside the lock — handle may have been closed
                # by another thread between the outer check and acquisition
                if self._text_handle is None:
                    return
                self._text_handle.write(text)
                if not text.endswith("\n"):
                    self._text_handle.write("\n")

                # Rotation check: if file grew past limit, rotate + reopen
                if self._log_path.exists():
                    try:
                        size = self._log_path.stat().st_size
                        if size > 5 * 1024 * 1024:
                            try:
                                self._text_handle.close()
                            except Exception:
                                pass
                            self._rotate_text_log()
                            # Re-open will reassign self._text_handle
                            self._text_handle = open(
                                self._log_path, "a", encoding="utf-8", buffering=1
                            )
                    except Exception:
                        pass
        except Exception as e:
            print(f"[diag.reporter] text log write failed: {e}")

    # ─── Lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Start the periodic summary thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="diag.reporter", daemon=True
        )
        self._thread.start()

        # Write a startup banner immediately
        self._write_startup_banner()

    def stop(self):
        """Signal thread to exit. Final summary is written by close()."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._summary_interval_s * 2.0)
            self._thread = None

    def close(self):
        """Close file handles. Idempotent."""
        with self._jsonl_lock:
            if self._jsonl_handle is not None:
                try:
                    self._jsonl_handle.flush()
                    self._jsonl_handle.close()
                except Exception:
                    pass
                self._jsonl_handle = None

        with self._text_lock:
            if self._text_handle is not None:
                try:
                    self._text_handle.flush()
                    self._text_handle.close()
                except Exception:
                    pass
                self._text_handle = None

    # ─── Main loop ──────────────────────────────────────────────────────

    def _run(self):
        """Periodic summary loop."""
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self._summary_interval_s):
                break
            try:
                with diag.time_diag_overhead():
                    self.write_summary_now()
            except Exception as e:
                # Never let reporter crash kill the thread
                try:
                    self._write_text(f"[diag.reporter] summary write failed: {e}")
                except Exception:
                    pass

    # ─── Summary writing ────────────────────────────────────────────────

    def _write_startup_banner(self):
        """Write a banner to the text log when reporting starts."""
        import datetime
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        banner = (
            "\n" + "═" * 70 + "\n"
            f"  DIAGNOSTICS SESSION STARTED — {ts}\n"
            + "═" * 70 + "\n"
            f"  Summary interval : {self._summary_interval_s}s\n"
            f"  Log file         : {self._log_path}\n"
            f"  JSONL file       : {self._jsonl_path}\n"
            + "═" * 70
        )
        self._write_text(banner)

        # Also write a startup record to JSONL
        try:
            from src.diagnostics.installer import get_install_summary
            install_info = get_install_summary()
        except Exception:
            install_info = {}

        self.write_jsonl_event({
            "type": "session_start",
            "timestamp": time.time(),
            "summary_interval_s": self._summary_interval_s,
            "install_summary": install_info,
        })

    def write_summary_now(self):
        """
        Compute and write one full summary block.

        Writes BOTH text (formatted) and JSONL (raw) versions.
        Safe to call from any thread.
        """
        now = time.time()
        snapshot = self._collect_snapshot(now)

        text = self._format_text_summary(snapshot)
        self._write_text(text)

        try:
            self.write_jsonl_event({"type": "summary", **snapshot})
        except Exception as e:
            print(f"[diag.reporter] JSONL write failed: {e}")

        # Increment our own counter
        try:
            if diag.counters is not None:
                diag.counters.increment("diag_summary_written")
        except Exception:
            pass

        # Also drain and log any outliers
        self._log_outliers()

        self._last_summary_at = now

    def write_final_summary(self):
        """Write a shutdown summary block."""
        import datetime
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            self.write_summary_now()
            uptime_s = (time.perf_counter() - diag.uptime_start) if diag.uptime_start else 0
            footer = (
                "\n" + "═" * 70 + "\n"
                f"  DIAGNOSTICS SESSION ENDED — {ts}\n"
                f"  Total uptime: {self._fmt_uptime(uptime_s)}\n"
                f"  Diagnostics overhead: {diag.diag_overhead_ns / 1_000_000:.1f} ms total\n"
                + "═" * 70 + "\n"
            )
            self._write_text(footer)

            self.write_jsonl_event({
                "type": "session_end",
                "timestamp": time.time(),
                "uptime_s": uptime_s,
                "overhead_ns_total": diag.diag_overhead_ns,
            })
        except Exception as e:
            print(f"[diag.reporter] final summary failed: {e}")

    # ─── Snapshot collection ────────────────────────────────────────────

    def _collect_snapshot(self, now: float) -> dict:
        """
        Gather a complete diagnostic snapshot from all collectors.
        Returns a dict suitable for both text formatting and JSONL serialization.
        """
        uptime_s = (time.perf_counter() - diag.uptime_start) if diag.uptime_start else 0

        snapshot = {
            "timestamp": now,
            "uptime_s": uptime_s,
            "diag_overhead_ms": diag.diag_overhead_ns / 1_000_000.0,
        }

        # System sampler data
        if diag.sampler is not None:
            try:
                avg = diag.sampler.get_avg(window_s=self._summary_interval_s)
                snapshot["system"] = {
                    "psutil_available": diag.sampler.is_psutil_available(),
                    "samples_in_window": avg["samples_in_window"],
                    "avg_cpu_percent": avg["avg_cpu_percent"],
                    "peak_cpu_percent": avg["peak_cpu_percent"],
                    "avg_memory_mb": avg["avg_memory_mb"],
                    "peak_memory_mb": avg["peak_memory_mb"],
                    "memory_growth_mb": diag.sampler.get_growth_mb(),
                    "avg_thread_count": avg["avg_thread_count"],
                    "max_thread_count": avg["max_thread_count"],
                }
                latest = diag.sampler.latest_sample()
                if latest:
                    snapshot["system"]["latest_gc_collections"] = latest.gc_collections
                    snapshot["system"]["latest_open_fds"] = latest.open_fds
            except Exception as e:
                snapshot["system_error"] = str(e)

        # Thread health
        if diag.thread_health is not None:
            try:
                snapshot["threads"] = diag.thread_health.get_all()
                snapshot["unhealthy_threads"] = diag.thread_health.get_unhealthy(
                    miss_threshold=cfg.DIAG_WARN_THREAD_MISS_FRAC
                )
                snapshot["stalled_threads"] = diag.thread_health.get_stalled(
                    stall_threshold_s=5.0
                )
            except Exception as e:
                snapshot["threads_error"] = str(e)

        # Profiler top 10
        if diag.profiler is not None:
            try:
                snapshot["top_functions_by_total_time"] = diag.profiler.get_top_n_by_total_time(10)
                snapshot["top_functions_by_p99"] = diag.profiler.get_top_n_by_recent_p99(5)
                snapshot["tracked_function_count"] = diag.profiler.get_tracked_function_count()
            except Exception as e:
                snapshot["profiler_error"] = str(e)

        # OSC traffic
        if diag.osc_tracker is not None:
            try:
                snapshot["osc"] = diag.osc_tracker.get_global_summary()
                snapshot["osc_top_senders"] = diag.osc_tracker.get_top_n_senders(8)
                snapshot["osc_top_receivers"] = diag.osc_tracker.get_top_n_receivers(8)
            except Exception as e:
                snapshot["osc_error"] = str(e)

        # Counters (nonzero only for brevity)
        if diag.counters is not None:
            try:
                snapshot["counters"] = diag.counters.get_nonzero()
            except Exception as e:
                snapshot["counters_error"] = str(e)

        # Rate limiter
        if diag.rate_limiter is not None:
            try:
                snapshot["rate_limit_total_suppressed"] = diag.rate_limiter.get_total_suppressed()
                snapshot["rate_limits_simple"] = diag.rate_limiter.get_all_simple()
            except Exception as e:
                snapshot["rate_limit_error"] = str(e)

        # Warnings — compare against thresholds
        snapshot["warnings"] = self._compute_warnings(snapshot)

        return snapshot

    def _compute_warnings(self, snapshot: dict) -> list:
        """Generate a list of warning strings based on thresholds in cfg."""
        warnings = []

        # CPU
        sys_data = snapshot.get("system", {})
        if sys_data.get("avg_cpu_percent", -1) > cfg.DIAG_WARN_CPU_PERCENT:
            warnings.append(
                f"CPU avg {sys_data['avg_cpu_percent']:.1f}% > threshold {cfg.DIAG_WARN_CPU_PERCENT}%"
            )

        # Memory growth
        growth = sys_data.get("memory_growth_mb", 0)
        if growth > cfg.DIAG_WARN_MEMORY_GROWTH_MB:
            warnings.append(
                f"Memory growth {growth:.1f} MB > threshold {cfg.DIAG_WARN_MEMORY_GROWTH_MB} MB"
            )

        # OSC rates
        osc = snapshot.get("osc", {})
        if osc.get("send_rate_per_sec", 0) > cfg.DIAG_WARN_OSC_SEND_PER_SEC:
            warnings.append(
                f"OSC send rate {osc['send_rate_per_sec']:.0f}/s > "
                f"threshold {cfg.DIAG_WARN_OSC_SEND_PER_SEC}/s"
            )
        if osc.get("recv_rate_per_sec", 0) > cfg.DIAG_WARN_OSC_RECV_PER_SEC:
            warnings.append(
                f"OSC recv rate {osc['recv_rate_per_sec']:.0f}/s > "
                f"threshold {cfg.DIAG_WARN_OSC_RECV_PER_SEC}/s"
            )

        # Thread health
        for unhealthy in snapshot.get("unhealthy_threads", []):
            warnings.append(
                f"Thread '{unhealthy['name']}' missing {unhealthy['miss_fraction']*100:.1f}% "
                f"of expected ticks (target {unhealthy['target_hz']:.1f} Hz, "
                f"actual {unhealthy['actual_hz']:.1f} Hz)"
            )

        # Stalled threads
        for stalled in snapshot.get("stalled_threads", []):
            warnings.append(
                f"Thread '{stalled['name']}' STALLED — no tick for "
                f"{stalled['seconds_since_last']:.1f}s"
            )

        # Single slow calls
        for fn in snapshot.get("top_functions_by_p99", []):
            if fn["recent_max_ms"] > cfg.DIAG_WARN_SINGLE_CALL_MS:
                warnings.append(
                    f"Function {fn['name']} had a {fn['recent_max_ms']:.1f} ms call "
                    f"(> threshold {cfg.DIAG_WARN_SINGLE_CALL_MS} ms)"
                )

        # Clip event rate
        if diag.counters is not None:
            clip_rate = diag.counters.get_rate_per_min("clip_event")
            if clip_rate > cfg.DIAG_WARN_CLIP_RATE_PER_MIN:
                warnings.append(
                    f"Clip events {clip_rate:.1f}/min > "
                    f"threshold {cfg.DIAG_WARN_CLIP_RATE_PER_MIN}/min"
                )

        return warnings

    # ─── Outlier logging ────────────────────────────────────────────────

    def _log_outliers(self):
        """Drain profiler outliers and write each to JSONL."""
        if diag.profiler is None:
            return
        try:
            outliers = diag.profiler.drain_all_outliers()
            for func_name, samples in outliers.items():
                for ts, elapsed_ns in samples:
                    self.write_jsonl_event({
                        "type": "outlier",
                        "function": func_name,
                        "timestamp": ts,
                        "elapsed_ms": elapsed_ns / 1_000_000.0,
                    })
                    try:
                        if diag.counters is not None:
                            diag.counters.increment("diag_outlier_logged")
                    except Exception:
                        pass
        except Exception as e:
            print(f"[diag.reporter] outlier log failed: {e}")

    # ─── Text formatting ────────────────────────────────────────────────

    def _format_text_summary(self, snapshot: dict) -> str:
        """Render a snapshot dict as a human-readable text block."""
        import datetime

        ts_str = datetime.datetime.fromtimestamp(snapshot["timestamp"]).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        uptime_str = self._fmt_uptime(snapshot["uptime_s"])

        lines = [
            "",
            "═" * 70,
            f"  DIAGNOSTICS SUMMARY — {ts_str}  (uptime {uptime_str})",
            "═" * 70,
        ]

        # SYSTEM section
        sys_data = snapshot.get("system", {})
        if sys_data:
            lines.append("")
            lines.append("SYSTEM")
            if sys_data.get("psutil_available"):
                lines.append(
                    f"  CPU%   : avg {sys_data['avg_cpu_percent']:5.1f}  "
                    f"peak {sys_data['peak_cpu_percent']:5.1f}  "
                    f"(threshold {cfg.DIAG_WARN_CPU_PERCENT:.0f}%)"
                )
                lines.append(
                    f"  RAM    : {sys_data['avg_memory_mb']:6.1f} MB  "
                    f"peak {sys_data['peak_memory_mb']:6.1f} MB  "
                    f"delta {sys_data['memory_growth_mb']:+6.1f} MB since startup"
                )
            else:
                lines.append("  CPU/RAM: not available (psutil not installed)")
            lines.append(
                f"  Threads: {sys_data['avg_thread_count']} avg, "
                f"{sys_data['max_thread_count']} peak"
            )
            if sys_data.get("latest_open_fds", -1) > 0:
                lines.append(f"  FDs    : {sys_data['latest_open_fds']}")

        # THREADS section
        threads = snapshot.get("threads", [])
        if threads:
            lines.append("")
            lines.append("THREAD HEALTH")
            for t in threads:
                if t["target_hz"] > 0:
                    health = "✓" if t["miss_fraction"] < cfg.DIAG_WARN_THREAD_MISS_FRAC else "⚠"
                    miss_pct = t["miss_fraction"] * 100
                    lines.append(
                        f"  {health} {t['name']:12} : "
                        f"{t['actual_hz']:6.1f} Hz / target {t['target_hz']:6.1f} Hz  "
                        f"({miss_pct:5.1f}% missed)"
                    )
                else:
                    lines.append(
                        f"    {t['name']:12} : {t['actual_hz']:6.1f} Hz  (no target)"
                    )

        # TOP FUNCTIONS section
        top_total = snapshot.get("top_functions_by_total_time", [])
        if top_total:
            lines.append("")
            lines.append("TOP FUNCTIONS BY TOTAL TIME")
            lines.append("  " + "─" * 64)
            lines.append(
                f"  {'function':38} {'calls':>7} {'total':>9} {'avg':>7} {'p99':>7}"
            )
            for fn in top_total:
                if fn["count"] == 0:
                    continue
                lines.append(
                    f"  {fn['name'][-38:]:38} "
                    f"{fn['count']:7d} "
                    f"{fn['total_ms']:8.1f}ms "
                    f"{fn['avg_ms']:6.2f}ms "
                    f"{fn['recent_p99_ms']:6.2f}ms"
                )

        # OSC TRAFFIC section
        osc = snapshot.get("osc", {})
        if osc:
            lines.append("")
            lines.append(f"OSC TRAFFIC (window {osc.get('window_s', 0):.1f}s)")
            lines.append(
                f"  Outbound: {osc.get('send_rate_per_sec', 0):6.1f} msg/s  "
                f"({osc.get('total_sends', 0)} total, "
                f"{osc.get('unique_send_addresses', 0)} unique addresses)"
            )
            lines.append(
                f"  Inbound : {osc.get('recv_rate_per_sec', 0):6.1f} msg/s  "
                f"({osc.get('total_receives', 0)} total, "
                f"{osc.get('unique_recv_addresses', 0)} unique addresses)"
            )

            top_send = snapshot.get("osc_top_senders", [])
            if top_send:
                lines.append("  Top outbound:")
                for s in top_send[:5]:
                    lines.append(
                        f"    {s['address'][:48]:48} "
                        f"{s['rate_per_sec']:6.1f}/s  ({s['count_total']} total)"
                    )

            top_recv = snapshot.get("osc_top_receivers", [])
            if top_recv:
                lines.append("  Top inbound:")
                for s in top_recv[:5]:
                    lines.append(
                        f"    {s['address'][:48]:48} "
                        f"{s['rate_per_sec']:6.1f}/s  ({s['count_total']} total)"
                    )

        # COUNTERS section
        counters = snapshot.get("counters", [])
        if counters:
            lines.append("")
            lines.append("EVENT COUNTERS (non-zero, last 60s rate)")
            for c in counters[:15]:
                lines.append(
                    f"  {c['name'][:40]:40} {int(c['total']):6d}  "
                    f"({c['rate_per_min']:5.1f}/min)"
                )

        # RATE LIMITER section
        if snapshot.get("rate_limit_total_suppressed", 0) > 0:
            lines.append("")
            lines.append(
                f"RATE LIMITING: {snapshot['rate_limit_total_suppressed']} "
                f"event(s) suppressed total"
            )

        # WARNINGS section
        warnings = snapshot.get("warnings", [])
        if warnings:
            lines.append("")
            lines.append("⚠ WARNINGS THIS PERIOD")
            for w in warnings:
                lines.append(f"  ⚠ {w}")
        else:
            lines.append("")
            lines.append("✓ No warnings this period")

        # FOOTER
        overhead_ms = snapshot.get("diag_overhead_ms", 0)
        lines.append("")
        lines.append(
            f"  Diagnostics overhead so far: {overhead_ms:.1f} ms cumulative"
        )
        lines.append("═" * 70)

        return "\n".join(lines)

    @staticmethod
    def _fmt_uptime(seconds: float) -> str:
        """Format seconds as 'Xh Ym Zs' or 'Ym Zs' or 'Zs'."""
        s = int(seconds)
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        if h > 0:
            return f"{h}h {m}m {sec}s"
        if m > 0:
            return f"{m}m {sec}s"
        return f"{sec}s"

    # ─── JSONL writing ──────────────────────────────────────────────────

    def write_jsonl_event(self, event: dict):
        """
        Write one event to the JSONL log.

        Each event is a JSON object on its own line. The 'type' field
        identifies the event kind (summary, outlier, session_start, etc.).
        Safe to call from any thread.
        """
        if self._jsonl_handle is None:
            return

        try:
            if cfg.DIAG_JSONL_FORMAT == "pretty":
                line = json.dumps(event, indent=2, default=str)
            else:
                line = json.dumps(event, default=str)

            with self._jsonl_lock:
                if self._jsonl_handle is not None:
                    self._jsonl_handle.write(line + "\n")
                    # Rotation check periodically
                    if event.get("type") == "summary":
                        if self._jsonl_path.exists():
                            size = self._jsonl_path.stat().st_size
                            if size > 5 * 1024 * 1024:
                                self._jsonl_handle.close()
                                self._rotate_jsonl()
                                self._open_jsonl()
        except Exception as e:
            print(f"[diag.reporter] JSONL event write failed: {e}")