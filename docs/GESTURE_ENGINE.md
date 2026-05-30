## docs/GESTURE_ENGINE.md

```markdown
# 🎮 FX Machine — Gesture Engine Deep Dive

## What This Document Covers

This guide explains the complete gesture recognition system that
translates physical gamepad stick movements into musical actions.
It covers the double-flick state machines, the continuous encoder
model, the axis dominance system, the mutual exclusion logic, the
TRIM-specific behavior, the ramp animation system, and every tunable
parameter that affects how gestures feel.

The gesture engine is the most novel part of FX Machine. It solves a
specific problem: how do you give a $10 USB gamepad the expressive
feel of a $2000 DJ mixer's EQ section? The answer is a combination
of velocity-based encoding, context-aware double-flick actions,
cross-axis mutual exclusion, and carefully tuned response curves —
all running on one physical stick with two axes.

If you're tuning the feel of the controller, debugging a gesture
that isn't firing, or adding new gesture types, this is the document
you need.

---

## Table of Contents

1. [The Problem This Solves](#the-problem-this-solves)
2. [Physical Input Model](#physical-input-model)
3. [Input Processing Pipeline](#input-processing-pipeline)
4. [The Continuous Encoder Model](#the-continuous-encoder-model)
5. [Encoder Math — Full Derivation](#encoder-math--full-derivation)
6. [The Sticky 0 dB Detent](#the-sticky-0-db-detent)
7. [Response Curves Explained](#response-curves-explained)
8. [Axis Smoothing](#axis-smoothing)
9. [Dead Zone Processing](#dead-zone-processing)
10. [The Double-Flick State Machine](#the-double-flick-state-machine)
11. [X-Axis Gestures — Value Actions](#x-axis-gestures--value-actions)
12. [Y-Axis Gestures — Band Navigation](#y-axis-gestures--band-navigation)
13. [Cross-Axis Mutual Exclusion](#cross-axis-mutual-exclusion)
14. [The Dominance Ratio](#the-dominance-ratio)
15. [Smart Kill and Normalize](#smart-kill-and-normalize)
16. [Smart Restore and Boost](#smart-restore-and-boost)
17. [The Asymptotic Boost](#the-asymptotic-boost)
18. [Bass Safety System](#bass-safety-system)
19. [TRIM-Specific Gesture Behavior](#trim-specific-gesture-behavior)
20. [Animated Transitions — Cubic Ease-Out Ramps](#animated-transitions--cubic-ease-out-ramps)
21. [Ramp Duration Scaling](#ramp-duration-scaling)
22. [The FX Integrator Model](#the-fx-integrator-model)
23. [FX Acceleration](#fx-acceleration)
24. [Delay FB Discrete Stepping](#delay-fb-discrete-stepping)
25. [Momentary Effects — Snapshot/Restore](#momentary-effects--snapshotrestore)
26. [L1 Release Recovery](#l1-release-recovery)
27. [Filter Lock and Wet Lock](#filter-lock-and-wet-lock)
28. [Throttling and Epsilon Culling](#throttling-and-epsilon-culling)
29. [The Armed Band Visual State](#the-armed-band-visual-state)
30. [Right Stick Rotation Compensation](#right-stick-rotation-compensation)
31. [Tuning Guide — Making It Feel Right](#tuning-guide--making-it-feel-right)
32. [Failure Modes and Recovery](#failure-modes-and-recovery)
33. [Adding a New Gesture Type](#adding-a-new-gesture-type)
34. [TOML Parameter Reference](#toml-parameter-reference)

---

## The Problem This Solves

A USB gamepad has two analog sticks (each with X and Y axes giving
4 analog channels total), 12-16 digital buttons, and a D-pad. A
Pioneer DJM-900 NXS2 channel strip has a TRIM knob, three EQ knobs
(HIGH/MID/LOW), and 8 FX macro knobs — all continuous rotary encoders
with detents, plus momentary buttons for effects.

The gamepad and the mixer use fundamentally different physical
interaction models:

**Rotary encoder (mixer):**
- Turn clockwise → value increases
- Turn counterclockwise → value decreases
- Stop turning → value HOLDS at current position
- Physical detent at 12 o'clock → tactile "you're at neutral"

**Analog stick (gamepad):**
- Push right → position = +0.7 (or wherever you pushed)
- Release → position snaps back to 0.0 (spring return)
- No detent, no holding position

If you naively map stick position to parameter value, releasing the
stick snaps everything to zero. You can't "set and forget" an EQ
boost because the stick always returns to center.

The gesture engine solves this by implementing two interaction models
on the same stick:

1. **Velocity encoder** — stick position controls SPEED of change,
   not the value itself. Release = stop changing = hold position.
2. **Double-flick gestures** — rapid there-and-back stick movements
   trigger discrete actions (kill, normalize, boost, restore, band
   switch).

Both run simultaneously on the same physical stick. The mutual
exclusion system prevents them from interfering with each other.

---

## Physical Input Model

The right stick provides two analog axes:

```
                     Y = -1.0 (up)
                            │
                            │
X = -1.0 ──────────┼────────── X = +1.0
  
     (left)                 │              (right)
                            │
                     Y = +1.0 (down)
```

Each axis reports a float from -1.0 to +1.0. At rest (stick centered),
both axes should read 0.0 — but in practice there's always a small
offset due to manufacturing tolerance. The dead zone handles this.

### Physical rotation compensation

Some USB gamepads report the right stick axes rotated 90° from the
expected orientation. FX Machine handles this via the
`RIGHT_STICK_ROTATED_90` constant in `src/config.py`:

```python
RIGHT_STICK_ROTATED_90 = True
```

When True, the raw X and Y axes are swapped and inverted to produce
the expected mapping where:
- Physical push RIGHT → positive X input to the EQ encoder
- Physical push UP → positive Y input to the band navigator

This compensation happens in `src/controller/axes.py` before the
gesture engine sees the input:

```python
if RIGHT_STICK_ROTATED_90:
    eq_y_input = -rx_curved   # physical X becomes logical Y (inverted)
    eq_x_input =  ry_curved   # physical Y becomes logical X
else:
    eq_y_input = -ry_curved
    eq_x_input =  rx_curved
```

---

## Input Processing Pipeline

Every frame (~125 Hz), the controller thread processes each axis through
a pipeline of transformations:

```
Raw pygame axis value (-1.0 to +1.0)
    │
    ▼
smooth_axis(previous, current, factor)
    Exponential smoothing to remove jitter
    │
    ▼
hybrid_curve(smoothed_value)
    Sign-preserving x^1.8 power curve
    │
    ▼
Rotation compensation (if RIGHT_STICK_ROTATED_90)
    Swap and invert axes
    │
    ▼
Axis dominance check (|Y| > |X| × ratio?)
    Decides which axis "owns" the stick this frame
    │
    ▼
Gesture state machine update
    Checks for double-flick patterns
    │
    ▼
If no gesture active:
    Continuous encoder processing
    │
    ▼
Dead zone check → velocity calculation → detent slowdown
    → bass safety cap → throttle → epsilon → OSC write
```

Each stage is explained in detail below.

---

## The Continuous Encoder Model

The encoder is not "stick position = parameter value." That would feel
like a broken potentiometer because sticks have a return spring. Instead
the encoder is **velocity-based**: stick position determines how fast
the value changes per second.

```
Stick at rest (center):  value stays where it is
Stick pushed right:      value INCREASES over time
Stick pushed far right:  value increases FASTER
Stick released:          value HOLDS at current position
```

This is how Pioneer's rotary encoders work, and it's why an EQ knob
on a real mixer holds its position when you let go. The gamepad stick
simulates this behavior even though the physical stick springs back.

### The encoder loop

Each frame (every ~8ms):

```python
def eq_drive_continuous_encoder(stick_x, now):
    # 1. Get elapsed time since last tick
    dt = now - last_tick
    
    # 2. Compute velocity-based delta
    delta = eq_encoder_delta(stick_x, dt)
    
    # 3. Apply detent slowdown near 0 dB
    if near_neutral:
        delta *= detent_factor
    
    # 4. Apply bass safety cap
    if is_bass and new_value > cap:
        new_value = cap
    
    # 5. Throttle check (15ms minimum between writes)
    if too_soon:
        return
    
    # 6. Epsilon check (skip imperceptible changes)
    if change_too_small:
        return
    
    # 7. Write to state + send OSC
    state[eq_macro_values][band] = new_value
    osc_set_eq_macro(band, new_value)
```

The key insight: `delta` depends on BOTH stick position AND elapsed time.
A small stick push held for 1 second produces the same total change as a
large stick push held for a fraction of a second. This gives the user
two ways to control the same parameter — precision (small push, patient)
or speed (large push, fast).

---

## Encoder Math — Full Derivation

The core equation:

```python
delta = (macro_range / sweep_seconds) × (stick_deflection ^ curve_exp) × dt
```

Where:
- `macro_range = 127.0` (Ableton macro values run 0 to 127)
- `sweep_seconds = cfg.EQ_SWEEP_SECONDS` (default 0.30)
- `curve_exp = cfg.EQ_ENCODER_CURVE_EXP` (default 1.0)
- `dt` = frame time delta (typically ~8ms)

### Step-by-step computation

```python
def eq_encoder_delta(stick_value, dt, dead_zone=None, curve_exp=None, sweep_seconds=None):
    dz  = dead_zone     or cfg.EQ_AXIS_DEAD_ZONE      # 0.18
    exp = curve_exp     or cfg.EQ_ENCODER_CURVE_EXP    # 1.0
    sw  = sweep_seconds or cfg.EQ_SWEEP_SECONDS        # 0.30
    
    abs_v = abs(stick_value)
    
    # Step 1: Dead zone gate
    if abs_v < dz:
        return 0.0    # stick is in the dead zone, no movement
    
    # Step 2: Rescale remaining range to 0.0-1.0
    # This prevents a step discontinuity at the dead zone edge
    normalized = (abs_v - dz) / (1.0 - dz)
    normalized = clamp(normalized, 0.0, 1.0)
    
    # Step 3: Apply response curve
    shaped = normalized ** exp
    
    # Step 4: Compute velocity (macro units per second)
    velocity = (127.0 / sw) * shaped
    
    # Step 5: Apply direction and time delta
    sign = 1.0 if stick_value > 0 else -1.0
    return velocity * sign * dt
```

### Example calculations

With default settings (`sweep_seconds=0.30`, `curve_exp=1.0`, `dead_zone=0.18`):

**Stick at 50% deflection (0.50):**
```
normalized = (0.50 - 0.18) / (1.0 - 0.18) = 0.32 / 0.82 = 0.390
shaped = 0.390 ^ 1.0 = 0.390
velocity = (127.0 / 0.30) × 0.390 = 423.3 × 0.390 = 165.1 macro/sec
delta per frame = 165.1 × 0.008 = 1.32 macro units
```

**Stick at maximum deflection (1.0):**
```
normalized = (1.0 - 0.18) / (1.0 - 0.18) = 1.0
shaped = 1.0 ^ 1.0 = 1.0
velocity = 423.3 × 1.0 = 423.3 macro/sec
delta per frame = 423.3 × 0.008 = 3.39 macro units
At this rate, full range (127 units) is swept in 127/423.3 = 0.30 sec
```

**Stick barely outside dead zone (0.20):**
```
normalized = (0.20 - 0.18) / (1.0 - 0.18) = 0.02 / 0.82 = 0.024
shaped = 0.024 ^ 1.0 = 0.024
velocity = 423.3 × 0.024 = 10.3 macro/sec
delta per frame = 10.3 × 0.008 = 0.082 macro units
```

Very slow near the dead zone edge (10.3 units/sec = ~12 seconds to
cross the full range). This gives excellent fine control.

---

## The Sticky 0 dB Detent

Real EQ knobs have a physical notch at the center position (0 dB = unity).
When you turn the knob past it, you feel a "click" that helps you find
zero by feel. We simulate this digitally by slowing the encoder down
when the value is close to 0 dB.

### The detent math

```python
distance_from_neutral = abs(current_value - EQ_NEUTRAL_MACRO)  # 107.9

if distance_from_neutral < cfg.EQ_DETENT_RANGE:  # default 1.0
    detent_factor = distance_from_neutral / cfg.EQ_DETENT_RANGE
    detent_factor = max(cfg.EQ_DETENT_MIN_FACTOR, detent_factor)
    delta *= detent_factor
```

With defaults (`range=1.0`, `min_factor=0.30`):

| Distance from 0 dB | Speed multiplier | Effect |
|---|---|---|
| 1.0+ macro units | 100% (no slowdown) | Normal speed |
| 0.8 units | 80% | Slightly slower |
| 0.5 units | 50% | Half speed |
| 0.3 units | 30% (minimum) | Strong resistance |
| 0.0 units (exactly at 0 dB) | 30% (minimum) | Maximum resistance |

The detent creates a "valley" around 0 dB that's easy to enter and
hard to accidentally leave. You can push through it by holding the
stick firmly — the 30% minimum means it's a speed reduction, not a
wall.

### TRIM detent

TRIM has its own detent parameters and its own neutral point:

```python
# TRIM uses TRIM_NEUTRAL_MACRO (64.0), not EQ_NEUTRAL_MACRO (107.9)
distance = abs(current_value - TRIM_NEUTRAL_MACRO)

if distance < cfg.TRIM_DETENT_RANGE:
    detent_factor = max(cfg.TRIM_DETENT_MIN_FACTOR, distance / cfg.TRIM_DETENT_RANGE)
    delta *= detent_factor
```

The two detents are independent — different neutral points, different
configurable ranges and minimum factors.

---

## Response Curves Explained

The `curve_exp` parameter shapes how stick deflection maps to encoder
speed. This is a power curve applied after dead-zone normalization.

### curve_exp = 1.0 (linear, the default)

```
stick:  0%  20%  40%  60%  80% 100%
speed:  0%  20%  40%  60%  80% 100%

Perception: Consistent proportional response. Push twice as far,
get twice the speed. Simple and predictable.
```

### curve_exp = 1.5 (slight ease)

```
stick:  0%  20%  40%  60%  80% 100%
speed:  0%   9%  25%  46%  72% 100%

Perception: Very fine control near rest (small pushes barely move).
Big movements needed for fast sweeps. Good for studio precision work.
```

### curve_exp = 2.0 (quadratic)

```
stick:  0%  20%  40%  60%  80% 100%
speed:  0%   4%  16%  36%  64% 100%

Perception: Almost nothing happens until 40-50% deflection, then
rapid acceleration. Feels like a physical knob with resistance.
Not recommended for live performance (too slow for emergency kills).
```

### curve_exp = 0.7 (inverse ease)

```
stick:  0%  20%  40%  60%  80% 100%
speed:  0%  28%  49%  65%  82% 100%

Perception: Very responsive. Small pushes have large effects.
Good for edgy, aggressive DJing. Bad for precision.
```

The default of 1.0 is a deliberate choice for general-purpose
performance. Tuning `curve_exp` is the single most effective way to
change how the controller "feels." Start at 1.0, try 1.2 if you
want more precision, try 0.8 if you want more aggression.

---

## Axis Smoothing

Raw gamepad axes are noisy — cheap potentiometers and ADCs produce
jitter of ±0.01 to ±0.05 at rest. Smoothing reduces this to near zero.

### Exponential smoothing formula

```python
def smooth_axis(previous, current, factor):
    return previous * (1.0 - factor) + current * factor
```

- `factor = 0.0`: output never changes (completely smoothed = frozen)
- `factor = 0.55` (default): balanced — ~3 frames to converge to a
  step change, jitter nearly eliminated
- `factor = 1.0`: no smoothing (raw input, all jitter passes through)

### Convergence speed

After a sudden stick change from 0.0 to 1.0 with `factor=0.55`:

| Frame | Output | % of target |
|---|---|---|
| 0 | 0.000 | 0% |
| 1 | 0.550 | 55% |
| 2 | 0.798 | 80% |
| 3 | 0.909 | 91% |
| 4 | 0.959 | 96% |
| 5 | 0.982 | 98% |

Three frames (24ms at 125 Hz) to reach 91% of the target. Fast enough
that stick movement feels instant, slow enough that jitter is invisible.

### Per-mode smoothing

Different modes can use different smoothing factors:

- **Navigation axes:** `cfg.SMOOTHING_FACTOR` (default 0.20) — heavier
  smoothing for navigation because you want stable track/scene positions
- **EQ encoder:** `cfg.EQ_SMOOTHING_FACTOR` (default 0.55) — lighter
  smoothing for responsive encoder feel
- **TRIM encoder:** `cfg.TRIM_SMOOTHING_FACTOR` (default 0.55) — same
  as EQ
- **FX sticks:** uses the default `cfg.SMOOTHING_FACTOR`

### Stale values on mode switch

When you switch from navigation to EQ mode, the `_smoothed_eq_rx` value
might be stale from the last EQ session. `action_toggle_eq_mode()` resets
it to 0.0 on mode entry to prevent the first encoder frame from
processing old data.

---

## Dead Zone Processing

The dead zone is the region around stick center where input is ignored.
Without it, tiny stick offsets from manufacturing tolerance would cause
slow, continuous parameter drift.

### Standard dead zone

```python
if abs(stick_value) < cfg.EQ_AXIS_DEAD_ZONE:  # default 0.18
    return 0.0  # no movement
```

### Rescaled dead zone (no step discontinuity)

After the dead zone gate, the remaining range is rescaled so 0%
starts at the dead zone edge, not at center:

```python
normalized = (abs_v - dead_zone) / (1.0 - dead_zone)
```

Without rescaling: the output jumps from 0 to 0.18 the instant you
cross the dead zone threshold. With rescaling: the output starts at
0.0 at the threshold and rises smoothly to 1.0 at full deflection.

```
Without rescaling:
  stick 0.00-0.18: output 0.00 (dead zone)
  stick 0.19:      output 0.19 ← JUMP from 0 to 0.19
  stick 1.00:      output 1.00

With rescaling:
  stick 0.00-0.18: output 0.00 (dead zone)
  stick 0.19:      output 0.012 ← smooth transition
  stick 0.50:      output 0.390
  stick 1.00:      output 1.000
```

The rescaling is mathematically equivalent to stretching the remaining
range (0.18 to 1.0) across the full output range (0.0 to 1.0). This
makes the dead zone truly transparent to the response curve.

### Per-mode dead zones

| Mode | Dead zone | Why |
|---|---|---|
| EQ encoder | 0.18 | Large — prevents drift when you think the stick is centered |
| TRIM encoder | 0.18 | Same — TRIM is sensitive to unintentional movement |
| FX sticks | 0.08 | Smaller — FX sweeps need more range |
| Volume control | 0.12 | Medium — volume changes should be deliberate |
| Navigation | 0.55 | Very large — navigation is threshold-based, not continuous |

---

## The Double-Flick State Machine

The double-flick is a gesture pattern: push the stick to an extreme
position, return to center, push to the same extreme again, all within
a short time window. It's designed to be impossible to trigger
accidentally during normal encoder use.

### State machine diagram

```
                        ┌────────────────────────────────────────────────────┐
                        │                                                    │
                        │   timeout (380ms elapsed since first flick)        │
                        ▼                                                    │
                   ┌─────────┐                                               │
            ┌──────│  IDLE   │◀──────────── timeout ────────────────────┐   │
            │      └─────────┘                                          │   │
            │           │                                               │   │
            │           │ abs(stick) ≥ 0.90                             │   │
            │           │ (extreme position detected)                   │   │
            │           ▼                                               │   │
            │      ┌─────────┐                                          │   │
            │      │ FLICKED │ ← direction and timestamp recorded       │   │
            │      └─────────┘                                          │   │
            │           │                                               │   │
            │           │ abs(stick) < 0.22                             │   │
            │           │ (stick returned to center)                    │   │
            │           ▼                                               │   │
            │      ┌──────────┐                                         │   │
            │      │ RETURNED │ ← waiting for second flick              │   │
            │      └──────────┘                                         │   │
            │           │                                               │   │
            │           │ abs(stick) ≥ 0.90                             │   │
            │           │ AND same direction as first flick             │   │
            │           ▼                                               │   │
            │      ┌───────────┐                                        │   │
            └──────│ CONFIRMED │ ── FIRE ACTION ── reset to IDLE ──────┘    │
                   └───────────┘                                            │
                                                                            │
    (if second flick is in OPPOSITE direction → reset to IDLE) ─────────────┘
```

### Tunable thresholds

```toml
[eq.flick]
extreme = 0.90          # stick must reach 90% deflection
return_threshold = 0.22  # stick must drop below 22% before second flick
timeout_ms = 380         # second flick must arrive within 380ms
```

### Why these specific values?

**extreme = 0.90:** Forces deliberate, committed stick movement. At 0.75,
accidental flicks happen during normal encoder use (the stick sometimes
overshoots on fast sweeps). At 0.95, the gesture is too hard to trigger
(you have to hit the mechanical stop).

**return_threshold = 0.22:** The stick must come back near center between
flicks. At 0.10, the gesture is too strict (stick has to hit exact center,
which is hard with a spring). At 0.40, partial returns are enough and
false triggers increase.

**timeout_ms = 380:** The time window for both flicks. At 300, fast but
achievable with practice. At 500, too relaxed — slow stick movements
during encoder use can accidentally chain into a gesture. 380ms was found
empirically as the sweet spot where deliberate flicks always succeed and
accidental ones almost never do.

---

## X-Axis Gestures — Value Actions

X-axis double-flicks on EQ bands (Low/Mid/High) trigger context-aware
actions that depend on the current value:

### Double-flick LEFT

```
if current_value > 0 dB:
    → NORMALIZE to 0 dB (pull it back to neutral)

else (current_value ≤ 0 dB):
    if BASS:    → KILL to -∞ dB (full kill)
    if MID:     → cut to -19 dB
    if HIGH:    → cut to -19 dB
```

### Double-flick RIGHT

```
if current_value < 0 dB:
    → RESTORE to 0 dB

else (current_value ≥ 0 dB):
    if MID or HIGH:  → BOOST by 15% of remaining headroom (asymptotic)
    if BASS:         → 🚫 BLOCKED (sub safety)
```

### Why context-aware?

A real DJ doesn't think "kill" and "normalize" as separate gestures.
They think "pull this back." The same physical movement does the
musically appropriate thing depending on where you are:

- Boost above neutral? Pull back to neutral.
- At or below neutral? Kill it.
- Cut below neutral? Push back to neutral.
- At or above neutral? Boost it (or block if bass).

This reduces the mental model from "6 different actions" to "2 physical
movements, each context-aware."

---

## Y-Axis Gestures — Band Navigation

Y-axis double-flicks switch the active EQ band. The rotation includes
TRIM as a fourth position:

```
Y double-flick UP:    MID → HIGH → TRIM → LOW → MID → ...   (wraps)
Y double-flick DOWN:  MID → LOW → TRIM → HIGH → MID → ...   (wraps)
```

The wrap is intentional. There's no "you've hit the end" — you just
keep cycling. Performance-friendly: you can reach any band in at most
two double-flicks from any starting position.

### The rotation modulus

```python
def eq_switch_band(direction):
    new = (current + direction) % EQ_MACRO_COUNT  # EQ_MACRO_COUNT = 4
```

`EQ_MACRO_COUNT` was 3 in the original build (Low/Mid/High). Build B
added TRIM as slot 3, making it 4. The modulus wraps seamlessly
regardless of how many bands there are.

---

## Cross-Axis Mutual Exclusion

The right stick is one physical input doing two logical things:
- X axis = value control (encoder + kill/restore gestures)
- Y axis = band navigation (band switch gestures)

When you push the stick diagonally, both axes see movement. Without
protection, this could trigger a band switch AND a value change
simultaneously — which would change the value on the WRONG band
(you'd switch bands first, then the value change applies to the new
band instead of the one you intended).

### The exclusion algorithm

```python
def handle_axes_eq(controller, dt):
    # Step 1: Process Y gesture first (band switch)
    y_in_gesture = update_eq_y_gesture(stick_y, now)

    # Step 2: Y-dominance suppression
    y_dominates = (abs(stick_y) > abs(stick_x) * DOMINANCE_RATIO)

    if y_in_gesture or y_dominates:
        # Y owns the stick → freeze X completely
        reset_x_gesture()
        return  # no encoder, no X gesture

    # Step 3: Process X gesture (kill/restore)
    x_in_gesture = update_eq_x_gesture(stick_x, now)

    if x_in_gesture:
        # X gesture in progress → freeze Y
        reset_y_gesture()
        return  # no encoder

    # Step 4: Only if neither gesture owns the stick → run encoder
    eq_drive_continuous_encoder(stick_x, now)
```

### Priority order

1. **Y gesture detection runs first** — because band switches must
   complete before value changes apply
2. **Y dominance check** — even if Y isn't in a gesture state, if the
   Y axis is much larger than X, we suppress X to prevent accidental
   value changes during vertical stick movement
3. **X gesture detection** — if Y isn't active and not dominating,
   check for X gestures (kill/restore)
4. **Encoder** — only runs when NO gesture owns the stick

### What "freeze" means

When one axis freezes the other, it:
- Resets the frozen axis's gesture state machine to "idle"
- Clears the frozen axis's direction and timestamp
- Prevents the encoder from running (for X freezing)
- Ensures no partial gesture carries over from the frozen axis

---

## The Dominance Ratio

```python
y_dominates = abs(stick_y) > abs(stick_x) * cfg.EQ_DOMINANCE_RATIO
```

Default ratio: 3.0. This means Y must be **3× larger than X** to claim
dominance. At the default:

| stick_x | stick_y | Y dominates? | Why |
|---|---|---|---|
| 0.2 | 0.7 | Yes | 0.7 > 0.2 × 3.0 = 0.6 |
| 0.3 | 0.7 | No | 0.7 < 0.3 × 3.0 = 0.9 |
| 0.1 | 0.4 | Yes | 0.4 > 0.1 × 3.0 = 0.3 |
| 0.5 | 0.5 | No | 0.5 < 0.5 × 3.0 = 1.5 |

**Tuning the ratio:**

- `1.0` = very loose. ANY vertical component suppresses horizontal.
  Band switches trigger too easily during diagonal stick movement.
- `2.0` = balanced. Moderate vertical emphasis needed.
- `3.0` (default) = strict. Only clearly vertical movements suppress
  horizontal. Good for performers who use sweeping stick movements
  that often have a diagonal component.
- `5.0` = very strict. Only nearly-vertical pushes count. Band switches
  become harder to trigger from rest.

---

## Smart Kill and Normalize

The "smart" part of the X-axis double-flick LEFT is the context
awareness. The same physical gesture does different things depending
on the current value:

### On EQ bands (Low/Mid/High):

```python
def eq_action_kill(band, flick_duration_s):
    current = state["eq_macro_values"][band]
    
    if current > EQ_NEUTRAL_MACRO + 0.5:
        # Above 0 dB → pull back to neutral
        start_eq_ramp(band, EQ_NEUTRAL_MACRO, flick_duration_s)
    
    elif band == EQ_SLOT_LOW:
        # Bass at or below neutral → FULL KILL to -∞
        start_eq_ramp(band, EQ_MACRO_MIN, flick_duration_s)
    
    else:
        # Mid or High at or below neutral → cut to -19 dB
        start_eq_ramp(band, EQ_CUT_HALF_MACRO, flick_duration_s)
```

### Why -19 dB for Mid/High instead of -∞?

On a real DJM-900, turning the MID or HIGH EQ knob fully left cuts to
about -26 dB — a deep cut but not silence. Full silence on mid or high
frequencies sounds unnatural and draws attention to the cut. -19 dB is
deep enough to "kill" the energy in that frequency band while maintaining
the perception that audio is still flowing.

Bass gets full -∞ kill because bass cuts are a fundamental DJ technique
— dropping the bass for 4-8 bars then bringing it back on the downbeat.
The audience expects the bass to VANISH. A partial bass cut sounds weak.

### The 0.5 tolerance

```python
if current > EQ_NEUTRAL_MACRO + 0.5:
```

The `0.5` prevents the normalize action from firing when the encoder
has drifted to neutral ± 0.5 due to floating point accumulation.
Without it, being at exactly 107.9 (neutral) and double-flicking left
would trigger a "normalize to 107.9" ramp that does nothing visible but
wastes an OSC write.

This tolerance is defined as `EQ_NEUTRAL_TOLERANCE = 0.5` in `eq.py`.

---

## Smart Restore and Boost

X-axis double-flick RIGHT:

```python
def eq_action_boost_or_restore(band, flick_duration_s):
    current = state["eq_macro_values"][band]
    
    if current < EQ_NEUTRAL_MACRO - 0.5:
        # Below 0 dB → restore to neutral
        start_eq_ramp(band, EQ_NEUTRAL_MACRO, flick_duration_s)
    
    elif band == EQ_SLOT_LOW:
        # Bass at or above neutral → BLOCKED
        state["last_action"] = "🚫 Bass boost blocked"
    
    else:
        # Mid/High at or above neutral → asymptotic boost
        remaining = EQ_MACRO_MAX - current
        boost = remaining * cfg.EQ_BOOST_PCT  # default 0.15
        target = clamp(current + boost, EQ_NEUTRAL_MACRO, EQ_MACRO_MAX)
        start_eq_ramp(band, target, flick_duration_s)
```

---

## The Asymptotic Boost

The boost action doesn't add a fixed amount — it adds a percentage of
the remaining headroom. This creates an asymptotic approach toward the
maximum:

```
Headroom remaining = EQ_MACRO_MAX (127) - current
Boost = headroom × 15%
```

**Example sequence starting from 0 dB (macro 107.9):**

| Flick # | Current | Headroom | Boost | New value | Approx dB |
|---|---|---|---|---|---|
| 1 | 107.9 | 19.1 | 2.87 | 110.77 | +0.9 dB |
| 2 | 110.77 | 16.23 | 2.43 | 113.20 | +1.7 dB |
| 3 | 113.20 | 13.80 | 2.07 | 115.27 | +2.4 dB |
| 4 | 115.27 | 11.73 | 1.76 | 117.03 | +3.0 dB |
| 5 | 117.03 | 9.97 | 1.50 | 118.53 | +3.5 dB |
| ... | ... | ... | ... | ... | ... |
| 20 | 125.9 | 1.1 | 0.17 | 126.07 | +5.9 dB |

You approach +6 dB but never quite reach it through gestures alone.
Each successive flick adds less boost. This forces deliberate, graduated
boosting rather than blindly stacking +3 dB per flick.

---

## Bass Safety System

Low frequencies carry enormous energy. A small boost in the sub-bass
can damage subwoofers, hurt listeners, or cause feedback in certain
room configurations. FX Machine has three layers of bass protection:

### Layer 1: Encoder cap

```python
if band == EQ_SLOT_LOW:
    upper_cap = cfg.EQ_BASS_BOOST_CAP  # default 114.0 ≈ +2 dB
else:
    upper_cap = EQ_MACRO_MAX  # 127.0 = +6 dB
new_val = clamp(new_val, EQ_MACRO_MIN, upper_cap)
```

The encoder physically cannot push bass above +2 dB. Mid and High
can reach +6 dB.

### Layer 2: Double-flick boost blocked

When the bass band is at or above 0 dB and you double-flick right,
nothing happens. The status line shows "🚫 Bass boost blocked."

### Layer 3: Double-flick kill is full -∞

Bass kills go to full silence (macro 0.0 = -∞ dB), not to -19 dB
like mid/high. This matches the real DJM behavior where the bass
kill is absolute.

---

## TRIM-Specific Gesture Behavior

TRIM controls input gain and has different gesture rules:

### Double-flick behavior

TRIM gestures only normalize toward 0 dB. They never kill or boost:

```python
# TRIM double-flick LEFT:
if current > TRIM_NEUTRAL + 0.5:
    # Above 0 dB → normalize down to 0
    ramp to TRIM_NEUTRAL
else:
    # At or below 0 dB → LEFT does nothing
    "already at/below 0 dB"

# TRIM double-flick RIGHT:
if current < TRIM_NEUTRAL - 0.5:
    # Below 0 dB → normalize up to 0
    ramp to TRIM_NEUTRAL
else:
    # At or above 0 dB → RIGHT does nothing
    "already at/above 0 dB"
```

This means the direction toward center always works, and the direction
away from center never does. TRIM's purpose is gain matching — you
set it once per track and leave it. It shouldn't be killable or
boostable via quick gestures.

### TRIM encoder

TRIM uses its own encoder parameters (`cfg.TRIM_*`) with its own
sweep speed, dead zone, and detent. The encoder function is shared
with EQ bands (via parameter overrides to `eq_encoder_delta()`) to
avoid code duplication:

```python
delta = eq_encoder_delta(
    stick_x, dt,
    dead_zone=cfg.TRIM_DEAD_ZONE,
    curve_exp=cfg.TRIM_CURVE_EXP,
    sweep_seconds=cfg.TRIM_SWEEP_SECONDS,
)
```

### TRIM visual mapping

TRIM's visual knob position maps the configurable cap (+9 dB) to the
full-right (5 o'clock) position:

```
Macro 0     → visual 0.0 (7 o'clock, -∞ dB)
Macro 64    → visual 0.5 (12 o'clock, 0 dB)
Macro 80.2  → visual 1.0 (5 o'clock, +9 dB cap)
```

The underlying Utility device goes up to +35 dB (macro 127), but
the visual range ends at the configured cap. This matches the DJM-900
NXS2 where the TRIM knob's physical range is -∞ to +9 dB.

---

## Animated Transitions — Cubic Ease-Out Ramps

When a double-flick gesture fires, the value doesn't snap — it animates
smoothly over 30-100ms using a cubic ease-out curve.

### Why cubic ease-out?

```python
eased = 1.0 - (1.0 - progress) ** 3
```

Three common easing options:

**Linear:** Constant speed. Sounds abrupt at the end (sudden stop).
```
progress:  0.0  0.2  0.4  0.6  0.8  1.0
eased:     0.0  0.2  0.4  0.6  0.8  1.0
```

**Exponential:** Slow start, fast end. Drags at the beginning.
```
progress:  0.0  0.2  0.4  0.6  0.8  1.0
eased:     0.0  0.05 0.15 0.33 0.55 1.0
```

**Cubic ease-out (what we use):** Fast start, gradual deceleration.
```
progress:  0.0  0.2  0.4  0.6  0.8  1.0
eased:     0.0  0.49 0.78 0.94 0.99 1.0
```

Cubic ease-out sounds natural because the biggest change happens
immediately (the "attack") and the remainder gently settles into the
target value. When killing the bass, you hear the low end disappear
quickly but the final -∞ silence arrives smoothly without a click.

### Ramp execution

The ramp runs in the EQ Ramp Thread at 60 Hz (16ms tick):

```python
while True:
    for slot in range(4):  # Low, Mid, High, Trim
        if not ramp_active[slot]:
            continue
        
        elapsed = now - ramp_start_time[slot]
        progress = clamp(elapsed / ramp_duration[slot], 0.0, 1.0)
        
        if progress >= 1.0:
            # Ramp complete — write final target exactly once
            state[eq_macro_values][slot] = target
            osc_set_eq_macro(slot, target)
            ramp_active[slot] = False
        else:
            # Interpolate
            eased = 1.0 - (1.0 - progress) ** 3
            value = start + (target - start) * eased
            state[eq_macro_values][slot] = value
            osc_set_eq_macro(slot, value)
```

---

## Ramp Duration Scaling

Ramp duration adapts to how fast you flicked:

```python
flick_duration = time_of_second_flick - time_of_first_flick

# Map flick speed to ramp duration
if flick_duration < 30ms:
    ramp = cfg.EQ_RAMP_MIN_MS   # 30ms — very snappy
elif flick_duration > 200ms:
    ramp = cfg.EQ_RAMP_MAX_MS   # 100ms — smooth
else:
    # Linear interpolation between min and max
    fraction = (flick_ms - 30) / (200 - 30)
    ramp = MIN + fraction * (MAX - MIN)
```

Fast flick = fast ramp. Slow, deliberate flick = smooth ramp. The
ramp adapts to your intention.

---

## The FX Integrator Model

FX macros use a different control model than the EQ encoder. Instead
of velocity-based encoding, they use a **direct integrator** with
acceleration:

```python
delta = stick_value × (macro_range / sweep_seconds) × dt × accel_mult
target = clamp(current + delta, min, max)
```

The difference from the EQ encoder:
- EQ encoder has dead-zone rescaling, response curves, and detent
- FX integrator is simpler: linear stick → delta mapping with acceleration
- FX uses stick value directly (after hybrid_curve), not through the
  eq_encoder_delta pipeline

---

## FX Acceleration

Holding the stick in one direction ramps up the speed:

```python
elapsed = now - direction_change_time
accel_mult = 1.0 + (elapsed / cfg.FX_ACCEL_RAMP_S)  # default 1.0s
accel_mult = min(accel_mult, cfg.FX_ACCEL_MAX_MULT)  # default 4.0
```

| Hold time | Multiplier | Speed |
|---|---|---|
| 0.0 s | 1.0× | Normal |
| 0.5 s | 1.5× | 50% faster |
| 1.0 s | 2.0× | Double speed |
| 2.0 s | 3.0× | Triple speed |
| 3.0+ s | 4.0× (cap) | Maximum |

**Change direction → multiplier resets to 1.0.** This gives precise
control for small adjustments (quick taps) AND fast sweeps for
build-ups (sustained holds).

---

## Delay FB Discrete Stepping

Delay feedback is controlled differently from other FX macros —
via D-pad steps instead of continuous stick:

```python
step_size = macro_range / cfg.FX_DELAY_FB_STEPS  # default 20 steps

D-pad right: new_step = current_step + 1
D-pad left:  new_step = current_step - 1

target = min_val + new_step × step_size
cap = min_val + macro_range × cfg.FX_DELAY_FB_CLAMP_FRAC  # 92%
target = min(target, cap)
```

### Why discrete instead of continuous?

Feedback is the parameter that goes runaway easiest. With continuous
stick control, an accidental 2-second hold could push feedback from
50% to 100% and create infinite delay. Discrete steps require
deliberate repeated button presses, and the 92% cap prevents infinite
feedback regardless.

### Debouncing

```python
if now - last_dpad_press < cfg.FX_DELAY_FB_DEBOUNCE:  # 180ms
    return  # too fast, ignore
```

Prevents double-steps from a single physical press (D-pad contacts
sometimes bounce and register twice).

---

## Momentary Effects — Snapshot/Restore

Three momentary effects follow the snapshot/restore pattern:

```
PRESS:
  1. Save snapshot of current parameter(s)
  2. Jam parameter(s) to target value
  3. Set "_momentary_X_active" = True

RELEASE:
  1. Check "_momentary_X_active" — skip if not active
  2. Restore parameter(s) from snapshot
  3. Set "_momentary_X_active" = False
```

### L1 + X — STUTTER

```
Press:    Stutter macro = max_val  (Beat Repeat activates)
Release:  Stutter macro = 0        (Beat Repeat deactivates)
```

No snapshot needed — Stutter is always 0 outside momentary use.

### L1 + O — BASS CUT

```
Press:    snapshot = {freq: current_filter_freq, mode: current_filter_mode}
          filter_freq = 42.3 (≈200 Hz on the macro scale)
          filter_mode = 0.0  (HP — high-pass mode)

Release:  filter_freq = snapshot.freq
          filter_mode = snapshot.mode
```

The snapshot captures BOTH frequency and mode so a release restores you
to exactly where you were — whether you had LP at 5 kHz or HP at 100 Hz.

### L1 + □ — FX SEND THROW

```
Press:    snapshot = {fx_send: current_fx_send}
          fx_send = max_val  (full feed to wet chain)

Release:  fx_send = snapshot.fx_send
```

Combined with the wet/dry routing, this creates the "throw and tail"
technique. Snapshot ensures you go back to your previous level, not
necessarily zero.

### Guard against stick fighting

When a momentary is active, the FX stick driver is blocked from
modifying the controlled parameter:

```python
def is_macro_under_momentary_control(slot):
    if slot == STUTTER and momentary_stutter_active:
        return True
    if slot in (FILTER_FREQ, FILTER_MODE) and momentary_bass_cut_active:
        return True
    if slot == FX_SEND and momentary_fx_throw_active:
        return True
    return False

def fx_drive_macro(slot, stick_value, dt, accel):
    if is_macro_under_momentary_control(slot):
        return  # momentary owns this slot, stick is blocked
```

---

## L1 Release Recovery

When L1 is released (exiting FX mode), recovery logic runs across
all 8 FX macros:

```python
FX_RECOVERY_BEHAVIOUR = {
    FX_SLOT_FILTER_FREQ: "filter",     # restore to baseline (unless locked)
    FX_SLOT_FILTER_MODE: "skip",       # leave as is
    FX_SLOT_FILTER_RES:  "skip",
    FX_SLOT_STUTTER:     "fixed:0.0",  # always snap to 0
    FX_SLOT_REVERB_SIZE: "skip",
    FX_SLOT_FX_SEND:     "wet",        # snap to 0 (unless locked)
    FX_SLOT_DELAY_FB:    "skip",
    FX_SLOT_WIDTH:       "skip",
}
```

| Behavior | What it does |
|---|---|
| `skip` | Leave this macro where the user set it |
| `fixed:N` | Always snap to value N |
| `filter` | Restore to baseline, unless filter-locked |
| `wet` | Snap to 0 (cut wet send), unless wet-locked |

This means a typical L1 release: filter goes back to baseline, FX send
drops to 0 (tails ring out), stutter turns off, everything else stays
where you put it. The tails keep their character (reverb size stays,
delay FB stays) but new wet signal stops.

---

## Filter Lock and Wet Lock

Two toggle buttons modify the recovery behavior:

**L1 + L3 → Toggle filter lock:**
When locked, Filter Freq is NOT restored to baseline on L1 release.
Useful for "I want to keep this filter sweep as the new baseline."

**L1 + R3 → Toggle wet lock:**
When locked, FX Send is NOT snapped to 0 on L1 release.
Useful for "I want a constant wet bath for this entire breakdown."

Both show 🔒 icons in the FX panel when active. Tap the same button
again to unlock.

---

## Throttling and Epsilon Culling

Two filters prevent flooding Ableton with OSC messages:

### Throttle

```python
if (now - last_write_at) < cfg.EQ_WRITE_THROTTLE:  # 15ms
    return  # too soon, skip this write
```

15ms = max ~66 writes/second per band. Higher rates don't improve
perceived smoothness but do increase Ableton's CPU load.

### Epsilon

```python
if abs(new_value - last_value) < cfg.EQ_WRITE_EPSILON:  # 0.15
    return  # change too small to perceive
```

0.15 macro units ≈ 0.07 dB (imperceptible). Skipping these saves
~80% of writes during small stick movements near the dead zone edge.

### Combined effect

Without throttle + epsilon: ~125 writes/sec per active band during
stick movement (one per controller frame).

With throttle + epsilon: ~15-30 writes/sec per active band. Still
perceptually smooth. ~80% reduction in OSC traffic.

---

## The Armed Band Visual State

When the first flick of a double-flick is detected, the target band
or action is shown as "armed" in the UI. This gives visual feedback
that the gesture has started before it completes.

```
state["eq_armed_band"]  = target_band   # which band will switch to
state["eq_armed_until"] = now + timeout  # auto-clears after timeout

# In the UI:
if is_armed:
    cell_bg = EQ_GLOW_ARMED        # yellow tint
    label_color = EQ_LABEL_ARMED    # yellow text
```

If the second flick doesn't arrive within the timeout (380ms), the
armed state auto-clears and the UI returns to normal. This prevents
stale "armed" highlights from lingering when a gesture is abandoned.

---

## Right Stick Rotation Compensation

```python
RIGHT_STICK_ROTATED_90 = True

if RIGHT_STICK_ROTATED_90:
    eq_y_input = -rx_curved   # physical X → logical Y (inverted)
    eq_x_input =  ry_curved   # physical Y → logical X
```

This exists because the specific USB gamepad used during development
reports its right stick axes in a non-standard orientation. Without
compensation, pushing the stick "right" would navigate bands instead
of adjusting values.

If your gamepad has standard axis orientation, set
`RIGHT_STICK_ROTATED_90 = False` in `src/config.py`.

### How to determine your gamepad's orientation

1. Run `python run.py`
2. Enter EQ mode (tap R3)
3. Push the right stick physically to the RIGHT
4. If the EQ value changes → axes are correct (`False`)
5. If the band switches → axes are swapped (`True`)

---

## Tuning Guide — Making It Feel Right

### "The encoder is too slow"
Decrease `sweep_seconds`. Default 0.30 = full range in 0.3 seconds.
Try 0.20 for faster sweeps. Going below 0.15 makes small movements
jump too much.

### "The encoder is too sensitive near center"
Increase `curve_exp`. Default 1.0 (linear). Try 1.3 for a gentle
ease near center. Going above 2.0 makes center movements nearly
imperceptible.

### "I keep accidentally switching bands while adjusting values"
Increase `dominance_ratio`. Default 3.0. Try 4.0 or 5.0. This
requires more vertical movement to trigger a band switch.

### "My double-flicks don't register"
- Increase `timeout_ms` (more time allowed between flicks). Try 500.
- Decrease `extreme` (less deflection needed). Try 0.85.
- Increase `return_threshold` (don't have to return as far). Try 0.30.

### "I get false double-flicks during normal encoder use"
- Decrease `timeout_ms`. Try 300.
- Increase `extreme`. Try 0.95.
- Decrease `return_threshold`. Try 0.15.

### "The bass cut doesn't feel deep enough"
The bass kill goes to -∞ (full silence). If you're hearing residual
low end, check that your EQ Three's GainLow macro is mapped correctly
to the "EQ Low" macro in the rack.

### "The TRIM encoder feels different from the EQ encoder"
It IS different — on purpose. TRIM has its own `sweep_seconds`,
`curve_exp`, `dead_zone`, and `detent_range` parameters in the
`[trim]` TOML section. Adjust those independently of the `[eq.encoder]`
section.

### "My controller's stick has drift at rest"
Increase `dead_zone`. Default 0.18. Try 0.25 or 0.30 for worn
controllers. At 0.30 you lose 30% of the stick's range but gain
rock-solid stability.

---

## Failure Modes and Recovery

| Failure | Behavior | Recovery |
|---|---|---|
| Controller unplugged mid-flick | Gesture state held in memory | On replug, gesture resets to "idle" (partial gesture lost) |
| Two gestures fired same frame | Mutual exclusion freezes the loser | Only one fires |
| Ramp in progress + new gesture | New gesture interrupts ramp | Ramp target changes mid-animation |
| TOML edited with bad value | cfg keeps previous working value | Fix typo, reload again |
| Bass cap reached via encoder | Value clamped at cap | Push harder → no effect (cap is hard) |
| Delay FB at 92% cap | Step refused, status shows "MAX" | Must reduce before adding more |
| Filter lock ON + L1 release | Filter stays at current position | Unlock to re-enable recovery |
| Wet lock ON + L1 release | FX Send stays at current level | Unlock to re-enable recovery |

---

## Adding a New Gesture Type

If you want to add a new gesture (e.g., triple-flick, long-press,
chord gesture):

### Step 1: Define the state machine

Model your gesture as states and transitions. Draw the state diagram.
Define what input transitions each state.

### Step 2: Add state keys to `src/state.py`

```python
"_my_gesture_state": "idle",
"_my_gesture_dir": 0,
"_my_gesture_time": 0.0,
```

### Step 3: Implement the state machine in `src/engine/eq.py`

Follow the pattern of `update_eq_x_gesture()`. Return True if the
gesture is in progress (to freeze other axes), False if idle.

### Step 4: Wire it into `src/controller/axes.py`

Add your gesture check in `handle_axes_eq()` at the appropriate
priority level. Remember: the first gesture to return True freezes
everything else.

### Step 5: Add the action function

What happens when the gesture completes? Write the action function
in `src/engine/eq.py` (e.g., `eq_action_triple_kill()`).

### Step 6: Add tunable parameters

Add threshold values to `config/default.toml` and wire them through
`config_loader.py` into the `cfg` singleton.

---

## TOML Parameter Reference

### `[eq.encoder]` — How the stick feels as a value encoder

| Key | Default | Description |
|---|---|---|
| `sweep_seconds` | 0.30 | Time for full range at max deflection |
| `curve_exp` | 1.0 | Response curve (1.0=linear, 1.5=ease, 2.0=quadratic) |
| `smoothing_factor` | 0.55 | Exponential smoothing (0.3=smooth, 0.8=snappy) |
| `dead_zone` | 0.18 | Stick rest area (0.05=sensitive, 0.30=stable) |

### `[eq.dominance]` — Cross-axis priority

| Key | Default | Description |
|---|---|---|
| `ratio` | 3.0 | Y must be Nx larger than X to win (1.0=loose, 5.0=strict) |

### `[eq.flick]` — Double-flick gesture detection

| Key | Default | Description |
|---|---|---|
| `extreme` | 0.90 | Deflection threshold for flick detection |
| `return_threshold` | 0.22 | Return-to-center threshold between flicks |
| `timeout_ms` | 380 | Maximum time between first and second flick |

### `[eq.detent]` — Sticky 0 dB feel

| Key | Default | Description |
|---|---|---|
| `range` | 1.0 | Width of the sticky zone (macro units) |
| `min_factor` | 0.30 | Minimum speed multiplier inside the zone |

### `[eq.osc]` — Write rate control

| Key | Default | Description |
|---|---|---|
| `write_throttle` | 0.015 | Minimum seconds between writes (15ms) |
| `write_epsilon` | 0.15 | Minimum value change worth sending |

### `[eq.ramp]` — Animation timing

| Key | Default | Description |
|---|---|---|
| `min_ms` | 30 | Fastest ramp (for fastest flicks) |
| `max_ms` | 100 | Slowest ramp (for slowest flicks) |

### `[eq.safety]` — Bass protection

| Key | Default | Description |
|---|---|---|
| `bass_boost_cap` | 114.0 | Maximum bass macro value (~+2 dB) |
| `mid_high_boost_pct` | 0.15 | Asymptotic boost percentage (15% of headroom) |

### `[trim]` — TRIM-specific encoder parameters

| Key | Default | Description |
|---|---|---|
| `sweep_seconds` | 0.40 | TRIM sweep speed (separate from EQ) |
| `curve_exp` | 1.0 | TRIM response curve |
| `smoothing_factor` | 0.55 | TRIM axis smoothing |
| `dead_zone` | 0.18 | TRIM dead zone |
| `max_db` | 10.5 | Maximum TRIM boost in dB |
| `write_throttle` | 0.015 | TRIM write rate |
| `write_epsilon` | 0.15 | TRIM epsilon culling |
| `detent_range` | 1.0 | TRIM detent width |
| `detent_min_factor` | 0.30 | TRIM detent minimum speed |

### `[fx]` — FX macro control

| Key | Default | Description |
|---|---|---|
| `filter_freq_sweep_s` | 1.5 | Filter Freq sweep speed |
| `filter_res_sweep_s` | 3.0 | Filter Res sweep speed |
| `reverb_size_sweep_s` | 5.0 | Reverb Size sweep speed |
| `fx_send_sweep_s` | 1.0 | FX Send sweep speed |
| `default_sweep_s` | 3.0 | Default for unlisted macros |
| `axis_dead_zone` | 0.08 | FX stick dead zone |
| `accel_ramp_s` | 1.0 | Seconds to reach full acceleration |
| `accel_max_mult` | 4.0 | Maximum acceleration multiplier |
| `write_throttle` | 0.025 | FX write rate (25ms) |
| `write_epsilon_frac` | 0.001 | FX epsilon (fraction of range) |

### `[fx.delay_fb]` — Delay feedback stepping

| Key | Default | Description |
|---|---|---|
| `steps` | 20 | Number of D-pad steps |
| `clamp_frac` | 0.92 | Maximum feedback (92% of range) |
| `debounce_s` | 0.18 | Debounce between presses (180ms) |

---

*This document describes the gesture engine as shipped in FX Machine
v1.0.0. All tunable parameters are hot-reloadable via TOML unless
noted otherwise. The gesture system is designed to be extensible —
new gesture types can be added by following the state machine pattern
described in "Adding a New Gesture Type" above.*
```

