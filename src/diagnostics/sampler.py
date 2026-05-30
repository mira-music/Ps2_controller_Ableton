"""
================================================================================
  src/diagnostics/sampler.py — System Resource Sampler
================================================================================
  Background daemon thread that samples CPU%, RAM, thread count, GC stats,
  and file descriptors at a configurable interval (default 1 second).

  All samples stored in a bounded ring buffer (default 600 samples = 10 min
  at 1 Hz). Older samples are evicted automatically.

  Optional dependency:
    psutil — provides accurate per-process CPU% and memory measurements.
    If unavailable, the sampler falls back to a "degraded" mode using
    only what's in the Python stdlib (threading.active_count,
    gc.get_count, gc.get_stats). CPU% and RAM will not be reported
    in degraded mode, but everything else still works.

  Self-measurement:
    Each sample iteration's time is itself recorded so we can verify the
    sampler isn't expensive relative to its sample interval. Typical
    overhead at 1 Hz: well under 1 ms per sample = 0.1% CPU.

  Thread model:
    Sampler runs in its own daemon thread, named "diag.sampler".
    Loop: sleep(sample_interval) → take sample → store → repeat.
    Stops cleanly via stop() which sets an event flag.

  Storage:
    self._samples is a deque of Sample namedtuples. Each Sample is
    ~80 bytes. At default 600 samples = ~48 KB memory.
================================================================================
"""

import time
import threading
import gc
import os
import sys
from collections import deque, namedtuple
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  OPTIONAL DEPENDENCY DETECTION
# ═══════════════════════════════════════════════════════════════════════════

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    _PSUTIL_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════
#  SAMPLE STRUCTURE
# ═══════════════════════════════════════════════════════════════════════════

Sample = namedtuple("Sample", [
    "timestamp",      # time.time() when sample was taken
    "cpu_percent",    # process CPU %, or -1.0 if psutil unavailable
    "memory_mb",      # process RSS in MB, or -1.0 if psutil unavailable
    "thread_count",   # threading.active_count()
    "gc_gen0_count",  # gc.get_count()[0] — gen-0 objects awaiting collection
    "gc_gen1_count",
    "gc_gen2_count",
    "gc_collections", # total collections across all generations
    "open_fds",       # open file descriptors, -1 on Windows or if unavailable
    "sample_dur_ns",  # how long this sample took to collect (self-measurement)
])


def _empty_sample(now: float) -> Sample:
    """Construct a zeroed sample, used during init."""
    return Sample(
        timestamp=now,
        cpu_percent=-1.0,
        memory_mb=-1.0,
        thread_count=0,
        gc_gen0_count=0,
        gc_gen1_count=0,
        gc_gen2_count=0,
        gc_collections=0,
        open_fds=-1,
        sample_dur_ns=0,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  SAMPLER
# ═══════════════════════════════════════════════════════════════════════════

class SystemSampler:
    """
    Periodic background sampling of system resource usage.

    Runs as a daemon thread. Sampling interval is configurable at construction
    and can be updated at runtime via set_interval().

    Public API:
        start()                 — begin sampling thread
        stop()                  — signal thread to exit (joins briefly)
        is_running()            — bool
        latest_sample()         — most recent Sample, or None
        get_samples(limit=N)    — last N samples (default all in buffer)
        get_avg(window_s=N)     — averages over last N seconds
        get_growth_mb()         — RAM growth since first sample
    """

    def __init__(self,
                 interval_s: float = 1.0,
                 buffer_size: int = 600):
        """
        Args:
            interval_s: seconds between samples (default 1.0)
            buffer_size: max samples to retain (default 600 = 10 min at 1 Hz)
        """
        self._interval_s = interval_s
        self._buffer_size = buffer_size
        self._lock = threading.RLock()
        self._samples: deque[Sample] = deque(maxlen=buffer_size)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # psutil.Process handle is cached for performance — getting it on
        # every sample would be wasteful. None if psutil unavailable.
        if _PSUTIL_AVAILABLE:
            try:
                self._psutil_proc = psutil.Process(os.getpid())
                # Prime CPU measurement — first call to cpu_percent() with
                # interval=None returns 0.0 because there's no baseline.
                # Calling it now establishes the baseline so the next call
                # gives a real number.
                self._psutil_proc.cpu_percent(interval=None)
            except Exception:
                self._psutil_proc = None
        else:
            self._psutil_proc = None

        # Track first memory reading for growth calculation
        self._initial_memory_mb: Optional[float] = None

        # Cache gc stats so we can compute deltas if desired
        self._last_gc_collections = sum(s["collections"] for s in gc.get_stats())

    # ─── Lifecycle ──────────────────────────────────────────────────────

    def start(self):
        """Start the background sampling thread."""
        if self._thread is not None and self._thread.is_alive():
            return  # already running
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="diag.sampler", daemon=True
        )
        self._thread.start()

    def stop(self):
        """
        Signal the sampling thread to exit. Joins for up to 2× the sample
        interval so we don't hang shutdown if the sampler is sleeping.
        """
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval_s * 2.0)
            self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ─── Sample loop ────────────────────────────────────────────────────

    def _run(self):
        """Main sampling loop — runs in its own thread."""
        # Take an initial sample immediately so latest_sample() doesn't
        # return None on first query.
        self._take_sample()

        while not self._stop_event.is_set():
            # Use stop_event.wait() instead of time.sleep() so stop() responds
            # quickly even if sampling interval is large.
            if self._stop_event.wait(timeout=self._interval_s):
                break  # stop signal received
            try:
                self._take_sample()
            except Exception as e:
                # Never crash the sampler thread. Just log and continue.
                try:
                    print(f"[diag.sampler] sample failed: {e}")
                except Exception:
                    pass

    def _take_sample(self):
        """Collect one sample and append to ring buffer."""
        start_ns = time.perf_counter_ns()
        now = time.time()

        # ─── CPU and memory (psutil) ─────────────────────────────────
        cpu_percent = -1.0
        memory_mb = -1.0
        open_fds = -1

        if self._psutil_proc is not None:
            try:
                # interval=None → uses delta since last call (cheap, accurate)
                cpu_percent = self._psutil_proc.cpu_percent(interval=None)
            except Exception:
                cpu_percent = -1.0

            try:
                mem_info = self._psutil_proc.memory_info()
                memory_mb = mem_info.rss / (1024 * 1024)
                # Capture initial memory for growth calculation
                if self._initial_memory_mb is None:
                    self._initial_memory_mb = memory_mb
            except Exception:
                memory_mb = -1.0

            # File descriptors — Unix only. On Windows psutil has
            # num_handles() instead but we report fds for consistency.
            try:
                if hasattr(self._psutil_proc, "num_fds"):
                    open_fds = self._psutil_proc.num_fds()
                elif hasattr(self._psutil_proc, "num_handles"):
                    open_fds = self._psutil_proc.num_handles()
            except Exception:
                open_fds = -1

        # ─── Stdlib metrics (always available) ───────────────────────
        thread_count = threading.active_count()
        gen_counts = gc.get_count()
        total_collections = sum(s["collections"] for s in gc.get_stats())

        sample_dur_ns = time.perf_counter_ns() - start_ns

        sample = Sample(
            timestamp=now,
            cpu_percent=cpu_percent,
            memory_mb=memory_mb,
            thread_count=thread_count,
            gc_gen0_count=gen_counts[0],
            gc_gen1_count=gen_counts[1],
            gc_gen2_count=gen_counts[2],
            gc_collections=total_collections,
            open_fds=open_fds,
            sample_dur_ns=sample_dur_ns,
        )

        with self._lock:
            self._samples.append(sample)

    # ─── Queries ────────────────────────────────────────────────────────

    def latest_sample(self) -> Optional[Sample]:
        """Most recently collected sample, or None if no samples yet."""
        with self._lock:
            if not self._samples:
                return None
            return self._samples[-1]

    def get_samples(self, limit: Optional[int] = None) -> list[Sample]:
        """
        Return list of samples, oldest to newest.
        If limit is given, returns the last N samples.
        """
        with self._lock:
            if limit is None:
                return list(self._samples)
            if limit >= len(self._samples):
                return list(self._samples)
            return list(self._samples)[-limit:]

    def get_samples_in_window(self, window_s: float) -> list[Sample]:
        """Return samples taken within the last window_s seconds."""
        cutoff = time.time() - window_s
        with self._lock:
            return [s for s in self._samples if s.timestamp >= cutoff]

    def get_avg(self, window_s: float = 10.0) -> dict:
        """
        Compute averages over the last window_s seconds.
        Returns dict with avg/peak cpu_percent, memory_mb, thread_count.
        Useful for "what's the system doing right now" summaries.
        """
        samples = self.get_samples_in_window(window_s)
        if not samples:
            return {
                "samples_in_window": 0,
                "window_s":          window_s,
                "avg_cpu_percent":   -1.0,
                "peak_cpu_percent":  -1.0,
                "avg_memory_mb":     -1.0,
                "peak_memory_mb":    -1.0,
                "avg_thread_count":  0,
                "max_thread_count":  0,
            }

        cpu_samples = [s.cpu_percent for s in samples if s.cpu_percent >= 0]
        mem_samples = [s.memory_mb for s in samples if s.memory_mb >= 0]
        thr_samples = [s.thread_count for s in samples]

        def _safe_avg(lst, default=-1.0):
            return (sum(lst) / len(lst)) if lst else default

        def _safe_max(lst, default=-1.0):
            return max(lst) if lst else default

        return {
            "samples_in_window": len(samples),
            "window_s":          window_s,
            "avg_cpu_percent":   _safe_avg(cpu_samples),
            "peak_cpu_percent":  _safe_max(cpu_samples),
            "avg_memory_mb":     _safe_avg(mem_samples),
            "peak_memory_mb":    _safe_max(mem_samples),
            "avg_thread_count":  int(_safe_avg(thr_samples, 0)),
            "max_thread_count":  int(_safe_max(thr_samples, 0)),
        }

    def get_growth_mb(self) -> float:
        """
        How much RSS memory has grown since the first sample.
        Returns 0.0 if psutil unavailable or no samples yet.
        Useful for detecting memory leaks.
        """
        latest = self.latest_sample()
        if (latest is None
                or latest.memory_mb < 0
                or self._initial_memory_mb is None):
            return 0.0
        return latest.memory_mb - self._initial_memory_mb

    def get_self_overhead_ns(self) -> int:
        """
        Sum of all sample_dur_ns in the buffer. Lets the reporter show
        "the sampler has spent X ms on itself over the last N samples".
        """
        with self._lock:
            return sum(s.sample_dur_ns for s in self._samples)

    def is_psutil_available(self) -> bool:
        """Whether high-quality CPU/RAM data is available."""
        return self._psutil_proc is not None

    # ─── Configuration ──────────────────────────────────────────────────

    def set_interval(self, interval_s: float):
        """
        Change the sampling interval at runtime.
        Takes effect on the next sleep cycle.
        """
        with self._lock:
            self._interval_s = max(0.1, interval_s)