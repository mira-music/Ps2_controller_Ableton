"""
================================================================================
  src/diagnostics/thread_health.py — Thread Frequency / Health Monitor
================================================================================
  Tracks how often each registered daemon thread "ticks" and compares to
  its target frequency. Detects when a thread misses deadlines (e.g. UI
  loop targeted at 40 Hz but running at 32 Hz means dropped frames).

  Threads register a target frequency at startup. They then call tick()
  once per iteration. We compute the actual frequency by counting ticks
  within a rolling time window.

  Registered threads in FX Machine:
    "ui"          target ~40 Hz   (cfg.UI_REFRESH_MS = 25 ms)
    "controller"  target ~125 Hz  (pygame.time.wait(8) in loop)
    "polling"     target ~6.6 Hz  (time.sleep(0.15) in loop)
    "eq_ramp"     target ~62.5 Hz (EQ_RAMP_TICK_MS = 16 ms)
    "watchdog"    target ~1 Hz    (cfg.WATCHDOG_INTERVAL = 1.0 s)

  Health metric:
    miss_fraction = max(0, 1 - actual_hz / target_hz)

    Examples:
      actual 40, target 40  → miss_fraction = 0.00  (healthy)
      actual 36, target 40  → miss_fraction = 0.10  (10% missed = at threshold)
      actual 20, target 40  → miss_fraction = 0.50  (50% missed = problem)
      actual 50, target 40  → miss_fraction = 0.00  (running faster than target = fine)

  Memory:
    Each thread keeps a rolling deque of last 500 tick timestamps.
    500 * 8 bytes = 4 KB per thread. With 5 tracked threads = 20 KB.

  Thread safety:
    tick() called from many threads concurrently. Single RLock guards
    the inner dict and per-thread state. Lock hold time is microseconds.
================================================================================
"""

import time
import threading
from collections import deque
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  KNOWN THREAD TARGETS
#
#  Map of thread_name → target_hz. Used by the installer to pre-register
#  the daemon threads we know about. tick() with an unknown name auto-
#  registers it with target_hz=0 (no health calc, just rate observation).
# ═══════════════════════════════════════════════════════════════════════════

KNOWN_THREAD_TARGETS = {
    "ui":         40.0,    # Tkinter UI update loop
    "controller": 125.0,   # pygame event loop @ 8 ms wait
    "polling":    6.6,     # OSC polling loop @ 150 ms sleep
    "eq_ramp":    62.5,    # EQ ramp loop @ 16 ms tick
    "watchdog":   1.0,     # Controller watchdog
}


# ═══════════════════════════════════════════════════════════════════════════
#  PER-THREAD STATE
# ═══════════════════════════════════════════════════════════════════════════

class _ThreadStats:
    """
    Per-thread tick tracking.

    All methods assume caller holds parent ThreadHealth lock.
    """

    __slots__ = (
        "name",
        "target_hz",
        "tick_count",
        "first_tick_at",
        "last_tick_at",
        "tick_timestamps",
        "_window_s",
    )

    def __init__(self, name: str, target_hz: float, window_s: float):
        self.name = name
        self.target_hz = target_hz
        self.tick_count = 0
        self.first_tick_at = 0.0
        self.last_tick_at = 0.0

        # Rolling timestamps for rate calculation
        self.tick_timestamps: deque[float] = deque(maxlen=500)
        self._window_s = window_s

    def tick(self, now: float):
        """Record one tick."""
        self.tick_count += 1
        self.last_tick_at = now
        if self.first_tick_at == 0.0:
            self.first_tick_at = now
        self.tick_timestamps.append(now)

    def actual_hz(self, now: float) -> float:
        """
        Compute actual frequency over the rolling window.
        Returns 0.0 if not enough samples.
        """
        cutoff = now - self._window_s
        # Count timestamps within the window (don't mutate the deque here —
        # the inner deque has maxlen so old entries auto-evict on next tick)
        recent = [t for t in self.tick_timestamps if t >= cutoff]
        if len(recent) < 2:
            return 0.0
        # Use actual window covered (last - first) for accurate rate
        # in case the deque doesn't span the full window_s yet.
        span = recent[-1] - recent[0]
        if span <= 0:
            return 0.0
        return (len(recent) - 1) / span

    def miss_fraction(self, now: float) -> float:
        """
        Fraction of expected ticks missed in the last window.
        0.0 = healthy (running at or above target)
        1.0 = no ticks at all in the window
        """
        if self.target_hz <= 0:
            return 0.0  # not health-checked
        actual = self.actual_hz(now)
        if actual >= self.target_hz:
            return 0.0
        return max(0.0, 1.0 - (actual / self.target_hz))

    def seconds_since_last_tick(self, now: float) -> float:
        """How long ago was the last tick? Useful for detecting stalled threads."""
        if self.last_tick_at == 0.0:
            return -1.0  # never ticked
        return now - self.last_tick_at

    def to_dict(self, now: float) -> dict:
        return {
            "name":                   self.name,
            "target_hz":              self.target_hz,
            "actual_hz":              self.actual_hz(now),
            "tick_count":             self.tick_count,
            "miss_fraction":          self.miss_fraction(now),
            "seconds_since_last":     self.seconds_since_last_tick(now),
            "first_tick_at":          self.first_tick_at,
            "last_tick_at":           self.last_tick_at,
            "window_s":               self._window_s,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  THREAD HEALTH (the public collector)
# ═══════════════════════════════════════════════════════════════════════════

class ThreadHealth:
    """
    Tracks frequency and health of registered daemon threads.

    Threads call tick(name) once per iteration. We compute actual_hz
    from a rolling window and compare to the registered target_hz.
    """

    def __init__(self, window_s: float = 10.0):
        """
        Args:
            window_s: rolling window for hz calculation (default 10 s)
        """
        self._lock = threading.RLock()
        self._threads: dict[str, _ThreadStats] = {}
        self._window_s = window_s

        # Pre-register known threads so they appear in reports
        # even if they never tick (so we can see they're not running).
        for name, target_hz in KNOWN_THREAD_TARGETS.items():
            self._threads[name] = _ThreadStats(name, target_hz, window_s)

    def tick(self, thread_name: str):
        """
        Heartbeat from a daemon thread.

        Hot path — called from inside thread loops. Keep fast.
        If thread_name is unknown, auto-registers with target_hz=0.

        Args:
            thread_name: short identifier (e.g. "ui", "controller")
        """
        now = time.time()
        with self._lock:
            stats = self._threads.get(thread_name)
            if stats is None:
                # Auto-register unknown thread with no target (health = N/A)
                stats = _ThreadStats(thread_name, 0.0, self._window_s)
                self._threads[thread_name] = stats
            stats.tick(now)

    def register(self, thread_name: str, target_hz: float):
        """
        Explicitly register a thread with a target frequency.
        Useful for threads with non-default targets.
        """
        with self._lock:
            if thread_name in self._threads:
                # Update target if already exists
                self._threads[thread_name].target_hz = target_hz
            else:
                self._threads[thread_name] = _ThreadStats(
                    thread_name, target_hz, self._window_s
                )

    def get(self, thread_name: str) -> Optional[dict]:
        """Get snapshot for one thread."""
        now = time.time()
        with self._lock:
            stats = self._threads.get(thread_name)
            if stats is None:
                return None
            return stats.to_dict(now)

    def get_all(self) -> list[dict]:
        """
        Get snapshots for all tracked threads.
        Sorted by name for stable report ordering.
        """
        now = time.time()
        with self._lock:
            results = [s.to_dict(now) for s in self._threads.values()]
        results.sort(key=lambda r: r["name"])
        return results

    def get_unhealthy(self, miss_threshold: float = 0.10) -> list[dict]:
        """
        Return threads with miss_fraction > threshold.
        Useful for warning summaries.
        """
        all_threads = self.get_all()
        return [t for t in all_threads
                if t["target_hz"] > 0 and t["miss_fraction"] > miss_threshold]

    def get_stalled(self, stall_threshold_s: float = 5.0) -> list[dict]:
        """
        Return threads that haven't ticked in stall_threshold_s.
        Threads that have never ticked (seconds_since_last == -1)
        are excluded — those just haven't started yet.
        """
        all_threads = self.get_all()
        return [t for t in all_threads
                if t["seconds_since_last"] >= stall_threshold_s
                and t["target_hz"] > 0]

    def reset(self):
        """Clear all tick stats. Re-registers known threads."""
        with self._lock:
            self._threads.clear()
            for name, target_hz in KNOWN_THREAD_TARGETS.items():
                self._threads[name] = _ThreadStats(name, target_hz, self._window_s)