"""
================================================================================
  src/diagnostics/__init__.py — Diagnostics Layer Public API
================================================================================
  This module is an OPTIONAL observability layer for FX Machine. When
  diagnostics is enabled in config (diagnostics.enabled = true), this
  package wraps key functions, tracks OSC traffic, samples system
  resources, and writes detailed analysis logs.

  When disabled, importing this module is essentially free — no hooks are
  installed, no threads are started, no overhead is added.

  Public entry points:
    install_if_enabled()  — call once from run.py BEFORE main()
    diag                  — singleton holding all collected stats
    shutdown_diagnostics() — flush + close logs cleanly (called by main on exit)

  Design principles:
    - Never crash the host app. All diagnostics code is wrapped in
      try/except — a bug in diagnostics must never prevent FX Machine
      from running.
    - Monkey-patch wrappers instead of source decorators. Zero changes
      required to the rest of the codebase to add or remove observation.
    - Self-measuring. The diagnostics overhead itself is tracked so you
      can see exactly what the layer costs.

  File layout:
    __init__.py        ← this file (public API + singleton)
    installer.py       ← hooks all wrappers into place at startup
    profiler.py        ← function timing stats collector
    counters.py        ← event counters with rate tracking
    osc_tracker.py     ← per-address OSC traffic accounting
    sampler.py         ← CPU/RAM/thread/GC sampling thread
    thread_health.py   ← thread frequency tracking
    rate_limiter.py    ← adaptive throttling
    reporter.py        ← text + JSONL log writers
    analyzer.py        ← post-session analysis (read JSONL → report)
================================================================================
"""

import time
import threading
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  DIAGNOSTICS SINGLETON
#
#  All diagnostic state lives on this object. Submodules import `diag` and
#  read/write its attributes. The singleton is constructed lazily in
#  install_if_enabled() so a disabled diagnostics layer has zero cost.
# ═══════════════════════════════════════════════════════════════════════════

class _DiagnosticsState:
    """
    Container for all live diagnostic state.

    Holds references to the various sub-collectors (profiler, osc_tracker,
    sampler, etc.) and provides the central lock for thread-safe updates.

    Attributes are set up lazily by install_if_enabled() so importing the
    diagnostics package without enabling it is essentially free.
    """

    def __init__(self):
        # Lifecycle
        self.enabled = False
        self.installed = False
        self.installed_at = 0.0
        self.uptime_start = 0.0

        # Sub-collectors (populated by installer.install())
        self.profiler           = None  # profiler.Profiler instance
        self.counters           = None  # counters.Counters instance
        self.osc_tracker        = None  # osc_tracker.OSCTracker instance
        self.sampler            = None  # sampler.SystemSampler instance
        self.thread_health      = None  # thread_health.ThreadHealth instance
        self.rate_limiter       = None  # rate_limiter.RateLimiter instance
        self.reporter           = None  # reporter.Reporter instance

        # Self-measurement
        self.diag_overhead_ns = 0       # ns spent inside diagnostics code

        # Central lock for diag-internal state (not the app's st._lock)
        self.lock = threading.RLock()

    def time_diag_overhead(self):
        """
        Context manager that adds elapsed nanoseconds to diag_overhead_ns.
        Used internally by diagnostics code to self-measure.

        Usage:
            with diag.time_diag_overhead():
                ... diagnostics work ...
        """
        return _OverheadTimer(self)


class _OverheadTimer:
    """Lightweight context manager for self-measurement."""
    __slots__ = ("_diag", "_start")

    def __init__(self, diag):
        self._diag = diag
        self._start = 0

    def __enter__(self):
        self._start = time.perf_counter_ns()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.perf_counter_ns() - self._start
        # Lockless atomic-ish addition. Drift of a few ns under contention
        # is acceptable for a self-measurement counter.
        self._diag.diag_overhead_ns += elapsed


# The singleton. Imported by all diagnostics submodules.
diag = _DiagnosticsState()


# ═══════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def install_if_enabled() -> bool:
    """
    Check cfg.DIAG_ENABLED and install the diagnostics layer if true.

    This is the single entry point called from run.py. It's safe to call
    even when diagnostics is disabled — it returns False without side
    effects.

    Returns:
        True if diagnostics was installed
        False if disabled or installation failed (logged, not raised)

    Failure modes:
        - Config loader not available → returns False silently
        - Any installer error → logged, returns False, app continues normally
    """
    try:
        # Import cfg here, not at module level. If config_loader hasn't been
        # initialized yet (init_config() not called), we still want to gracefully
        # return False.
        from src.config_loader import cfg
    except Exception as e:
        print(f"[diagnostics] config loader unavailable: {e}")
        return False

    if not getattr(cfg, "DIAG_ENABLED", False):
        return False

    if diag.installed:
        # Already installed (idempotent — don't double-install)
        return True

    try:
        # Lazy import installer so the heavy dependencies (psutil etc.)
        # are only loaded when diagnostics is actually enabled.
        from src.diagnostics.installer import install
        install()
        diag.enabled = True
        diag.installed = True
        diag.installed_at = time.time()
        diag.uptime_start = time.perf_counter()
        return True
    except Exception as e:
        # Diagnostics must NEVER crash the host app. Any failure during
        # installation is logged and swallowed.
        import traceback
        print(f"[diagnostics] install failed: {e}")
        print(traceback.format_exc())
        diag.enabled = False
        diag.installed = False
        return False


def shutdown_diagnostics():
    """
    Flush all logs and stop background threads.
    Called from main.py's on_close() handler.

    Safe to call when diagnostics was never enabled — no-ops in that case.
    """
    if not diag.installed:
        return

    try:
        # Sampler thread is a daemon, it'll die with the process, but we
        # ask it nicely to stop so it can write a final sample.
        if diag.sampler is not None:
            diag.sampler.stop()

        if diag.reporter is not None:
            diag.reporter.write_final_summary()
            diag.reporter.close()

        diag.installed = False
    except Exception as e:
        print(f"[diagnostics] shutdown error: {e}")


def is_enabled() -> bool:
    """Public check — has diagnostics been activated?"""
    return diag.enabled and diag.installed


def get_overhead_ms() -> float:
    """Return total milliseconds spent inside diagnostics code since startup."""
    return diag.diag_overhead_ns / 1_000_000.0


# ═══════════════════════════════════════════════════════════════════════════
#  CONVENIENCE PROXY ACCESSORS
#
#  Submodules can also import these and use them as shortcuts:
#      from src.diagnostics import diag, record_event, time_function
#
#  Each is a thin wrapper that's a no-op when diagnostics is disabled,
#  so callers don't need to check is_enabled() everywhere.
# ═══════════════════════════════════════════════════════════════════════════

def record_event(name: str, value: float = 1.0):
    """Increment an event counter. No-op if diagnostics disabled."""
    if not diag.enabled or diag.counters is None:
        return
    try:
        diag.counters.increment(name, value)
    except Exception:
        pass


def record_function_time(name: str, elapsed_ns: int):
    """Record a function timing sample. No-op if diagnostics disabled."""
    if not diag.enabled or diag.profiler is None:
        return
    try:
        diag.profiler.record(name, elapsed_ns)
    except Exception:
        pass


def record_osc_send(address: str, payload_bytes: int = 0):
    """Record an outbound OSC message. No-op if diagnostics disabled."""
    if not diag.enabled or diag.osc_tracker is None:
        return
    try:
        diag.osc_tracker.record_send(address, payload_bytes)
    except Exception:
        pass


def record_osc_recv(address: str, payload_bytes: int = 0):
    """Record an inbound OSC message. No-op if diagnostics disabled."""
    if not diag.enabled or diag.osc_tracker is None:
        return
    try:
        diag.osc_tracker.record_recv(address, payload_bytes)
    except Exception:
        pass


def record_thread_tick(thread_name: str):
    """Heartbeat from a daemon thread. No-op if diagnostics disabled."""
    if not diag.enabled or diag.thread_health is None:
        return
    try:
        diag.thread_health.tick(thread_name)
    except Exception:
        pass


# Module-level exports for `from src.diagnostics import X`
__all__ = [
    "diag",
    "install_if_enabled",
    "shutdown_diagnostics",
    "is_enabled",
    "get_overhead_ms",
    "record_event",
    "record_function_time",
    "record_osc_send",
    "record_osc_recv",
    "record_thread_tick",
]