"""
================================================================================
  src/diagnostics/osc_tracker.py — Per-Address OSC Traffic Accounting
================================================================================
  Tracks every OSC message sent or received, broken down by address.

  Two-level breakdown:
    - Per-address counters (one entry per unique OSC address)
    - Global send/receive totals

  Stats kept per address:
    - count_total       cumulative since startup
    - bytes_total       cumulative payload bytes (when available)
    - timestamps        deque for rolling rate calculation
    - max_msg_per_sec   peak burst rate observed

  Address filtering (set up by installer from TOML):
    - track_all_sends    : True = record every send, False = only listed
    - track_all_receives : same for receives
    - tracked_addresses  : list of prefix patterns (e.g. "/live/device")

  When track_all_* is False, only addresses matching one of the prefixes
  in tracked_addresses are recorded. Useful to reduce log volume on busy
  sessions where you only care about specific endpoints.

  Memory bound:
    Each tracked address allocates ~16 KB at peak rate (timestamp deque
    plus stats struct). Hundreds of unique addresses = ~few MB.
    A typical Ableton session uses ~30 unique addresses → ~500 KB.

  Hot path:
    record_send / record_recv are called by the OSC client and server
    wrappers on every message. Designed to be very fast:
      - single RLock acquire
      - dict lookup
      - deque append
      - occasional eviction of old timestamps
    Sub-microsecond per call typical.

  Thread safety:
    OSC server uses ThreadingOSCUDPServer — receive handlers run in many
    threads concurrently. The RLock here serializes only the stats
    bookkeeping, not the actual OSC processing.
================================================================================
"""

import time
import threading
from collections import deque
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  PER-ADDRESS STATS
# ═══════════════════════════════════════════════════════════════════════════

class _AddressStats:
    """Stats for one OSC address (either send-side or receive-side)."""

    __slots__ = (
        "address",
        "count_total",
        "bytes_total",
        "timestamps",
        "window_s",
        "max_per_sec_observed",
        "max_per_sec_at",
    )

    def __init__(self, address: str, window_s: float):
        self.address = address
        self.count_total = 0
        self.bytes_total = 0
        # Rolling window of message timestamps for rate calc
        self.timestamps: deque[float] = deque()
        self.window_s = window_s
        self.max_per_sec_observed = 0.0
        self.max_per_sec_at = 0.0   # time.time() when peak was observed

    def record(self, now: float, payload_bytes: int):
        """Record one message."""
        self.count_total += 1
        self.bytes_total += payload_bytes
        self.timestamps.append(now)
        self._evict_old(now)

        # Update peak rate (computed cheaply from current window length)
        if self.window_s > 0:
            current_rate = len(self.timestamps) / self.window_s
            if current_rate > self.max_per_sec_observed:
                self.max_per_sec_observed = current_rate
                self.max_per_sec_at = now

    def _evict_old(self, now: float):
        cutoff = now - self.window_s
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def rate_per_sec(self, now: float) -> float:
        self._evict_old(now)
        if self.window_s <= 0:
            return 0.0
        return len(self.timestamps) / self.window_s

    def count_in_window(self, now: float) -> int:
        self._evict_old(now)
        return len(self.timestamps)

    def to_dict(self, now: float) -> dict:
        return {
            "address":              self.address,
            "count_total":          self.count_total,
            "bytes_total":          self.bytes_total,
            "rate_per_sec":         self.rate_per_sec(now),
            "count_in_window":      self.count_in_window(now),
            "max_per_sec_observed": self.max_per_sec_observed,
            "max_per_sec_at":       self.max_per_sec_at,
            "window_s":             self.window_s,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  OSC TRACKER (the public collector)
# ═══════════════════════════════════════════════════════════════════════════

class OSCTracker:
    """
    Per-address accounting of outbound and inbound OSC traffic.

    Two independent dicts: sends and receives. Each maps OSC address
    → _AddressStats. Address filtering is configured at construction
    and can be updated at runtime.
    """

    def __init__(self,
                 window_s: float = 5.0,
                 track_all_sends: bool = True,
                 track_all_receives: bool = True,
                 tracked_addresses: Optional[list] = None):
        """
        Args:
            window_s: rolling window for rate calculation (seconds)
            track_all_sends: if True, record every outbound message
            track_all_receives: if True, record every inbound message
            tracked_addresses: list of address prefixes to track when
                               track_all_* is False
        """
        self._lock = threading.RLock()
        self._sends:    dict[str, _AddressStats] = {}
        self._receives: dict[str, _AddressStats] = {}

        self._window_s = window_s
        self._track_all_sends = track_all_sends
        self._track_all_receives = track_all_receives
        self._tracked_prefixes = list(tracked_addresses or [])

        # Global totals (separate from per-address sums for fast access)
        self._total_sends = 0
        self._total_receives = 0
        self._total_send_bytes = 0
        self._total_recv_bytes = 0

        # Global timestamp deques for overall rate
        self._all_send_timestamps:    deque[float] = deque()
        self._all_receive_timestamps: deque[float] = deque()

    # ─── Filtering ──────────────────────────────────────────────────────

    def _should_track(self, address: str, is_send: bool) -> bool:
        """
        Decide whether to record a message based on config filter.
        Returns True if (track_all OR address matches a tracked prefix).
        """
        if is_send and self._track_all_sends:
            return True
        if not is_send and self._track_all_receives:
            return True
        # Per-address filter mode: check prefix match
        for prefix in self._tracked_prefixes:
            if address.startswith(prefix):
                return True
        return False

    # ─── Recording ──────────────────────────────────────────────────────

    def record_send(self, address: str, payload_bytes: int = 0):
        """
        Record one outbound OSC message.

        Hot path — keep fast. Called by the OSC client send wrapper
        on every message.
        """
        if not self._should_track(address, is_send=True):
            return

        now = time.time()
        with self._lock:
            self._total_sends += 1
            self._total_send_bytes += payload_bytes
            self._all_send_timestamps.append(now)
            self._evict_global_timestamps(now)

            stats = self._sends.get(address)
            if stats is None:
                stats = _AddressStats(address, self._window_s)
                self._sends[address] = stats
            stats.record(now, payload_bytes)

    def record_recv(self, address: str, payload_bytes: int = 0):
        """Record one inbound OSC message."""
        if not self._should_track(address, is_send=False):
            return

        now = time.time()
        with self._lock:
            self._total_receives += 1
            self._total_recv_bytes += payload_bytes
            self._all_receive_timestamps.append(now)
            self._evict_global_timestamps(now)

            stats = self._receives.get(address)
            if stats is None:
                stats = _AddressStats(address, self._window_s)
                self._receives[address] = stats
            stats.record(now, payload_bytes)

    def _evict_global_timestamps(self, now: float):
        cutoff = now - self._window_s
        while self._all_send_timestamps and self._all_send_timestamps[0] < cutoff:
            self._all_send_timestamps.popleft()
        while self._all_receive_timestamps and self._all_receive_timestamps[0] < cutoff:
            self._all_receive_timestamps.popleft()

    # ─── Querying ───────────────────────────────────────────────────────

    def get_send_stats(self) -> list[dict]:
        """Per-address send stats, sorted by count_total descending."""
        now = time.time()
        with self._lock:
            results = [s.to_dict(now) for s in self._sends.values()]
        results.sort(key=lambda r: r["count_total"], reverse=True)
        return results

    def get_receive_stats(self) -> list[dict]:
        """Per-address receive stats, sorted by count_total descending."""
        now = time.time()
        with self._lock:
            results = [s.to_dict(now) for s in self._receives.values()]
        results.sort(key=lambda r: r["count_total"], reverse=True)
        return results

    def get_global_summary(self) -> dict:
        """
        Overall traffic stats (not per-address).
        Returns dict with total counts + current window rates + cumulative bytes.
        """
        now = time.time()
        with self._lock:
            self._evict_global_timestamps(now)
            return {
                "total_sends":          self._total_sends,
                "total_receives":       self._total_receives,
                "total_send_bytes":     self._total_send_bytes,
                "total_recv_bytes":     self._total_recv_bytes,
                "send_rate_per_sec":    (len(self._all_send_timestamps) / self._window_s) if self._window_s > 0 else 0.0,
                "recv_rate_per_sec":    (len(self._all_receive_timestamps) / self._window_s) if self._window_s > 0 else 0.0,
                "unique_send_addresses":    len(self._sends),
                "unique_recv_addresses":    len(self._receives),
                "window_s":             self._window_s,
            }

    def get_top_n_senders(self, n: int = 10) -> list[dict]:
        """Top N outbound addresses by message count."""
        return self.get_send_stats()[:n]

    def get_top_n_receivers(self, n: int = 10) -> list[dict]:
        """Top N inbound addresses by message count."""
        return self.get_receive_stats()[:n]

    # ─── Maintenance ────────────────────────────────────────────────────

    def reset(self):
        """Clear all accumulated stats."""
        with self._lock:
            self._sends.clear()
            self._receives.clear()
            self._total_sends = 0
            self._total_receives = 0
            self._total_send_bytes = 0
            self._total_recv_bytes = 0
            self._all_send_timestamps.clear()
            self._all_receive_timestamps.clear()

    def update_window(self, window_s: float):
        """
        Change the rolling window size at runtime.
        New window applies to all existing and future stats objects.
        Existing timestamps outside the new window will be evicted on next access.
        """
        with self._lock:
            self._window_s = window_s
            for s in self._sends.values():
                s.window_s = window_s
            for s in self._receives.values():
                s.window_s = window_s

    def update_filters(self,
                       track_all_sends: bool,
                       track_all_receives: bool,
                       tracked_addresses: list):
        """Update filtering rules at runtime."""
        with self._lock:
            self._track_all_sends = track_all_sends
            self._track_all_receives = track_all_receives
            self._tracked_prefixes = list(tracked_addresses)