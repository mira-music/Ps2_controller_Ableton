"""
================================================================================
  src/diagnostics/rate_limiter.py — Adaptive Throttling
================================================================================
  Optional self-defense: when certain events fire too frequently, the
  rate limiter suppresses subsequent occurrences for a cooldown period.

  This is the only "active" diagnostics component — everything else just
  observes. The rate limiter ACTS on the system by saying "no, don't
  fire that callback this time".

  Disabled by default (cfg.DIAG_RL_ENABLED = false). When disabled,
  should_allow() always returns True — zero behavior change.

  Use cases:
    1. CLIP notification spam protection
       Without limiting: 40 Hz UI loop pushes a clip notif every frame
                         during a clip event = 40 notifications/sec
       With limiting:    Max 20 per minute. Excess silently suppressed.

    2. OSC flood protection
       Without limiting: A misbehaving thread could spam OSC sends to
                         the same address, overwhelming Ableton.
       With limiting:    Max 100 sends/sec per address. Excess dropped.

  How it works:
    For each "limit name", we keep a deque of recent timestamps.
    On should_allow() call:
      1. Evict timestamps older than the window
      2. Count remaining timestamps
      3. If count < limit → allow (and record this timestamp)
      4. If count >= limit → suppress (do NOT record this timestamp)

  After a limit triggers, all calls within the cooldown_s window are
  rejected. Once cooldown expires, normal counting resumes.

  Per-address sub-limiting:
    For OSC, we want "100 sends per second per address" not "100 sends
    per second globally". The OSC limit uses a nested dict:
    {address: deque of timestamps}.

  Thread safety:
    RLock around all state. Hot path is fast: timestamp deque +
    occasional eviction.

  Observability:
    Every suppression increments a counter via the counters module:
      "clip_notification_suppressed_by_rate_limit"
      "osc_sends_suppressed_by_rate_limit"
    So you can see HOW MANY events were suppressed in the report.
================================================================================
"""

import time
import threading
from collections import deque
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
#  PER-LIMIT STATE
# ═══════════════════════════════════════════════════════════════════════════

class _LimitState:
    """
    State for one rate-limited resource.

    All methods assume caller holds parent RateLimiter lock.
    """

    __slots__ = (
        "name",
        "max_per_window",
        "window_s",
        "cooldown_s",
        "timestamps",
        "cooldown_until",
        "total_allowed",
        "total_suppressed",
    )

    def __init__(self,
                 name: str,
                 max_per_window: int,
                 window_s: float,
                 cooldown_s: float):
        self.name = name
        self.max_per_window = max_per_window
        self.window_s = window_s
        self.cooldown_s = cooldown_s

        self.timestamps: deque[float] = deque()
        self.cooldown_until: float = 0.0
        self.total_allowed = 0
        self.total_suppressed = 0

    def _evict_old(self, now: float):
        cutoff = now - self.window_s
        while self.timestamps and self.timestamps[0] < cutoff:
            self.timestamps.popleft()

    def check(self, now: float) -> bool:
        """
        Return True if action is allowed, False to suppress.
        Updates internal state to record the decision.
        """
        # Check cooldown first — short-circuit if still cooling
        if now < self.cooldown_until:
            self.total_suppressed += 1
            return False

        self._evict_old(now)

        if len(self.timestamps) < self.max_per_window:
            self.timestamps.append(now)
            self.total_allowed += 1
            return True
        else:
            # Limit reached — start cooldown and suppress
            self.cooldown_until = now + self.cooldown_s
            self.total_suppressed += 1
            return False

    def to_dict(self, now: float) -> dict:
        self._evict_old(now)
        remaining_cooldown = max(0.0, self.cooldown_until - now)
        return {
            "name":              self.name,
            "max_per_window":    self.max_per_window,
            "window_s":          self.window_s,
            "cooldown_s":        self.cooldown_s,
            "count_in_window":   len(self.timestamps),
            "in_cooldown":       remaining_cooldown > 0,
            "cooldown_remaining": remaining_cooldown,
            "total_allowed":     self.total_allowed,
            "total_suppressed":  self.total_suppressed,
        }


# ═══════════════════════════════════════════════════════════════════════════
#  RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """
    Manages many independent rate limits.

    Two types of limits:
      - Simple limits: one global counter for the name
      - Per-key limits: one counter per (name, key) pair
                        (e.g. per-address OSC limits)

    The enabled flag is a master switch. When False, should_allow_*
    methods always return True — no throttling, no overhead.
    """

    def __init__(self, enabled: bool = False):
        self._lock = threading.RLock()
        self._enabled = enabled

        # Simple limits: {name: _LimitState}
        self._limits: dict[str, _LimitState] = {}

        # Per-key limits: {name: {key: _LimitState}}
        # Each sub-dict shares the same configuration (max/window/cooldown)
        # but tracks independent state per key.
        self._keyed_limits: dict[str, dict[str, _LimitState]] = {}
        self._keyed_configs: dict[str, dict] = {}

    # ─── Master switch ──────────────────────────────────────────────────

    def set_enabled(self, enabled: bool):
        """Enable or disable all rate limiting at runtime."""
        with self._lock:
            self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    # ─── Simple limit configuration ─────────────────────────────────────

    def register_limit(self,
                       name: str,
                       max_per_window: int,
                       window_s: float = 60.0,
                       cooldown_s: float = 5.0):
        """
        Register a simple rate limit.

        Args:
            name: identifier (e.g. "clip_notifications")
            max_per_window: max events per window before triggering cooldown
            window_s: rolling window for counting (default 60s)
            cooldown_s: how long to suppress after limit triggers

        max_per_window <= 0 means no limit (always allow). The state is
        still created so you can change the limit later.
        """
        with self._lock:
            self._limits[name] = _LimitState(name, max_per_window, window_s, cooldown_s)

    def should_allow(self, name: str) -> bool:
        """
        Check if the named action is allowed right now.

        Returns True unless:
          - the limiter is disabled (always True)
          - the named limit is unknown (always True; safer default)
          - the limit has been reached and cooldown is active

        Hot path. Called from places like the UI clip-notification
        push site, so must be fast.
        """
        if not self._enabled:
            return True

        now = time.time()
        with self._lock:
            limit = self._limits.get(name)
            if limit is None:
                # Unknown limit name — allow by default. Caller may not have
                # registered it. (Better than silently dropping events.)
                return True
            if limit.max_per_window <= 0:
                return True  # configured as "no limit"
            return limit.check(now)

    # ─── Per-key limit configuration ────────────────────────────────────

    def register_keyed_limit(self,
                             name: str,
                             max_per_window: int,
                             window_s: float = 1.0,
                             cooldown_s: float = 5.0):
        """
        Register a per-key rate limit (e.g. per-OSC-address).

        All keys under this name share the same max/window/cooldown values.
        Use should_allow_keyed(name, key) to check.

        Example:
            limiter.register_keyed_limit("osc_per_address",
                                         max_per_window=100, window_s=1.0)
            limiter.should_allow_keyed("osc_per_address", "/live/song/get/tempo")
        """
        with self._lock:
            self._keyed_limits[name] = {}
            self._keyed_configs[name] = {
                "max_per_window": max_per_window,
                "window_s":       window_s,
                "cooldown_s":     cooldown_s,
            }

    def should_allow_keyed(self, name: str, key: str) -> bool:
        """
        Check if (name, key) is allowed right now.

        First call for a new key auto-registers a _LimitState for that key
        using the registered configuration.
        """
        if not self._enabled:
            return True

        config = self._keyed_configs.get(name)
        if config is None:
            return True  # unknown limit name
        if config["max_per_window"] <= 0:
            return True  # disabled per-config

        now = time.time()
        with self._lock:
            key_map = self._keyed_limits.get(name)
            if key_map is None:
                return True
            limit = key_map.get(key)
            if limit is None:
                limit = _LimitState(
                    f"{name}:{key}",
                    config["max_per_window"],
                    config["window_s"],
                    config["cooldown_s"],
                )
                key_map[key] = limit
            return limit.check(now)

    # ─── Querying ───────────────────────────────────────────────────────

    def get_all_simple(self) -> list[dict]:
        """All registered simple limits' state."""
        now = time.time()
        with self._lock:
            return [l.to_dict(now) for l in self._limits.values()]

    def get_all_keyed(self) -> dict[str, list[dict]]:
        """
        All registered keyed limits' state.
        Returns {limit_name: [state_per_key, ...], ...}
        """
        now = time.time()
        with self._lock:
            result = {}
            for name, key_map in self._keyed_limits.items():
                result[name] = [s.to_dict(now) for s in key_map.values()]
            return result

    def get_total_suppressed(self) -> int:
        """Total suppression count across all limits (simple + keyed)."""
        total = 0
        with self._lock:
            for l in self._limits.values():
                total += l.total_suppressed
            for key_map in self._keyed_limits.values():
                for l in key_map.values():
                    total += l.total_suppressed
        return total

    # ─── Maintenance ────────────────────────────────────────────────────

    def reset(self):
        """Clear all rate limit state. Configs preserved."""
        with self._lock:
            for limit in self._limits.values():
                limit.timestamps.clear()
                limit.cooldown_until = 0.0
                limit.total_allowed = 0
                limit.total_suppressed = 0
            for key_map in self._keyed_limits.values():
                key_map.clear()