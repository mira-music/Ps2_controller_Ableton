## docs/CONFIG_REFERENCE.md

```markdown
# ⚙️ FX Machine — Configuration Reference

## What This Document Covers

This guide is the complete reference for every tunable parameter in
FX Machine's TOML configuration system. Every key, every default value,
every valid range, what each value controls musically, and how to tune
it for your specific needs.

If you've ever wondered "what happens if I change this number?" — this
is where you find out.

For an explanation of the configuration system's architecture (how
hot-reload works, where files live, how the cfg singleton is built),
see [ARCHITECTURE.md](ARCHITECTURE.md) — specifically the sections on
"The Config Singleton Pattern" and "The TOML Hot-Reload System."

---

## Table of Contents

1. [How to Read This Reference](#how-to-read-this-reference)
2. [TOML Basics](#toml-basics)
3. [File Locations](#file-locations)
4. [Hot-Reload Workflow](#hot-reload-workflow)
5. [[eq.encoder] — EQ Stick Feel](#eqencoder--eq-stick-feel)
6. [[eq.dominance] — Cross-Axis Priority](#eqdominance--cross-axis-priority)
7. [[eq.flick] — Double-Flick Gesture Detection](#eqflick--double-flick-gesture-detection)
8. [[eq.detent] — Sticky 0 dB Feel](#eqdetent--sticky-0-db-feel)
9. [[eq.osc] — EQ Write Rate Control](#eqosc--eq-write-rate-control)
10. [[eq.ramp] — Animation Timing](#eqramp--animation-timing)
11. [[eq.safety] — Bass Protection](#eqsafety--bass-protection)
12. [[trim] — TRIM Knob Parameters](#trim--trim-knob-parameters)
13. [[meter] — Channel Meter Behavior](#meter--channel-meter-behavior)
14. [[meter.clip] — CLIP Indicator](#meterclip--clip-indicator)
15. [[fx] — FX Macro Sweep Speeds](#fx--fx-macro-sweep-speeds)
16. [[fx.delay_fb] — Delay Feedback Stepping](#fxdelay_fb--delay-feedback-stepping)
17. [[volume] — Volume Control](#volume--volume-control)
18. [[navigation] — Track/Scene Navigation](#navigation--trackscene-navigation)
19. [[timing] — System Timing Values](#timing--system-timing-values)
20. [[ui] — User Interface](#ui--user-interface)
21. [[network] — OSC Ports](#network--osc-ports)
22. [[diagnostics] — Performance Monitoring](#diagnostics--performance-monitoring)
23. [[diagnostics.warnings] — Threshold Triggers](#diagnosticswarnings--threshold-triggers)
24. [[diagnostics.rate_limit] — Adaptive Throttling](#diagnosticsrate_limit--adaptive-throttling)
25. [[diagnostics.hooks] — Profiler Targets](#diagnosticshooks--profiler-targets)
26. [Preset Profiles](#preset-profiles)
27. [Common Tuning Scenarios](#common-tuning-scenarios)
28. [Architectural Constants](#architectural-constants)
29. [Restoring Defaults](#restoring-defaults)
30. [Validating Your Configuration](#validating-your-configuration)

---

## How to Read This Reference

Each parameter is documented with:

- **TOML key:** The exact name as written in the config file
- **Type:** What kind of value it accepts (float, int, bool, string, list)
- **Default:** The shipped value
- **Hot-reload status:** Whether changes take effect immediately
  - **[LIVE]:** Changes take effect on next read (within milliseconds)
  - **[RESTART]:** Changes require restarting the app to take effect
- **Range:** Valid values
- **Effect:** What the value controls musically/technically
- **Tuning advice:** When to increase, when to decrease
- **Example values:** Specific suggested values for different use cases

When a TOML key has a dot in it (e.g., `eq.encoder.sweep_seconds`),
the dots represent nested sections:

```toml
[eq.encoder]
sweep_seconds = 0.30   # this is "eq.encoder.sweep_seconds"
```

---

## TOML Basics

TOML (Tom's Obvious Minimal Language) is the format FX Machine uses
for its configuration. The rules are simple:

### Comments

Lines starting with `#` are comments (ignored):

```toml
# This is a comment
sweep_seconds = 0.30   # this is also a comment (inline)
```

### Sections

Section headers go in square brackets:

```toml
[eq.encoder]
# values under [eq.encoder] go here

[eq.flick]
# values under [eq.flick] go here
```

### Values

Each key gets a value. The type matters:

```toml
sweep_seconds = 0.30      # float (decimal point)
timeout_ms = 380           # int (no decimal point)
enabled = true             # bool (true/false, lowercase)
osc_host = "127.0.0.1"     # string (double quotes)
addresses = ["a", "b"]     # list of strings
```

### Common mistakes

- **Quoting numbers:** `sweep_seconds = "0.30"` ← WRONG (don't quote)
- **Capitalized booleans:** `enabled = True` ← WRONG (use lowercase)
- **Missing decimal point:** `sweep_seconds = 1` ← OK for ints but
  becomes weird if the system expects float
- **Trailing comma in lists:** `addresses = ["a", "b",]` ← WRONG

If you make a TOML syntax error, FX Machine catches it on reload and
keeps the previous working values. You won't break the app with a
typo — but you also won't see your intended change take effect until
you fix the syntax.

---

## File Locations

```
config/
├── default.toml          Factory template — DON'T EDIT
├── active.toml           Your settings — EDIT THIS
├── EXAMPLES.toml         Ready-to-copy preset snippets
├── README.md             Plain-English explainer for the config folder
└── presets/              Save your own profiles here
    └── my_punchy_club.toml   (example)
```

### default.toml

Shipped with the app. Contains every parameter with its default value
and explanatory comments. **Do not edit this file.** It's your reference
and your safety net.

If `active.toml` doesn't exist, the app reads from `default.toml`.

### active.toml

Created automatically on first launch by copying `default.toml`. This
is the file you edit. Changes here are read on every launch and on
every hot-reload.

### EXAMPLES.toml

Contains 5 preset snippets (Punchy Club, Studio Precise, Beginner
Forgiving, Radio Safe, Vintage Analog). Copy snippets from here into
`active.toml` to apply preset configurations.

### presets/

Your personal preset library. Save copies of `active.toml` here with
descriptive names. To activate a preset, copy it back over `active.toml`
and reload.

---

## Hot-Reload Workflow

```
1. Open config/active.toml in any text editor
2. Edit a value (or paste a preset snippet)
3. Save the file
4. In FX Machine, press SELECT + START
   OR click the ⟳ REFRESH button in the UI
5. The new values take effect immediately
   (or a warning appears if you changed a [RESTART] value)
```

The reload is fast — usually under 100ms. You'll see a notification in
the UI:
- "✓ Config reload — N applied" if successful
- "⚠ N need restart" if you changed a [RESTART] value
- "⚠ Config has errors" if your TOML has syntax problems

If reload fails, the previous values remain in effect. The app never
breaks from a config edit.

---

## [eq.encoder] — EQ Stick Feel

Controls how the right stick feels when you push it to change EQ band
values. This section has the biggest impact on the "feel" of the
controller.

### sweep_seconds

- **Type:** float
- **Default:** `0.30`
- **Hot-reload:** [LIVE]
- **Range:** 0.10 to 5.00 (practical)
- **Effect:** Time to sweep the full EQ range at maximum stick deflection

This is the most important parameter for encoder feel. It sets the
maximum speed of the encoder.

**Low values (0.15-0.25):**
- Very fast, very responsive
- Good for aggressive performances ("riding the waves")
- Risk: tiny stick movements cause big value jumps
- Risk: easy to overshoot your target

**Default (0.30):**
- Punchy, performance-friendly
- Balanced between speed and precision
- Suitable for most use cases

**Medium values (0.50-1.00):**
- Slower, more controlled
- Good for studio work where precision matters
- Feels less like a DJ controller, more like a fader

**High values (1.50-3.00):**
- Slow, deliberate
- Good for fine-tuning specific bands
- Feels sluggish during live performance

**Going below 0.15:** the encoder becomes nearly impossible to use
precisely because every micro-movement of the stick produces large
value changes.

**Going above 5.00:** the encoder feels broken. Even full deflection
barely moves the value.

### curve_exp

- **Type:** float
- **Default:** `1.0`
- **Hot-reload:** [LIVE]
- **Range:** 0.5 to 3.0 (practical)
- **Effect:** Response curve shape (how stick deflection maps to encoder speed)

This is a power curve applied to the stick deflection. The math:

```
speed = (deflection ^ curve_exp) × max_speed
```

**curve_exp = 1.0 (linear, default):**
- Push stick 50% → get 50% of max speed
- Predictable, consistent response
- The "I want what I asked for" choice

**curve_exp = 1.2-1.5 (slight ease):**
- Very precise near rest (small movements barely move)
- Big movements needed for fast sweeps
- Good for performers who want fine control AND occasional bursts

**curve_exp = 2.0 (quadratic):**
- Almost nothing happens until ~40% deflection
- Then rapid acceleration to max speed
- Feels like a physical knob with resistance
- NOT recommended for live performance (too slow for emergency kills)

**curve_exp = 0.7-0.8 (inverse ease):**
- Very responsive
- Small pushes have large effects
- Good for aggressive DJing
- Bad for precision

**Recommendation:** Start at 1.0. If you find yourself overshooting,
try 1.2. If you want more "snap," try 0.85.

### smoothing_factor

- **Type:** float
- **Default:** `0.55`
- **Hot-reload:** [LIVE]
- **Range:** 0.05 to 1.00
- **Effect:** Exponential smoothing applied to stick input (jitter removal)

Gamepad sticks are noisy. The ADC inside the stick fluctuates ±0.01 to
±0.05 even when the stick is physically stationary. Smoothing removes
this noise.

**Low values (0.10-0.30):**
- Heavy smoothing
- Very stable but laggy
- Takes 10-20 frames to fully respond to stick changes
- Use if your controller has visible drift or twitch

**Default (0.55):**
- Balanced
- Responds within ~3-4 frames
- Jitter nearly eliminated

**High values (0.75-1.00):**
- Light or no smoothing
- Snappy response
- Visible jitter at rest
- Use if your controller is brand new and stable

**Going below 0.10:** the encoder feels disconnected from the stick.
Movements lag noticeably.

**Going above 1.00:** no smoothing at all — full jitter passes through.

### dead_zone

- **Type:** float
- **Default:** `0.18`
- **Hot-reload:** [LIVE]
- **Range:** 0.00 to 0.50
- **Effect:** How far you must push the stick before any movement registers

The dead zone prevents drift when the stick is at rest. Most controllers
have small offsets from manufacturing tolerance — the stick reads
±0.02 to ±0.05 even when "centered."

**Low values (0.05-0.10):**
- Very sensitive
- Risk: parameter drift when stick is "at rest"
- Use only with brand-new, high-quality controllers

**Default (0.18):**
- Comfortable middle ground
- Handles typical controller wear
- No noticeable drift on most controllers

**High values (0.25-0.35):**
- Very stable
- You have to push noticeably before anything happens
- Good for old/worn controllers

**Going above 0.50:** you lose most of the stick's usable range.

**How to tune for your specific controller:**

1. Set `dead_zone = 0.05`
2. Run the app, enter EQ mode, leave the stick alone
3. If the EQ value drifts (slowly creeps up or down), increase `dead_zone`
4. Increase until drift stops
5. Add 0.03 as a safety margin

---

## [eq.dominance] — Cross-Axis Priority

When you push the right stick diagonally, both X and Y axes see
movement. The dominance system decides which axis "wins" and prevents
the other from interfering.

### ratio

- **Type:** float
- **Default:** `3.0`
- **Hot-reload:** [LIVE]
- **Range:** 1.0 to 10.0
- **Effect:** How much one axis must exceed the other to claim dominance

The check: `if abs(stick_y) > abs(stick_x) * ratio: Y wins`

**ratio = 1.0 (loose):**
- Any vertical component suppresses horizontal
- Band switches trigger too easily during normal encoder use
- Not recommended

**ratio = 2.0 (balanced):**
- Moderate vertical emphasis needed
- Some accidental band switches still possible

**ratio = 3.0 (default, strict):**
- Strong vertical emphasis required
- Diagonal stick movements bias toward X (value adjustment)
- Band switches require deliberate vertical pushes

**ratio = 5.0 (very strict):**
- Almost pure vertical movement needed
- Band switches become harder to trigger from rest
- Use if you find yourself accidentally switching bands

**Tuning advice:**

If you accidentally switch bands while adjusting values, INCREASE this
value (4.0, 5.0). If band switches feel hard to trigger even when you
intend them, DECREASE it (2.0, 1.5).

---

## [eq.flick] — Double-Flick Gesture Detection

Double-flicks are the rapid there-and-back stick movements that trigger
discrete actions (kill, normalize, boost, restore, band switch). These
parameters control the detection logic.

### extreme

- **Type:** float
- **Default:** `0.90`
- **Hot-reload:** [LIVE]
- **Range:** 0.50 to 1.00
- **Effect:** How far you must push the stick to register the start of a flick

**Low values (0.70-0.80):**
- Easy to trigger flicks
- Risk: accidental triggers during fast normal stick movements
- Use if your controller can't reach 0.90 deflection (worn springs)

**Default (0.90):**
- Decisive, deliberate flicks required
- Almost impossible to trigger accidentally
- Industry-standard threshold

**High values (0.95-1.00):**
- Very strict
- Requires hitting the mechanical stop of the stick
- Almost impossible to trigger accidentally, but also hard to trigger intentionally

### return_threshold

- **Type:** float
- **Default:** `0.22`
- **Hot-reload:** [LIVE]
- **Range:** 0.05 to 0.50
- **Effect:** How close to center the stick must return between the two flicks

After the first flick, the stick must return near center before the
second flick can register.

**Low values (0.10-0.15):**
- Must return very close to center
- Strict — partial returns don't count
- Reduces false triggers from stick bounce

**Default (0.22):**
- Balanced
- Stick must be noticeably released
- Works with typical controller spring behavior

**High values (0.30-0.40):**
- Loose — partial returns are enough
- More forgiving for users with imprecise stick control
- Risk: false triggers when stick is wobbling

### timeout_ms

- **Type:** int (milliseconds)
- **Default:** `380`
- **Hot-reload:** [LIVE]
- **Range:** 100 to 1000
- **Effect:** Maximum time between first and second flick

**Low values (200-300):**
- Very fast — gesture must be snappy
- Strict but reliable
- Use if you can do quick flicks naturally

**Default (380):**
- Comfortable for most users
- Allows deliberate but not rushed gestures

**High values (500-700):**
- Relaxed timing
- Risk: slow stick movements during encoder use chain into accidental gestures

**Tuning advice:**

If you're missing gestures because you can't flick fast enough, INCREASE
this value (500). If you're getting accidental gestures from slow stick
movements, DECREASE it (300).

---

## [eq.detent] — Sticky 0 dB Feel

Real EQ knobs have a tactile notch at 0 dB (unity gain) to help find
center by feel. The detent simulates this digitally by slowing the
encoder when the value is near 0 dB.

### range

- **Type:** float (macro units)
- **Default:** `1.0`
- **Hot-reload:** [LIVE]
- **Range:** 0.0 to 10.0
- **Effect:** Width of the "sticky" zone around 0 dB

**range = 0.0 (no detent):**
- Encoder slides smoothly through 0 dB
- No tactile feedback at neutral
- Pure linear feel

**range = 0.5 (narrow):**
- Detent only when very close to 0 dB
- Easy to pass through
- Subtle "hint" rather than "wall"

**Default (1.0):**
- Narrow but noticeable detent
- Easy to find 0 dB by feel
- Easy to pass through if you keep pushing

**range = 3.0-5.0 (wide):**
- Pronounced detent feel
- Strong pull toward 0 dB
- Can feel restrictive during boost/cut sweeps

**range = 10.0 (extremely wide):**
- Almost everything feels sticky
- Hard to leave the neutral zone
- Not recommended

### min_factor

- **Type:** float
- **Default:** `0.30`
- **Hot-reload:** [LIVE]
- **Range:** 0.0 to 1.0
- **Effect:** Minimum speed multiplier inside the detent zone

**min_factor = 0.0:**
- Encoder STOPS at 0 dB
- Cannot push through without releasing and re-engaging
- Not recommended

**min_factor = 0.15 (sticky):**
- Strong resistance at 0 dB
- Encoder slows to 15% of normal speed
- Feels like a wall

**Default (0.30):**
- Noticeable resistance
- Feels like a real EQ knob's center detent

**min_factor = 0.5-0.7 (mild):**
- Slight slowdown
- Subtle feedback that you're near 0

**min_factor = 1.0 (no slowdown):**
- Same as setting `range = 0.0`
- No detent effect

---

## [eq.osc] — EQ Write Rate Control

Controls how often OSC messages are sent to Ableton. Too many messages
overwhelm Ableton; too few cause perceived lag.

### write_throttle

- **Type:** float (seconds)
- **Default:** `0.015` (15ms)
- **Hot-reload:** [LIVE]
- **Range:** 0.001 to 0.100
- **Effect:** Minimum time between OSC writes per EQ band

**Low values (0.005-0.010):**
- Ultra-smooth visual updates
- High OSC traffic to Ableton
- Risk: Ableton CPU load increases

**Default (0.015 = 15ms = 66 Hz):**
- Smooth perception
- Moderate OSC traffic
- Safe for most systems

**High values (0.030-0.050):**
- Visibly steppy movements
- Low OSC traffic
- Good for slow systems or when Ableton is heavily loaded

### write_epsilon

- **Type:** float (macro units)
- **Default:** `0.15`
- **Hot-reload:** [LIVE]
- **Range:** 0.01 to 5.0
- **Effect:** Minimum value change worth sending

If a value change is smaller than this threshold, the write is skipped.
Saves bandwidth on imperceptible changes.

**Low values (0.05-0.10):**
- Very smooth visual updates
- More OSC traffic
- Catches every tiny change

**Default (0.15 ≈ 0.07 dB):**
- Imperceptible threshold
- ~80% reduction in OSC traffic during small movements
- No visible quality loss

**High values (0.30-1.00):**
- Steppy movements
- Major OSC traffic reduction
- Visible quality loss

---

## [eq.ramp] — Animation Timing

When double-flick actions fire (kill, normalize, boost, restore), the
value animates smoothly. These parameters control the animation speed.

### min_ms

- **Type:** int (milliseconds)
- **Default:** `30`
- **Hot-reload:** [LIVE]
- **Range:** 10 to 200
- **Effect:** Fastest ramp duration (for fastest flicks)

**Low values (20):**
- Lightning fast
- Almost instant
- Risk: audible click on sharp transitions

**Default (30):**
- Snappy but smooth
- Click-free

**High values (50-100):**
- Noticeably smooth
- Less "snappy" feel

### max_ms

- **Type:** int (milliseconds)
- **Default:** `100`
- **Hot-reload:** [LIVE]
- **Range:** 50 to 500
- **Effect:** Slowest ramp duration (for slowest flicks)

**Default (100):**
- Balanced
- Smooth for slow, deliberate flicks

**High values (200-300):**
- Dramatic, sweeping transitions
- Good for ambient/melodic music
- Bad for percussive music (too slow)

---

## [eq.safety] — Bass Protection

Critical for protecting speakers and listeners. Bass frequencies carry
enormous energy and can cause damage if boosted too much.

### bass_boost_cap

- **Type:** float (macro units)
- **Default:** `114.0` (≈+2 dB)
- **Hot-reload:** [LIVE]
- **Range:** 107.9 to 127.0
- **Effect:** Maximum bass macro value via encoder

**107.9 (= 0 dB):**
- No boost allowed
- Bass can only be cut or kept neutral
- Maximum safety

**Default (114.0 ≈ +2 dB):**
- Safe musical boost
- Audible emphasis without speaker risk

**120.0 (≈+4 dB):**
- Aggressive boost
- Only use if you trust your system

**127.0 (≈+6 dB max):**
- Full boost — NO SAFETY
- Can damage subwoofers at high volumes

**Recommendation:** Leave at default unless you're working in a
controlled environment with known-good speakers.

### mid_high_boost_pct

- **Type:** float (0.0 to 1.0)
- **Default:** `0.15` (15%)
- **Hot-reload:** [LIVE]
- **Range:** 0.05 to 0.50
- **Effect:** Asymptotic boost percentage per double-flick for mid/high bands

When you double-flick right above 0 dB, the boost is calculated as:
```
boost = (headroom_remaining) × mid_high_boost_pct
```

**Default (0.15):**
- Musical, gradual approach to maximum
- ~3-4 flicks to reach noticeable boost
- ~10+ flicks to approach +6 dB

**Lower values (0.05-0.10):**
- Very subtle per-flick boost
- Many flicks needed for significant boost

**Higher values (0.25-0.50):**
- Aggressive per-flick boost
- 2-3 flicks to reach maximum
- Easier to over-boost

---

## [trim] — TRIM Knob Parameters

TRIM has its own complete set of parameters separate from the EQ bands.
This allows different feel characteristics (TRIM is typically tuned
for fluid gain matching, EQ bands for snappy performance).

### sweep_seconds

- **Type:** float
- **Default:** `0.40`
- **Hot-reload:** [LIVE]
- **Range:** 0.10 to 5.00
- **Effect:** TRIM full-range sweep time

TRIM is typically swept slower than EQ bands because it's used for
deliberate gain matching, not rapid performance.

**Default (0.40):**
- Smooth, controlled feel
- Good for A/B-ing tracks

**Faster (0.20-0.30):**
- More like EQ encoder
- Snappy for quick adjustments

**Slower (0.60-1.00):**
- Very deliberate
- Studio precision

### curve_exp

- **Type:** float
- **Default:** `1.0`
- **Hot-reload:** [LIVE]
- **Range:** 0.5 to 3.0
- **Effect:** TRIM response curve (same logic as eq.encoder.curve_exp)

### smoothing_factor

- **Type:** float
- **Default:** `0.55`
- **Hot-reload:** [LIVE]
- **Range:** 0.05 to 1.00
- **Effect:** TRIM stick smoothing (same logic as eq.encoder.smoothing_factor)

### dead_zone

- **Type:** float
- **Default:** `0.18`
- **Hot-reload:** [LIVE]
- **Range:** 0.00 to 0.50
- **Effect:** TRIM dead zone (same logic as eq.encoder.dead_zone)

### max_db

- **Type:** float (dB)
- **Default:** `10.5`
- **Hot-reload:** [LIVE]
- **Range:** 3.0 to 35.0
- **Effect:** Maximum TRIM boost in dB

The DJM-900 NXS2 caps TRIM at +9 dB. FX Machine defaults to 10.5 dB
for slightly more headroom.

**3.0:** Conservative cap
**6.0:** Standard EQ-style cap
**9.0:** DJM-900 NXS2 standard
**10.5 (default):** Slight extension
**12.0:** Aggressive
**Going above 12.0:** unusual for a DJ workflow

### write_throttle / write_epsilon

Same logic as eq.osc parameters but specific to TRIM. Defaults are
identical to EQ (0.015 / 0.15).

### detent_range / detent_min_factor

Same logic as eq.detent parameters but specific to TRIM. Note that
TRIM's neutral point is macro 64.0 (not 107.9 like EQ bands), so the
detent operates at a different physical position on the macro range.

---

## [meter] — Channel Meter Behavior

Controls the channel meter's visual response to audio levels.

### reference_offset_db

- **Type:** float (dB)
- **Default:** `8.7`
- **Hot-reload:** [LIVE]
- **Range:** 0 to 24
- **Effect:** dB offset added to Ableton's raw meter values for display

Ableton reports meter levels in dBFS (0 dBFS = digital clipping). DJ
mixers display levels relative to a NOMINAL "0 dB" reference, typically
-18 dBFS in digital systems. This offset shifts the display so 0 dBFS
shows as a high value on the meter (around +12 to +18).

**+6:** Very hot reference (rarely shows red)
**+9 (broadcast/mastering standard):** Default
**+15:** Quiet reference (everything looks loud)

**How to tune:**

1. Play audio at your normal performance level through Ableton
2. Check the meter's typical reading
3. If everything reads in the red zone, INCREASE this offset
4. If everything reads in the bottom green zone, DECREASE this offset

The exact value of `8.7` was calibrated empirically against a specific
audio interface during development. Your system may differ.

### release_db_per_sec

- **Type:** float (dB/second)
- **Default:** `20.0`
- **Hot-reload:** [LIVE]
- **Range:** 1.0 to 200.0
- **Effect:** How fast the meter falls back down after signal drops

**Low values (5-10):**
- Slow release (like analog VU meters)
- Smooth, musical
- Slower visual response to dynamics

**Default (20):**
- Moderate release
- Good balance of smoothness and responsiveness

**High values (60-200):**
- Fast release (digital style)
- Highly responsive
- Can flicker with percussive content

### peak_hold_seconds

- **Type:** float (seconds)
- **Default:** `1.5`
- **Hot-reload:** [LIVE]
- **Range:** 0.0 to 10.0
- **Effect:** How long the PEAK indicator holds at the highest recent level

**Low values (0.5):**
- Quick peak indicator
- Always shows current peak

**Default (1.5):**
- Easy to see momentary peaks
- Holds long enough to read

**High values (3-5):**
- Lingering peak hold
- Easier to catch transient peaks
- Slow to update for new peaks

### peak_fall_db_per_sec

- **Type:** float (dB/second)
- **Default:** `30.0`
- **Hot-reload:** [LIVE]
- **Range:** 1.0 to 200.0
- **Effect:** How fast the peak indicator falls after the hold time

Similar to release_db_per_sec but specifically for the peak indicator.

---

## [meter.clip] — CLIP Indicator

The CLIP indicator at the top of the meter warns when audio is
approaching dangerous levels.

### warn_db

- **Type:** float (dB on the display scale)
- **Default:** `6.0`
- **Hot-reload:** [LIVE]
- **Range:** -6 to +15
- **Effect:** dB threshold for CLIP to start showing (yellow warning)

**+3:** Very early warning (lots of safety margin)
**+6 (default):** Early — gives you time to react
**+9:** Late warning (close to clipping)

### critical_db

- **Type:** float (dB on the display scale)
- **Default:** `9.0`
- **Hot-reload:** [LIVE]
- **Range:** -3 to +18
- **Effect:** dB threshold for CLIP to become urgent (flashing red)

Must be higher than `warn_db`. The transition between warn and critical
is smooth (yellow → orange → red gradient).

**+9 (default):** Standard urgent threshold
**+11:** Very late (clipping basically imminent)

### flicker_hz

- **Type:** float (Hz)
- **Default:** `4.0`
- **Hot-reload:** [LIVE]
- **Range:** 0.0 to 30.0
- **Effect:** How fast the CLIP light flickers when above critical_db

**2:** Slow, calm flicker
**4 (default):** Moderate, attention-getting
**8:** Fast, urgent
**12:** Strobe-like (may trigger visual sensitivities)

**0:** No flicker (solid color)

### fadeout_seconds

- **Type:** float (seconds)
- **Default:** `0.5`
- **Hot-reload:** [LIVE]
- **Range:** 0.0 to 5.0
- **Effect:** How long CLIP stays lit after signal drops below warn_db

**0.2:** Quick fade
**0.5 (default):** Balanced
**1.0+:** Lingering — easier to notice that clipping happened

---

## [fx] — FX Macro Sweep Speeds

Per-macro sweep durations. Different macros have different musical
characters and benefit from different sweep speeds.

### filter_freq_sweep_s

- **Type:** float (seconds)
- **Default:** `1.5`
- **Hot-reload:** [LIVE]
- **Range:** 0.3 to 10.0
- **Effect:** Filter Freq sweep time at max stick deflection

The most-played macro. Keep it fast for performance.

**0.8:** Aggressive, snappy
**1.5 (default):** Balanced
**3.0:** Slow, sweeping (good for build-ups)

### filter_res_sweep_s

- **Type:** float (seconds)
- **Default:** `3.0`
- **Hot-reload:** [LIVE]
- **Effect:** Filter Resonance sweep time

Resonance is usually "set and forget" — most performers find a good
value and rarely change it during a session.

### reverb_size_sweep_s

- **Type:** float (seconds)
- **Default:** `5.0`
- **Hot-reload:** [LIVE]
- **Effect:** Reverb decay time sweep speed

Reverb size is rarely swept during a track. Slow sweep is fine.

### fx_send_sweep_s

- **Type:** float (seconds)
- **Default:** `1.0`
- **Hot-reload:** [LIVE]
- **Effect:** FX Send sweep time

Punchy for throw effects. Don't make this too slow or throws lose
their immediacy.

### default_sweep_s

- **Type:** float (seconds)
- **Default:** `3.0`
- **Hot-reload:** [LIVE]
- **Effect:** Default sweep time for any FX macro not listed above

### axis_dead_zone

- **Type:** float
- **Default:** `0.08`
- **Hot-reload:** [LIVE]
- **Range:** 0.0 to 0.5
- **Effect:** Dead zone for FX layer (separate from EQ dead zone)

FX uses a smaller dead zone (0.08) than EQ (0.18) because FX sweeps
typically use more of the stick's range.

### accel_ramp_s

- **Type:** float (seconds)
- **Default:** `1.0`
- **Hot-reload:** [LIVE]
- **Range:** 0.1 to 10.0
- **Effect:** Time to reach maximum acceleration when holding the stick

When you hold the FX stick in one direction, acceleration ramps up.
This parameter sets how quickly that ramp completes.

**0.5:** Fast ramp — quick acceleration
**1.0 (default):** Smooth, predictable ramp
**3.0:** Slow ramp — only reaches max with extended hold

### accel_max_mult

- **Type:** float
- **Default:** `4.0`
- **Hot-reload:** [LIVE]
- **Range:** 1.0 to 10.0
- **Effect:** Maximum acceleration multiplier

**1.0:** No acceleration (sweeps always at base speed)
**4.0 (default):** Up to 4x faster when held
**10.0:** Extreme acceleration

### write_throttle

- **Type:** float (seconds)
- **Default:** `0.025` (25ms)
- **Hot-reload:** [LIVE]
- **Effect:** Minimum time between FX OSC writes

Higher than EQ throttle (15ms) because FX sweeps don't need quite the
same smoothness as EQ adjustments.

### write_epsilon_frac

- **Type:** float (fraction of macro range)
- **Default:** `0.001` (0.1% of range)
- **Hot-reload:** [LIVE]
- **Effect:** Minimum value change worth sending (as fraction of full range)

---

## [fx.delay_fb] — Delay Feedback Stepping

Delay feedback uses discrete D-pad steps instead of continuous stick
control, because feedback runaway is a real risk.

### steps

- **Type:** int
- **Default:** `20`
- **Hot-reload:** [LIVE]
- **Range:** 5 to 100
- **Effect:** Number of D-pad steps across the feedback range

**10:** Coarse (10% per step)
**20 (default):** Moderate (5% per step)
**50:** Fine (2% per step)

### clamp_frac

- **Type:** float (0.0 to 1.0)
- **Default:** `0.92`
- **Hot-reload:** [LIVE]
- **Range:** 0.5 to 0.99
- **Effect:** Maximum feedback as fraction of macro range

**0.92 (default):** Caps at 92% to prevent runaway
**0.95-0.99:** Risk of infinite feedback
**0.50-0.75:** Very safe but limits creative options

### debounce_s

- **Type:** float (seconds)
- **Default:** `0.18`
- **Hot-reload:** [LIVE]
- **Range:** 0.05 to 1.0
- **Effect:** Minimum time between D-pad presses

Prevents double-steps from a single physical press (D-pad contact
bounce).

---

## [volume] — Volume Control

SELECT + R-stick volume control parameters.

### dead_zone

- **Type:** float
- **Default:** `0.12`
- **Hot-reload:** [LIVE]
- **Range:** 0.0 to 0.5
- **Effect:** Dead zone for volume stick

### sensitivity

- **Type:** float
- **Default:** `0.004`
- **Hot-reload:** [LIVE]
- **Range:** 0.001 to 0.05
- **Effect:** How much volume changes per stick movement frame

**Low values (0.002):** Slow, precise volume changes
**Default (0.004):** Balanced
**High values (0.010+):** Fast, aggressive changes

### ableton_unity

- **Type:** float
- **Default:** `0.85`
- **Hot-reload:** [LIVE]
- **Range:** 0.0 to 1.0
- **Effect:** Ableton's "0 dB unity gain" position on the track fader

This is Ableton's internal mapping. 0.85 corresponds to 0 dB on the
fader. Don't change unless you know what you're doing.

### change_threshold

- **Type:** float
- **Default:** `0.003`
- **Hot-reload:** [LIVE]
- **Effect:** Minimum volume change worth sending to Ableton

---

## [navigation] — Track/Scene Navigation

Controls left-stick scrolling through tracks and scenes.

### analog_threshold

- **Type:** float
- **Default:** `0.55`
- **Hot-reload:** [LIVE]
- **Range:** 0.3 to 0.9
- **Effect:** How far the stick must push before navigation triggers

Higher than other dead zones because navigation should require
deliberate stick movement.

### hold_scroll_delay

- **Type:** float (seconds)
- **Default:** `0.50`
- **Hot-reload:** [LIVE]
- **Range:** 0.1 to 2.0
- **Effect:** How long to hold the stick before auto-scroll kicks in

**Low values (0.2):** Auto-scroll engages quickly
**Default (0.5):** Comfortable
**High values (1.0):** Single steps must be deliberate single pushes

### hold_scroll_rate

- **Type:** float (seconds)
- **Default:** `0.18`
- **Hot-reload:** [LIVE]
- **Range:** 0.05 to 1.0
- **Effect:** How fast auto-scroll repeats once active

### smoothing_factor

- **Type:** float
- **Default:** `0.18`
- **Hot-reload:** [LIVE]
- **Effect:** Stick smoothing for navigation (heavier than EQ smoothing)

### dpad_debounce

- **Type:** float (seconds)
- **Default:** `0.30`
- **Hot-reload:** [LIVE]
- **Effect:** Minimum time between D-pad presses

---

## [timing] — System Timing Values

Various internal timing parameters. Most users never need to change
these.

### r3_double_click_window

- **Type:** float (seconds)
- **Default:** `0.40`
- **Hot-reload:** [LIVE]
- **Effect:** Time window for R3 double-click to register as mute

### query_defer_time

- **Type:** float (seconds)
- **Default:** `0.04`
- **Hot-reload:** [LIVE]
- **Effect:** Delay before deferred OSC position queries fire (debouncing)

### fx_safety_poll_interval

- **Type:** float (seconds)
- **Default:** `2.0`
- **Hot-reload:** [LIVE]
- **Effect:** How often to re-poll FX/EQ values as safety net

### watchdog_interval

- **Type:** float (seconds)
- **Default:** `1.0`
- **Hot-reload:** [LIVE]
- **Effect:** How often the controller watchdog checks health

### idle_reprobe_after

- **Type:** float (seconds)
- **Default:** `5.0`
- **Hot-reload:** [LIVE]
- **Effect:** Idle threshold before performing deep controller health check

### select_reconcile_interval

- **Type:** float (seconds)
- **Default:** `0.10`
- **Hot-reload:** [LIVE]
- **Effect:** How often to check for dropped SELECT button-up events

---

## [ui] — User Interface

UI parameters. All are [RESTART] because they're consumed once at
startup.

### refresh_ms

- **Type:** int (milliseconds)
- **Default:** `25` (40 Hz)
- **Hot-reload:** [RESTART]
- **Range:** 10 to 200
- **Effect:** UI redraw interval

**16 (60 Hz):** Smoother but more CPU
**25 (40 Hz, default):** Balanced
**40 (25 Hz):** Choppy but low CPU

### blink_period_ms

- **Type:** int (milliseconds)
- **Default:** `500`
- **Hot-reload:** [RESTART]
- **Effect:** Blink rate for status indicators (e.g., "NO CONTROLLER")

### window_width / window_height

- **Type:** int (pixels)
- **Default:** `760` / `900`
- **Hot-reload:** [RESTART]
- **Effect:** Initial window dimensions

---

## [network] — OSC Ports

Network configuration. All [RESTART] because OSC sockets bind at
startup.

### osc_host

- **Type:** string
- **Default:** `"127.0.0.1"`
- **Hot-reload:** [RESTART]
- **Effect:** IP address where Ableton's OSC is listening (usually localhost)

### osc_send_port

- **Type:** int
- **Default:** `11000`
- **Hot-reload:** [RESTART]
- **Effect:** Port to SEND OSC messages to (Ableton's input)

### osc_receive_port

- **Type:** int
- **Default:** `11001`
- **Hot-reload:** [RESTART]
- **Effect:** Port to RECEIVE OSC messages on (FX Machine's input)

Both must match AbletonOSC's configuration. Change only if you have
port conflicts.

---

## [diagnostics] — Performance Monitoring

The diagnostics layer is fully covered in [DIAGNOSTICS_GUIDE.md](DIAGNOSTICS_GUIDE.md).
This section is a quick reference.

### enabled

- **Type:** bool
- **Default:** `false`
- **Hot-reload:** [LIVE]
- **Effect:** Master switch for the diagnostics layer

When `false`, the diagnostics module isn't even imported — zero
overhead. When `true`, expect ~1-2% CPU overhead.

### log_path / jsonl_path

- **Type:** string
- **Defaults:** `"logs/diagnostics.log"` / `"logs/diagnostics.jsonl"`
- **Hot-reload:** [RESTART]
- **Effect:** Output file paths

### summary_interval_s

- **Type:** float (seconds)
- **Default:** `10.0`
- **Hot-reload:** [LIVE]
- **Effect:** How often to write a summary block

### sample_interval_s

- **Type:** float (seconds)
- **Default:** `1.0`
- **Hot-reload:** [LIVE]
- **Effect:** System resource sampling rate

### slow_function_threshold_ms

- **Type:** float (milliseconds)
- **Default:** `5.0`
- **Hot-reload:** [LIVE]
- **Effect:** Threshold for flagging slow function calls as outliers

### slow_frame_threshold_ms

- **Type:** float (milliseconds)
- **Default:** `50.0`
- **Hot-reload:** [LIVE]
- **Effect:** Threshold for flagging slow UI frames

### osc_traffic_window_s

- **Type:** float (seconds)
- **Default:** `5.0`
- **Hot-reload:** [LIVE]
- **Effect:** Rolling window for OSC rate calculations

### jsonl_format

- **Type:** string
- **Default:** `"compact"`
- **Hot-reload:** [LIVE]
- **Range:** `"compact"` or `"pretty"`
- **Effect:** JSONL output format

### jsonl_include_osc_args

- **Type:** bool
- **Default:** `false`
- **Hot-reload:** [LIVE]
- **Effect:** Include OSC message arguments in JSONL

---

## [diagnostics.warnings] — Threshold Triggers

Thresholds that trigger warnings in the summary log.

| Key | Default | Effect |
|---|---|---|
| `clip_event_rate_per_min` | 10 | Warn if clipping > N/min |
| `osc_send_rate_per_sec` | 200 | Warn if outbound OSC > N/sec |
| `osc_recv_rate_per_sec` | 300 | Warn if inbound OSC > N/sec |
| `single_call_warn_ms` | 100.0 | Warn if any function call > N ms |
| `cpu_warn_percent` | 25.0 | Warn if CPU average > N% |
| `memory_growth_warn_mb` | 50.0 | Warn if memory growth > N MB |
| `thread_miss_warn_fraction` | 0.10 | Warn if thread misses > N fraction |

---

## [diagnostics.rate_limit] — Adaptive Throttling

Optional self-defense — suppress events that fire too frequently.

| Key | Default | Effect |
|---|---|---|
| `enabled` | `false` | Master switch for rate limiting |
| `clip_notifications_per_min` | 20 | Max clip notifications per minute |
| `osc_sends_per_address_per_sec` | 100 | Max OSC sends per address per second |
| `cooldown_s` | 5.0 | Suppression duration after limit hits |

---

## [diagnostics.hooks] — Profiler Targets

Configures which functions to profile. See [DIAGNOSTICS_GUIDE.md](DIAGNOSTICS_GUIDE.md)
for the full list.

| Key | Default | Effect |
|---|---|---|
| `timed_functions` | 16 functions | Functions to wrap with timing shims |
| `track_all_osc_sends` | `true` | Track every outbound OSC message |
| `track_all_osc_receives` | `true` | Track every inbound OSC message |
| `tracked_osc_addresses` | 4 prefixes | Filtered addresses when track_all is false |

---

## Preset Profiles

Five ready-to-copy preset snippets ship in `config/EXAMPLES.toml`.
Copy snippets into `active.toml` to apply preset configurations.

### PUNCHY CLUB

Aggressive, fast, decisive. For peak-time club energy.

```toml
[eq.encoder]
sweep_seconds = 0.20
curve_exp = 0.85

[eq.flick]
timeout_ms = 300

[fx]
filter_freq_sweep_s = 0.8
fx_send_sweep_s = 0.6

[eq.ramp]
min_ms = 20
max_ms = 60
```

### STUDIO PRECISE

Slow, surgical, fine-grained. For mixing and arrangement.

```toml
[eq.encoder]
sweep_seconds = 1.00
curve_exp = 1.4

[eq.detent]
range = 3.0
min_factor = 0.15

[fx]
filter_freq_sweep_s = 3.0
filter_res_sweep_s = 5.0
```

### BEGINNER FORGIVING

Easy controls, hard to make mistakes. Good for learning.

```toml
[eq.encoder]
sweep_seconds = 0.50
dead_zone = 0.25

[eq.flick]
extreme = 0.85
return_threshold = 0.30
timeout_ms = 500

[fx]
axis_dead_zone = 0.15
```

### RADIO/STREAM SAFE

Strict gain control. Paranoid metering. For broadcast.

```toml
[eq.safety]
bass_boost_cap = 110.0
mid_high_boost_pct = 0.10

[trim]
max_db = 6.0

[meter.clip]
warn_db = 3.0
critical_db = 6.0
```

### VINTAGE ANALOG FEEL

Springy, mechanical, gentle ramps. For organic feel.

```toml
[eq.encoder]
smoothing_factor = 0.35
curve_exp = 1.3

[eq.ramp]
min_ms = 60
max_ms = 200

[eq.detent]
range = 2.0
min_factor = 0.20
```

---

## Common Tuning Scenarios

### "The controller feels twitchy at rest"

Likely causes:
- Worn controller with stick drift
- Dead zone too small

Fix:
```toml
[eq.encoder]
dead_zone = 0.25  # increase from 0.18

[fx]
axis_dead_zone = 0.15  # increase from 0.08
```

### "I keep accidentally switching bands while sweeping values"

Cross-axis dominance is too loose.

Fix:
```toml
[eq.dominance]
ratio = 4.5  # increase from 3.0
```

### "Double-flicks aren't registering reliably"

The detection is too strict for your stick movement style.

Fix:
```toml
[eq.flick]
extreme = 0.85           # decrease from 0.90
return_threshold = 0.28  # increase from 0.22
timeout_ms = 500         # increase from 380
```

### "The encoder feels sluggish"

Sweep time too long.

Fix:
```toml
[eq.encoder]
sweep_seconds = 0.20  # decrease from 0.30
```

### "EQ kills sound clicky"

Ramp too short — value snaps abruptly.

Fix:
```toml
[eq.ramp]
min_ms = 50    # increase from 30
max_ms = 150   # increase from 100
```

### "Audio is clipping during throws"

Wet chain output too hot.

Fix:
- In Ableton: reduce Reverb output level, reduce Delay output level
- Or in config: reduce TRIM cap to prevent over-boosting first
```toml
[trim]
max_db = 6.0  # decrease from 10.5
```

### "Meter never shows yellow/red"

Reference offset too low.

Fix:
```toml
[meter]
reference_offset_db = 12.0  # increase from 8.7
```

### "Meter is always in the red"

Reference offset too high.

Fix:
```toml
[meter]
reference_offset_db = 6.0  # decrease from 8.7
```

---

## Architectural Constants

Some values are NOT in TOML and CANNOT be changed via configuration.
These are "architectural constants" baked into `src/config.py`. They
represent measured physical facts (EQ_NEUTRAL_MACRO = 107.9 is the
empirically calibrated value where 0 dB occurs on EQ Three's macro).

Changing these requires modifying source code, and doing so usually
breaks calibration or breaks features. Don't change them unless you
understand what you're doing.

Examples:

- `EQ_NEUTRAL_MACRO = 107.9` — where 0 dB sits on EQ Three's macro
- `TRIM_NEUTRAL_MACRO = 64.0` — where 0 dB sits on Utility Gain's macro
- `EQ_CUT_HALF_MACRO = 53.95` — the -19 dB target for mid/high kills
- Button index constants (BTN_CROSS = 2, etc.) — pygame conventions
- OSC paths and slot indices

See `src/config.py` for the complete list with documentation.

---

## Restoring Defaults

If you've messed up `active.toml` and want to start fresh:

```bash
# Option A: Copy default.toml over active.toml
copy config\default.toml config\active.toml

# Option B: Delete active.toml — app regenerates it on next launch
del config\active.toml
```

Either way, the app will use factory defaults on next launch.

---

## Validating Your Configuration

Run the diagnostic tool to verify your TOML is valid and all values
are within expected ranges:

```bash
python diagnose.py
```

Look for these checks:
- "config/active.toml parses correctly"
- "All N loader mappings resolve to keys in default.toml"
- "All cfg.X references in code resolve correctly"

If any of these fail, your config has a problem that will cause the
app to crash or misbehave. The diagnostic tool will tell you exactly
which key is broken.

---

*This document describes the configuration system as shipped in
FX Machine v1.0.0. Every documented parameter is functional and tested.
Adding new parameters requires changes to `src/config.py`,
`src/config_loader.py`, and the relevant consuming modules — see
[ARCHITECTURE.md](ARCHITECTURE.md) for the full procedure.*
```
