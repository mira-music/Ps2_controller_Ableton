##  docs/DIAGNOSTICS_GUIDE.md 

```markdown
# 🔍 FX Machine — Diagnostics Layer Guide

## What This Document Covers

This guide explains the complete diagnostics layer built into FX Machine —
how it works internally, how to use it during development and live sessions,
how to read and interpret its output, how to add custom instrumentation,
and how to use the post-session analyzer to identify performance bottlenecks.

The diagnostics layer is the most technically sophisticated observability
system you'll find in a Python desktop application of this size. It was
built because the app had a real performance problem (20% CPU consumed by
a single UI function) and no way to identify it. The diagnostics layer
found the bug in its first session, measured the fix, and now serves as
ongoing insurance that performance stays healthy.

If you're a musician who just wants to use FX Machine, you don't need to
read this guide — the diagnostics layer is disabled by default and has
zero runtime cost when off. This guide is for developers, power users,
and anyone who wants to understand what's happening inside the app at
the microsecond level.

---

## Table of Contents

1. [Why This Exists](#why-this-exists)
2. [Quick Start — 5-Minute Version](#quick-start--5-minute-version)
3. [Architecture Overview](#architecture-overview)
4. [The Installer — How Hooks Work](#the-installer--how-hooks-work)
5. [The Profiler — Function Timing](#the-profiler--function-timing)
6. [Event Counters](#event-counters)
7. [OSC Traffic Tracker](#osc-traffic-tracker)
8. [System Resource Sampler](#system-resource-sampler)
9. [Thread Health Monitor](#thread-health-monitor)
10. [Rate Limiter](#rate-limiter)
11. [The Reporter — Log Output](#the-reporter--log-output)
12. [The Post-Session Analyzer](#the-post-session-analyzer)
13. [Reading a Diagnostics Summary](#reading-a-diagnostics-summary)
14. [Reading the JSONL Log](#reading-the-jsonl-log)
15. [Adding Custom Hooks](#adding-custom-hooks)
16. [Adding Custom Counters](#adding-custom-counters)
17. [Tuning Warning Thresholds](#tuning-warning-thresholds)
18. [Using Rate Limiting](#using-rate-limiting)
19. [Real-World Case Studies](#real-world-case-studies)
20. [Troubleshooting the Diagnostics Layer Itself](#troubleshooting-the-diagnostics-layer-itself)
21. [Performance Cost of Diagnostics](#performance-cost-of-diagnostics)
22. [TOML Configuration Reference](#toml-configuration-reference)
23. [File Reference](#file-reference)
24. [Design Decisions and Trade-Offs](#design-decisions-and-trade-offs)

---

## Why This Exists

FX Machine runs 5 concurrent threads, processes ~70 OSC messages per
second, redraws its UI at 40 Hz, and responds to gamepad input at 125 Hz.
When something is slow, you can't just "feel" which part is slow — you
need measurements.

Early in development, the UI was using 85% of one CPU core during audio
playback. The app was visibly stuttering. Without instrumentation, the
possible culprits were:

- The meter redraw (340 canvas items per frame)
- The EQ knob redraws (4 knobs × multiple canvas items each)
- The FX knob redraws (8 knobs)
- The state snapshot under lock (one big lock acquisition per frame)
- The OSC traffic flooding the server thread
- The set_label calls (potentially 30+ per frame)
- GC pauses from Python's garbage collector
- Lock contention between threads

The diagnostics layer was built to answer this question definitively.
In its first session with all hooks active, it showed:

```
src.ui.widgets.draw_djm_meter    6423 calls    46122.0ms total    7.18ms avg
```

The meter was consuming 20% of wall time. Everything else was sub-1ms
per call. The fix (PhotoImage bitmap rendering) brought the meter down
to 0.11ms average — a 65× improvement. Without the diagnostics data,
we would have optimized blindly and probably fixed the wrong thing.

---

## Quick Start — 5-Minute Version

### Enable diagnostics

Open `config/active.toml` and change:

```toml
[diagnostics]
enabled = false
```

to:

```toml
[diagnostics]
enabled = true
```

### Run the app

```bash
python run.py
```

Use the app normally for 60+ seconds. Sweep some EQ. Play audio. Navigate
tracks. Close the window cleanly when done.

### Read the results

**Human-readable summary:**

```bash
notepad logs\diagnostics.log
```

You'll see periodic summary blocks (every 10 seconds) showing CPU usage,
thread health, top functions by time, OSC traffic, and any warnings.

**Post-session analysis:**

```bash
python analyze_diagnostics.py
```

This produces a complete breakdown of the entire session — aggregated
stats, worst offenders, warning patterns, and resource trends.

### Disable when done

Change `enabled = true` back to `enabled = false` in `active.toml`.
The diagnostics layer adds ~1-2% CPU overhead, so you may want to
disable it for actual performances unless you're actively investigating
a problem.

---

## Architecture Overview

The diagnostics layer is a self-contained package at `src/diagnostics/`
that observes the running app without modifying any source code outside
its own package.

### Package structure

```
src/diagnostics/
├── __init__.py        Public API + diag singleton
│                      Exports: install_if_enabled(), shutdown_diagnostics(),
│                      is_enabled(), record_event(), record_function_time(),
│                      record_osc_send(), record_osc_recv(), record_thread_tick()
│
├── installer.py       The hook installer. Monkey-patches timing wrappers
│                      into target functions at startup. The most critical
│                      file — everything else is data collection/reporting.
│
├── profiler.py        Per-function timing stats. Rolling window of 1000
│                      samples per function for percentile calculations.
│                      Cumulative totals for session-wide analysis.
│
├── counters.py        Named event counters (clip events, gesture activations,
│                      OSC errors, etc.) with rolling-window rate tracking.
│                      35+ pre-registered counter names.
│
├── osc_tracker.py     Per-OSC-address traffic accounting. Tracks every
│                      send and receive with address, count, bytes, and
│                      rolling-window rate. Configurable filtering.
│
├── sampler.py         Background thread sampling CPU%, RAM, thread count,
│                      GC stats, and file descriptors at 1 Hz via psutil.
│                      Falls back gracefully if psutil is unavailable.
│
├── thread_health.py   Per-thread frequency monitor. Each daemon thread
│                      reports a heartbeat every iteration. The monitor
│                      compares actual Hz to target Hz and flags misses.
│
├── rate_limiter.py    Optional adaptive throttling. Can suppress events
│                      (like clip notifications or OSC sends) that exceed
│                      a configured rate. Disabled by default.
│
├── reporter.py        Writes two output files:
│                      - diagnostics.log (human-readable summaries)
│                      - diagnostics.jsonl (machine-readable per-event)
│                      Runs in its own background thread at 10s intervals.
│
└── analyzer.py        Post-session analysis module. Reads JSONL, computes
                       aggregates, identifies top offenders. Used by the
                       standalone analyze_diagnostics.py CLI tool.
```

### How it integrates with the app

The entry point is in `run.py`:

```python
# run.py
from src.main import main

if __name__ == "__main__":
    try:
        from src.config_loader import init_config
        init_config()
        from src.diagnostics import install_if_enabled
        install_if_enabled()
    except Exception as e:
        print(f"[run.py] diagnostics setup failed (continuing without): {e}")
    main()
```

`install_if_enabled()` checks `cfg.DIAG_ENABLED`. If False, it returns
immediately — no imports, no threads, no overhead. If True, it:

1. Creates all collector instances (profiler, counters, tracker, etc.)
2. Starts the system sampler background thread
3. Installs function timing wrappers via monkey-patching
4. Installs the OSC client send wrapper (deferred until st.osc is ready)
5. Installs OSC server receive wrappers (deferred until dispatcher is ready)
6. Installs the UI thread tick wrapper
7. Starts the reporter background thread

The shutdown path is wired into `main.py`'s `on_close()` handler:

```python
# In main.py on_close():
from src.diagnostics import shutdown_diagnostics, is_enabled
if is_enabled():
    shutdown_diagnostics()
```

`shutdown_diagnostics()` stops the sampler and reporter threads, writes
a final summary, and closes file handles. It must run BEFORE the OSC
server is torn down and BEFORE Tkinter is destroyed — otherwise the
reporter thread would crash trying to write to a destroyed stdout.

### The diag singleton

All diagnostics state lives on a single object:

```python
# src/diagnostics/__init__.py
diag = _DiagnosticsState()
```

Sub-modules import `diag` and access its attributes:

```python
diag.profiler       # Profiler instance
diag.counters       # Counters instance
diag.osc_tracker    # OSCTracker instance
diag.sampler        # SystemSampler instance
diag.thread_health  # ThreadHealth instance
diag.rate_limiter   # RateLimiter instance
diag.reporter       # Reporter instance
```

The singleton also tracks self-measurement:

```python
diag.diag_overhead_ns  # nanoseconds spent inside diagnostics code
```

This lets the reporter tell you "diagnostics itself consumed 161ms
over the entire session" — so you know the observation cost.

---

## The Installer — How Hooks Work

The installer is the most technically interesting part of the diagnostics
layer. It solves a specific Python problem: how do you wrap a function
that's been imported by name into another module's namespace?

### The problem

Consider this code:

```python
# src/ui/widgets.py
def draw_djm_meter(canvas, smoothed_db, ...):
    ...

# src/ui/updater.py
from src.ui.widgets import draw_djm_meter

def update_ui(root, lbl):
    ...
    draw_djm_meter(canvas, ...)   # calls the LOCAL reference
```

When `updater.py` does `from src.ui.widgets import draw_djm_meter`, Python
copies the function reference into `updater`'s namespace. If we later
replace `src.ui.widgets.draw_djm_meter` with a wrapper:

```python
# installer.py
import src.ui.widgets as widgets_mod
original = widgets_mod.draw_djm_meter
wrapper = make_timed_wrapper(original)
widgets_mod.draw_djm_meter = wrapper  # replaces in widgets module
```

...`updater.py`'s local `draw_djm_meter` still points to the ORIGINAL
function. The wrapper sits in `widgets_mod` doing nothing because no one
calls it from there — everyone uses the imported name.

### The solution: cross-module patching

After wrapping the function in its origin module, the installer walks
every loaded module in `sys.modules` and replaces any attribute that
references the original function (by identity comparison) with the wrapper:

```python
# installer.py — simplified
for mod_name, mod_obj in sys.modules.items():
    if mod_obj is origin_module:
        continue  # already patched
    if mod_name.startswith("src.diagnostics"):
        continue  # don't patch ourselves

    for attr_name, attr_value in vars(mod_obj).items():
        if attr_value is original:
            setattr(mod_obj, attr_name, wrapper)
```

The `attr_value is original` check uses Python's identity comparison
(`is`, not `==`). Functions are objects with unique identities, so this
only matches the exact function we wrapped — not other functions with
the same name.

After this pass, every module that imported `draw_djm_meter` via
`from src.ui.widgets import draw_djm_meter` now has a reference to the
wrapper instead of the original. The wrapper measures time, calls the
original, and reports the result.

### What gets wrapped

The list of functions to wrap is configured in `config/active.toml`:

```toml
[diagnostics.hooks]
timed_functions = [
    # UI hot path
    "src.ui.updater.update_ui",
    "src.ui.widgets.draw_djm_meter",
    "src.ui.widgets.draw_eq_knob",
    "src.ui.widgets.draw_trim_knob",
    "src.ui.widgets.draw_knob",

    # EQ engine
    "src.engine.eq.eq_drive_continuous_encoder",
    "src.engine.eq.update_eq_x_gesture",
    "src.engine.eq.update_eq_y_gesture_v911",

    # FX engine
    "src.engine.fx.fx_drive_macro",

    # Polling threads
    "src.engine.polling.eq_ramp_loop",
    "src.engine.polling.polling_loop",

    # Controller loop
    "src.controller.loop.controller_loop",

    # OSC discovery
    "src.osc.discovery.fetch_all_names",

    # Meter math
    "src.ui.widgets.raw_meter_to_display_db",
    "src.ui.widgets.apply_meter_ballistics",
    "src.ui.widgets.compute_clip_state",
]
```

You can add or remove entries without modifying any source code. If a
function name has a typo or the module doesn't exist, the installer logs
a warning and skips it — it never crashes the app.

### The wrapper itself

Each wrapper is minimal — the hot path is a single `time.perf_counter_ns()`
call before and after the original:

```python
@functools.wraps(original)
def _wrapped(*args, **kwargs):
    start_ns = time.perf_counter_ns()
    try:
        return original(*args, **kwargs)
    finally:
        elapsed_ns = time.perf_counter_ns() - start_ns
        try:
            diag.profiler.record(name, elapsed_ns)
        except Exception:
            pass  # diagnostics must NEVER crash the wrapped function
```

The `try/finally` ensures the original's return value is always returned,
even if the profiler recording fails. The inner `try/except` around
`profiler.record()` swallows any diagnostics errors silently.

### OSC hooks

The OSC client and server use a different hooking mechanism because
they're not simple functions — they're methods on objects that are
created at runtime.

**OSC client (outbound):** The installer replaces `st.osc.send_message`
with a wrapper that records each outbound message's address and payload
size. Since `setup_osc()` runs inside `main()` and the installer runs
before `main()`, the OSC client hook uses a deferred installation:
a background thread polls for `st.osc` to become non-None, then installs
the wrapper.

**OSC server (inbound):** The installer waits up to 5 seconds for
`st._osc_server` to be populated by the OSC server thread, then walks
the dispatcher's internal handler map and wraps each handler's callback.

### Thread health hooks

The five daemon threads (controller, polling, eq_ramp, watchdog, UI)
each call `record_thread_tick("thread_name")` at the top of their main
loop. This is the ONE place where the diagnostics layer does touch
existing source files — one line per loop. The call is wrapped in
`try/except` so a diagnostics failure never breaks the loop:

```python
# Example from controller/loop.py
while True:
    try:
        from src.diagnostics import record_thread_tick
        record_thread_tick("controller")
    except Exception:
        pass
    # ... rest of loop ...
```

The `from src.diagnostics import record_thread_tick` inside the function
body is intentional — Python caches module imports after first resolution,
so this is effectively a dict lookup (not a file read) on subsequent calls.
If `src.diagnostics` doesn't exist (e.g., someone deleted the package),
the import fails silently and the loop continues.

---

## The Profiler — Function Timing

The profiler (`src/diagnostics/profiler.py`) collects per-function timing
data with two views:

### Rolling window (last 1000 samples)

Used for percentile calculations (median, p95, p99). Bounded memory — a
deque with maxlen=1000. Newest sample replaces oldest when full.

At 1000 samples × 8 bytes per sample = 8 KB per tracked function.
With 16 functions = 128 KB total. Negligible.

### Cumulative counters

- `call_count` — total calls since startup
- `total_ns` — total nanoseconds consumed
- `max_ns` — slowest single call ever observed
- `max_ns_at` — timestamp of the slowest call

These never reset (except via `profiler.reset()`), so session-long
analysis always has the complete picture.

### Outlier tracking

Any call exceeding `cfg.DIAG_SLOW_FUNCTION_MS` (default 5ms) is added
to a separate outlier deque (last 100 per function). Outliers are
written to the JSONL log individually with timestamps, so you can
correlate "function X was slow at time T" with "OSC traffic spiked at
time T" or "the user was doing action Y at time T."

### Querying the profiler

The reporter calls these methods every 10 seconds:

```python
# Top 10 by cumulative time
profiler.get_top_n_by_total_time(10)

# Top 5 by worst p99 (latency outliers)
profiler.get_top_n_by_recent_p99(5)

# Drain all outliers since last summary
profiler.drain_all_outliers()
```

Each returns a list of dicts with keys like:

```python
{
    "name":           "src.ui.updater.update_ui",
    "count":          9426,
    "total_ms":       17464.9,
    "avg_ms":         1.85,
    "recent_median_ms": 1.62,
    "recent_p95_ms":  3.41,
    "recent_p99_ms":  4.60,
    "recent_max_ms":  198.46,
    "max_ms":         198.46,
    "outlier_count":  83,
}
```

---

## Event Counters

The counters module (`src/diagnostics/counters.py`) tracks discrete
events — things that happen N times rather than things that take X
milliseconds.

### Pre-registered counters

35+ event names are pre-registered so they always appear in reports
even when count = 0. This helps you spot "wait, why are there zero
gesture activations? Is something broken?" situations.

Categories include:

**Audio events:**
- `clip_event` — signal exceeded the clip warning threshold
- `clip_notification_pushed` — a clip notification was shown to the user
- `clip_notification_suppressed_by_rate_limit` — rate limiter blocked it

**User actions:**
- `gesture_x_activation` — X double-flick fired
- `gesture_y_band_switch` — Y double-flick fired
- `eq_mode_toggle`, `fx_mode_enter`, `fx_mode_exit`
- `momentary_stutter_press`, `momentary_bass_cut_press`, `momentary_fx_throw_press`
- `baseline_save_manual`, `baseline_save_auto`
- `filter_lock_toggle`, `wet_lock_toggle`

**Engine events:**
- `eq_ramp_started`, `eq_ramp_completed`
- `eq_encoder_write`, `trim_encoder_write`
- `fx_macro_write`, `fx_recovery_executed`
- `delay_fb_step`

**Navigation:**
- `scene_navigate`, `track_navigate`
- `bookmark_navigate`, `group_navigate`

**System events:**
- `ableton_error_received`, `osc_send_failed`
- `controller_reprobe`, `controller_disconnect_detected`
- `select_ghost_event_corrected`

**Diagnostics meta:**
- `diag_summary_written`, `diag_outlier_logged`

### Rate tracking

Each counter maintains a rolling deque of event timestamps. Rate is
calculated as `events_in_window / window_seconds`. Default window is
60 seconds, so rates are per-minute.

For example, if `clip_event` shows 45 events with a rate of 15.0/min,
you know the signal is clipping roughly every 4 seconds — probably
need to lower the input gain.

### Using counters from outside the diagnostics package

If you ever add a feature that should be counted, you can increment
a counter from anywhere in the codebase:

```python
from src.diagnostics import record_event
record_event("my_custom_event")
```

This is a no-op when diagnostics is disabled (the function checks
`diag.enabled` and returns immediately if False).

---

## OSC Traffic Tracker

The OSC tracker (`src/diagnostics/osc_tracker.py`) records every OSC
message sent or received, broken down by address.

### What it tracks per address

- `count_total` — cumulative message count since startup
- `bytes_total` — cumulative payload bytes
- `rate_per_sec` — rolling-window rate (default 5-second window)
- `max_per_sec_observed` — peak burst rate ever seen
- `max_per_sec_at` — timestamp of the peak

### Global totals

In addition to per-address stats, the tracker maintains global
send/receive totals for quick "how busy is OSC overall" queries.

### Filtering

By default, ALL sends and ALL receives are tracked. If you find this
too noisy, you can configure address-prefix filtering in TOML:

```toml
[diagnostics.hooks]
track_all_osc_sends = false
track_all_osc_receives = false
tracked_osc_addresses = [
    "/live/device/set/parameter/value",
    "/live/track/get/output_meter",
]
```

With filtering enabled, only messages matching one of the listed
prefixes are recorded. Others are silently ignored (zero overhead).

### What the traffic data tells you

**High outbound rate to `/live/device/set/parameter/value`:**
You're sweeping a macro aggressively. If the rate exceeds ~100/s,
consider increasing `cfg.EQ_WRITE_THROTTLE` or `cfg.FX_WRITE_THROTTLE`.

**High inbound rate from `/live/track/get/output_meter_*`:**
The meter listeners are firing at Ableton's audio buffer rate (~90 Hz).
This is normal and expected. If the rate is significantly lower, Ableton
may be under heavy load and dropping updates.

**Unexpected outbound to `/live/song/get/tempo`:**
In v1.0.0, tempo is listener-driven so you should NOT see polling for
it. If you do, the session listener registration may have failed.

**Inbound `/live/error` messages:**
Ableton is complaining about something you sent. Check `fxmachine.log`
for the specific error text.

---

## System Resource Sampler

The sampler (`src/diagnostics/sampler.py`) runs a background daemon
thread named `diag.sampler` that collects system metrics at configurable
intervals (default 1 second).

### What it samples

| Metric | Source | Notes |
|---|---|---|
| CPU% | `psutil.Process.cpu_percent()` | Per-process, not system-wide |
| Memory (RSS) | `psutil.Process.memory_info()` | In megabytes |
| Thread count | `threading.active_count()` | Always available |
| GC gen0/1/2 counts | `gc.get_count()` | Objects awaiting collection |
| GC total collections | `gc.get_stats()` | Cumulative across all gens |
| Open file descriptors | `psutil.Process.num_handles()` | Windows: handles |

### psutil dependency

`psutil` provides CPU% and memory data. Without it, the sampler runs
in "degraded mode" — only thread count and GC stats are available.

Install it with:

```bash
pip install psutil
```

The diagnostics layer handles its absence gracefully. No warnings, no
errors, just fewer metrics in the report.

### Memory growth tracking

The sampler records the first RSS reading and computes growth over time:

```
Memory:  48.0 MB → 50.6 MB  delta +2.6 MB since startup
```

If you see memory growing steadily without leveling off (e.g., +10 MB
every 5 minutes for a 30-minute session), you may have a memory leak.
Typical FX Machine sessions show +2-3 MB of growth that stabilizes
within the first few minutes (Python's memory allocator warming up).

### Sample storage

Samples are stored in a bounded ring buffer (default 600 entries =
10 minutes at 1 Hz). Each sample is a namedtuple of ~80 bytes.
Total memory: ~48 KB.

Older samples are evicted automatically. The post-session analyzer
reads from the JSONL log (which contains all summary snapshots), not
from the in-memory ring buffer.

---

## Thread Health Monitor

The thread health monitor (`src/diagnostics/thread_health.py`) tracks
whether each daemon thread is actually running at its expected frequency.

### Registered threads and targets

| Thread | Target Hz | What it does |
|---|---|---|
| `controller` | 125.0 | Gamepad polling via pygame |
| `eq_ramp` | 62.5 | EQ value animation (16ms tick) |
| `polling` | 2.0 | Safety OSC re-polls |
| `ui` | 40.0 | Tkinter UI redraw |
| `watchdog` | 1.0 | Controller health checks |

### How it works

Each thread calls `record_thread_tick("name")` once per iteration.
The monitor keeps a rolling deque of the last 500 tick timestamps per
thread. Actual frequency is computed from the deque:

```python
actual_hz = (len(recent_timestamps) - 1) / (newest - oldest)
```

### Health metric

```
miss_fraction = max(0, 1 - actual_hz / target_hz)
```

A thread is flagged "unhealthy" when `miss_fraction` exceeds the
configured threshold (default 10% = the thread is running at less
than 90% of its target).

### What "unhealthy" actually means

In practice, Python threads almost never hit their exact target
frequency due to GIL contention, OS scheduling, and the overhead
of the sleep/wait mechanisms. Typical real-world values:

- `controller` at 110 Hz (target 125) = **12% miss** = flagged, but harmless
- `ui` at 36 Hz (target 40) = **10% miss** = borderline, harmless
- `polling` at 2.0 Hz (target 2.0) = **0% miss** = perfect
- `watchdog` at 1.0 Hz (target 1.0) = **0% miss** = perfect

The warning threshold can be relaxed in TOML:

```toml
[diagnostics.warnings]
thread_miss_warn_fraction = 0.20   # 20% tolerance instead of 10%
```

### Stall detection

A thread is flagged "STALLED" if it hasn't ticked in more than 5 seconds
AND it has a non-zero target frequency. This catches threads that have
genuinely hung — as opposed to threads that are just slightly slow.

A stalled thread is a serious problem. If the controller is stalled,
the gamepad doesn't respond. If the UI is stalled, the window freezes.
If you see a stall warning, check the fxmachine.log around that
timestamp for exceptions or deadlocks.

---

## Rate Limiter

The rate limiter (`src/diagnostics/rate_limiter.py`) is the only
"active" diagnostics component — everything else just observes, but
the rate limiter can actually **suppress events**.

### Why it exists

Without limiting, the UI update loop pushes a clip notification every
frame during a clip event = 40 notifications/sec. Or a misbehaving
thread could spam OSC sends to the same address, overwhelming Ableton.

### How it works

For each "limit name," the limiter keeps a deque of recent timestamps.
On `should_allow()`:

1. Evict timestamps older than the window
2. Count remaining timestamps
3. If count < limit → allow (record this timestamp)
4. If count >= limit → suppress (start cooldown period)

During cooldown, all calls are rejected until the cooldown expires.

### Configuration

Disabled by default. To enable:

```toml
[diagnostics.rate_limit]
enabled = true
clip_notifications_per_min = 20      # max clip notifications per minute
osc_sends_per_address_per_sec = 100  # max OSC sends per second per address
cooldown_s = 5.0                     # seconds of suppression after limit triggers
```

### Observability

Every suppression increments a counter:
- `clip_notification_suppressed_by_rate_limit`
- `osc_sends_suppressed_by_rate_limit`

These appear in the summary report so you can see how many events were
suppressed and decide whether to raise or lower the limits.

---

## The Reporter — Log Output

The reporter (`src/diagnostics/reporter.py`) writes two files:

### Text log (`logs/diagnostics.log`)

Human-readable summary blocks every `cfg.DIAG_SUMMARY_INTERVAL_S`
seconds (default 10). Each block contains:

- System metrics (CPU, RAM, threads)
- Thread health (per-thread Hz and miss fraction)
- Top functions by total time
- OSC traffic rates and totals
- Non-zero event counters
- Active rate-limiting state
- Warnings (threshold violations)
- Diagnostics overhead

The text log uses direct file writes (not Python's `logging` module).
This was a deliberate design choice — earlier versions used `logging`
and experienced write duplication when the logger's handler accumulated
across process lifetimes. Direct writes guarantee one write per call.

### JSONL log (`logs/diagnostics.jsonl`)

Machine-readable records, one JSON object per line. Event types:

```json
{"type": "session_start", "timestamp": 1748564400.0, ...}
{"type": "summary", "timestamp": 1748564410.0, "system": {...}, "threads": [...], ...}
{"type": "outlier", "function": "src.ui.updater.update_ui", "elapsed_ms": 213.45, ...}
{"type": "session_end", "timestamp": 1748564700.0, "uptime_s": 300.0, ...}
```

The JSONL format is designed for post-session analysis with Python,
pandas, or any tool that reads JSON.

### Rotation

Both files rotate at 5 MB with 10 backups:
- `diagnostics.log` → `diagnostics.log.1` → ... → `diagnostics.log.10`
- `diagnostics.jsonl` → `diagnostics.jsonl.1` → ... → `diagnostics.jsonl.10`

Maximum disk usage: 2 × 5 MB × 11 files = 110 MB

### Live tailing

Because the text log uses line-buffered mode, you can tail it in
real-time during a session:

```bash
# PowerShell
Get-Content logs\diagnostics.log -Wait -Tail 50

# WSL or Git Bash
tail -f logs/diagnostics.log
```

You'll see summaries appearing every 10 seconds as you use the app.

---

## The Post-Session Analyzer

The standalone CLI tool `analyze_diagnostics.py` reads the JSONL log
and produces a comprehensive breakdown of the entire session.

### Usage

```bash
python analyze_diagnostics.py                     # default location
python analyze_diagnostics.py --file PATH         # specific JSONL file
python analyze_diagnostics.py --no-rotated        # current file only
python analyze_diagnostics.py --json              # output raw JSON
```

### What it analyzes

1. **Session summary** — start/end times, duration, clean shutdown status
2. **System resource trends** — CPU min/avg/max/p95, memory growth rate
3. **Thread health** — per-thread average Hz, worst Hz, % unhealthy periods
4. **Top functions by time** — cumulative CPU consumption per function
5. **Worst p99 latencies** — functions with the worst tail latencies
6. **Outlier frequency** — which functions spike most often
7. **OSC traffic** — total sends/receives, peak rates, top addresses
8. **Event counters** — cumulative counts of all tracked events
9. **Warning patterns** — most common warnings, time clustering

### Including rotated backups

By default, the analyzer reads the main `.jsonl` plus all rotated
backups (`.jsonl.1` through `.jsonl.10`), giving you the full history.
Use `--no-rotated` to analyze just the current session.

### JSON output

The `--json` flag outputs the raw analysis dict as JSON, suitable for
piping to other tools or saving for comparison:

```bash
python analyze_diagnostics.py --json > session_report.json
```

---

## Reading a Diagnostics Summary

Here's a complete summary block with annotations:

```
══════════════════════════════════════════════════════════════════════
  DIAGNOSTICS SUMMARY — 2026-05-30 03:12:09  (uptime 4m 17s)
══════════════════════════════════════════════════════════════════════

SYSTEM
  CPU%   : avg  18.7  peak  23.5  (threshold 25%)
           ─── avg is the mean across all samples in the last 10 seconds.
               "threshold 25%" is cfg.DIAG_WARN_CPU_PERCENT — if avg
               exceeds this, a warning fires.

  RAM    :  48.0 MB  peak   50.6 MB  delta   +2.6 MB since startup
           ─── RSS (resident set size). "delta" is growth since the first
               sample. Stable growth of 1-3 MB then leveling off is normal.

  Threads: 8 avg, 8 peak
           ─── Expected: 8 (main + 5 daemons + sampler + reporter)

THREAD HEALTH
  ✓ controller   :  111.1 Hz / target  125.0 Hz  ( 11.1% missed)
  ✓ eq_ramp      :   59.2 Hz / target   62.5 Hz  (  5.3% missed)
  ✓ polling      :    2.0 Hz / target    2.0 Hz  (  0.0% missed)
  ✓ ui           :   36.8 Hz / target   40.0 Hz  (  8.0% missed)
  ✓ watchdog     :    1.0 Hz / target    1.0 Hz  (  0.0% missed)
     ─── ✓ = healthy (miss < threshold). ⚠ = unhealthy. ✗ = stalled.
         Actual Hz is computed from the last 10 seconds of tick data.

TOP FUNCTIONS BY TOTAL TIME
  function                                  calls    total     avg     p99
  ──────────────────────────────────────────────────────────────────────
  src.ui.updater.update_ui                   9426  17464ms   1.85ms  4.60ms
  src.ui.widgets.draw_djm_meter              9426   1024ms   0.11ms  0.61ms
     ─── "total" is cumulative CPU time since startup.
         "avg" is total/calls. "p99" is the 99th percentile of the
         rolling 1000-sample window (not cumulative).

OSC TRAFFIC (window 5.0s)
  Outbound:    5.0 msg/s  (1,361 total, 38 unique addresses)
  Inbound :   72.8 msg/s  (10,612 total, 20 unique addresses)
     ─── "window 5.0s" = rate calculated over the last 5 seconds.
         "total" is cumulative since startup.

✓ No warnings this period
     ─── If there were warnings, each would appear as:
         ⚠ CPU avg 38.3% > threshold 25.0%

  Diagnostics overhead so far: 161.9 ms cumulative
     ─── Total CPU time consumed by the diagnostics code itself.
         161ms across 4+ minutes = 0.07% overhead.
```

---

## Reading the JSONL Log

Each line in `diagnostics.jsonl` is one JSON object. Open it with any
text editor or parse it with Python:

```python
import json

with open("logs/diagnostics.jsonl") as f:
    events = [json.loads(line) for line in f if line.strip()]

# Filter to just summary events
summaries = [e for e in events if e["type"] == "summary"]

# Get CPU history
cpu_history = [
    (s["timestamp"], s["system"]["avg_cpu_percent"])
    for s in summaries
    if "system" in s
]
```

### Event types

**`session_start`** — first record, includes install summary

**`summary`** — periodic snapshot (every 10 seconds), contains:
- `system` — CPU, RAM, threads, GC, FDs
- `threads` — per-thread Hz and miss fraction
- `top_functions_by_total_time` — profiler top 10
- `top_functions_by_p99` — latency outliers
- `osc` — global traffic stats
- `osc_top_senders` / `osc_top_receivers` — per-address
- `counters` — non-zero event counts
- `warnings` — list of warning strings

**`outlier`** — one slow function call:
```json
{
    "type": "outlier",
    "function": "src.ui.updater.update_ui",
    "timestamp": 1748564523.456,
    "elapsed_ms": 213.45
}
```

**`session_end`** — final record with total uptime and overhead

### Analysis with pandas

```python
import pandas as pd
import json

with open("logs/diagnostics.jsonl") as f:
    events = [json.loads(line) for line in f if line.strip()]

summaries = [e for e in events if e["type"] == "summary"]

# CPU over time
df = pd.DataFrame([
    {"time": s["timestamp"], "cpu": s["system"]["avg_cpu_percent"]}
    for s in summaries if "system" in s
])

print(df.describe())
# Or plot: df.plot(x="time", y="cpu")
```

---

## Adding Custom Hooks

To profile a function that's not in the default hook list, add its
dotted path to `config/active.toml`:

```toml
[diagnostics.hooks]
timed_functions = [
    # ... existing entries ...
    "src.engine.navigation.navigate_scene",
    "src.engine.momentary.momentary_stutter_on",
]
```

Restart the app (hooks are [RESTART]-only — they're installed once at
startup). The function will appear in profiler output immediately.

### Requirements for hookable functions

The function must be:
1. A regular Python function (not a method on an instance — class
   methods work if called via the class, not via an instance)
2. Importable via its dotted path at install time
3. Not inside `src/diagnostics/` (the installer skips its own package)

### Verifying hooks installed

After starting the app with diagnostics enabled, check the main log:

```bash
findstr "diag.installer" logs\fxmachine.log
```

You should see lines like:

```
[diag.installer] OSC client send_message wrapped
[diag.installer] OSC server: wrapped 20 receive handler(s)
```

If a specific hook failed, you'll see a warning with the reason.

---

## Adding Custom Counters

To count a new event type, call `record_event()` from anywhere in the
codebase:

```python
from src.diagnostics import record_event

# In src/engine/actions.py, inside action_launch_clip():
def action_launch_clip():
    record_event("clip_launched")
    ...
```

The call is a no-op when diagnostics is disabled (zero overhead).
The counter auto-registers on first use — no need to pre-declare it.

To pre-register it (so it appears in reports even when count = 0),
add the name to the `KNOWN_COUNTERS` list in `src/diagnostics/counters.py`.

---

## Tuning Warning Thresholds

All warning thresholds are in `config/active.toml`:

```toml
[diagnostics.warnings]
clip_event_rate_per_min = 10        # warn if clipping > 10×/min
osc_send_rate_per_sec = 200         # warn if outbound > 200 msg/s
osc_recv_rate_per_sec = 300         # warn if inbound > 300 msg/s
single_call_warn_ms = 100.0         # warn if any function > 100ms
cpu_warn_percent = 25.0             # warn if CPU avg > 25%
memory_growth_warn_mb = 50.0        # warn if RAM growth > 50 MB
thread_miss_warn_fraction = 0.20    # warn if thread < 80% of target
```

All are [LIVE] — change them, press SELECT+START, and they take effect
immediately without restarting.

### Recommended tuning approach

1. Run a normal session with default thresholds
2. Check which warnings fire in the analyzer output
3. If a warning fires constantly but the behavior is normal (e.g.,
   controller at 111 Hz when target is 125), relax that threshold
4. If a warning never fires, consider tightening it to catch regressions

---

## Using Rate Limiting

Rate limiting is disabled by default. To enable:

```toml
[diagnostics.rate_limit]
enabled = true
clip_notifications_per_min = 20
osc_sends_per_address_per_sec = 100
cooldown_s = 5.0
```

### What gets limited

**Clip notifications:** The UI update loop checks `should_allow("clip_notifications")`
before pushing a clip notification. If the rate exceeds 20/min, subsequent
notifications are silently dropped until the cooldown expires.

**OSC sends per address:** The OSC client wrapper checks
`should_allow_keyed("osc_per_address", address)` before each send. If
a single address exceeds 100 msg/s, subsequent sends to that address are
dropped for the cooldown period.

### When to use it

Rate limiting is a self-defense mechanism for when something goes wrong.
Normal usage should never hit the default limits. If the limits trigger
during normal use, something else is broken (e.g., a runaway encoder
that's not respecting its throttle interval).

The diagnostic counters `clip_notification_suppressed_by_rate_limit` and
`osc_sends_suppressed_by_rate_limit` tell you when limiting has kicked in
and how many events were affected.

---

## Real-World Case Studies

### Case 1: The PhotoImage Meter Optimization

**Problem:** UI felt sluggish during audio playback.

**Diagnostics data:**

```
src.ui.widgets.draw_djm_meter    6423 calls    46122.0ms total    7.18ms avg    p99 19.90ms
```

**Interpretation:** `draw_djm_meter` consuming 20% of wall time. Called
every frame (6423 calls ÷ 227s = 28.3 Hz), taking 7ms average. Since the
UI target is 40 Hz (25ms per frame), the meter alone consumed 28% of each
frame's budget.

**Fix:** Replaced canvas-item rendering (340 items per frame) with
PhotoImage bitmap rendering (1-3 pixel updates per frame).

**Result after fix:**

```
src.ui.widgets.draw_djm_meter    9426 calls    1024.9ms total    0.11ms avg    p99 0.61ms
```

45× faster. CPU dropped from 85% to 20%.

### Case 2: The Listener Registration Leak

**Problem:** After several SELECT+START refreshes, the app became
sluggish and OSC traffic spiked.

**Diagnostics data:**

```
OSC TRAFFIC
  Inbound: 117.2 msg/s (much higher than expected ~70/s)

src.osc.discovery.fetch_all_names    26 calls    27554.1ms total
```

**Interpretation:** `fetch_all_names` ran 26 times in a 4-minute session
(should be 1-2 times). Each run registered a new set of listeners without
unregistering the old ones. After 4 refreshes, each parameter change was
firing 5 listener callbacks instead of 1.

**Fix:** Added `osc_stop_*_listeners()` calls at the start of
`fetch_all_names()` to unregister previous listeners before re-registering.

**Result:** `fetch_all_names` runs 1-2 times per session. Inbound OSC
rate dropped to normal ~70 msg/s.

### Case 3: The OSC Polling Overhead

**Problem:** Ableton's CPU increased from 12% to 39% when FX Machine
was running, even though FX Machine itself used only 5%.

**Diagnostics data:**

```
OSC TRAFFIC
  Outbound: 52 msg/s peak
  Top outbound: /live/song/get/tempo 6.8/s, /live/song/get/is_playing 6.8/s,
                /live/song/get/num_tracks 7.0/s, /live/song/get/num_scenes 7.0/s
```

**Interpretation:** Polling 5 static values at 6.8 Hz = 34 messages/sec
of pure waste (these values change less than once per session). Each poll
forces Ableton to look up the value and send a response, consuming CPU.

**Fix:** Replaced polling with AbletonOSC listener registrations. Ableton
now pushes updates only when values change. Polling loop reduced to 2 Hz
for safety re-polls only.

**Result:** Outbound OSC dropped from 52 msg/s to 5 msg/s. Ableton's CPU
delta from FX Machine dropped from +27% to +0% (invisible).

---

## Troubleshooting the Diagnostics Layer Itself

### Diagnostics won't enable

**Symptom:** `enabled = true` in TOML but no `diagnostics.log` appears.

**Check 1:** Is `init_config()` being called before `install_if_enabled()`?
Both are in `run.py` — verify they're in the right order.

**Check 2:** Is the TOML syntax valid?
```bash
python -c "import tomllib; tomllib.load(open('config/active.toml', 'rb')); print('OK')"
```

**Check 3:** Is the value actually reaching the singleton?
```bash
python -c "from src.config_loader import init_config, cfg; init_config(); print(cfg.DIAG_ENABLED)"
```

### Functions not appearing in profiler output

**Symptom:** You added a function to `timed_functions` but it doesn't
show in the TOP FUNCTIONS section.

**Cause 1:** Typo in the function path. Check spelling exactly.

**Cause 2:** The function is never called during the session. If it has
0 calls, it won't appear in reports.

**Cause 3:** The cross-module patch didn't reach the caller. Check the
main log for the "also patched" debug messages (enable DEBUG logging
to see them).

### Reporter writing duplicate lines

**Symptom:** Each summary block appears multiple times in the log.

**Cause:** This was a bug in earlier versions that used Python's `logging`
module. The v1.0.0 reporter uses direct file writes specifically to avoid
this. If you see duplication, make sure you're running the latest
`reporter.py` that uses `_write_text()` instead of `self._text_logger.info()`.

### "Fatal Python error: _enter_buffered_busy" on shutdown

**Symptom:** Crash message about stdout lock during interpreter shutdown.

**Cause:** A daemon thread (sampler or reporter) is still writing to stdout
when the main thread has started Python's finalization sequence.

**Fix:** Ensure `shutdown_diagnostics()` is called BEFORE `root.destroy()`
and BEFORE `sys.exit()` in `main.py`'s `on_close()` handler. Also ensure
the controller loop checks `_shutting_down` at the top of each iteration
to exit before attempting any I/O.

---

## Performance Cost of Diagnostics

### CPU overhead

The diagnostics layer adds approximately 1-2% of one core when enabled.
This breaks down as:

| Component | Cost | Frequency |
|---|---|---|
| Function timing wrappers | ~200ns per call | ~10,000 calls/sec across all hooks |
| OSC send tracking | ~100ns per send | ~5-50 sends/sec |
| OSC receive tracking | ~100ns per receive | ~70 receives/sec |
| Thread health ticks | ~50ns per tick | ~230 ticks/sec (all threads combined) |
| System sampler | ~2ms per sample | 1 Hz |
| Reporter summary | ~5ms per summary | Every 10 seconds |
| JSONL writes | ~0.5ms per write | Every 10 seconds + outliers |

Total: ~2ms/sec of CPU = 0.2% of one core.

### Memory overhead

| Component | Memory |
|---|---|
| Profiler rolling windows | 16 functions × 8 KB = 128 KB |
| Counter timestamp deques | 35 counters × 480 B = 17 KB |
| OSC tracker per-address stats | ~30 addresses × 16 KB = 480 KB |
| System sampler ring buffer | 600 samples × 80 B = 48 KB |
| Thread health tick deques | 5 threads × 4 KB = 20 KB |
| Reporter file handles | 2 file handles |
| **Total** | **~700 KB** |

### Self-measurement

The reporter includes a "diagnostics overhead" counter in every summary:

```
Diagnostics overhead so far: 161.9 ms cumulative
```

This is measured by wrapping the diagnostics' own code in
`diag.time_diag_overhead()`, which adds nanoseconds to `diag.diag_overhead_ns`.
161ms across a 4-minute session = 0.07% of wall time.

---

## TOML Configuration Reference

### `[diagnostics]`

| Key | Type | Default | [LIVE] | Description |
|---|---|---|---|---|
| `enabled` | bool | `false` | ✓ | Master on/off switch |
| `log_path` | string | `"logs/diagnostics.log"` | RESTART | Text log path |
| `jsonl_path` | string | `"logs/diagnostics.jsonl"` | RESTART | JSONL log path |
| `summary_interval_s` | float | `10.0` | ✓ | Summary frequency |
| `sample_interval_s` | float | `1.0` | ✓ | System sample rate |
| `slow_function_threshold_ms` | float | `5.0` | ✓ | Outlier flagging threshold |
| `slow_frame_threshold_ms` | float | `50.0` | ✓ | UI frame warning threshold |
| `osc_traffic_window_s` | float | `5.0` | ✓ | OSC rate calculation window |
| `jsonl_format` | string | `"compact"` | ✓ | `"compact"` or `"pretty"` |
| `jsonl_include_osc_args` | bool | `false` | ✓ | Include message payloads |

### `[diagnostics.warnings]`

| Key | Type | Default | Description |
|---|---|---|---|
| `clip_event_rate_per_min` | int | `10` | Clip rate warning threshold |
| `osc_send_rate_per_sec` | int | `200` | Outbound OSC rate warning |
| `osc_recv_rate_per_sec` | int | `300` | Inbound OSC rate warning |
| `single_call_warn_ms` | float | `100.0` | Single-call duration warning |
| `cpu_warn_percent` | float | `25.0` | CPU usage warning |
| `memory_growth_warn_mb` | float | `50.0` | Memory growth warning |
| `thread_miss_warn_fraction` | float | `0.20` | Thread health warning |

### `[diagnostics.rate_limit]`

| Key | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Enable adaptive throttling |
| `clip_notifications_per_min` | int | `20` | Max clip notifs per minute |
| `osc_sends_per_address_per_sec` | int | `100` | Max OSC sends per address |
| `cooldown_s` | float | `5.0` | Suppression duration |

### `[diagnostics.hooks]`

| Key | Type | Default | Description |
|---|---|---|---|
| `timed_functions` | list | 16 functions | Functions to profile |
| `track_all_osc_sends` | bool | `true` | Track every outbound OSC |
| `track_all_osc_receives` | bool | `true` | Track every inbound OSC |
| `tracked_osc_addresses` | list | 4 prefixes | Filtered OSC addresses |

---

## File Reference

| File | Lines | Purpose |
|---|---|---|
| `__init__.py` | ~180 | Public API, singleton, convenience proxies |
| `installer.py` | ~350 | Hook installation + cross-module patching |
| `profiler.py` | ~250 | Per-function timing with rolling percentiles |
| `counters.py` | ~220 | Event counters with rate tracking |
| `osc_tracker.py` | ~280 | Per-address OSC traffic accounting |
| `sampler.py` | ~300 | System resource sampling thread |
| `thread_health.py` | ~200 | Thread frequency monitoring |
| `rate_limiter.py` | ~250 | Adaptive event throttling |
| `reporter.py` | ~450 | Text + JSONL log writers |
| `analyzer.py` | ~400 | Post-session analysis module |

Total: ~2,880 lines of diagnostics code.

---

## Design Decisions and Trade-Offs

### Why monkey-patching instead of decorators?

Decorators require modifying source files. Monkey-patching keeps all
diagnostics code inside `src/diagnostics/` — you can delete the entire
folder and the app works exactly as before. This separation was a
deliberate design constraint: the diagnostics layer should be removable
with zero impact.

The trade-off is that monkey-patching is more complex and fragile than
decorators. The cross-module patch (walking `sys.modules`) is a hack
that works reliably but looks unusual. If Python's import system ever
changes how `from X import Y` works, the patch might break. In practice,
this mechanism has been stable since Python 2 and is unlikely to change.

### Why direct file writes instead of Python's logging module?

Python's `logging.getLogger()` returns a singleton by name. Handlers
accumulate across process lifetimes if not carefully managed. Multi-line
messages get fragmented by formatters. Unicode characters in box-drawing
summaries were split into separate log records, each appearing as its
own line with the formatter prefix duplicated.

Direct file writes (`open("a", encoding="utf-8", buffering=1)`) give
complete control: one `write()` call = one block in the file. No
formatters, no handlers, no propagation, no stacking.

### Why not `cProfile` or `py-spy`?

Python's built-in `cProfile` is a statistical profiler — it samples the
call stack periodically and estimates time. It can't tell you "this
specific call to `draw_djm_meter` at 02:38:15.123 took 141ms." Our
profiler measures every call individually with nanosecond resolution.

`py-spy` is an excellent external sampling profiler but requires a
separate process and doesn't integrate with the app's own logging,
counters, or OSC tracking. Our diagnostics layer is self-contained
and correlates performance data with application-specific events.

### Why bounded data structures?

Every data collection structure has a hard cap on memory:
- Profiler: 1000 samples per function (deque maxlen)
- Counters: 1 timestamp per event, 60-second rolling window
- OSC tracker: same pattern
- Sampler: 600 samples (10 minutes at 1 Hz)
- Thread health: 500 ticks per thread
- Outliers: 100 per function
- Rate limiter: one deque per limit

This guarantees the diagnostics layer never causes memory growth
regardless of session length. A 6-hour live set produces the same
memory footprint as a 2-minute test.

### Why try/except around every diagnostics call?

Diagnostics must NEVER crash the host app. Every hook, every callback,
every data access is wrapped in try/except. If the profiler has a bug,
it logs the error and the wrapped function still returns its result.
If the reporter can't write to disk, it prints to stderr and continues.

This is the #1 design rule: **a broken diagnostics layer is invisible
to the user, not catastrophic.**

---

*This document describes the diagnostics layer as shipped in FX Machine
v1.0.0. The implementation may evolve as new collectors or analysis
tools are added. The TOML configuration interface is stable and backward
compatible.*
```
