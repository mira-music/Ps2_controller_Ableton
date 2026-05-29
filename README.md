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

1. Download the `FX_Machine.rar` file
2. Extract and Double-click `FX_Machine/FX_Machine.exe`
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

EQ comes first (you decide what frequencies survive), FX comes second (you decide what to do with what survived). Same topology as a Pioneer DJM-900 NXS2 channel strip.

---

## 🎚️ EQ Engine — Deep Dive

The EQ engine is the most sophisticated part of FX Machine. Three bands controlled by one stick, with two distinct gesture vocabularies that don't interfere with each other.

### What's on each band

| Band | Macro | Ableton parameter | Cut limit | Boost limit (encoder) | Boost limit (double-flick) |
|---|---|---|---|---|---|
| **LOW** | `EQ Low` | EQ Three `GainLow` | -∞ dB (full kill) | **+2 dB** (safety cap) | 🚫 **BLOCKED** (sub safety) |
| **MID** | `EQ Mid` | EQ Three `GainMid` | -19 dB (kill target) / -∞ (encoder) | +6 dB | +6 dB (asymptotic) |
| **HIGH** | `EQ High` | EQ Three `GainHi` | -19 dB (kill target) / -∞ (encoder) | +6 dB | +6 dB (asymptotic) |

The asymmetry on the bass band is intentional. Sub-bass content has so much energy that even a small boost can damage subs, blow speakers, or hurt listeners. The bass band is the only one that allows true full-range cut but caps boost aggressively in both gesture modes.

### Signal flow — from physical movement to audio change

```
   You move the stick
          │
          ▼
   pygame.event.get()      [Controller Thread, ~125 Hz polling]
          │
          ▼
   smooth_axis(prev, curr)            [exponential smoothing, factor=0.55]
          │
          ▼
   hybrid_curve(value)                [x^1.8 sign-preserving curve]
          │
          ▼
   handle_axes_eq(ctrl, dt)           [routes to gesture or encoder]
          │
          ├──▶ axis dominance check    [|Y| > |X| * 3.0 → Y wins]
          │
          ├──▶ Y gesture state machine [band switch]
          │
          ├──▶ X gesture state machine [kill / normalize / boost / restore]
          │
          └──▶ eq_drive_continuous_encoder()
                     │
                     ▼
              eq_encoder_delta(stick, dt)   [velocity calc with curve_exp]
                     │
                     ▼
              detent slowdown               [if within ±1 macro of 0 dB]
                     │
                     ▼
              cap by bass safety            [Low band only]
                     │
                     ▼
              throttle check                [15ms minimum between writes]
                     │
                     ▼
              epsilon check                 [skip if change < 0.15 macro units]
                     │
                     ▼
              osc_set_eq_macro(slot, value)
                     │
                     ▼ UDP
              AbletonOSC                    [127.0.0.1:11000]
                     │
                     ▼
              Ableton Live macro
                     │
                     ▼
              EQ Three device parameter
                     │
                     ▼
              Audio output                  [you hear it]
```

**End-to-end latency budget** (typical):

| Stage | Time |
|---|---|
| Controller event polling | ~8 ms (125 Hz loop) |
| Gesture processing | <1 ms |
| OSC throttle wait | 0-15 ms (worst case) |
| UDP send | <1 ms (localhost) |
| AbletonOSC processing | ~2-5 ms |
| Ableton parameter update | ~5-10 ms (audio buffer dependent) |
| **Total** | **~15-40 ms** |

Well below the 50-100 ms threshold where humans perceive lag.

### Continuous control (X-axis encoder)

The encoder isn't a "stick position = parameter value" mapping. That would feel like a wobbly potentiometer. Instead it's **velocity-based**: stick position determines how fast the value changes, not what the value is.

```
Stick at rest:           value stays where it is
Stick pushed right:      value increases over time
Stick pushed left:       value decreases over time
Stick released:          value HOLDS at current position
```

This is how Pioneer's rotary encoders work, and it's why an EQ knob on a real DJ mixer holds its position when you let go.

#### The encoder math

```python
delta = (macro_range / sweep_seconds) × (stick_deflection ^ curve_exp) × dt
```

Where:
- `macro_range = 127.0` (Ableton macro values run 0-127)
- `sweep_seconds = 0.30` — time to sweep the full range at maximum stick deflection
- `curve_exp = 1.0` — pure linear response
- `dt` — frame time delta (typically ~8 ms)

Tuning `curve_exp`:

```
curve_exp = 1.0  (linear):
  stick:  0%  20%  40%  60%  80% 100%
  speed:  0%  20%  40%  60%  80% 100%
  
  ASCII curve: ─────────────────────────
                ░░░░▒▒▒▒▓▓▓▓███████████

curve_exp = 1.5  (slight ease):
  stick:  0%  20%  40%  60%  80% 100%
  speed:  0%   9%  25%  46%  72% 100%
  
  ASCII curve: ──────────────────────
                ─░░░░▒▒▒▓▓▓▓██████████

curve_exp = 2.0  (quadratic):
  stick:  0%  20%  40%  60%  80% 100%
  speed:  0%   4%  16%  36%  64% 100%
  
  ASCII curve: ─────────────────────
                ──░░░░▒▒▒▓▓▓██████████
```

Lower `curve_exp` = more aggressive (small movements have big effect). Higher = more precise near rest (small movements have small effect).

#### Sticky 0 dB detent

When the encoder is near neutral (within ±1 macro unit of 0 dB), it slows down. This mimics the tactile detent on real EQ knobs at noon — easy to "find" zero without overshooting.

```python
distance = abs(current_value - 107.9)   # EQ_NEUTRAL_MACRO
if distance < cfg.EQ_DETENT_RANGE:       # default 1.0
    detent_factor = max(cfg.EQ_DETENT_MIN_FACTOR, distance / cfg.EQ_DETENT_RANGE)
    delta *= detent_factor
```

With defaults (`range=1.0`, `min_factor=0.30`):
- 1.0 macro units from neutral → speed = 100%
- 0.5 macro units from neutral → speed = 50%
- 0.0 macro units from neutral → speed = 30% (minimum)

You can stop AT 0 dB easily, but you don't get stuck there.

### Discrete actions (double-flick gestures)

The same stick handles BOTH continuous encoder AND discrete actions via double-flicks. The distinction is gesture detection: a "flick" is movement that reaches 90% extreme deflection within a few frames.

```
       extreme         center         extreme
  idle ────────▶ flicked ─────▶ returned ─────▶ confirmed → fire action
  ◀─────── timeout (380ms) ──────────────────▶ reset
                                  ▼
                          must be SAME direction
```

Tunable thresholds:
- `EQ_FLICK_EXTREME = 0.90` — stick must reach 90% deflection
- `EQ_FLICK_RETURN = 0.22` — must drop below 22% to count as "returned"
- `EQ_FLICK_TIMEOUT_MS = 380` — second flick must arrive within 380 ms

The state machine code in pseudo-Python:

```python
state = "idle"

while True:
    if state == "idle":
        if abs(stick_x) >= 0.90:
            state = "flicked"
            gesture_dir = sign(stick_x)
            gesture_time = now()
    
    elif state == "flicked":
        if abs(stick_x) < 0.22:
            state = "returned"
        elif (now() - gesture_time) > 0.380:
            state = "idle"           # timeout, reset
    
    elif state == "returned":
        if abs(stick_x) >= 0.90 and sign(stick_x) == gesture_dir:
            FIRE_ACTION(gesture_dir)  # second flick confirmed
            state = "idle"
        elif (now() - gesture_time) > 0.380:
            state = "idle"           # timeout, reset
```

#### Smart kill / normalize (double-flick LEFT)

```
if current_value > 0 dB:
    → normalize to 0 dB (pull it back to neutral)

else (current_value ≤ 0 dB):
    if BASS:    → KILL to -∞ dB
    if MID:     → cut to -19 dB
    if HIGH:    → cut to -19 dB
```

**Why context-aware?** A real DJ doesn't think "kill" and "normalize" as separate gestures — they think "pull this back". The same stick movement does the musically appropriate thing depending on where you are. Boost above neutral? Pull back to neutral. At/below neutral? Kill it.

#### Smart restore / boost (double-flick RIGHT)

```
if current_value < 0 dB:
    → restore to 0 dB

else (current_value ≥ 0 dB):
    if MID or HIGH:  → boost by 15% of remaining headroom (asymptotic)
    if BASS:         → 🚫 BLOCKED (sub safety)
```

The asymptotic boost: if you're at +2 dB on Mid (headroom = +4 dB to ceiling), the boost adds 15% of that headroom = +0.6 dB, putting you at +2.6 dB. Next flick adds 15% of the new headroom (+3.4 dB × 15% = +0.51 dB), putting you at +3.11 dB. You approach +6 dB but never quite reach it through gestures alone. Forces you to think about each boost rather than blindly stacking them.

### Band navigation (Y-axis double-flick)

Same gesture pattern as X, but Y axis controls which band is selected.

```
Y double-flick UP:    MID → HIGH → LOW → MID → ...   (wraps, no borders)
Y double-flick DOWN:  MID → LOW → HIGH → MID → ...   (wraps, no borders)
```

The wrap is intentional. There's no "you've hit the end" message — you just keep cycling. Performance-friendly: you can always reach any band in at most one double-flick.

### Cross-axis safety (mutual exclusion)

The right stick is one physical input doing two logical things (X = value, Y = band). To prevent diagonal motion from triggering both:

```python
# Step 1: process Y gesture first (band switch)
y_in_gesture = update_eq_y_gesture(stick_y, now)

# Step 2: Y-dominance suppression
y_dominates = abs(stick_y) > abs(stick_x) * 3.0

if y_in_gesture or y_dominates:
    # Y owns the stick this frame → freeze X completely
    reset_x_gesture_state()
    return

# Step 3: process X gesture (kill / restore / etc)
x_in_gesture = update_eq_x_gesture(stick_x, now)

if x_in_gesture:
    # X gesture in progress → freeze Y this frame
    reset_y_gesture_state()
    return

# Step 4: only if no gesture owns the stick, run continuous encoder
eq_drive_continuous_encoder(stick_x, now)
```

Both axes use mutual exclusion. Once one wins, the other is frozen until the first completes or times out. The 3.0 dominance ratio means Y must be **3× larger than X** to claim dominance — preventing accidental band switches when you're just trying to adjust value with slight stick drift.

### Animated transitions (cubic ease-out ramps)

When a gesture triggers an action, the macro value doesn't snap — it animates over 30-100 ms using cubic ease-out:

```python
progress = elapsed / duration            # 0.0 → 1.0
eased = 1.0 - (1.0 - progress) ** 3      # cubic ease-out
current_value = start + (target - start) * eased
```

Why cubic ease-out specifically:
- **Linear ramps** sound abrupt at the end (sudden stop)
- **Exponential ramps** (`1 - e^(-3x)`) drag at the start (slow attack)
- **Cubic ease-out** starts fast and decelerates smoothly — musically natural, click-free

The ramp duration scales with how fast you flicked:
- Fast flick (30 ms between extremes) → 30 ms ramp (snappy)
- Slow flick (200 ms between extremes) → 100 ms ramp (smooth)

Linear interpolation in between.

### Throttling and epsilon culling

The encoder runs at ~125 Hz (controller loop rate). Sending an OSC message every frame would flood Ableton with ~125 messages/sec per band, ~375/sec across all three bands when you're sweeping. That's wasteful.

Two filters prevent this:

**Throttle**: minimum time between writes for the same band
```python
if (now - last_write_at) < cfg.EQ_WRITE_THROTTLE:   # default 15 ms
    return  # skip this write
```

**Epsilon**: minimum value change worth sending
```python
if abs(new_value - last_value) < cfg.EQ_WRITE_EPSILON:   # default 0.15 macro units
    return  # too small to perceive
```

15 ms = ~66 messages/sec per band, 0.15 macro units ≈ 0.07 dB at neutral (imperceptible). Net result: smooth feel, ~80% reduction in OSC traffic.

### Failure modes

What happens when things go wrong:

| Failure | Recovery |
|---|---|
| Ableton crashes | OSC sends fail silently (UDP). Controller still responds. App keeps running. When Ableton restarts and AbletonOSC reconnects, FX Machine auto-discovers it. |
| Controller unplugged mid-flick | Gesture state held in memory. Watchdog detects disconnect within 5 sec. When you replug, gesture resets to `idle` — partial gesture is lost (correct behavior, prevents stuck states). |
| TOML edited with syntax error mid-session | `reload_config()` catches the error, keeps current values in memory, shows error in action bar. Encoder keeps working with old values. Fix the typo, reload again. |
| Two gestures fired simultaneously | Mutual exclusion freezes the loser. Only one fires. |
| Macro value drifts due to OSC packet loss | Polling thread re-queries macro values every 2 sec (the "safety poll"). Drift gets corrected within 2 sec. |

---

## ⚡ FX Engine — Deep Dive

The FX engine is simpler than EQ in gesture vocabulary (no double-flicks, no smart actions) but its **internal rack architecture is the most clever piece of the project**. It mirrors the topology of a real DJ mixer's send/return loop.

### What's on each macro

| Slot | Macro | Effect | Range | Behavior |
|---|---|---|---|---|
| 1 | `Filter Freq` | Auto Filter cutoff | 20 Hz – 20 kHz (logarithmic) | Sweeps with acceleration |
| 2 | `Filter Mode` | Auto Filter type | 0 = HP, 1 = LP | Toggle via Bass Cut momentary |
| 3 | `Filter Res` | Auto Filter resonance | 20% – 100% | Sweeps |
| 4 | `Stutter` | Beat Repeat on/off | 0 or max | Momentary (L1+X) |
| 5 | `Reverb Size` | Dark Hall decay | 200 ms – 60 s | Sweeps slowly |
| 6 | `FX Send` | Wet chain gain (Utility) | 0% – 100% | Sweeps; momentary throw (L1+□) |
| 7 | `Delay FB` | Long Digi Delay feedback | 0% – 92% (capped) | Discrete D-pad steps |
| 8 | `Width` | Stereo Utility width | 0% – 200% | Sweeps |

### Internal rack topology — the wet/dry trick

Most macro mappings would put effects in series: Filter → Reverb → Delay → Output. That's wrong for live performance. You want the dry signal to **always pass through**, and effects to add on top without ever replacing the dry. You also want reverb and delay tails to **continue ringing** when you stop sending to them.

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

#### Audio signal flow

```
Input ─┐
       │
       ├──▶ Auto Filter (always) ──▶ Beat Repeat (always) ─┐
       │                                                    │
       │                                          ┌─────────┴─────────┐
       │                                          │                   │
       │                                       Dry path          Wet path
       │                                       (passthrough)     (via Utility gain)
       │                                          │                   │
       │                                          │                   ▼
       │                                          │              Dark Hall (reverb)
       │                                          │                   │
       │                                          │                   ▼
       │                                          │              Long Digi Delay
       │                                          │                   │
       │                                          └─────────┬─────────┘
       │                                                    │
       │                                              Sum dry + wet
       │                                                    │
       │                                                    ▼
       │                                                Utility (width)
       │                                                    │
       └────────────────────────────────────────────────────┴──▶ Output
```

The key insight: **FX Send macro controls the GAIN of the input to the wet chain, not the wet/dry mix**. When FX Send = 0:
- The Utility's gain in the wet chain drops to -∞
- **No new signal enters the wet processing**
- BUT: the reverb and delay already inside the wet chain **continue to decay/feed back naturally**
- The dry chain continues passing through unchanged

That's why dropping FX Send to 0 leaves the dry signal pristine while the existing tails fade out gracefully over the next 5-30 seconds.

#### Why this matters musically

Traditional wet/dry: `wet_amount` controls the blend. Set to 0 → wet sound vanishes instantly, including any tails. Set to 100% → no dry sound.

This routing: `FX Send` controls the input to the wet processor. Set to 0 → no new wet signal generated, but existing tails keep ringing. Dry is always at 100%.

This is **exactly how a Pioneer DJM-900's send/return loop works**, and why a DJM-900 throw doesn't sound like a wet/dry knob — it sounds like a real send.

### The "throw and let it tail" technique

The momentary FX SEND THROW button (L1+□) is built for this routing:

```
1. Press L1+□        → FX Send macro jams to 100% (full feed to wet chain)
                       Reverb and delay get fed maximum input
2. Hold for 1-2 bars  → big wet swell builds up in the wet chain
3. Release            → FX Send snaps back to its previous value (snapshot restore)
                       New wet input stops, but the wet chain still has signal in it
4. Dry continues clean throughout
5. Reverb decay rings for 5-30+ sec depending on Reverb Size
6. Delay feedback bounces with the rhythm you had set
```

You can stack throws — throw, release, throw, release — to build walls of tails. Then kill the bass and drop a fresh element. The tails carry the energy through the transition while the new sound establishes itself. Classic Ben Böhmer / Yotto / Nora En Pure move.

### How each macro lives in the chain

| Macro | Path | What it does | Affects |
|---|---|---|---|
| Filter Freq | Outer (main) | Auto Filter cutoff frequency | Everything (dry AND wet) |
| Filter Mode | Outer (main) | HP/LP type | Everything |
| Filter Res | Outer (main) | Resonance peak | Everything |
| Stutter | Outer (main) | Beat Repeat on/off | Everything |
| **FX Send** | **Inner (wet chain input)** | **Gain into the wet processing chain** | **Wet feed only — dry untouched** |
| Reverb Size | Inner (wet chain) | Dark Hall decay time | Wet only |
| Delay FB | Inner (wet chain) | Delay feedback amount | Wet only |
| Width | Outer (final) | Stereo width | Combined dry+wet output |

This means you can **filter the wet tails** by sweeping Filter Freq while the wet chain is decaying — outer effects process the combined signal. Stutter affects everything. Width widens the entire output.

Powerful for transitions: sweep down the filter while letting reverb tails ring through, then re-open the filter on the drop. The tails "filter through" the cutoff sweep, which sounds completely different from sweeping the filter on dry signal alone.

### Macro stick driver — integrator model

Unlike the EQ encoder (velocity-based, value holds on release), the FX macros use a **direct integrator** with acceleration. Holding the stick longer increases the rate of change.

```python
# In fx_drive_macro():

# Compute the per-frame delta
delta = stick_value × (macro_range / sweep_seconds) × dt × accel_mult

# Apply with clamping to macro min/max
target = clamp(current + delta, min_val, max_val)

# Throttle, epsilon, write
```

Where `accel_mult` ramps from 1.0 to 4.0 over 1 second when you hold the stick in one direction:

```python
elapsed_since_direction_change = now - direction_change_time
accel_mult = 1.0 + (elapsed / FX_ACCEL_RAMP_S)
accel_mult = min(accel_mult, FX_ACCEL_MAX_MULT)
```

The acceleration model is **directional** — change direction and the multiplier resets to 1.0. This gives precise control for small adjustments AND fast sweeps for build-ups, without forcing you to choose between them.

#### Per-macro sweep times

Each named macro has its own sweep duration, tuned for musical use:

| Macro | Default sweep | Why |
|---|---|---|
| Filter Freq | 1.5 s | The most-played macro — fast enough for builds, slow enough for control |
| Filter Res | 3.0 s | Resonance is "set and forget" most of the time |
| Reverb Size | 5.0 s | You rarely want to sweep reverb size during a track |
| FX Send | 1.0 s | Punchy throws need quick response |
| (any other) | 3.0 s | Default fallback |

All tunable via TOML. A producer who lives on the filter might want `filter_freq_sweep_s = 0.8` for snappier sweeps. A studio engineer might prefer `3.0` for slower, more deliberate changes.

### Momentary buttons — snapshot/restore

Three buttons in FX mode trigger momentary effects that **snapshot the current parameter state** when pressed, jam to a target value while held, and **restore the snapshot** on release.

```
Press   →  snapshot[slot] = current_value[slot]
           current_value[slot] = target_value   (write to Ableton)

Release →  current_value[slot] = snapshot[slot]  (restore to Ableton)
```

#### L1 + X — STUTTER

```
Press:    Stutter macro = max  (Beat Repeat activates)
Release:  Stutter macro = 0    (Beat Repeat deactivates)
```

No snapshot needed — Stutter is always 0 outside of momentary use.

#### L1 + O — BASS CUT

```
Press:    snapshot = (filter_freq, filter_mode)
          filter_freq = 42.3      (≈200 Hz on the macro)
          filter_mode = 0.0       (HP — high-pass mode)

Release:  filter_freq = snapshot.filter_freq
          filter_mode = snapshot.filter_mode
```

The snapshot captures BOTH Filter Freq and Filter Mode so a release restores you to exactly where you were — whether you had LP at 5 kHz or HP at 100 Hz before pressing.

#### L1 + □ — FX SEND THROW

```
Press:    snapshot = fx_send
          fx_send = max          (full feed to wet chain)

Release:  fx_send = snapshot
```

Combined with the wet/dry routing above, this creates the "throw and tail" technique. Snapshot ensures you go back to your previous level, not necessarily 0.

### L1 release recovery — the safety net

When you release the L1 button (exit FX mode), the system runs a recovery sweep across all 8 macros. Each macro has a behavior defined in `FX_RECOVERY_BEHAVIOUR`:

```python
FX_RECOVERY_BEHAVIOUR = {
    FX_SLOT_FILTER_FREQ:  "filter",     # restore to baseline (unless filter-locked)
    FX_SLOT_FILTER_MODE:  "skip",       # leave it as is
    FX_SLOT_FILTER_RES:   "skip",       # leave it as is
    FX_SLOT_STUTTER:      "fixed:0.0",  # always snap to 0
    FX_SLOT_REVERB_SIZE:  "skip",       # leave the size where you set it
    FX_SLOT_FX_SEND:      "wet",        # snap to 0 (unless wet-locked)
    FX_SLOT_DELAY_FB:     "skip",       # leave the FB where you set it
    FX_SLOT_WIDTH:        "skip",       # leave width where you set it
}
```

| Behavior | Meaning |
|---|---|
| `skip` | Don't touch this macro on L1 release |
| `fixed:N` | Always snap to value N |
| `filter` | Restore to baseline (snapshotted at startup or via SELECT+R1), unless filter-locked |
| `wet` | Snap to 0 (drop the wet send), unless wet-locked |

So a typical L1 release sequence is:
1. Filter Freq → baseline (e.g., 20 kHz fully open) ← unless filter-locked
2. FX Send → 0 ← unless wet-locked (the reverb/delay tails ring out)
3. Stutter → 0 (force off, always)
4. Everything else stays put

The **tails keep their character** (Reverb Size stays at whatever you set, Delay FB stays at whatever you set) but the **send dries up** — exactly the throw-and-tail behavior.

### Filter lock and Wet lock

Two toggle buttons (L1+L3 and L1+R3) flip these flags:

```python
fx_filter_locked = True/False    # affects "filter" recovery behavior
fx_wet_locked    = True/False    # affects "wet" recovery behavior
```

When `filter_locked` is True, the Filter Freq macro is NOT restored to baseline on L1 release — it stays where you swept it to. Useful for "I want to keep this filter sweep as the new baseline for this section".

When `wet_locked` is True, the FX Send macro is NOT snapped to 0 on L1 release — it stays at whatever level you set. Useful for "I want a constant wet bath for this entire breakdown".

Visually, the FX panel shows the lock state with 🔒 icons. Tap the same button again to unlock.

### Delay FB — discrete D-pad stepping

Unlike the other macros (continuous stick control), Delay FB is controlled by the D-pad in FX mode with **discrete steps**. Why: feedback is the parameter that can go runaway easiest, and you usually want predictable amounts (50%, 60%, 70%) not analog sweeps.

```python
step_size = macro_range / cfg.FX_DELAY_FB_STEPS   # default 20 steps
current_step = round((current - min) / step_size)

D-pad right: new_step = clamp(current_step + 1, 0, 20)
D-pad left:  new_step = clamp(current_step - 1, 0, 20)

target = min + new_step × step_size

# Safety cap — never let feedback exceed 92% (runaway prevention)
cap = min + macro_range × cfg.FX_DELAY_FB_CLAMP_FRAC
target = min(target, cap)
```

20 steps across the range, capped at 92% to prevent infinite feedback. Debounced (`cfg.FX_DELAY_FB_DEBOUNCE = 0.18 s`) so a quick double-tap doesn't accidentally skip two steps.

### Failure modes (FX layer)

| Failure | Recovery |
|---|---|
| L1 released mid-momentary | The momentary button's release handler runs, restoring its snapshot. Then `fx_recover_on_l1_release()` runs. Order is correct. |
| Stutter button stuck pressed (controller bug) | Watchdog ghost-event reconciliation will detect physical release within 100 ms and force the stutter off. |
| Delay FB pushed past cap | Cap is enforced. The status line shows "MAX (capped 92%)" so you know it's capped. |
| Ableton crashes mid-throw | Momentary release will still write to the OSC port. Ableton restart picks up the value. App keeps running. |
| Filter lock and Wet lock both on at L1 release | Status shows "filter+wet HELD". Only Stutter recovers (it's "fixed:0.0"). All other macros stay put. |

---

## 🔧 How It Works — Architecture Deep Dive

This section is for the engineering-curious. Skip if you just want to use the app.

### The 5-thread coordination model

FX Machine runs **5 concurrent daemon threads** that share state through a thread-safe dictionary. None of them block each other, but they all coordinate through one central state object.

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Main Thread (Tkinter UI, 40 Hz)                           │
│   ├─ Reads state dict every 25 ms                           │
│   ├─ Renders knobs, meters, labels                          │
│   └─ Schedules itself via root.after()                      │
│                                                             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ reads state[*]
                     │
                     ▼
              ┌─────────────────────┐
              │  shared state dict  │  ◀──── all threads converge here
              │  protected by RLock │       (state = {...} in src/state.py)
              └─────────────────────┘
                     ▲    ▲    ▲    ▲
                     │    │    │    │
                     │    │    │    │
   ┌─────────────────┘    │    │    └─────────────────┐
   │                      │    │                      │
   │                      │    │                      │
┌──┴──────────────┐  ┌────┴────┐  ┌─────┴──────┐  ┌──┴──────────────┐
│ Controller      │  │  OSC    │  │  Polling   │  │  Watchdog       │
│ Thread (125 Hz) │  │ Server  │  │  Thread    │  │  Thread (1 Hz)  │
│                 │  │ Thread  │  │  (6.6 Hz)  │  │                 │
│ pygame events   │  │         │  │            │  │ Controller      │
│ axis sampling   │  │ Receive │  │ Periodic   │  │ health checks   │
│ gesture engine  │  │ from    │  │ Ableton    │  │ Ghost-event     │
│ writes to       │  │ Ableton │  │ queries    │  │ reconciliation  │
│ Ableton via OSC │  │ Update  │  │ Safety     │  │ Auto-reprobe    │
│                 │  │ state   │  │ polls      │  │                 │
└─────────────────┘  └─────────┘  └────────────┘  └─────────────────┘

                              + EQ Ramp Thread (60 Hz)
                                Animates kill/normalize/boost
                                Smooth value transitions
```

### Why these specific rates

| Thread | Rate | Why this rate |
|---|---|---|
| Controller | 125 Hz (8 ms) | pygame.time.wait(8) — sweet spot for stick smoothness without burning CPU. Higher = no perceptible improvement. Lower = visible stutter on fast flicks. |
| OSC Server | Event-driven | Pythonosc dispatches as soon as a UDP packet arrives. ~5 ms latency from Ableton to handler. |
| Polling | 6.6 Hz (150 ms) | Slow enough to not flood Ableton. Fast enough to catch BPM changes, volume tweaks, and rebuild sessions within 1-2 sec. |
| Watchdog | 1 Hz | Controller disconnect detection within 5 sec is fine. More frequent = wasted CPU. |
| EQ Ramps | 60 Hz (16 ms) | Visual smoothness threshold. Below 30 Hz looks janky. Above 60 Hz is wasted (UI only redraws at 40 Hz anyway). |
| Tkinter UI | 40 Hz (25 ms) | Smooth knob/meter animation without burning CPU. Tk struggles above 60 Hz on Windows. |

### The lock strategy

All five threads read and write to the same `state` dict. Coordination uses a single **reentrant lock (`RLock`)**:

```python
# src/state.py
import threading
_lock = threading.RLock()
state = {...}    # the shared dict
ableton = {...}  # mirror of Ableton's current values
```

Three rules govern lock usage:

**Rule 1: Always hold the lock when reading or writing state**

```python
with st._lock:
    selected_band = st.state["eq_selected_band"]
    current_val   = st.state["eq_macro_values"][selected_band]
```

**Rule 2: NEVER call OSC functions while holding the lock**

```python
# BAD — holds lock during network I/O
with st._lock:
    osc.send_message(...)   # could take 5 ms, blocks all other threads

# GOOD — copy state into local, release lock, then call OSC
with st._lock:
    track = st.state["track"]
    value = st.state["eq_macro_values"][slot]
osc.send_message(..., [track, value])   # lock released
```

**Rule 3: Use a reentrant lock so nested calls don't self-deadlock**

```python
def update_ui():
    with st._lock:
        snapshot_state()
        clear_flashes_if_expired()  # this function ALSO acquires st._lock

# clear_flashes_if_expired:
def clear_flashes_if_expired():
    with st._lock:   # OK with RLock — same thread can re-acquire
        ...
```

This combination eliminates deadlocks and race conditions, even with 5 threads hitting state thousands of times per second.

### What state lives where

```python
# src/state.py

state = {
    # NAVIGATION
    "track":              0,         # current track index
    "scene":              0,         # current scene index
    "bookmark_cursor":    0,         # current bookmark
    "group_cursor":       0,         # current group
    
    # MODIFIERS
    "l1_held":            False,
    "r2_held":            False,
    "select_held":        False,
    
    # EQ
    "eq_mode_active":     False,
    "eq_selected_band":   1,         # 0=Low, 1=Mid, 2=High
    "eq_macro_values":    [107.9, 107.9, 107.9],  # current values
    "_eq_flick_x_state":  "idle",    # gesture state machine
    "_eq_flick_y_state":  "idle",
    "_eq_encoder_last_tick": 0.0,    # for dt calculation
    "_eq_last_write_at":  [0.0, 0.0, 0.0],   # OSC throttle tracking
    "_eq_ramp_active":    [False, False, False],
    
    # FX
    "fx_macro_values":    [0.0] * 8,
    "fx_baseline":        [0.0] * 8,
    "fx_filter_locked":   False,
    "fx_wet_locked":      False,
    "_momentary_stutter_active":  False,
    "_momentary_bass_cut_snapshot": {"freq": 0, "mode": 0},
    
    # METER
    "eq_meter_left":      0.0,       # 0.0 to 1.0
    "eq_meter_right":     0.0,
    "eq_meter_peak":      0.0,
    
    # UI
    "last_action":        "Starting up…",
    "flash_until":        0.0,
    
    # ... many more ...
}

ableton = {
    "bpm":            120.0,
    "is_playing":     False,
    "track_name":     "—",
    "track_volume":   0.85,
    "clip_name":      "—",
    "all_track_names": [],
    "all_scene_names": [],
    # ... mirror of Ableton's current values, populated by OSC handlers ...
}
```

### The OSC roundtrip

When you push the EQ stick right:

```
T+0 ms:    Controller thread reads stick = (0, 0.8)
T+0.1 ms:  smooth_axis() applies exponential filter
T+0.2 ms:  hybrid_curve() applies x^1.8 shaping
T+0.5 ms:  axis dominance check → X wins
T+0.6 ms:  X gesture state machine: stick < 0.90 extreme → not a flick
T+0.7 ms:  eq_drive_continuous_encoder() called
T+0.8 ms:  eq_encoder_delta() computes velocity-based delta
T+1.0 ms:  detent check (we're not near neutral, no slowdown)
T+1.1 ms:  bass safety cap check (we're on Mid, no cap)
T+1.2 ms:  throttle check (15 ms since last write? yes, proceed)
T+1.3 ms:  epsilon check (change > 0.15 macro units? yes, proceed)
T+1.4 ms:  state[eq_macro_values][1] updated
T+1.5 ms:  osc.send_message("/live/device/set/parameter/value", [13, 0, 2, 110.5])
T+2.0 ms:  UDP packet arrives at 127.0.0.1:11000
T+5.0 ms:  AbletonOSC receives, parses, dispatches to handler
T+8.0 ms:  Ableton's macro value updates internally
T+10.0 ms: EQ Three device parameter updates
T+15.0 ms: Audio buffer reflects new EQ curve
T+20.0 ms: You hear the change

Meanwhile, asynchronously:
T+50 ms:   AbletonOSC sends "/live/device/get/parameter/value" listener event back
T+52 ms:   FX Machine's OSC server thread receives it
T+53 ms:   on_fx_param_value() updates ableton.eq_macro_values[1]
T+55 ms:   UI thread reads the updated value
T+80 ms:   Knob position visually updates in the UI
```

So you push the stick → hear it in ~20 ms → see the knob move in ~80 ms. Both fast enough that the system feels instantaneous.

### The dirty-cache UI rendering

The Tkinter UI runs at 40 Hz. Naively redrawing 8 FX knobs, 3 EQ knobs, a 24-segment meter, and ~30 labels every frame would burn CPU on operations Tkinter is bad at (canvas redraws, label updates).

Optimization: **dirty caching**. Every render call checks if the rendered output would actually change. If not, skip the draw.

```python
# src/ui/widgets.py
_knob_cache = {}

def draw_knob(canvas, slot, value_frac, color, active, locked, moment):
    cache_key = (round(value_frac, 3), color, active, locked, moment)
    if _knob_cache.get(slot) == cache_key:
        return   # nothing changed, skip the canvas redraw
    _knob_cache[slot] = cache_key
    
    canvas.delete("all")
    # ... actually draw ...
```

Each knob has a cache key built from its parameters. When the parameters haven't changed since last frame, the function returns immediately without touching the canvas. In a static UI moment (no controller input, no Ableton activity), the entire UI consumes <0.1% CPU.

Same pattern for labels (`set_label` function) — it tracks the last text and color and skips the update if both are identical.

### The session discovery handshake

When the app starts, it needs to learn Ableton's session state. This takes ~2-3 seconds and happens in stages:

```
T+0.0 s:   App launches, OSC sender and receiver come up
T+0.5 s:   fetch_all_names() thread starts
T+0.5 s:     osc.send("/live/song/get/num_scenes", [])
T+0.5 s:     osc.send("/live/song/get/num_tracks", [])
T+1.1 s:   Counts received: 8 scenes, 21 tracks
T+1.1 s:   Fetch all scene names + colors (each takes ~12 ms)
T+1.6 s:   rebuild_bookmarks() — finds scenes prefixed with §
T+1.6 s:   Fetch all track names + colors
T+2.1 s:   rebuild_groups() — finds tracks prefixed with *
T+2.1 s:   rebuild_fx_track() — finds the track named "~ FX Macros"
T+2.1 s:   rebuild_eq_track() — finds the track named "~ EQ Macros"
T+2.2 s:   FX rack discovered at index 20
T+2.2 s:   Load FX macro names (8 parallel queries)
T+2.6 s:   FX macros mapped: 8/8
T+2.6 s:   Load FX min/max/values
T+2.9 s:   Baseline auto-captured from current values
T+2.9 s:   FX listeners registered (16 listeners: 8 values + 8 strings)
T+2.9 s:   EQ rack discovered at index 18
T+3.0 s:   EQ macro names mapped: 3/3
T+3.4 s:   EQ listeners registered (6 listeners)
T+3.5 s:   EQ meter listeners armed (track output L+R)
T+3.5 s:   Ready — all systems online
```

During those 3 seconds, the UI shows "loading" indicators and macro names appear as they're discovered. After T+3.5 s, everything is reactive — Ableton's listeners push updates as they happen.

### The config singleton pattern

The TOML hot-reload system relies on a design pattern that's worth explaining: the **runtime singleton**.

```python
# src/config_loader.py

class _RuntimeConfig:
    def __init__(self):
        # Seed from hardcoded defaults
        self.EQ_SWEEP_SECONDS = defaults.EQ_SWEEP_SECONDS
        self.EQ_AXIS_DEAD_ZONE = defaults.EQ_AXIS_DEAD_ZONE
        # ... etc ...

cfg = _RuntimeConfig()   # singleton — module-level
```

Modules consume it like this:

```python
# src/engine/eq.py
from src.config_loader import cfg

def eq_drive_continuous_encoder(stick_x, now):
    if abs(stick_x) < cfg.EQ_AXIS_DEAD_ZONE:   # always reads current value
        return
    # ...
```

**Why this works for hot-reload**: when `reload_config()` runs, it modifies `cfg` attributes in place:

```python
def _apply_toml(toml_data):
    for attr, path in _CFG_MAP:
        value = _nested_get(toml_data, path)
        if value != getattr(cfg, attr):
            setattr(cfg, attr, value)   # mutate the singleton
```

Because every module accesses `cfg.EQ_SWEEP_SECONDS` (not a cached local copy), the **next time any function reads it, it gets the new value**. No import refresh needed, no module reload, no thread restart.

This is the difference between:
```python
# BAD — value cached at import time
from src.config import EQ_SWEEP_SECONDS
def encoder():
    delta = EQ_SWEEP_SECONDS * x   # always old value
```

```python
# GOOD — value read every call
from src.config_loader import cfg
def encoder():
    delta = cfg.EQ_SWEEP_SECONDS * x   # always current value
```

We use the first pattern for **architectural constants** that genuinely never change (button indices, OSC paths). We use the second for everything that should be tunable.

### Why we have a diagnostic tool

`diagnose.py` exists because **distributed state across 30+ files is hard to reason about manually**. The tool runs 150+ checks in ~1.5 seconds:

- Every `.py` file syntactically valid?
- Every import resolves?
- Every TOML key referenced in code actually exists in `default.toml`?
- Every `cfg.X` reference in code actually exists in the singleton? *(this caught a real bug during Build A)*
- Every required project file present?
- OSC ports actually bindable?
- Gamepad detected with expected button count?
- Logs folder writable?

The "deep cfg.X reference check" is the most powerful: it walks every source file's AST, finds every `cfg.<attribute>` reference, and verifies the singleton actually has that attribute. **Catches a class of bug that would otherwise crash at runtime during a show**.

You run it before every commit, before every show. Exit codes: 0 = clean, 1 = warnings, 2 = errors. Use it in your shell aliases.

---

## 📊 DJM-Style Channel Meter

A 24-segment vertical LED meter beside the EQ stack shows real-time audio output level from the EQ track via Ableton's `output_meter_left/right` listeners. 

### How the meter reads audio

```
Audio plays in Ableton
        │
        ▼
Ableton calculates output_meter_left and output_meter_right
(updates every audio buffer, typically every ~11 ms)
        │
        ▼
AbletonOSC sends "/live/track/get/output_meter_left" listener events
        │
        ▼ UDP
FX Machine OSC server receives
        │
        ▼
on_track_meter_left() updates state["eq_meter_left"]
on_track_meter_right() updates state["eq_meter_right"]
        │
        ▼
UI thread (40 Hz) reads max(left, right)
        │
        ▼
draw_channel_meter() updates the segment display
```

### Visual design

- **24 segments** stacked vertically
- **Color zones**: bottom 18 = green (safe), middle 4 = yellow (loud), top 2 = red (clipping zone)
- **Peak hold indicator**: brightest segment hovers at the recent peak for 1.5 seconds, then decays

### Peak hold math

```python
def update_meter_peak(current, last_peak, last_peak_time, now):
    if current >= last_peak:
        # New peak — capture it
        return (current, now)
    
    elapsed = now - last_peak_time
    if elapsed < cfg.METER_PEAK_HOLD_SECONDS:
        # Still in hold window — keep the peak
        return (last_peak, last_peak_time)
    
    # Hold expired — start decaying
    fall_elapsed = elapsed - cfg.METER_PEAK_HOLD_SECONDS
    decayed = last_peak - cfg.METER_PEAK_FALL_DB_PER_SEC * fall_elapsed
    if decayed < current:
        return (current, now)   # caught up to current
    return (max(decayed, 0.0), last_peak_time)
```

Three states: capture new peak → hold for 1.5 s → linear decay until it reaches the current level.

> 🚧 **Build B (in progress)** will redesign this as a 15-segment -30 to +12 dB meter matching the DJM-900 NXS2 reference image, plus a CLIP indicator at the top with 2-stage warning (yellow→red color fade + configurable flicker) when audio approaches digital clipping. The meter will also gain a separate TRIM knob to control input gain before the EQ Three.

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

## 🏗️ Project Structure

<details>
<summary><b>📖 Click for full file tree</b></summary>

```
fxmachine/
├── run.py                      Entry point: python run.py
├── build.py                    PyInstaller .exe builder (onedir mode)
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

</details>

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