<div align="center">

# 🎛️ FX Machine

### A USB Gamepad Turned Into a Live Performance Instrument for Ableton Live

*Built by a DJ, for DJs. Modeled after the Pioneer DJM-900 NXS2 channel strip.*

![FX Machine Main UI](docs/screenshots/fx_machine_ui_v_9_11.png)

---

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org)
[![Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey.svg)]()
[![Ableton](https://img.shields.io/badge/Ableton-Live%2010%2F11%2F12-black.svg)](https://www.ableton.com)
[![Version](https://img.shields.io/badge/version-v1.0.0--toml-green.svg)]()
[![License](https://img.shields.io/badge/license-Non--Commercial-red.svg)](#-license)

**Latest: v1.0.0-toml** · TOML hot-reload + portable .exe builder shipped

</div>

---

## 🎯 What It Does

FX Machine bridges a generic USB gamepad to Ableton Live via OSC, exposing a **3-band kill EQ** and an **8-macro FX rack** through a custom gesture vocabulary. Push a stick, hold a button, double-flick to fire a kill — all in real time, with values you tune through a plain-text config file while the app is running.

It is not a MIDI mapping. It's a performance instrument with its own gesture engine, safety logic, visual feedback, and hot-reloadable configuration system.

```
       Gamepad ──── USB ──── FX Machine ──── OSC ──── Ableton Live
                              (Python)              (AbletonOSC)
                                  │
                                  ▼
                          Real-time UI
                          (knobs · meters · status)
```

---

## 🎬 At a Glance

<div align="center">

| Default mode | EQ mode active |
|:---:|:---:|
| ![Main UI](docs/screenshots/fx_machine_ui_v_9_11.png) | ![EQ Mode](docs/screenshots/ableton_fx_machine.png) |

</div>

Two-column layout: vertical EQ stack with channel meter on the left, session navigation on the right. FX panel spans full width below. Built with Tkinter, rendered at 40 Hz, with canvas-drawn metallic knobs and live OSC-driven meters.

---

## 🚀 Quick Start

### Option A — Run from source (if you have Python 3.12+)

```bash
pip install pygame python-osc
python run.py
```

### Option B — Run the portable .exe (no Python needed)

1. Download the `dist/FX_Machine/` folder
2. Double-click `FX_Machine.exe`
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

## ✨ What's In It

### 🎚️ The Signal Chain (DJM-900 Style)

Two racks inserted in series before your master output, just like a real DJ mixer channel:

```
All instrument tracks ──▶ Return A
                              │
                              ▼
                       ~ EQ Macros      (3-band kill EQ — shapes the source)
                              │
                              ▼
                       ~ FX Macros      (filter / reverb / delay / stutter)
                              │
                              ▼
                          Master
```

The FX rack uses a nested wet/dry rack so reverb and delay tails **continue ringing after you cut the send** — exactly like a hardware DJ mixer's send/return loop. This enables the classic "throw and let it tail" technique (push FX Send to max, release, watch the dry signal continue clean while the wet tail decays naturally over several seconds).

<details>
<summary><b>📖 Click for deep dive on internal wet/dry routing</b></summary>

```
Audio Effect Rack (~ FX Macros)
│
├── Auto Filter           ← always on the main path (Filter Freq + Mode + Res)
├── Beat Repeat           ← always on the main path (Stutter macro)
│
├── ┌─[ Nested Wet/Dry Rack ]──────────────────────┐
│   │                                              │
│   ├── Chain "Dry"  ─────────▶ passes through     │
│   │   (empty — direct signal continues)          │
│   │                                              │
│   └── Chain "Wet"                                │
│       ├── Utility    ◀── FX Send macro (gain)   │
│       ├── Dark Hall  ◀── Reverb Size macro      │
│       └── Long Digi Delay ◀── Delay FB macro    │
│                                                  │
└── └──────────────────────────────────────────────┘
│
└── Utility               ← Width macro (stereo width)
```

**Why this matters**: If FX Send were a simple wet/dry knob in series, dropping it to 0 would cut everything dry. Instead, the FX Send macro controls how much signal *feeds into* the wet chain. The dry path always passes through, and the wet chain's existing reverb decay and delay feedback keep running even after you stop feeding it new signal.

**The "throw and tail" technique**:
1. Crank FX Send to max (L1+□ throw button)
2. Release → FX Send snaps back to 0
3. The dry signal continues clean
4. Reverb decays naturally for 30+ seconds
5. Delay feedback bounces with the rhythm you set

You can stack throws to build walls of tails, then kill the bass and drop a fresh element — the tails carry the energy through the transition. Classic Ben Böhmer / Yotto / Nora En Pure move.

</details>

---

### 🎛️ EQ Engine — Encoder + Smart Gestures

Three bands (Low / Mid / High), controlled by the right stick with two distinct gesture modes.

#### Continuous control (X-axis encoder)

| Action | Result |
|---|---|
| Stick X right (held) | Boost current band, value HOLDS on release |
| Stick X left (held) | Cut current band, value HOLDS on release |

The encoder uses a **velocity-based model with curve shaping** — push hard for fast sweeps, push gently for precise tweaks. A sticky 0 dB detent slows the encoder when crossing neutral, mimicking the tactile feel of a real EQ knob at noon.

#### Discrete actions (double-flick gestures)

| Gesture | Action |
|---|---|
| Stick X left double-flick | **Smart kill / normalize** |
| Stick X right double-flick | **Smart restore / boost** |
| Stick Y up double-flick | Switch band up (wraps MID → HIGH → LOW → MID) |
| Stick Y down double-flick | Switch band down (wraps MID → LOW → HIGH → MID) |

The "smart" actions are context-aware:

**Double-flick LEFT** behavior:
```
if current_value > 0 dB:
    → normalize to 0 dB (pull it back to neutral)
else:
    if BASS: → KILL to -∞ dB
    else (MID/HIGH): → cut to -19 dB
```

**Double-flick RIGHT** behavior:
```
if current_value < 0 dB:
    → restore to 0 dB
else if MID or HIGH:
    → boost by 15% of remaining headroom (asymptotic)
else (BASS):
    → 🚫 BLOCKED (sub safety)
```

<details>
<summary><b>📖 Click for the math behind the encoder feel</b></summary>

#### Why the encoder isn't linear

```python
delta = (macro_range / sweep_seconds) × (stick_deflection ^ curve_exp)
```

- `sweep_seconds = 0.3` — full-range sweep time at max stick deflection
- `curve_exp = 1.0` — pure linear response

Higher `curve_exp` (1.3+) adds easing near rest for precise tweaks. `1.0` gives instant proportional response — aggressive and performer-friendly. All values tunable via the TOML config — see [Configuration](#️-configuration).

#### Why 0 dB isn't in the middle of the macro range

Ableton's EQ Three uses a logarithmic gain scale: -∞ to 0 dB on the cut side, 0 to +6 dB on the boost side. In macro space (0–127), neutral 0 dB lives at **macro value 107.9**, not 64.

If we used a linear mapping (stick center → macro 64 → -13.8 dB), the EQ would feel completely wrong. Instead, the system uses empirical calibration:

| Macro Value | dB Output |
|---:|---:|
| 0 | -∞ (full kill) |
| 32 | -28.6 dB |
| 64 | -13.8 dB |
| 96 | -3.76 dB |
| **107.9** | **0 dB (neutral)** |
| 114 | +2 dB (bass safety cap) |
| 127 | +6 dB (max) |

The encoder works in **macro units per second**, not stick-position-to-dB. This makes the response feel symmetric even though the underlying dB curve isn't.

#### Sticky 0 dB detent

Within ±1 macro unit of neutral, the encoder slows to 30% speed:

```python
distance = abs(current_value - 107.9)
if distance < 1.0:
    detent_factor = max(0.30, distance / 1.0)
    delta *= detent_factor
```

Mimics the tactile detent on real EQ knobs at noon without becoming a wall that fights sweeps.

#### Double-flick state machine

```
       extreme         center         extreme
  idle ────────▶ flicked ─────▶ returned ─────▶ confirmed
  ◀───────── timeout (380ms) ─────────────────▶ reset
```

- `EQ_FLICK_EXTREME = 0.90` — stick must reach 90% deflection
- `EQ_FLICK_RETURN = 0.22` — must drop below 22% to count as "returned"
- `EQ_FLICK_TIMEOUT_MS = 380` — second flick must arrive within 380ms
- Same direction required for second flick; different direction or timeout = silent reset

#### Cubic ease-out ramps

When a gesture triggers an action (kill, normalize, etc.), the macro value animates over 30–100ms using:

```python
progress = elapsed / duration            # 0.0 → 1.0
eased = 1.0 - (1.0 - progress) ** 3      # cubic ease-out
current_value = start + (target - start) * eased
```

Linear ramps sound abrupt. Exponential ramps drag at the start. Cubic ease-out is musically natural and click-free.

#### Axis dominance suppression

The right stick is one physical input controlling two logical things (X = value, Y = band). To prevent diagonal motion from triggering both:

```python
if abs(y) > abs(x) * 3.0:
    # Y dominates → suppress X completely
    return

if x_in_gesture:
    # X gesture in progress → freeze Y
    reset_y_gesture_state()
    return
```

Both axes use mutual exclusion. Once one wins, the other is frozen until the first completes or times out.

</details>

---

### ⚡ FX Engine — 8 Macros, 5 Effects

| Slot | Macro | Effect | Range |
|---|---|---|---|
| 1 | Filter Freq | Auto Filter cutoff (logarithmic) | 20 Hz – 20 kHz |
| 2 | Filter Mode | Auto Filter type | 0 = HP, 1 = LP |
| 3 | Filter Res | Auto Filter resonance | 20% – 100% |
| 4 | Stutter | Beat Repeat on/off | 0 / max |
| 5 | Reverb Size | Dark Hall decay | 200ms – 60s |
| 6 | FX Send | Wet chain gain (Utility-based) | 0% – 100% |
| 7 | Delay FB | Long Digi Delay feedback | 0% – 92% (capped) |
| 8 | Width | Stereo Utility width | 0% – 200% |

#### Momentary buttons (hold L1 to enter FX mode)

| Button | Effect |
|---|---|
| **L1 + X** | 💥 STUTTER (jam to max while held) |
| **L1 + O** | 🔻 BASS CUT (HP filter @ 200 Hz while held, restores snapshot on release) |
| **L1 + □** | 🌫 FX SEND THROW (jam to max while held, restores snapshot on release) |
| **L1 + △** | Launch scene |
| **L1 + L3** | Toggle filter lock |
| **L1 + R3** | Toggle wet lock |

On L1 release, the system runs recovery: Filter Freq returns to baseline (unless filter-locked), FX Send drops to 0 (unless wet-locked), Stutter snaps to 0. Reverb Size and Delay FB are left untouched so tails keep their character.

---

### 📊 DJM-Style Channel Meter

A 24-segment vertical LED meter beside the EQ stack shows real-time audio output level from the EQ track via Ableton's `output_meter_left/right` listeners. Color zones: green (safe), yellow (loud), red (clipping). Peak-hold indicator hovers at recent peaks for 1.5s before decaying.

> 🚧 **Build B (in progress)** will redesign this as a 15-segment -30 to +12 dB meter matching the DJM-900 NXS2 reference, plus a CLIP indicator with smooth yellow→red fade and configurable thresholds.

---

## ⚙️ Configuration

FX Machine ships with a **TOML-based configuration system** that lets you tune every aspect of the controller's feel without editing code. Changes apply instantly via `SELECT + START` on the controller — no app restart needed for most settings.

### The config folder

```
config/
├── default.toml          Factory template — don't edit (your safety net)
├── active.toml           Your current settings — edit this
├── EXAMPLES.toml         5 ready-to-copy preset snippets
├── README.md             Detailed explainer for non-programmers
└── presets/              Save your own profiles here
```

On first launch, the app auto-creates `active.toml` by copying `default.toml`.

### Hot-reload workflow

1. Open `config/active.toml` in any text editor
2. Read the comments — every value is explained in plain English with safe ranges
3. Change a number, save the file
4. Press **`SELECT + START`** on your controller (or click **⟳ REFRESH** in the UI)
5. Your changes apply instantly

If you write invalid TOML, the app keeps your previous working values and shows a clear error — your show is never broken by a typo.

### What you can tune

**~30 hot-reloadable parameters** spanning:

| Section | What it controls |
|---|---|
| `[eq.encoder]` | Stick sweep speed, curve shape, smoothing, deadzone |
| `[eq.dominance]` | How decisive Y vs X must be to trigger band-switch |
| `[eq.flick]` | Double-flick timing thresholds |
| `[eq.detent]` | Sticky 0 dB feel near unity |
| `[eq.ramp]` | Animation duration for actions |
| `[eq.safety]` | Bass boost cap, headroom boost percentage |
| `[trim]` | TRIM knob feel (Build B) |
| `[meter]` | Channel meter ballistics, peak hold |
| `[meter.clip]` | CLIP indicator thresholds & flicker (Build B) |
| `[fx]` | Per-macro sweep speeds, deadzone, acceleration |
| `[fx.delay_fb]` | Delay feedback discrete stepping |
| `[volume]` | SELECT+R-stick volume sensitivity |
| `[navigation]` | Track/scene scrolling responsiveness |
| `[timing]` | Polling, watchdog, debounce intervals |
| `[ui]` | UI refresh rate, window size (RESTART required) |
| `[network]` | OSC ports (RESTART required) |

### Ready-made presets

Five preset snippets ship in `config/EXAMPLES.toml`:

- 🔥 **PUNCHY CLUB** — aggressive, fast, decisive (peak-time energy)
- 🎚️ **STUDIO PRECISE** — slow, surgical, fine-grained (mixing/arrangement)
- 👋 **BEGINNER FORGIVING** — easy controls, hard to make mistakes
- 📻 **RADIO/STREAM SAFE** — strict gain control, paranoid metering
- 🎨 **VINTAGE ANALOG FEEL** — springy, mechanical, gentle ramps

Copy snippets from `EXAMPLES.toml` into your `active.toml`, mix and match across sections.

### Save your own profiles

When `active.toml` feels perfect, save it:

```bash
copy config\active.toml config\presets\my_club_set.toml
```

Send `.toml` files to other producers to share your tuning — they drop yours into their `config/` folder, rename to `active.toml`, reload. They get your exact feel.

---

## 🎚️ Ableton Setup

### 1. Install AbletonOSC

[AbletonOSC by ideoforms](https://github.com/ideoforms/AbletonOSC) — install in Ableton's `Remote Scripts` folder. Default ports `11000` (recv) / `11001` (send) match FX Machine.

### 2. Create two specifically-named tracks

**`~ FX Macros`** — Audio track or Return with an Audio Effect Rack containing these 8 macros (names must match exactly):

`Filter Freq`, `Filter Mode`, `Filter Res`, `Stutter`, `Reverb Size`, `FX Send`, `Delay FB`, `Width`

The rack must follow the [nested wet/dry topology](#-the-signal-chain-djm-900-style) — Auto Filter and Beat Repeat on the main path, then a wet/dry sub-rack containing Utility → Dark Hall → Long Digi Delay, then a final Utility for Width.

**`~ EQ Macros`** — Audio track or Return with an Audio Effect Rack containing 3 macros mapped to an EQ Three:

- `EQ Low` → GainLow
- `EQ Mid` → GainMid
- `EQ High` → GainHi

### 3. Optional prefix conventions

- Scenes prefixed with **`§`** become bookmarks (jump targets via D-pad)
- Tracks prefixed with **`*`** become group lead tracks (group navigation via D-pad)

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
| R-stick | FX Send + Reverb Size |
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
| R-stick Y ↑↑ | Switch band up (wraps MID → HIGH → LOW → MID) |
| R-stick Y ↓↓ | Switch band down (wraps MID → LOW → HIGH → MID) |
| R-stick X ←← | Smart kill / normalize |
| R-stick X →→ | Smart restore / boost (bass blocked at ≥ 0 dB) |

### Modifier Combos (hold SELECT)

| Input | Action |
|---|---|
| SELECT + R-stick Y | Track volume control |
| SELECT + R3 | Volume mute toggle (single tap = unity, double tap = mute) |
| SELECT + R1 | Save FX baseline |
| SELECT + START | Full refresh (TOML reload + Ableton session refresh + controller reprobe) |

---

## 🔒 Safety Features

Built for live performance, where errors are unacceptable.

- **Bass boost cap** — encoder cannot push bass above +2 dB
- **Bass double-flick boost blocked** — protects subs and listeners
- **Delay feedback cap** — limited to 92% to prevent runaway feedback
- **R2 safety gate** — prevents accidental clip/scene launches when held
- **Lock states** — Filter and Wet can be locked against L1-release recovery
- **FX baseline snapshot** — auto-captures startup values, restorable any time
- **Pre-engage snapshots** — momentary effects restore exactly what was there before press
- **Ghost-event reconciliation** — auto-recovers from dropped SELECT release events
- **Controller auto-reprobe** — detects silent disconnects within 5 seconds
- **Throttled OSC writes** — prevents Ableton flooding (25ms FX / 15ms EQ minimums)
- **Epsilon culling** — skips writes when the value change is imperceptible
- **TOML reload protection** — broken configs keep last working values, never crash the show

---

## 🏗️ Architecture

Modular Python app with **5 concurrent daemon threads** coordinated through a thread-safe shared state.

<details>
<summary><b>📖 Click for the architecture diagram</b></summary>

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

</details>

### Project structure

```
fxmachine/
├── run.py                      Entry point: python run.py
├── build.py                    PyInstaller .exe builder
├── diagnose.py                 150+ automated health checks
├── inspect_exe.py              Verify .exe bundling
├── FX_Machine.spec             PyInstaller spec file
├── README.md                   This file
├── .gitignore
├── config/                     TOML configuration system
│   ├── default.toml            Factory template (don't edit)
│   ├── active.toml             User settings (edit this)
│   ├── EXAMPLES.toml           Preset snippets
│   ├── README.md               Config folder explainer
│   └── presets/                Saved user profiles
├── docs/
│   └── screenshots/            UI screenshots
├── logs/
│   └── fxmachine.log           Rotating log file (auto-created)
└── src/
    ├── config.py               Architectural constants (don't change at runtime)
    ├── config_loader.py        TOML loader + cfg singleton + hot-reload
    ├── state.py                Shared state + thread locks
    ├── helpers.py              Math, formatting, smoothing
    ├── log_setup.py            Centralized logging system
    ├── main.py                 App entry: spawns 5 threads + Tkinter
    │
    ├── osc/
    │   ├── client.py           Outbound OSC (all osc_* send functions)
    │   ├── server.py           Inbound OSC (all on_* handlers)
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
        ├── widgets.py          Canvas renderers
        ├── builder.py          Tkinter UI construction
        └── updater.py          UI update loop (40 Hz)
```

---

## 🛠️ Development

### Tech stack

- **Python 3.12** — language
- **pygame 2.6** — gamepad input
- **python-osc** — OSC communication with Ableton
- **tomllib** — TOML parsing (Python 3.11+ built-in)
- **tkinter** — UI (standard library)
- **PyInstaller** — `.exe` builder
- **Git** — version control

### Diagnostic tool

A diagnostic script runs 150+ automated health checks on the entire codebase:

```bash
python diagnose.py            # full check
python diagnose.py --quick    # skip slow tests (OSC, gamepad, git)
python diagnose.py --verbose  # show every check, not just failures
```

It validates Python version, dependencies, project structure, syntax across every `.py` file, all module imports, TOML config validity and key mappings, `cfg` singleton attribute coverage (catches broken `cfg.X` references at static-analysis time before runtime crashes), log folder writability, dead/unused imports, OSC port availability, gamepad detection, and git status.

Exit codes: `0` = clean, `1` = warnings only, `2` = errors found. Run before every commit and before every show.

### Architectural constants vs tunables

The codebase distinguishes two kinds of constants:

- **Architectural constants** (`src/config.py`) — facts about the system that never change at runtime. Button indices, OSC paths, the EQ neutral macro value calibrated empirically. These stay hardcoded.

- **Tunable values** (`config/active.toml` via `src/config_loader.py`) — preferences that affect feel. Sweep speeds, deadzones, gesture timings. These load from TOML and are hot-reloadable.

The `cfg` singleton makes the distinction explicit at every call site:

```python
from src.config import EQ_NEUTRAL_MACRO       # architectural — direct import
from src.config_loader import cfg

if value > EQ_NEUTRAL_MACRO:                  # architectural constant
    delta = cfg.EQ_SWEEP_SECONDS * x          # tunable — always current
```

After a hot-reload, `cfg.EQ_SWEEP_SECONDS` returns the new value immediately. The architectural import stays the same forever.

### Adding a new tunable value

Three places need updating:

1. **`config/default.toml`** — add the key in the appropriate `[section]` with a descriptive comment
2. **`src/config_loader.py`** — add the attribute to `_RuntimeConfig.__init__()` and the mapping to `_CFG_MAP`
3. **The module that uses it** — read via `cfg.YOUR_NEW_VALUE`

The diagnostic tool's deep `cfg` reference check will catch missing additions at static-analysis time, before they crash at runtime.

### Logging

FX Machine writes a rotating log file with timestamps:

- `logs/fxmachine.log` (script mode)
- `[exe_folder]/logs/fxmachine.log` (.exe mode)

5 MB per file, 10 rotated backups (~55 MB history). INFO level by default, DEBUG available. Per-module loggers, crash handler for uncaught exceptions, session start/end banners.

Example output:
```
22:47:13.124 [INFO ] fxmachine.osc.client            : OSC sender ready → 127.0.0.1:11000
22:47:13.890 [INFO ] fxmachine.controller.watchdog   : Controller FOUND: USB Gamepad
22:47:14.501 [INFO ] fxmachine.osc.discovery         : FX track found at index 12
22:47:15.001 [INFO ] fxmachine.engine.eq             : EQ band switched to High
22:48:01.789 [INFO ] fxmachine.config_loader         : Reload: EQ_SWEEP_SECONDS 0.3 → 0.5  [applied]
```

---

## 🗺️ Roadmap

### Build B — in progress

- 🎚️ **TRIM knob** — 4th EQ macro controlling a Utility gain device before the EQ Three (input trim, -∞ to +9 dB, DJM-900 NXS2 style)
- 📊 **Redesigned channel meter** — 15-segment vertical, -30 to +12 dB range, color-zoned green→yellow→orange→red
- 🚨 **CLIP indicator** — 2-stage warning (yellow warn + red critical) with smooth color fade and configurable flicker
- 🔄 **Notification slot** — dedicated UI area for transient warnings (config errors, clipping, critical events)
- 🖼️ **UI layout update** — matches DJM-900 NXS2 reference image

### Future builds

- ⏱️ **Tap tempo** — long-press START → tap 4 times → set BPM
- 🥁 **Note repeat / clip roll** — Push-inspired tempo-synced auto-fire
- 🚨 **Panic reset** — L1+L3+R3 = restore all FX + EQ to neutral
- 🎯 **Quantized bass cut release** — beat-synced auto-release at the next downbeat (the "Ben Böhmer move")
- 🖥️ **Big touch overlay** — Push-inspired large value readout when adjusting
- 🎛️ **Auto-map mode** — gamepad maps to currently selected device's first parameters
- 💾 **Per-bookmark baselines** — different FX state per song section
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

🎵 Performing as **[MIRA](https://instagram.com/MIRA___OFC)** (formerly half of **Mirymood** duo)  
🎛️ Project: **Modulated_OFC**  
🇲🇦 Based in Marrakech, Morocco  

Built out of necessity. I wanted a controller that felt like a DJM-900 in front of Ableton — without buying a DJM-900. Then I wanted my friends to be able to use it too, so I made it configurable. Then I wanted to ship it, so I made it a portable app.

Made by and for live performance.

---

<div align="center">

*If this project helped you, leave a ⭐ on the repo.*

</div>