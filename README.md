<div align="center">

# 🎛️ FX Machine

### A USB Gamepad Turned Into a Live Performance Instrument for Ableton Live

![FX Machine Main UI](docs/screenshots/fx_machine_ui_v_9_11.png)

*Designed for melodic house & progressive deep house*

**v9.11** · Modeled after the Pioneer DJM-900 NXS2 channel strip topology

---

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org)
[![Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()
[![Ableton](https://img.shields.io/badge/Ableton-Live%2010%2F11%2F12-black.svg)](https://www.ableton.com)
[![License](https://img.shields.io/badge/license-Non--Commercial-red.svg)](#license)

</div>

---

## 🎯 What Is This?

**FX Machine** transforms a generic USB gamepad into a precision instrument for live electronic music performance. It bridges a PlayStation-style controller to Ableton Live via OSC, exposing two parallel effect racks — a 3-band kill EQ and an 8-macro FX rack — that you can manipulate with **encoder-style sticks**, **double-flick gestures**, and **momentary button effects**.

This isn't a MIDI mapping. It's a custom-built performance system with its own gesture language, safety logic, and visual feedback layer.

```
       Gamepad ──── USB ──── FX Machine ──── OSC ──── Ableton Live
                              (Python)              (AbletonOSC)
                                  │
                                  ▼
                          Real-time Tkinter UI
                          (knobs · meters · status)
```

---

## ✨ Key Features

### 🎚️ Dual-Rack Signal Chain (DJM-900 Style)

The system inserts two racks in series before your master output, exactly like a real DJ mixer channel strip:

```
All instrument tracks ──▶ Return A
                              │
                              ▼
                       ~ EQ Macros      (3-band kill EQ, shapes the source)
                              │
                              ▼
                       ~ FX Macros      (filter / reverb / delay / stutter)
                              │
                              ▼
                          Master
```

### 🎛️ EQ Engine — Encoder + Smart Gestures

Three bands (Low / Mid / High), each with **two gesture modes** on the right stick:

| Gesture | Action |
|---|---|
| **Stick X right (held)** | Encoder: boost current band, value HOLDS on release |
| **Stick X left (held)** | Encoder: cut current band, value HOLDS on release |
| **Stick Y up double-flick** | Switch to band above (wraps: MID → HIGH → LOW → MID) |
| **Stick Y down double-flick** | Switch to band below (wraps: MID → LOW → HIGH → MID) |
| **Stick X left double-flick** | Smart kill / normalize (see logic below) |
| **Stick X right double-flick** | Smart restore / boost (see logic below) |

#### Smart Kill/Normalize Logic (Double-flick LEFT)

```
if current_value > 0 dB:
    → normalize back to 0 dB
else (current_value ≤ 0 dB):
    if band is BASS:
        → KILL to -∞ dB
    else (MID or HIGH):
        → cut to -19 dB
```

#### Smart Restore/Boost Logic (Double-flick RIGHT)

```
if current_value < 0 dB:
    → restore to 0 dB
else (current_value ≥ 0 dB):
    if band is BASS:
        → 🚫 BLOCKED (speaker safety)
    else (MID or HIGH):
        → boost by 15% of remaining headroom (asymptotic)
```

### ⚡ FX Engine — 8 Macros, 5 Effects

| Slot | Macro | Effect | Range |
|---|---|---|---|
| 1 | Filter Freq | Auto Filter cutoff (logarithmic) | 20 Hz – 20 kHz |
| 2 | Filter Mode | Auto Filter type | 0 = HP, 1 = LP |
| 3 | Filter Res | Auto Filter resonance | 20% – 100% |
| 4 | Stutter | Beat Repeat on/off | 0 / max |
| 5 | Reverb Size | Dark Hall decay | 200ms – 60s |
| 6 | FX Send | Wet/dry crossfade (Utility-based) | 0% – 100% |
| 7 | Delay FB | Long Digi Delay feedback | 0% – 92% (capped) |
| 8 | Width | Stereo Utility width | 0% – 200% |

#### Momentary Buttons (FX Layer = hold L1)

| Button | Effect |
|---|---|
| **L1 + X** | 💥 STUTTER (jam to max while held) |
| **L1 + O** | 🔻 BASS CUT (HP filter @ 200 Hz while held, restores snapshot on release) |
| **L1 + □** | 🌫 FX SEND THROW (jam to max while held, restores snapshot on release) |
| **L1 + △** | ▶▶ Launch scene |

### 📊 DJM-Style Channel Meter

A 24-segment vertical LED meter beside the EQ stack shows **real-time audio output level** from the EQ track, with:

- Green zone (0 – 0 dB)
- Yellow zone (0 – +3 dB)
- Red zone (+3 – +6 dB)
- **Peak hold** indicator (1.5s hold, then decay)
- Live data from Ableton via `output_meter_left/right` listeners

### 🎮 Controller Layers

| Layer | Trigger | Behavior |
|---|---|---|
| **Navigation** | Default | L-stick = track/scene, D-pad = bookmarks/groups |
| **FX Mode** | Hold L1 | Both sticks control FX macros, view follows |
| **EQ Mode** | Tap R3 | Right stick = EQ encoder + gestures |
| **Volume** | Hold SELECT | Right stick Y = track volume |

---

## 📸 Gallery

### Default / Navigation Mode

<div align="center">

![Main UI](docs/screenshots/screenshot-main.png)

</div>

Two-column layout: vertical EQ stack with DJM-900 style channel meter on the left, session navigation info on the right (bookmarks, groups, track / scene / clip names, position counters, volume display, modifier pills). FX panel spans the full width below.

The interface is built with Tkinter and rendered at 40 Hz. Knob bodies use canvas-drawn metallic gradients with white indicator lines, dB tick labels around the perimeter, and subtle glow rings to indicate selected/armed states.

### EQ Mode Active

<div align="center">

![EQ Mode Active](docs/screenshots/ableton_fx_machine.png)

</div>

When EQ mode is toggled on (R3 in nav layer), the selected band glows white and the status bar shows the active controls. The right stick becomes an encoder for value control on the X axis, with double-flick gestures for band switching (Y) and smart kill / normalize / boost actions (X). The real-time audio output meter responds to the EQ track's actual signal level via OSC listeners on Ableton's `output_meter_left/right`.

---

## 🧮 The Math Behind the Feel

### Why the Encoder Isn't Linear

A real DJ wants **fine control near zero** and **fast sweeps at the edges**. So the encoder uses a curved velocity function:

```python
delta = (macro_range / sweep_seconds) × (stick_deflection ^ curve_exp)
```

Where:
- `sweep_seconds = 0.6` — time to sweep the full range at full deflection
- `curve_exp = 1.2` — slight ease at the start, mostly linear after

Result: at 50% stick, you move at ~43% of max speed. At 100%, you move at 100%. The curve is gentle enough that precise edits feel natural, but full deflection still sweeps the whole range in under a second.

### Why 0 dB Isn't in the Middle of the Macro Range

Ableton's EQ Three uses a **logarithmic gain scale**: -∞ to 0 dB on the cut side, 0 to +6 dB on the boost side. The cut side has infinite range; the boost side only 6 dB. So in macro space (0–127), neutral 0 dB lives at **macro value 107.9**, not 64.

If we used a linear mapping (stick center → macro 64 → -13.8 dB), the EQ would feel completely wrong. Instead, the system uses **empirical calibration**:

| Macro Value | dB Output |
|---:|---:|
| 0 | -∞ (full kill) |
| 32 | -28.6 dB |
| 64 | -13.8 dB |
| 96 | -3.76 dB |
| **107.9** | **0 dB (neutral)** |
| 114 | +2 dB (bass safety cap) |
| 127 | +6 dB (max) |

The encoder works in **macro units per second**, not stick-position-to-dB mapping. This makes the response feel symmetric even though the underlying curve isn't.

### Sticky 0 dB Detent

When the encoder is **near neutral** (within ±3 macro units of 0 dB), it slows down to 15% speed. This mimics the tactile detent on real EQ knobs at noon, making it easy to "find" 0 dB without overshooting.

```python
distance = abs(current_value - 107.9)
if distance < 3.0:
    detent_factor = max(0.15, distance / 3.0)
    delta *= detent_factor
```

### Double-Flick Gesture Detection

A double-flick is a state machine:

```
       extreme         center         extreme
  idle ────────▶ flicked ─────▶ returned ─────▶ confirmed
  ◀───────── timeout (500ms) ─────────────────▶ reset
```

- **EQ_FLICK_EXTREME = 0.85** — stick must reach 85% deflection to count as "flicked"
- **EQ_FLICK_RETURN = 0.30** — must drop below 30% to count as "returned"
- **EQ_FLICK_TIMEOUT_MS = 500** — second flick must arrive within 500ms

Same direction required for second flick. Different direction or timeout → silent reset.

### Cubic Ease-Out Ramps

When a gesture triggers an action (e.g., kill bass), the system animates the macro change over 30–100ms using a **cubic ease-out** curve:

```python
progress = elapsed / duration            # 0.0 → 1.0
eased = 1.0 - (1.0 - progress) ** 3      # cubic ease-out
current_value = start + (target - start) * eased
```

Why cubic ease-out: linear ramps sound abrupt at the end. Exponential ramps (`1 - e^-3x`) sound too slow at the start. Cubic ease-out is musically natural and click-free.

### Axis Dominance Suppression

The right stick is one physical input controlling two logical things (X = value, Y = band switch). To prevent accidental cross-axis triggers when diagonal motion happens:

```python
if abs(y) > abs(x) * 1.3:
    # Y dominates → suppress X completely
    skip_x_processing()
```

If Y is more than 30% larger than X, Y wins and X is ignored entirely. This makes band-switch flicks feel decisive without polluting the EQ value.

---

## 🏗️ Architecture

A modular Python application with **5 concurrent daemon threads** coordinated through a thread-safe shared state:

```
┌─ Main Thread ─────────────────────────────────┐
│  Tkinter UI (40 Hz update)                    │
│   ├─ build_ui() / update_ui()                 │
│   └─ Canvas-based knob & meter rendering      │
└───────────────────────────────────────────────┘
        ▲                              ▲
        │ reads state                  │
        │                              │
┌─ Controller Thread (~125 Hz) ────────┐
│  pygame events → handlers            │
│  axis handlers (smooth + curve)      │
│  → eq_drive_continuous_encoder()     │
│  → fx_drive_macro()                  │
└──────────────────────────────────────┘
        │ OSC out
        ▼
┌─ Ableton Live (via AbletonOSC) ──────┐
│   FX rack + EQ rack                  │
│   Audio output meters                │
└──────────────────────────────────────┘
        │ OSC in (listeners)
        ▼
┌─ OSC Server Thread ──────────────────┐
│  Routes by track_id / device_id      │
│  Updates shared state                │
└──────────────────────────────────────┘

┌─ Polling Thread (~6.6 Hz) ───────────┐
│  Periodic queries + safety polls     │
└──────────────────────────────────────┘

┌─ Watchdog Thread (1 Hz) ─────────────┐
│  Controller health + auto-reprobe    │
│  Ghost-event reconciliation          │
└──────────────────────────────────────┘

┌─ EQ Ramp Thread (60 Hz) ─────────────┐
│  Smooth value transitions            │
└──────────────────────────────────────┘
```

### Project Structure

```
fxmachine/
├── run.py                      Entry point: python run.py
├── build.py                    PyInstaller .exe builder
├── README.md                   This file
├── .gitignore
├── docs/
│   └── screenshots/            UI screenshots embedded in README
└── src/
    ├── config.py               All constants (timings, deadzones, curves)
    ├── state.py                Shared state + thread locks
    ├── helpers.py              Math, formatting, smoothing
    ├── log_setup.py            Centralized logging system
    ├── main.py                 App entry: spawns 5 threads + Tkinter
    │
    ├── osc/
    │   ├── client.py           Outbound OSC (all osc_* send functions)
    │   ├── server.py           Inbound OSC (all on_* handlers + dispatcher)
    │   └── discovery.py        Session scanning + rack detection
    │
    ├── engine/
    │   ├── navigation.py       Scene/track/bookmark/group movement
    │   ├── actions.py          Discrete button actions
    │   ├── momentary.py        Stutter / bass cut / FX throw
    │   ├── eq.py               EQ gestures, encoder, smart actions
    │   ├── fx.py               FX macro stick driver + Delay FB stepping
    │   └── polling.py          Background polling + 60Hz EQ ramp thread
    │
    ├── controller/
    │   ├── watchdog.py         Auto-detect, reprobe, ghost-event fix
    │   ├── buttons.py          Layer-aware button routing
    │   ├── axes.py             Stick + D-pad handlers
    │   └── loop.py             Main controller thread (125 Hz)
    │
    └── ui/
        ├── palette.py          Colors + typography
        ├── widgets.py          Canvas renderers (knob, meter, label cache)
        ├── builder.py          Tkinter UI construction
        └── updater.py          UI update loop (40 Hz)
```

---

## 🚀 Quick Start

### Option A: Run from Python Source

**Requirements:**
- Windows 10 / 11
- Python 3.12+
- USB gamepad (PlayStation-style: 12 buttons, 2 analog sticks, D-pad)

```bash
# Install dependencies
pip install pygame python-osc

# Run
python run.py
```

### Option B: Run the Standalone .exe

No Python needed on the target machine. Just download/build the `.exe`:

```bash
# One-time build setup
pip install pyinstaller

# Build the .exe
python build.py
```

The executable is created at `dist/FX_Machine.exe`. Double-click to run.

---

## 🎚️ Ableton Setup

Your Ableton session needs:

### 1. AbletonOSC Installed

Install [AbletonOSC](https://github.com/ideoforms/AbletonOSC) in Ableton's `Remote Scripts` folder. Default ports `11000` (recv) / `11001` (send) — matches FX Machine defaults.

### 2. Two Specifically-Named Tracks

**`~ FX Macros`** — An audio track or Return track containing an Audio Effect Rack with these 8 macros (names must match exactly):

- `Filter Freq` → Auto Filter frequency
- `Filter Mode` → Auto Filter type (HP/LP)
- `Filter Res` → Auto Filter resonance
- `Stutter` → Beat Repeat on/off
- `Reverb Size` → Dark Hall decay time
- `FX Send` → Utility (inside nested wet/dry chain)
- `Delay FB` → Long Digi Delay feedback
- `Width` → Utility stereo width

**`~ EQ Macros`** — An audio track or Return track containing an Audio Effect Rack with these 3 macros mapped to an EQ Three device:

- `EQ Low` → GainLow
- `EQ Mid` → GainMid
- `EQ High` → GainHi

### 3. Optional Prefix Conventions

- Scenes prefixed with **`§`** become bookmarks (jump targets via D-pad)
- Tracks prefixed with **`*`** become group lead tracks (group navigation via D-pad)

---

## 🎮 Full Controller Map

### Navigation Layer (Default)

| Input | Action |
|---|---|
| L-stick Y | Scene navigation (hold to auto-scroll) |
| L-stick X | Track navigation |
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

### FX Mode Layer (Hold L1)

| Input | Action |
|---|---|
| L-stick Y | Filter Freq (with acceleration) |
| L-stick X | Filter Res |
| R-stick | FX Send + Reverb Size |
| D-pad ↑ / ↓ | Bookmark prev/next |
| D-pad ← / → | Delay FB step (1/20 of range) |
| L1 + ✕ | 💥 STUTTER (momentary) |
| L1 + ○ | 🔻 BASS CUT (momentary, snapshot restore) |
| L1 + △ | Launch scene |
| L1 + □ | 🌫 FX SEND THROW (momentary, snapshot restore) |
| L1 + L3 | Toggle filter lock |
| L1 + R3 | Toggle wet lock |

### EQ Mode Layer (Tap R3 to enter, R3 again to exit)

| Input | Action |
|---|---|
| R-stick X (hold) | Encoder: boost (right) / cut (left) — value HOLDS on release |
| R-stick Y ↑↑ | Switch band up (MID → HIGH → LOW, no borders) |
| R-stick Y ↓↓ | Switch band down (MID → LOW → HIGH, no borders) |
| R-stick X ←← | Smart kill / normalize |
| R-stick X →→ | Smart restore / boost (bass blocked at ≥ 0 dB) |

### Modifier Combos (SELECT held)

| Input | Action |
|---|---|
| SELECT + R-stick Y | Track volume control |
| SELECT + R3 | Volume mute toggle (single = unity, double = mute) |
| SELECT + R1 | Save FX baseline |
| SELECT + START | Force full refresh (Ableton + controller) |

---

## 🔒 Safety Features

This system is built for **live performance**, where errors are unacceptable. Several safety mechanisms are baked in:

- **Bass boost cap** — encoder cannot push bass above +2 dB
- **Bass double-flick boost blocked** — protects subs and listeners
- **Delay feedback cap** — limited to 92% to prevent runaway feedback
- **R2 safety gate** — prevents accidental clip/scene launches when held
- **Lock states** — Filter and Wet can be locked to prevent FX recovery from changing them
- **FX baseline snapshot** — auto-captures startup values, restorable any time
- **Pre-engage snapshots** — momentary effects restore exactly what was there before press
- **Ghost-event reconciliation** — auto-recovers from dropped SELECT button release events
- **Controller auto-reprobe** — detects silent disconnects within 5 seconds and reconnects
- **Throttled OSC writes** — prevents Ableton flooding (25ms FX / 20ms EQ minimums)
- **Epsilon culling** — skips writes when the value change would be imperceptible

---

## 🪵 Logging

FX Machine writes a rotating log file with timestamps to:

- `logs/fxmachine.log` (when run from Python source)
- `[exe_folder]/logs/fxmachine.log` (when run from `.exe`)

Configuration:
- **5 MB per file**
- **10 rotated backups** (~55 MB total history)
- **INFO level by default** (DEBUG available for deep diagnostics)
- **Mirrors to console** during development
- **Per-module loggers** for clean filtering
- **Crash handler** logs uncaught exceptions before death
- **Session start/end banners** for easy log navigation

Example output:
```
22:47:13.124 [INFO ] fxmachine.osc.client            : OSC sender ready → 127.0.0.1:11000
22:47:13.890 [INFO ] fxmachine.controller.watchdog   : Controller FOUND: DragonRise Inc.
22:47:14.501 [INFO ] fxmachine.osc.discovery         : FX track found at index 12
22:47:14.602 [INFO ] fxmachine.osc.discovery         : EQ track found at index 13
22:47:15.001 [INFO ] fxmachine.engine.eq             : EQ band switched to High
22:47:15.345 [WARN ] fxmachine.controller.watchdog   : SELECT ghost release detected — force-cleared
```

---

## 🛠️ Development

### Tech Stack

- **Python 3.12** — language
- **pygame 2.6** — gamepad input
- **python-osc** — OSC communication
- **tkinter** — UI (standard library, no extra install)
- **PyInstaller** — `.exe` builder
- **Git** — version control

### Tunable Constants

All performance-critical values live in `src/config.py`. Common knobs to turn:

```python
# EQ encoder feel
EQ_SWEEP_SECONDS      = 0.6     # full-range sweep time at max deflection
EQ_ENCODER_CURVE_EXP  = 1.2     # 1.0 = linear, higher = more easing at start
EQ_AXIS_DEAD_ZONE     = 0.18    # ignore tiny stick movements

# Double-flick gesture timing
EQ_FLICK_TIMEOUT_MS   = 500     # window between flicks
EQ_FLICK_EXTREME      = 0.85    # deflection to register "flicked"
EQ_FLICK_RETURN       = 0.30    # threshold to register "returned"

# Animation
EQ_RAMP_MIN_MS        = 30      # fastest ramp (fast flick)
EQ_RAMP_MAX_MS        = 100     # slowest ramp (slow flick)

# Safety
EQ_BASS_BOOST_CAP     = 114.0   # bass encoder upper limit (+2 dB)
```

---

## 🗺️ Roadmap

Features under consideration:

- ⏱️ **Tap tempo** — long-press START → tap 4 times → set BPM
- 🚨 **Panic reset** — L1+L3+R3 simultaneous = restore all FX + EQ to neutral
- 💾 **Per-bookmark baselines** — different FX state per song section
- ⚙️ **TOML config file** — tune feel without editing code
- 🔄 **State persistence** — pick up where you left off across restarts
- 🎵 **MIDI clock output** — FX Machine as master clock for external hardware
- 🧪 **Unit tests** — automated gesture engine validation
- 📦 **MSI installer** — one-click install for end users

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

🎵 Artist alias: **[MIRA](https://instagram.com/MIRA___OFC)** (formerly half of **Mirymood** duo)  
🎛️ Project: **Modulated_OFC**  
🇲🇦 Based in Marrakech, Morocco

Made by and for live performance.

---

<div align="center">

*If this project helped you, leave a ⭐ on the repo.*

</div>