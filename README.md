
---

<div align="center">

# 🎛️ FX Machine

### A USB Gamepad Turned Into a Live Performance Instrument for Ableton Live

*Built by a DJ, for DJs. Modeled after the Pioneer DJM-900 NXS2 channel strip.*

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org)
[![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey.svg)]()
[![Ableton](https://img.shields.io/badge/Ableton-Live%2010%2F11%2F12-black.svg)](https://www.ableton.com)
[![Version](https://img.shields.io/badge/version-v1.0.0-green.svg)]()
[![License](https://img.shields.io/badge/license-Non--Commercial-red.svg)](#-license)

**v1.0.0** · First stable release · TOML hot-reload · Diagnostics layer · PhotoImage meter · Listener-based architecture

</div>

---

## 🎯 What It Does

FX Machine bridges a generic USB gamepad to Ableton Live via OSC, exposing a **3-band kill EQ + TRIM**, an **8-macro FX rack**, and a **DJM-900 NXS2 style channel meter** through a custom gesture vocabulary. Push a stick, hold a button, double-flick to fire a kill — all in real time, with values you tune through a plain-text config file while the app is running.

It is not a MIDI mapping. It's a performance instrument with its own gesture engine, safety logic, visual feedback, hot-reloadable configuration, and a built-in diagnostics profiler that tells you exactly how every part of the system is performing.

```
       Gamepad ──── USB ──── FX Machine ──── OSC ──── Ableton Live
                              (Python)              (AbletonOSC)
                                  │
                                  ├─── Real-time UI
                                  │    (knobs · meters · status)
                                  │
                                  └─── Diagnostics Layer
                                       (profiler · counters · analyzer)
```

---

## 🚀 Quick Start

### Option A — Run from source (Python 3.12+)

```bash
pip install pygame python-osc psutil
python run.py
```

`psutil` is optional — enables CPU/RAM monitoring in the diagnostics layer. The app runs without it.

### Option B — Run the portable .exe (no Python needed)

1. Download the `FX_Machine.rar` release
2. Extract and double-click `FX_Machine/FX_Machine.exe`
3. On first launch it creates `config/active.toml` automatically

To build the .exe yourself:

```bash
pip install pyinstaller
python build.py
```

Output appears at `dist/FX_Machine/FX_Machine.exe`. To distribute: zip the entire `dist/FX_Machine/` folder and share it.

### Verify your setup

Before your first session, run the diagnostic tool — it runs 150+ automated health checks:

```bash
python diagnose.py
```

Green checks mean you're good to perform. Red errors tell you exactly what to fix.

---

## ✨ What's In This Release (v1.0.0)

### Core Features

| Feature | Description |
|---|---|
| **3-Band Kill EQ** | Low / Mid / High with double-flick gestures for kill, normalize, restore, asymptotic boost |
| **TRIM Knob** | Input gain control before the EQ Three, DJM-900 NXS2 style (-∞ to +9 dB cap) |
| **8-Macro FX Rack** | Filter Freq, Filter Mode, Filter Res, Stutter, Reverb Size, FX Send, Delay FB, Width |
| **DJM Channel Meter** | 22-segment LED meter with peak hold, dB labels, and 2-stage CLIP indicator |
| **Momentary Effects** | L1+X Stutter, L1+O Bass Cut, L1+□ FX Send Throw — all with snapshot/restore |
| **Session Navigation** | Scene/Track/Bookmark/Group navigation via D-pad and L-stick |
| **TOML Hot-Reload** | Edit config while the app runs, press SELECT+START to apply |
| **Diagnostics Layer** | Optional runtime profiler, OSC traffic analyzer, thread health monitor |
| **Portable .exe** | PyInstaller onedir build — no Python needed on the target machine |

### Architecture Highlights

| Component | Detail |
|---|---|
| **5 daemon threads** | UI (40 Hz), Controller (125 Hz), Polling (2 Hz), EQ Ramp (60 Hz), Watchdog (1 Hz) |
| **Listener-based OSC** | Session metadata pushed by Ableton — no polling for tempo, transport, counts |
| **PhotoImage meter** | Single-bitmap incremental rendering — 45× faster than canvas-item approach |
| **Cross-module hook profiler** | Monkey-patches timing wrappers into any function without modifying source |
| **Thread-safe shared state** | Single RLock, Rule 2 (no OSC inside locks), snapshot pattern for UI reads |

---

## 🎚️ The Signal Chain (DJM-900 NXS2 Style)

Two racks inserted in series before your master output, replicating a real DJ mixer channel strip:

```
All instrument tracks ──▶ Return A
                              │
                              ▼
                       ~ EQ Macros      (TRIM + 3-band kill EQ — shapes the source)
                              │
                              ▼
                       ~ FX Macros      (filter / reverb / delay / stutter)
                              │
                              ▼
                          Master
```

EQ comes first (you decide what frequencies survive), FX comes second (you decide what to do with what survived). Same topology as a Pioneer DJM-900 NXS2 channel strip.

### Internal FX Rack Topology — the wet/dry trick

Most macro mappings put effects in series: Filter → Reverb → Delay → Output. That's wrong for live performance. You want the dry signal to **always pass through**, and effects to add on top without ever replacing the dry. You also want reverb and delay tails to **continue ringing** when you stop sending to them.

The solution is a **nested wet/dry rack**:

```
~ FX Macros (Audio Effect Rack)
│
├── Auto Filter           ← always on the main path
│                            (Filter Freq + Filter Mode + Filter Res macros)
│
├── Beat Repeat           ← always on the main path
│                            (Stutter macro)
│
├── ┌─[ Nested Wet/Dry Rack ]──────────────────────┐
│   │                                              │
│   ├── Chain "Dry"  ─────────▶ passes through     │
│   │   (completely empty — direct signal)         │
│   │                                              │
│   └── Chain "Wet"                                │
│       │                                          │
│       ├── Utility    ◀── FX Send macro (gain)   │
│       │   (controls how much signal enters       │
│       │    the wet processing chain)             │
│       │                                          │
│       ├── Dark Hall  ◀── Reverb Size macro      │
│       │   (long reverb, holds tails)             │
│       │                                          │
│       └── Long Digi Delay ◀── Delay FB macro    │
│           (long delay, feedback loop)            │
│                                                  │
└── └──────────────────────────────────────────────┘
│
└── Utility               ← Width macro
    (stereo width on the combined dry+wet output)
```

**FX Send macro controls the GAIN of the input to the wet chain, not the wet/dry mix.** When FX Send = 0, no new signal enters the wet processing, BUT the reverb and delay already inside the wet chain continue to decay/feed back naturally. This is exactly how a Pioneer DJM-900's send/return loop works.

### The "throw and let it tail" technique

```
1. Press L1+□        → FX Send jams to 100% (full feed to wet chain)
2. Hold for 1-2 bars  → big wet swell builds up
3. Release            → FX Send snaps back to previous value
4. Dry continues clean throughout
5. Reverb/delay tails ring for 5-30+ seconds
```

You can stack throws to build walls of tails. Then kill the bass and drop a fresh element. Classic Ben Böhmer / Yotto / Nora En Pure move.

---

## 🎚️ EQ Engine — How It Works

The EQ engine is the most sophisticated part of FX Machine. Three EQ bands plus TRIM controlled by one stick, with two distinct gesture vocabularies that don't interfere with each other.

### What's on each band

| Band | Macro | Cut limit | Boost limit (encoder) | Boost limit (double-flick) |
|---|---|---|---|---|
| **LOW** | EQ Three `GainLow` | -∞ dB (full kill) | **+2 dB** (safety cap) | 🚫 **BLOCKED** (sub safety) |
| **MID** | EQ Three `GainMid` | -19 dB / -∞ (encoder) | +6 dB | +6 dB (asymptotic) |
| **HIGH** | EQ Three `GainHi` | -19 dB / -∞ (encoder) | +6 dB | +6 dB (asymptotic) |
| **TRIM** | Utility Gain | -∞ dB | +9 dB (DJM-900 cap) | Normalize to 0 dB only |

### Continuous encoder (X-axis)

The encoder is **velocity-based**: stick position determines how fast the value changes, not what the value is. This is how Pioneer's rotary encoders work.

```
Stick at rest:           value stays where it is
Stick pushed right:      value increases over time
Stick pushed left:       value decreases over time
Stick released:          value HOLDS at current position
```

The encoder math:

```python
delta = (macro_range / sweep_seconds) × (stick_deflection ^ curve_exp) × dt
```

All parameters are hot-reloadable via TOML:
- `sweep_seconds = 0.30` — time to sweep full range at max deflection
- `curve_exp = 1.0` — linear response (higher = more precise near rest)
- `smoothing_factor = 0.55` — exponential stick smoothing

### Double-flick gestures

Same stick handles BOTH encoder AND discrete actions via double-flicks. A "flick" is movement reaching 90% extreme deflection within 380ms.

```
       extreme         center         extreme
  idle ────────▶ flicked ─────▶ returned ─────▶ confirmed → fire action
  ◀─────── timeout (380ms) ──────────────────▶ reset
```

**X double-flick LEFT** (smart kill / normalize):
- If value > 0 dB → normalize to 0 dB
- If value ≤ 0 dB → KILL (Bass = -∞, Mid/High = -19 dB)

**X double-flick RIGHT** (smart restore / boost):
- If value < 0 dB → restore to 0 dB
- If value ≥ 0 dB + Mid/High → +15% headroom boost (asymptotic)
- If value ≥ 0 dB + Bass → 🚫 BLOCKED (sub safety)

**Y double-flick UP/DOWN** — band navigation (4-position rotation including TRIM):
```
Y up:   MID → HIGH → TRIM → LOW → MID → ...   (wraps)
Y down: reverse
```

### Cross-axis safety (mutual exclusion)

Both axes use mutual exclusion. Y-dominance ratio (3.0×) prevents accidental band switches during value adjustments. Once one axis wins, the other is frozen until the first completes or times out.

### Animated transitions (cubic ease-out)

When a gesture triggers an action, the value animates smoothly using cubic ease-out:

```python
eased = 1.0 - (1.0 - progress) ** 3
```

Ramp duration scales with flick speed: fast flick → 30ms ramp (snappy), slow flick → 100ms ramp (smooth).

### TRIM — special behavior

TRIM controls a Utility Gain device BEFORE the EQ Three (input trim, -∞ to +9 dB). Its visual range is mapped so the knob indicator reaches the full-right position (5 o'clock) at the configured +9 dB cap, matching real DJM-900 NXS2 trim behavior.

TRIM double-flicks only normalize toward 0 dB — no kill, no boost stacking. The +9 dB hard cap IS the safety mechanism.

---

## ⚡ FX Engine — How It Works

The FX engine uses an **integrator model** with acceleration. Holding the stick longer increases the rate of change.

```python
delta = stick_value × (macro_range / sweep_seconds) × dt × accel_mult
```

Where `accel_mult` ramps from 1.0 to 4.0 over 1 second when holding the stick in one direction.

### Per-macro sweep times

| Macro | Default sweep | Why |
|---|---|---|
| Filter Freq | 1.5 s | Most-played — fast for builds, slow enough for control |
| Filter Res | 3.0 s | "Set and forget" most of the time |
| Reverb Size | 5.0 s | Rarely swept during a track |
| FX Send | 1.0 s | Punchy throws need quick response |

### Momentary buttons — snapshot/restore

Three buttons trigger momentary effects with pre-engage snapshot:

| Button | Effect | Press | Release |
|---|---|---|---|
| L1 + X | **STUTTER** | Beat Repeat ON | Beat Repeat OFF |
| L1 + O | **BASS CUT** | HP filter @ 200 Hz | Restore freq + mode |
| L1 + □ | **FX THROW** | FX Send → 100% | Restore to snapshot |

### L1 release recovery

When L1 is released, recovery logic runs per-slot:
- Filter Freq → baseline (unless filter-locked)
- FX Send → 0 (unless wet-locked)
- Stutter → always 0
- Everything else → stays where you set it

### Delay FB — discrete D-pad stepping

20 steps across the range, capped at 92% to prevent runaway feedback. Debounced at 180ms.

---

## 📊 DJM-Style Channel Meter

A 22-segment vertical LED meter beside the EQ stack shows real-time audio output level from the EQ track via Ableton's `output_meter_left/right` listeners.

### PhotoImage bitmap rendering (v1.0.0 optimization)

Previous versions used ~340 Tkinter canvas items per frame (rectangles, ovals, lines). Profiling with the diagnostics layer revealed this consumed 20% of one CPU core — 46 seconds of CPU in a 4-minute session.

The v1.0.0 meter uses a **single `tk.PhotoImage` bitmap** with incremental pixel updates:

```
Before:  38,520 ms total    avg 6.26 ms per frame    p99 18.05 ms
After:    1,024 ms total    avg 0.11 ms per frame    p99 0.61 ms
```

**45× faster average, 30× fewer outliers.**

The bitmap tracks which LED segments changed state since last frame and only repaints those (typically 1-3 segments per frame during audio playback). The CLIP indicator and dB labels are canvas items updated via `itemconfig` (no creation/destruction).

### CLIP indicator

Two-stage warning with smooth color interpolation:
- **+6 dB**: yellow warning (solid)
- **+7.5 dB**: orange transition
- **+9 dB**: red critical (flickering at 4 Hz)

Fadeout after the signal drops below the warning threshold (0.5 seconds).

---

## 🔧 Architecture — 5-Thread Coordination Model

```
┌─────────────────────────────────────────────────────────────┐
│   Main Thread (Tkinter UI, 40 Hz)                           │
│   ├─ Reads state dict every 25 ms                           │
│   ├─ Renders knobs, meters, labels                          │
│   └─ Schedules itself via root.after()                      │
└────────────────────┬────────────────────────────────────────┘
                     │ reads state[*]
                     ▼
              ┌─────────────────────┐
              │  shared state dict  │  ◀──── all threads converge here
              │  protected by RLock │       (state = {...} in src/state.py)
              └─────────────────────┘
                     ▲    ▲    ▲    ▲
   ┌─────────────────┘    │    │    └─────────────────┐
   │                      │    │                      │
┌──┴──────────────┐  ┌────┴────┐  ┌─────┴──────┐  ┌──┴──────────────┐
│ Controller      │  │  OSC    │  │  Polling   │  │  Watchdog       │
│ Thread (125 Hz) │  │ Server  │  │  Thread    │  │  Thread (1 Hz)  │
│                 │  │ Thread  │  │  (2 Hz)    │  │                 │
│ pygame events   │  │         │  │            │  │ Controller      │
│ axis sampling   │  │ Receive │  │ Safety     │  │ health checks   │
│ gesture engine  │  │ from    │  │ polls      │  │ Ghost-event     │
│ writes to       │  │ Ableton │  │            │  │ reconciliation  │
│ Ableton via OSC │  │ Update  │  │            │  │ Auto-reprobe    │
│                 │  │ state   │  │            │  │                 │
└─────────────────┘  └─────────┘  └────────────┘  └─────────────────┘

                              + EQ Ramp Thread (60 Hz)
                                Animates kill/normalize/boost
                                Smooth cubic ease-out transitions
```

### Listener-Based Architecture (v1.0.0)

Session metadata (tempo, transport state, track/scene counts) is now pushed via AbletonOSC listeners rather than polled. This eliminated ~30 OSC messages per second of background traffic and reduced Ableton's CPU overhead to effectively zero.

**Measured impact:**

| Metric | Before (polling) | After (listeners) | Improvement |
|---|---|---|---|
| OSC outbound rate | 52 msg/s | 5 msg/s | **-90%** |
| Ableton CPU delta | +27% over baseline | **+0%** | **eliminated** |
| Polling loop rate | 6.6 Hz | 2.0 Hz | Safety-net only |

The polling loop still runs at 2 Hz as a safety net for catching drift from missed listener events, but it no longer sends routine queries.

### Lock Strategy

Three rules govern all lock usage:

1. **Always hold the lock when reading or writing `st.state`**
2. **NEVER call OSC functions while holding the lock** (prevents I/O-bound lock holds)
3. **Use RLock so nested calls don't self-deadlock**

---

## 🔍 Diagnostics Layer — Runtime Performance Profiler

FX Machine includes a complete, optional diagnostics layer that observes the running app and reports detailed performance metrics. It's the engineering equivalent of a car's OBD-II port — you plug it in when you want to know what's happening inside.

### Architecture

The diagnostics layer is a self-contained package (`src/diagnostics/`) that hooks into the running app via monkey-patching. **Zero modifications to any source file outside `src/diagnostics/` are needed** — the hooks install themselves at startup by replacing function references in loaded modules.

```
src/diagnostics/
├── __init__.py        ← public API + diag singleton
├── installer.py       ← monkey-patch hook installer
├── profiler.py        ← per-function timing stats
├── counters.py        ← event counters with rate tracking
├── osc_tracker.py     ← per-address OSC traffic accounting
├── sampler.py         ← CPU/RAM/thread sampling (psutil)
├── thread_health.py   ← per-thread frequency monitoring
├── rate_limiter.py    ← adaptive throttling
├── reporter.py        ← text + JSONL log writers
└── analyzer.py        ← post-session analysis module
```

### How to enable

In `config/active.toml`, set:

```toml
[diagnostics]
enabled = true
```

When disabled (the default), there is **zero runtime cost** — the diagnostics module isn't even imported.

When enabled, expect ~1-2% CPU overhead and ~5-10 MB memory for rolling stats buffers.

### What it measures

**Per-function timing** — 16 instrumented functions tracked with mean, median, p95, p99, max, outlier logging. The profiler uses a rolling window of 1000 samples per function for percentile calculations, plus cumulative totals since startup.

```
TOP FUNCTIONS BY TOTAL TIME
  function                                     calls       total       avg       p99
  ────────────────────────────────────────────────────────────────────────────────
  src.ui.updater.update_ui                      9426    17464.9ms     1.85ms     4.60ms
  src.osc.discovery.fetch_all_names                2    11049.2ms  5524.60ms  5526.61ms
  src.ui.widgets.draw_djm_meter                 9426     1024.9ms     0.11ms     0.61ms
  src.ui.widgets.draw_knob                     75408      307.0ms     0.00ms     0.01ms
  src.ui.widgets.draw_eq_knob                  28278      279.1ms     0.01ms     0.80ms
```

**OSC traffic accounting** — every inbound and outbound OSC message tracked by address. Rolling window for rate calculation, peak burst detection, cumulative totals.

```
OSC TRAFFIC (window 5.0s)
  Outbound:    5.0 msg/s  (1,361 total, 38 unique addresses)
  Inbound :   72.8 msg/s  (10,612 total, 20 unique addresses)

  Top inbound addresses:
    /live/track/get/output_meter_left       4753 total  peak 30.4/s
    /live/track/get/output_meter_right      4753 total  peak 30.4/s
```

**Thread health monitoring** — each of the 5 daemon threads reports a heartbeat on every iteration. The monitor compares actual frequency to the target and flags threads that miss their deadlines.

```
THREAD HEALTH
  ✓ 0% unhealthy      eq_ramp      target   62.5 Hz   avg   59.2 Hz
  ✓ 0% unhealthy      polling      target    2.0 Hz   avg    2.0 Hz
  ✓ 4% unhealthy      ui           target   40.0 Hz   avg   36.8 Hz
  ✓ 0% unhealthy      watchdog     target    1.0 Hz   avg    1.0 Hz
```

**System resource sampling** — CPU%, RAM, thread count, GC activity, file descriptors. Sampled every second via `psutil` (falls back gracefully if `psutil` is unavailable).

```
SYSTEM
  CPU%   : avg  18.7  peak  23.5  (threshold 25%)
  RAM    :  48.0 MB  peak   50.6 MB  delta   +2.6 MB since startup
  Threads: 8
```

**Event counters** — 35+ named events (clip events, gesture activations, mode switches, OSC errors) with cumulative totals and per-minute rolling rates.

**Warning system** — configurable thresholds for CPU usage, memory growth, OSC traffic rates, thread miss fractions, and individual slow function calls. Warnings appear in the summary log and are aggregated by the analyzer.

### Cross-module monkey-patching (how the hooks work)

The diagnostics installer wraps target functions by replacing their references in both the origin module AND every other module that imported them. This solves Python's `from X import Y` semantics where the caller gets a local reference to the original function:

```python
# installer.py — simplified
for mod_name, mod_obj in sys.modules.items():
    if mod_obj is not origin_module:
        for attr_name, attr_value in vars(mod_obj).items():
            if attr_value is original_function:
                setattr(mod_obj, attr_name, wrapper)
```

This ensures the timing wrapper intercepts every call path, not just those that go through the origin module. Without this, functions called via `from src.ui.widgets import draw_djm_meter` would bypass the profiler entirely.

### Output files

| File | Format | Content | Rotation |
|---|---|---|---|
| `logs/diagnostics.log` | Human-readable text | Summary blocks every 10 seconds | 5 MB × 10 backups |
| `logs/diagnostics.jsonl` | JSON Lines (machine-readable) | Per-event records for analysis | 5 MB × 10 backups |

### Post-session analyzer

```bash
python analyze_diagnostics.py
```

Reads the JSONL log and produces a comprehensive breakdown:

```
━━━ SESSION OVERVIEW ━━━
  Start time         2026-05-30 03:10:29
  Duration           4m 17s
  Clean shutdown     ✓ yes

━━━ SYSTEM RESOURCES ━━━
  CPU usage: min 13.7%  avg 18.7%  p95 23.2%  max 23.5%
  Memory:    48.0 MB → 50.6 MB  (+2.6 MB, +0.63 MB/min)

━━━ TOP FUNCTIONS BY TOTAL TIME ━━━
  src.ui.updater.update_ui       9426 calls   17464.9ms total   1.85ms avg
  src.ui.widgets.draw_djm_meter  9426 calls    1024.9ms total   0.11ms avg
  ...

━━━ WARNINGS SUMMARY ━━━
  Total warnings: 50
  Most common: fetch_all_names slow calls (26×), thread misses (21×)
```

### Tunable parameters

~25 diagnostics parameters in `config/active.toml` under `[diagnostics]`, `[diagnostics.warnings]`, `[diagnostics.rate_limit]`, and `[diagnostics.hooks]`. All are documented with comments explaining what each value controls.

### How the diagnostics found real bugs

During development, the diagnostics layer discovered three bugs that would have been invisible otherwise:

1. **OSC dispatcher overwrite** — `pythonosc.Dispatcher.map()` only allows one handler per address. Both FX and EQ single-param listeners were mapped to the same address, causing the second to silently overwrite the first. FX live updates were being dropped. The diagnostics traffic analysis showed zero inbound FX parameter updates.

2. **Listener registration leak** — Each manual refresh (SELECT+START) registered a new set of listeners without unregistering the old ones. After 4 refreshes, Ableton was sending each parameter change 5 times. The diagnostics OSC tracker showed inbound message rates that didn't match the expected 1:1 ratio.

3. **PhotoImage meter bottleneck** — The function profiler showed `draw_djm_meter` consuming 20% of CPU (46 seconds in a 4-minute session). This led directly to the PhotoImage rewrite that achieved a 45× speedup.

---

## 🎮 Full Controller Map

### Navigation Layer (default)

| Input | Action |
|---|---|
| L-stick X / Y | Track / Scene navigation (hold to auto-scroll) |
| D-pad ↑ / ↓ | Bookmark prev/next |
| D-pad ← / → | Group prev/next |
| ✕ | Launch clip |
| ○ | Stop clip |
| △ | Launch scene |
| □ | Arm track |
| L2 | Stop track |
| R2 (hold) | Safety gate (prevents accidental launches) |
| START | Play/stop transport |
| R3 | Toggle EQ mode |

### FX Mode (hold L1)

| Input | Action |
|---|---|
| L-stick Y | Filter Freq (with acceleration) |
| L-stick X | Filter Res |
| R-stick | FX Send + Reverb Size (rotation-corrected) |
| D-pad ↑ / ↓ | Bookmark prev/next |
| D-pad ← / → | Delay FB step (1/20 of range) |
| L1 + ✕ | 💥 STUTTER (momentary) |
| L1 + ○ | 🔻 BASS CUT (momentary, snapshot restore) |
| L1 + △ | Launch scene |
| L1 + □ | 🌫 FX SEND THROW (momentary, snapshot restore) |
| L1 + L3 | Toggle filter lock |
| L1 + R3 | Toggle wet lock |

### EQ Mode (tap R3 to enter / exit)

| Input | Action |
|---|---|
| R-stick X (hold) | Encoder: right = boost, left = cut, release = HOLD |
| R-stick Y ↑↑ | Switch band up (wraps: MID → HIGH → TRIM → LOW → MID) |
| R-stick Y ↓↓ | Switch band down (wraps reverse) |
| R-stick X ←← | Smart kill / normalize |
| R-stick X →→ | Smart restore / boost (bass blocked at ≥ 0 dB) |

### Modifier Combos (hold SELECT)

| Input | Action |
|---|---|
| SELECT + R-stick Y | Track volume control |
| SELECT + R3 | Volume mute toggle (single tap = unity, double tap = mute) |
| SELECT + R1 | Save FX baseline |
| SELECT + START | Full refresh (TOML reload + Ableton session refresh) |

---

## 🔒 Safety Features

Built for live performance where errors are unacceptable.

- **Bass boost cap** — encoder cannot push bass above +2 dB
- **Bass double-flick boost blocked** — protects subs and listeners
- **Delay feedback cap** — limited to 92% to prevent runaway
- **R2 safety gate** — prevents accidental clip/scene launches
- **Filter + Wet locks** — lock state against L1-release recovery
- **FX baseline snapshot** — auto-captures startup values, restorable any time
- **Pre-engage snapshots** — momentary effects restore exactly what was there
- **Ghost-event reconciliation** — auto-recovers from dropped SELECT release events
- **Controller auto-reprobe** — detects silent disconnects within 5 seconds
- **Listener-based OSC** — eliminates polling overhead on Ableton's CPU
- **Throttled OSC writes** — prevents flooding (25ms FX / 15ms EQ minimums)
- **Epsilon culling** — skips writes when value change is imperceptible
- **TOML reload protection** — broken configs keep last working values
- **Clean shutdown sequencing** — diagnostics → listeners → OSC server → Tkinter, with idempotency guard against double-close

---

## ⚙️ Configuration

FX Machine ships with a TOML-based configuration system. Changes apply instantly via `SELECT + START` on the controller — no app restart needed for most settings.

### Config folder

```
config/
├── default.toml          Factory template — don't edit (safety net)
├── active.toml           Your current settings — edit this
├── EXAMPLES.toml         5 ready-to-copy preset snippets
├── README.md             Config folder explainer
└── presets/              Save your own profiles here
```

### What you can tune

**~55 hot-reloadable parameters** spanning:

| Section | Controls |
|---|---|
| `[eq.encoder]` | Sweep speed, curve shape, smoothing, deadzone |
| `[eq.flick]` | Double-flick timing thresholds |
| `[eq.detent]` | Sticky 0 dB feel near unity |
| `[eq.ramp]` | Animation duration for actions |
| `[eq.safety]` | Bass boost cap, headroom boost percentage |
| `[trim]` | TRIM knob feel, max dB cap |
| `[meter]` | Channel meter ballistics, peak hold |
| `[meter.clip]` | CLIP indicator thresholds and flicker |
| `[fx]` | Per-macro sweep speeds, acceleration |
| `[fx.delay_fb]` | Delay feedback discrete stepping |
| `[volume]` | SELECT+R-stick volume sensitivity |
| `[navigation]` | Track/scene scrolling responsiveness |
| `[timing]` | Polling, watchdog, debounce intervals |
| `[ui]` | UI refresh rate, window size [RESTART] |
| `[network]` | OSC ports [RESTART] |
| `[diagnostics]` | Profiler enable, thresholds, hooks list |

### Ready-made presets

Five preset snippets ship in `config/EXAMPLES.toml`:

- 🔥 **PUNCHY CLUB** — aggressive, fast, decisive
- 🎚️ **STUDIO PRECISE** — slow, surgical, fine-grained
- 👋 **BEGINNER FORGIVING** — easy controls, hard to make mistakes
- 📻 **RADIO/STREAM SAFE** — strict gain control, paranoid metering
- 🎨 **VINTAGE ANALOG FEEL** — springy, mechanical, gentle ramps

---

## 🎚️ Ableton Setup

### 1. Install AbletonOSC

[AbletonOSC by ideoforms](https://github.com/ideoforms/AbletonOSC) — install in Ableton's `Remote Scripts` folder. Default ports `11000` (recv) / `11001` (send) match FX Machine.

### 2. Create two specifically-named tracks

**`~ FX Macros`** — Audio track or Return with an Audio Effect Rack containing these 8 macros:

`Filter Freq`, `Filter Mode`, `Filter Res`, `Stutter`, `Reverb Size`, `FX Send`, `Delay FB`, `Width`

The rack must follow the nested wet/dry topology described above.

**`~ EQ Macros`** — Audio track or Return with an Audio Effect Rack containing 4 macros:

- `EQ Low` → EQ Three GainLow
- `EQ Mid` → EQ Three GainMid
- `EQ High` → EQ Three GainHi
- `Trim` → Utility Gain (placed BEFORE the EQ Three in the chain)

### 3. Optional prefix conventions

- Scenes prefixed with **`§`** become bookmarks (jump targets via D-pad)
- Tracks prefixed with **`*`** become group lead tracks (group navigation via D-pad)

---

## 🏗️ Project Structure

```
fxmachine/
├── run.py                      Entry point + diagnostics activation
├── build.py                    PyInstaller .exe builder
├── diagnose.py                 150+ automated health checks
├── inspect_exe.py              .exe bundle verifier (PyInstaller 6.20+)
├── analyze_diagnostics.py      Post-session diagnostics analyzer CLI
├── FX_Machine.spec             PyInstaller spec file
├── README.md                   This file
├── .gitignore
├── config/                     TOML configuration system
│   ├── default.toml            Factory template
│   ├── active.toml             User settings
│   ├── EXAMPLES.toml           Preset snippets
│   ├── README.md               Config folder explainer
│   └── presets/                Saved user profiles
├── docs/                       Screenshots and reference images
├── logs/                       Runtime logs (auto-created)
│   ├── fxmachine.log           Main app log (rotating, 5MB × 10)
│   ├── diagnostics.log         Diagnostics text summaries
│   └── diagnostics.jsonl       Machine-readable diagnostics data
└── src/
    ├── config.py               Architectural constants
    ├── config_loader.py        TOML loader + cfg singleton + hot-reload
    ├── state.py                Shared state + thread locks
    ├── helpers.py              Math, formatting, smoothing
    ├── log_setup.py            Logging configuration
    ├── main.py                 App entry + shutdown sequencing
    │
    ├── osc/
    │   ├── client.py           OSC send + listener registration
    │   ├── server.py           OSC receive + unified dispatch handlers
    │   └── discovery.py        Session scanning + rack detection
    │
    ├── engine/
    │   ├── navigation.py       Scene/track/bookmark/group movement
    │   ├── actions.py          Discrete button actions
    │   ├── momentary.py        Stutter / bass cut / FX throw
    │   ├── eq.py               EQ gestures, encoder, smart actions
    │   ├── fx.py               FX macro stick driver + Delay FB stepping
    │   └── polling.py          Safety polling + 60Hz EQ ramp thread
    │
    ├── controller/
    │   ├── watchdog.py         Auto-detect, reprobe, ghost-event fix
    │   ├── buttons.py          Layer-aware button routing
    │   ├── axes.py             Stick + D-pad handlers
    │   └── loop.py             Main controller thread (125 Hz)
    │
    ├── ui/
    │   ├── palette.py          Colors + typography
    │   ├── widgets.py          Canvas renderers + PhotoImage meter
    │   ├── builder.py          Tkinter UI construction
    │   └── updater.py          UI update loop (40 Hz)
    │
    └── diagnostics/
        ├── __init__.py         Public API + diag singleton
        ├── installer.py        Monkey-patch hook installer
        ├── profiler.py         Per-function timing stats
        ├── counters.py         Event counters with rate tracking
        ├── osc_tracker.py      Per-address OSC traffic accounting
        ├── sampler.py          CPU/RAM/thread sampling
        ├── thread_health.py    Per-thread frequency monitoring
        ├── rate_limiter.py     Adaptive throttling
        ├── reporter.py         Text + JSONL log writers
        └── analyzer.py         Post-session analysis module
```

---

## 🛠️ Development

### Tech stack

- **Python 3.12** — language
- **pygame 2.6** — gamepad input
- **python-osc** — OSC communication
- **psutil** — system resource monitoring (optional)
- **tomllib** — TOML parsing (Python 3.11+ built-in)
- **tkinter** — current UI (migration to PySide6 planned)
- **PyInstaller 6.20** — `.exe` builder

### Running the diagnostic tool

```bash
python diagnose.py            # full check (150+ tests)
python diagnose.py --quick    # skip slow tests (no OSC, gamepad, git)
python diagnose.py --verbose  # show every check, not just failures
```

### Running the diagnostics profiler

1. Set `enabled = true` in `config/active.toml` under `[diagnostics]`
2. Run the app normally: `python run.py`
3. Use the app for your session
4. Close cleanly
5. View results: `notepad logs\diagnostics.log`
6. Run analyzer: `python analyze_diagnostics.py`

### Building the .exe

```bash
pip install pyinstaller
python build.py
```

Output: `dist/FX_Machine/FX_Machine.exe` (portable folder, ~40 MB)

Verify the build: `python inspect_exe.py`

---

## 🗺️ Roadmap

### Current Focus

**UI Framework Migration (PySide6)**

The current Tkinter-based UI is functional but visually limited. The planned migration to PySide6 (Qt for Python) targets a **dark analog hardware aesthetic** — matte black faceplate with warm LED indicators and metallic knob textures, inspired by Pioneer DJM-900 NXS2 and Eurorack modular design language (Cwejman, Intellijel).

PySide6 provides:
- Hardware-accelerated rendering via QPainter with antialiasing
- Real animations, transitions, easing curves
- Qt Style Sheets for visual theming
- Mixed native widgets and custom-painted elements

**Device Mode (Instrument Macro Control)**

Planned feature: automatic detection and control of Ableton instrument macros on the currently selected track. When a track has a rack device with macros, FX Machine would offer direct gamepad control of those parameters — extending the concept from "FX controller" to "universal Ableton macro controller."

### Future Features

- ⏱️ **Tap tempo** — long-press START → tap 4 times → set BPM
- 🚨 **Panic reset** — L1+L3+R3 = restore all FX + EQ to neutral
- 🎯 **Quantized bass cut release** — beat-synced auto-release at next downbeat
- 💾 **State persistence** — pick up where you left off across restarts
- 🧪 **Unit tests** — automated gesture engine validation

---

## 📜 License

```
© 2026 Ayoub Agoujdad. All rights reserved.
Trademark registered. Copyrighted work.

Strictly NON-COMMERCIAL USE ONLY.

You are welcome to:
  ✓ Study the code
  ✓ Modify it for personal use
  ✓ Share with attribution

You are NOT permitted to:
  ✗ Sell or commercialize this software
  ✗ Remove copyright notices
  ✗ Claim authorship
```

---

## 👤 Author

**Ayoub Agoujdad**

🎵 Performing as **[MIRA](https://instagram.com/MIRA___OFC)** (formerly half of **Mirymood** duo)
🎛️ Project: **Modulated_OFC**
🇲🇦 Based in Marrakech, Morocco

Built out of necessity. I wanted a controller that felt like a DJM-900 in front of Ableton — without buying a DJM-900. Then I wanted my friends to be able to use it too, so I made it configurable. Then I wanted to know why it was slow, so I built a diagnostics layer. Then I wanted it to look like real hardware, so I'm migrating to Qt.

Made by and for live performance.

---

<div align="center">

*If this project helped you, leave a ⭐ on the repo.*

</div>