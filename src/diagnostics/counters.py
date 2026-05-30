"""
================================================================================
  src/diagnostics/counters.py — Event Counters with Rate Tracking
================================================================================
  Discrete event counting (clips, gesture activations, mode switches, OSC
  errors, etc.). Tracks both cumulative totals and per-window rates.

  Differs from profiler.py:
    - profiler.py measures TIME spent in functions
    - counters.py counts EVENTS regardless of duration

  Two views per counter:
    1. Cumulative total since startup (monotonic, never decreases)
    2. Rolling timestamp window for rate calculation (events/sec, /min)

  Rate calculation:
    For each counter we keep a deque of event timestamps within the
    configured window (default 60 seconds). Rate = len(deque) / window.
    Old timestamps are evicted on the next increment or rate query.

  Memory bound:
    Each timestamp is a float (8 bytes). At 1000 events/sec sustained
    for 60s, that's 60000 × 8 = 480 KB per counter — bounded.
    A counter incremented once per second uses 480 bytes.

  Thread safety:
    All public methods use a single RLock. Lock hold time is microseconds
    (deque append + occasional eviction).

  Pre-registered counters:
    The installer registers these at startup so they always appear in
    reports even if zero. Custom counters auto-register on first increment.
================================================================================
"""

import time
import threading
from collections import deque
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  KNOWN COUNTER NAMES
#
#  These are registered up-front so they appear in every summary report
#  even when count = 0. Helps you spot "wait, why ARE there zero gesture
#  activations? is something broken?" situations.
# ═══════════════════════════════════════════════════════════════════════════

KNOWN_COUNTERS = [
    # Audio events
    "clip_event",
    "clip_notification_pushed",
    "clip_notification_suppressed_by_rate_limit",

    # User actions
    "gesture_x_activation",          # X double-flick fired (kill/restore/boost)
    "gesture_y_band_switch",         # Y double-flick fired
    "eq_mode_toggle",
    "fx_mode_enter",
    "fx_mode_exit",
    "momentary_stutter_press",
    "momentary_bass_cut_press",
    "momentary_fx_throw_press",
    "baseline_save_manual",
    "baseline_save_auto",
    "filter_lock_toggle",
    "wet_lock_toggle",

    # EQ engine
    "eq_ramp_started",
    "eq_ramp_completed",
    "eq_encoder_write",
    "trim_encoder_write",

    # FX engine
    "fx_macro_write",
    "fx_recovery_executed",
    "delay_fb_step",

    # Navigation
    "scene_navigate",
    "track_navigate",
    "bookmark_navigate",
    "group_navigate",

    # OSC errors
    "ableton_error_received",
    "osc_send_failed",

    # Controller events
    "controller_reprobe",
    "controller_disconnect_detected",
    "select_ghost_event_corrected",

    # Diagnostics meta
    "diag_summary_written",
    "diag_outlier_logged",
]


# ═══════════════════════════════════════════════════════════════════════════
#  SINGLE COUNTER
# ═══════════════════════════════════════════════════════════════════════════

class _Counter:
    """
    One named counter. Tracks total + rolling timestamp deque.

    All methods assume caller holds the parent Counters lock.
    """

    __slots__ = ("name", "total", "timestamps", "window_s", "_last_value")

    def __init__(self, name: str, window_s: float = 60.0):
        self.name = name
        self.total: float = 0.0     # cumulative (supports fractional via 'value' arg)
        # Deque of timestamps for rate calc. Each entry = one event.
        # For non-unit increments (value > 1), we still store one timestamp
        # per call — the per-call value is tracked via _last_value if needed.
        self.timestamps: deque[float] = deque()
        self.window_s = window_s
        self._last_value = 1.0       # most recent increment value

    def increment(self, value: float, now: float):
        """Record one event."""
        self.total += value
        self.timestamps.append(now)
        self._last_value = value
        self._evict_old(now)

    def _evict_old(self, now: float):
        """Remove timestamps older than the window."""
        cutoff = now - self.window_s
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def rate_per_sec(self, now: float) -> float:
        """Events per second over the rolling window."""
        self._evict_old(now)
        if self.window_s <= 0:
            return 0.0
        return len(self.timestamps) / self.window_s

    def rate_per_min(self, now: float) -> float:
        return self.rate_per_sec(now) * 60.0

    def count_in_window(self, now: float) -> int:
        """Number of events in the rolling window."""
        self._evict_old(now)
        return len(self.timestamps)

    def to_dict(self, now: float) -> dict:
        return {
            "name":            self.name,
            "total":           self.total,
            "rate_per_sec":    self.rate_per_sec(now),
            "rate_per_min":    self.rate_per_min(now),
            "count_in_window": self.count_in_window(now),
            "window_s":        self.window_s,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  COUNTERS (the public collector)
# ═══════════════════════════════════════════════════════════════════════════

class Counters:
    """
    Manages many named event counters.

    Pre-registers KNOWN_COUNTERS at construction so they always appear in
    reports. Unknown names auto-register on first increment.

    Thread-safe via a single RLock.
    """

    def __init__(self, default_window_s: float = 60.0):
        """
        Args:
            default_window_s: rolling window for rate calculation.
                              60s = "events per minute" view.
                              Auto-registered counters use this default.
                              Custom counters can override per-counter.
        """
        self._lock = threading.RLock()
        self._counters: dict[str, _Counter] = {}
        self._default_window_s = default_window_s

        # Pre-register known counters so they always show in reports
        for name in KNOWN_COUNTERS:
            self._counters[name] = _Counter(name, window_s=default_window_s)

    def increment(self, name: str, value: float = 1.0):
        """
        Increment a counter by value (default 1).

        Hot path: this gets called many times per second. Single lock,
        no exceptions in the normal case.

        Args:
            name: counter name (will be auto-registered if unknown)
            value: amount to add (usually 1.0)
        """
        now = time.time()
        with self._lock:
            counter = self._counters.get(name)
            if counter is None:
                # Auto-register on first use
                counter = _Counter(name, window_s=self._default_window_s)
                self._counters[name] = counter
            counter.increment(value, now)

    def register(self, name: str, window_s: Optional[float] = None):
        """
        Explicitly create a counter with a custom window.
        Useful for counters that should NOT use the default 60s window.
        """
        with self._lock:
            if name not in self._counters:
                w = window_s if window_s is not None else self._default_window_s
                self._counters[name] = _Counter(name, window_s=w)

    def get(self, name: str) -> Optional[dict]:
        """Return counter snapshot dict, or None if unknown."""
        now = time.time()
        with self._lock:
            counter = self._counters.get(name)
            if counter is None:
                return None
            return counter.to_dict(now)

    def get_all(self) -> list[dict]:
        """
        Return all counter snapshots.
        Sorted by total descending (most-active first).
        """
        now = time.time()
        with self._lock:
            results = [c.to_dict(now) for c in self._counters.values()]
        results.sort(key=lambda r: r["total"], reverse=True)
        return results

    def get_nonzero(self) -> list[dict]:
        """Return only counters with total > 0. Skips silent ones."""
        return [c for c in self.get_all() if c["total"] > 0]

    def get_total(self, name: str) -> float:
        """Quick cumulative-total accessor."""
        with self._lock:
            counter = self._counters.get(name)
            return counter.total if counter else 0.0

    def get_rate_per_sec(self, name: str) -> float:
        """Quick rate accessor."""
        now = time.time()
        with self._lock:
            counter = self._counters.get(name)
            if counter is None:
                return 0.0
            return counter.rate_per_sec(now)

    def get_rate_per_min(self, name: str) -> float:
        """Quick per-minute rate accessor."""
        return self.get_rate_per_sec(name) * 60.0

    def reset(self):
        """Reset all counters to zero. Re-registers known counters."""
        with self._lock:
            self._counters.clear()
            for name in KNOWN_COUNTERS:
                self._counters[name] = _Counter(name, window_s=self._default_window_s)