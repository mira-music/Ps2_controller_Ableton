"""
================================================================================
  src/diagnostics/profiler.py — Function Timing Stats Collector
================================================================================
  Records per-function timing samples and computes statistics over rolling
  windows. The installer (installer.py) wraps target functions with timing
  shims that call profiler.record(name, elapsed_ns) on every invocation.

  Storage strategy:
    For each function we maintain TWO views of the data:

    1. ROLLING WINDOW (last N samples, default 1000)
       Used to compute mean, median, p95, p99 over recent activity.
       Bounded memory — newest sample replaces oldest when full.

    2. CUMULATIVE COUNTERS (total since startup)
       call_count, total_ns, max_ns, max_ns_at (timestamp of slowest call)
       Constant memory regardless of session length.

  The dual-view design means we get both "recent performance" (rolling
  percentiles) and "session totals" (cumulative time / hot path identification)
  with bounded memory.

  Thread safety:
    All public methods are thread-safe via an internal RLock. The lock is
    held briefly — only long enough to copy a value or append to a deque.
    Statistical computations (sorted, percentile) happen on local copies
    made under the lock.

  Outlier tracking:
    Any call exceeding cfg.DIAG_SLOW_FUNCTION_MS gets added to a separate
    outlier deque (last 100). These are dumped to the JSONL log as they
    happen and summarized in the text report.

  No-op when diagnostics disabled:
    The profiler is created by the installer only when DIAG_ENABLED is True.
    The public diag.record_function_time() helper in __init__.py short-
    circuits when diagnostics is off, so this class is never even
    instantiated unless needed.
================================================================================
"""

import time
import threading
import statistics
from collections import deque
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  PER-FUNCTION STATS CONTAINER
# ═══════════════════════════════════════════════════════════════════════════

class _FunctionStats:
    """
    Holds all timing data for one tracked function.

    Memory bounded: rolling window is fixed-size deque (~8 KB per function
    at default 1000-sample window).

    All methods assume the caller holds the parent Profiler's lock.
    """

    __slots__ = (
        "name",
        "call_count",
        "total_ns",
        "max_ns",
        "max_ns_at",
        "rolling_samples",
        "outliers",
        "_window_size",
    )

    def __init__(self, name: str, window_size: int = 1000):
        self.name = name
        self.call_count = 0
        self.total_ns = 0
        self.max_ns = 0
        self.max_ns_at = 0.0   # time.time() of slowest call

        # Bounded rolling window of recent samples (newest at the right)
        self.rolling_samples: deque[int] = deque(maxlen=window_size)

        # Outlier log: (timestamp, elapsed_ns) for calls exceeding threshold
        # Bounded so we don't accumulate forever during a long session
        self.outliers: deque[tuple[float, int]] = deque(maxlen=100)

        self._window_size = window_size

    def add_sample(self, elapsed_ns: int, now: float, outlier_threshold_ns: int):
        """Record one timing sample."""
        self.call_count += 1
        self.total_ns += elapsed_ns
        self.rolling_samples.append(elapsed_ns)

        if elapsed_ns > self.max_ns:
            self.max_ns = elapsed_ns
            self.max_ns_at = now

        if elapsed_ns >= outlier_threshold_ns:
            self.outliers.append((now, elapsed_ns))

    def compute_stats(self) -> dict:
        """
        Compute summary statistics from rolling window.

        Returns a dict with:
            count, total_ms, avg_ms, max_ms,
            median_ms, p95_ms, p99_ms,
            recent_count (samples in window), outlier_count
        """
        recent = list(self.rolling_samples)
        recent_count = len(recent)

        result = {
            "name":           self.name,
            "count":          self.call_count,
            "total_ms":       self.total_ns / 1_000_000.0,
            "avg_ms":         (self.total_ns / self.call_count / 1_000_000.0) if self.call_count else 0.0,
            "max_ms":         self.max_ns / 1_000_000.0,
            "max_ms_at":      self.max_ns_at,
            "recent_count":   recent_count,
            "outlier_count":  len(self.outliers),
        }

        if recent_count > 0:
            recent_sorted = sorted(recent)
            result["recent_avg_ms"]    = (sum(recent) / recent_count) / 1_000_000.0
            result["recent_median_ms"] = recent_sorted[recent_count // 2] / 1_000_000.0
            result["recent_p95_ms"]    = recent_sorted[min(recent_count - 1, int(recent_count * 0.95))] / 1_000_000.0
            result["recent_p99_ms"]    = recent_sorted[min(recent_count - 1, int(recent_count * 0.99))] / 1_000_000.0
            result["recent_max_ms"]    = recent_sorted[-1] / 1_000_000.0
        else:
            result["recent_avg_ms"]    = 0.0
            result["recent_median_ms"] = 0.0
            result["recent_p95_ms"]    = 0.0
            result["recent_p99_ms"]    = 0.0
            result["recent_max_ms"]    = 0.0

        return result

    def drain_outliers(self) -> list:
        """
        Return all outliers and clear the deque.
        Called by the reporter to log outliers since last summary.
        """
        out = list(self.outliers)
        self.outliers.clear()
        return out


# ═══════════════════════════════════════════════════════════════════════════
#  PROFILER (the public collector)
# ═══════════════════════════════════════════════════════════════════════════

class Profiler:
    """
    Collects timing data for arbitrarily many functions.

    Public methods are thread-safe. Internal state is protected by a single
    RLock; lock hold time per call is sub-microsecond (just a deque append).

    Usage:
        profiler = Profiler()
        # ... wrap target functions with shims that call profiler.record(...)

        # Periodically:
        stats = profiler.get_all_stats()
        outliers = profiler.drain_all_outliers()
    """

    def __init__(self, window_size: int = 1000):
        """
        Args:
            window_size: how many recent samples to keep per function
                         for percentile calculations. Default 1000 ≈
                         8 KB memory per tracked function.
        """
        self._lock = threading.RLock()
        self._functions: dict[str, _FunctionStats] = {}
        self._window_size = window_size

        # Threshold for outlier flagging. Set externally by installer
        # based on cfg.DIAG_SLOW_FUNCTION_MS. Stored in ns for fast compare.
        self._outlier_threshold_ns = 5_000_000   # 5 ms default

    def set_outlier_threshold_ms(self, ms: float):
        """Update the outlier threshold. Safe to call at runtime."""
        with self._lock:
            self._outlier_threshold_ns = int(ms * 1_000_000)

    def record(self, name: str, elapsed_ns: int):
        """
        Record a timing sample for the named function.

        Called by the timing shim wrapper for every function call.
        Hot path: keep this as fast as possible. Single lock acquisition,
        no dict lookups outside the lock, no exception paths.

        Args:
            name: dotted function path, e.g. "src.ui.updater.update_ui"
            elapsed_ns: wall-clock duration in nanoseconds
        """
        now = time.time()
        with self._lock:
            stats = self._functions.get(name)
            if stats is None:
                stats = _FunctionStats(name, window_size=self._window_size)
                self._functions[name] = stats
            stats.add_sample(elapsed_ns, now, self._outlier_threshold_ns)

    def get_stats(self, name: str) -> Optional[dict]:
        """Return stats dict for one function, or None if never recorded."""
        with self._lock:
            stats = self._functions.get(name)
            if stats is None:
                return None
            return stats.compute_stats()

    def get_all_stats(self) -> list[dict]:
        """
        Return stats for every tracked function.
        Result is sorted by total_ms descending (heaviest first).
        """
        with self._lock:
            results = [s.compute_stats() for s in self._functions.values()]

        results.sort(key=lambda r: r["total_ms"], reverse=True)
        return results

    def get_top_n_by_total_time(self, n: int = 10) -> list[dict]:
        """Top N functions by cumulative time. Useful for reports."""
        return self.get_all_stats()[:n]

    def get_top_n_by_recent_p99(self, n: int = 10) -> list[dict]:
        """Top N functions by recent p99 — finds latency outliers."""
        stats = self.get_all_stats()
        stats.sort(key=lambda r: r["recent_p99_ms"], reverse=True)
        return stats[:n]

    def drain_all_outliers(self) -> dict[str, list]:
        """
        Drain outlier deques from all functions.
        Returns {function_name: [(timestamp, elapsed_ns), ...], ...}
        """
        result = {}
        with self._lock:
            for name, stats in self._functions.items():
                outliers = stats.drain_outliers()
                if outliers:
                    result[name] = outliers
        return result

    def get_tracked_function_count(self) -> int:
        with self._lock:
            return len(self._functions)

    def reset(self):
        """Clear all stats. Useful for tests or 'restart measurement' actions."""
        with self._lock:
            self._functions.clear()