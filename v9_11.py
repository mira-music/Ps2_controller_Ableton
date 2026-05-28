"""
================================================================================
  THE FX MACHINE  —  Live Performance System v9.11
================================================================================

  A USB gamepad transformed into a live performance instrument for
  Ableton Live, designed for melodic house and progressive deep house.
  Real-time effects control, scene navigation, parallel-bus FX
  manipulation, AND a 3-band kill EQ via OSC — all in one controller.

  Conceived, designed, and developed by:
    Ayoub Agoujdad
    Artist:    MIRA___OFC   (Instagram)
    Project:   Modulated_OFC

  Made by and for Modulated_OFC.

  © 2026 Ayoub Agoujdad. All rights reserved.
  Trademark registered. Copyrighted work.
  Strictly NON-COMMERCIAL USE ONLY.

================================================================================
                              SYSTEM OVERVIEW
================================================================================

  The FX Machine bridges a USB gamepad to Ableton Live via OSC
  (AbletonOSC backend, ports 11000 send / 11001 receive). It exposes
  two parallel-bus racks inserted in series before the master output:

      All instrument tracks ──▶ Return A
                                    │
                                    ▼
                              ~ EQ Macros      (3-band kill EQ)
                                    │
                                    ▼
                              ~ FX Macros      (filter/reverb/delay/stutter)
                                    │
                                    ▼
                                 Master

  This mirrors a Pioneer DJM-900 NXS2 channel strip topology: EQ first
  (shape the source), then FX (process the shaped signal). The signal
  flows through both racks in series, just like a DJ mixer channel.

  The controller is a standard USB gamepad with PS-style layout
  (Triangle, Circle, Cross, Square, L1/R1/L2/R2/L3/R3, Select, Start,
  D-pad, two analog sticks). Tested on PS2-USB adapters and PS3/PS4
  pads via xinput/dinput on Windows.

================================================================================
                            ARCHITECTURE OVERVIEW
================================================================================

  Five daemon threads run concurrently, coordinated via a shared
  `state` dict protected by a reentrant lock (`_lock`):

  1. CONTROLLER THREAD    (~125 Hz)
     pygame event loop reads buttons, axes, D-pad. Dispatches to
     handlers. Manages connection state and ghost-release detection.

  2. POLLING THREAD       (~6.6 Hz)
     Periodic OSC queries to Ableton (BPM, transport, volume, FX/EQ
     macro values for safety reconciliation, session size detection).

  3. OSC SERVER THREAD    (event-driven)
     Receives OSC messages from Ableton via pythonosc dispatcher.
     Updates `state` and `ableton` dicts with current values.

  4. WATCHDOG THREAD      (1 Hz)
     Monitors controller health. Auto-reprobes on silent disconnect.
     Detects ghost button-up events (especially SELECT).

  5. EQ RAMP THREAD       (~60 Hz)
     Animates EQ value changes for double-flick actions. Cubic
     ease-out for smooth, click-free transitions.

  Main thread runs Tkinter UI (40 Hz refresh) with dirty-cache label
  updates and canvas-based knob/meter rendering.

================================================================================
                            SYSTEM 1 — FX MACHINE
================================================================================

  The FX rack is a multi-effect Audio Effect Rack on the ~ FX Macros
  track. Eight macros control five effects:

    Macro 1 — Filter Freq    (Auto Filter freq, log 20 Hz – 20 kHz)
    Macro 2 — Filter Mode    (Auto Filter LP/HP, 0 = HP, 1 = LP)
    Macro 3 — Filter Res     (Auto Filter resonance, 20%–100%)
    Macro 4 — Stutter        (Beat Repeat on/off)
    Macro 5 — Reverb Size    (Dark Hall decay 200ms–60s)
    Macro 6 — FX Send        (Utility-as-send inside nested wet/dry rack)
    Macro 7 — Delay FB       (Simple Long Digi Delay feedback)
    Macro 8 — Width          (Utility stereo width 0%–200%)

  FX SIGNAL ROUTING (the nested wet/dry trick):

    Audio Effect Rack
      ├── Auto Filter       (main path — filter applied to everything)
      ├── Beat Repeat       (main path — stutter applied to everything)
      ├── [Nested Wet/Dry Rack]
      │   ├── Chain "Dry"   (empty — passthrough)
      │   └── Chain "Wet"
      │       ├── Utility   (gain controlled by FX Send macro)
      │       ├── Dark Hall (reverb)
      │       └── Long Digi Delay
      └── Utility           (main path — Width macro)

  FX Send controls how much signal feeds into the wet processing chain
  WITHOUT killing the dry signal. When FX Send drops to 0, reverb/delay
  tails continue to ring out naturally — the wet bus just stops being
  fed new signal. This is the "throw and let it tail" technique.

================================================================================
                            SYSTEM 2 — EQ MACHINE
================================================================================

  The EQ rack is an Audio Effect Rack on the ~ EQ Macros track
  containing one Ableton EQ Three device. Three macros control the
  three band gains:

    Macro 1 — EQ Low    (EQ Three GainLow,  -inf dB to +6 dB)
    Macro 2 — EQ Mid    (EQ Three GainMid,  -inf dB to +6 dB)
    Macro 3 — EQ High   (EQ Three GainHi,   -inf dB to +6 dB)

  EMPIRICAL MAPPING (measured via eq_debug.py session):

    Macro 0       → -inf dB    (full kill)
    Macro 32      → -28.6 dB
    Macro 64      → -13.8 dB
    Macro 96      → -3.76 dB
    Macro 107.9   →  0.00 dB   ← NEUTRAL POSITION
    Macro 112     → +1.28 dB
    Macro 114     → roughly +2 dB  (bass safety cap)
    Macro 127     → +6.00 dB   (max boost)

  CRITICAL OBSERVATION: 0 dB is NOT at macro 64 (the midpoint). It sits
  at macro 107.9 because the cut side spans -inf to 0 dB (logarithmic)
  while the boost side only spans 0 to +6 dB. This is correct EQ Three
  behavior — it's a kill EQ that allows lots of cut and only a small
  amount of boost.

  CONSEQUENCE: The encoder uses real macro-value deltas, NOT linear
  joystick-to-macro mapping. The encoder adds/subtracts macro units
  per frame based on stick deflection — so visual feel is symmetric
  even though the underlying dB curve isn't.

  BASS BOOST CAP: For speaker/listener safety, the Low band's boost
  via continuous stick control is capped at +2 dB (macro 114). The
  stick can be pushed all the way right, but the bass output will
  never exceed +2 dB via the encoder. Additionally, double-flick
  RIGHT on bass when already at/above 0 dB is BLOCKED entirely.

================================================================================
                          EQ GESTURE ENGINE (v9.11)
================================================================================

  When EQ mode is active (toggle via R3 in nav layer), the right stick
  becomes a dual-axis gesture controller. Gestures fall into THREE
  categories:

  ╔═════════════════════════════════════════════════════════════════╗
  ║  1. CONTINUOUS ENCODER (X axis — held)                          ║
  ╠═════════════════════════════════════════════════════════════════╣
  ║  Stick RIGHT held → boost current band (adds to value)          ║
  ║  Stick LEFT held  → cut current band  (subtracts from value)    ║
  ║  Release stick    → value HOLDS at current position             ║
  ║                                                                 ║
  ║  Speed: ~0.6 seconds for full macro range sweep at max defl.    ║
  ║  Curve: slight easing at start, mostly linear (exp = 1.2)       ║
  ║  Dead zone: 0.18 (prevents drift at center)                     ║
  ║  Bass safety: hard cap at +2 dB (macro 114)                     ║
  ║                                                                 ║
  ║  Sticky 0 dB detent: encoder slows when crossing neutral        ║
  ║  (within ±3 macro units of 0 dB, speed drops to 15%)            ║
  ╚═════════════════════════════════════════════════════════════════╝

  ╔═════════════════════════════════════════════════════════════════╗
  ║  2. VALUE ACTIONS — Double-flick X axis                         ║
  ╠═════════════════════════════════════════════════════════════════╣
  ║  Pattern: extreme → center → extreme (same direction)           ║
  ║  Window:  500ms between first and second flick                  ║
  ║                                                                 ║
  ║  DOUBLE-FLICK LEFT — smart kill/normalize:                      ║
  ║    Current value ≤ 0 dB:                                        ║
  ║      LOW band   → KILL to -inf dB                               ║
  ║      MID band   → cut to -19 dB                                 ║
  ║      HIGH band  → cut to -19 dB                                 ║
  ║    Current value > 0 dB:                                        ║
  ║      ANY band   → normalize back to 0 dB                        ║
  ║                                                                 ║
  ║  DOUBLE-FLICK RIGHT — smart restore/boost:                      ║
  ║    Current value < 0 dB:                                        ║
  ║      ANY band   → restore to 0 dB                               ║
  ║    Current value ≥ 0 dB:                                        ║
  ║      LOW band   → BLOCKED (speaker safety)                      ║
  ║      MID band   → +15% of remaining headroom (asymptotic)       ║
  ║      HIGH band  → +15% of remaining headroom (asymptotic)       ║
  ║                                                                 ║
  ║  Animation: cubic ease-out ramp (30-100ms)                      ║
  ║  Ramp speed: faster flicks produce faster ramps                 ║
  ╚═════════════════════════════════════════════════════════════════╝

  ╔═════════════════════════════════════════════════════════════════╗
  ║  3. BAND NAVIGATION — Double-flick Y axis                       ║
  ╠═════════════════════════════════════════════════════════════════╣
  ║  Pattern: extreme → center → extreme (same direction)           ║
  ║  Window:  500ms between first and second flick                  ║
  ║                                                                 ║
  ║  DOUBLE-FLICK UP:                                               ║
  ║    Switches to next band UP. Loop wraps with NO BORDERS:        ║
  ║    MID → HIGH → LOW → MID → HIGH → LOW → ...                    ║
  ║                                                                 ║
  ║  DOUBLE-FLICK DOWN:                                             ║
  ║    Switches to next band DOWN. Loop wraps with NO BORDERS:      ║
  ║    MID → LOW → HIGH → MID → LOW → HIGH → ...                    ║
  ║                                                                 ║
  ║  Visual feedback: during first flick, the target band lights    ║
  ║  up amber (armed state). On second flick, switch confirmed,     ║
  ║  selected band glow moves to the new knob.                      ║
  ║                                                                 ║
  ║  If second flick doesn't arrive within 500ms → silent reset.    ║
  ╚═════════════════════════════════════════════════════════════════╝

  CROSS-AXIS SAFETY:
    - Y gesture (band switch) FREEZES X encoder until Y completes.
    - Axis dominance suppression: if |Y| > |X| * 1.3, Y wins and X
      is ignored entirely. Prevents accidental value changes during
      band switches.
    - All gesture state resets on EQ mode toggle.

  GESTURE PRIORITY (top to bottom, first match wins):
    1. L1 held         → EQ mode paused, FX layer takes stick
    2. SELECT held     → EQ mode paused, volume control takes stick
    3. Y gesture active or Y dominates → X encoder frozen
    4. X gesture active                → encoder paused
    5. Default         → continuous X encoder control

================================================================================
                              CONTROLLER LAYERS
================================================================================

  LAYER 0 — NAVIGATION (default, no modifier held)

    Sticks:
      L-stick   : Scene navigation (Y) / Track navigation (X), hold-to-scroll
      R-stick   : (idle, unused by default — activate via R3 to enter EQ mode)

    D-pad:
      Up/Down   : Bookmark prev/next (§-prefixed scenes)
      Left/Right: Group prev/next (*-prefixed tracks)

    Buttons:
      X      = Launch clip            O      = Stop clip
      △      = Launch scene           □      = Arm track
      L2     = Stop track             R2     = Safety gate (modifier)
      START  = Play/stop transport
      R3     = Toggle EQ mode  (was volume-mute in pre-v9.7)

  LAYER 1 — FX MODE (L1 held)

    Sticks:
      L-stick Y : Filter Freq (sweep, with acceleration)
      L-stick X : Filter Res  (sweep)
      R-stick Y/X : FX Send + Reverb Size (rotation-corrected)

    D-pad:
      Up/Down   : Bookmark prev/next (works in FX mode too)
      Left/Right: Delay FB step (up/down by 1/20th of range)

    Buttons:
      X = STUTTER (momentary)         O = BASS CUT (momentary, 200 Hz HP)
      △ = Launch scene (works here!)  □ = FX SEND THROW (momentary to max)
      L3 = Toggle Filter Lock         R3 = Toggle Wet Lock

    On L1 RELEASE:
      Filter Freq → baseline (unless filter locked)
      FX Send → 0 (unless wet locked)
      Stutter → 0 (always)
      Other macros stay where they are

  LAYER 2 — EQ MODE (R3 tap to enter/exit, see gesture engine above)

    R-stick X : ENCODER (continuous value of selected band)
    R-stick X : DOUBLE-FLICK (kill/normalize/restore/boost actions)
    R-stick Y : DOUBLE-FLICK (band navigation with wraparound)
    L-stick   : Still controls navigation (untouched by EQ mode)

  LAYER 3 — SELECT MODIFIER (SELECT held, in any layer)

    SELECT + R-stick Y : Track volume control (always takes priority)
    SELECT + START     : Force full refresh (Ableton + controller)
    SELECT + R1        : Save FX baseline
    SELECT + R3        : Volume mute toggle (preserved for old behavior)

================================================================================
                            BUTTON MAP QUICK REFERENCE
================================================================================

  Button | Nav Layer        | FX Mode (L1)     | EQ Mode (R3 toggled)
  -------|------------------|------------------|---------------------
  X      | Launch clip      | STUTTER hold     | (no special action)
  O      | Stop clip        | BASS CUT hold    | (no special action)
  △      | Launch scene     | Launch scene     | (no special action)
  □      | Arm track        | FX SEND THROW    | (no special action)
  L1     | (enter FX mode)  | (already in)     | Pauses EQ → enters FX
  R1     | (—)              | (—)              | (—)
  L2     | Stop track       | (—)              | Stop track
  R2     | Safety gate      | Safety gate      | Safety gate
  L3     | (—)              | Filter lock      | (—)
  R3     | Toggle EQ mode   | Wet lock         | Toggle EQ mode (exit)
  SELECT | Vol modifier     | Vol modifier     | Pauses EQ → vol modifier
  START  | Play/Stop        | Play/Stop        | Play/Stop

================================================================================
                              PREFIX CONVENTIONS
================================================================================

  §  on a SCENE name  → that scene is a BOOKMARK
  *  on a TRACK name  → that track is a GROUP boundary (lead track)
  ~ FX Macros         → the audio return track holding the FX rack
  ~ EQ Macros         → the audio return track holding the EQ rack

================================================================================
                            UI LAYOUT (v9.10+)
================================================================================

  Two-column top area + full-width FX panel below:

    ┌──────────────────────┬──────────────────────────────────────┐
    │  ┌────┐  ┌────────┐  │ BMARK   xxx                          │
    │  │HIGH│  │        │  │ GROUP   xxx                          │
    │  │ ⊙  │  │        │  │ TRACK   xxx                          │
    │  │val │  │  LED   │  │ SCENE   xxx                          │
    │  └────┘  │  meter │  │ CLIP    xxx                          │
    │  ┌────┐  │        │  │ [SCENE][TRACK][BMARK]                │
    │  │MID │  │  ████  │  │ +0.0 dB    SELECT+R-stick            │
    │  │ ⊙  │  │  ████  │  │ [■ STOP TRACK (L2)]                  │
    │  │val │  │  ████  │  │ [R2][SEL][PLAY][L1][◇EQ]             │
    │  └────┘  │  ████  │  │ EQ status line                       │
    │  ┌────┐  │  ████  │  │                                      │
    │  │LOW │  │  ████  │  │                                      │
    │  │ ⊙  │  │        │  │                                      │
    │  │val │  │        │  │                                      │
    │  └────┘  └────────┘  │                                      │
    └──────────────────────┴──────────────────────────────────────┘
    ┌──────────────────────────────────────────────────────────────┐
    │  ⚡ FX MACHINE                                               │
    │  [Filter Freq][Mode][Res][Stutter]                           │
    │  [Reverb][FX Send][Delay FB][Width]                          │
    └──────────────────────────────────────────────────────────────┘

  LEFT COLUMN — EQ stack (HIGH/MID/LOW vertical, DJM-900 channel
  strip style) + single big DJM channel meter showing real-time
  audio output level from the EQ track (via Ableton meter listeners).
  Meter has peak-hold indicator that decays over time.

  RIGHT COLUMN — Session navigation info: bookmark, group, track,
  scene, clip names. Number grid showing scene/track/bookmark
  positions. Volume display. Stop button. Modifier status pills.
  EQ status line.

  FX PANEL (full width) — 8 macro knobs in 2 rows of 4. Live
  Ableton parameter values. Visual highlights for active, locked,
  recovering, and momentary states.

================================================================================
                            CRITICAL CONSTANTS
================================================================================

  EQ continuous encoder:
    EQ_SWEEP_SECONDS      = 0.6   # full deflection sweep time
    EQ_ENCODER_CURVE_EXP  = 1.2   # slight start easing, mostly linear
    EQ_AXIS_DEAD_ZONE     = 0.18  # ignore tiny stick movements
    EQ_SMOOTHING_FACTOR   = 0.40  # axis smoothing (lower = snappier)
    EQ_DOMINANCE_RATIO    = 1.3   # |Y| > |X| * this → Y wins
    EQ_DETENT_RANGE       = 3.0   # macro units around 0 dB for detent
    EQ_DETENT_MIN_FACTOR  = 0.15  # min speed multiplier at exact 0 dB

  EQ double-flick gestures:
    EQ_FLICK_EXTREME      = 0.85  # stick at this magnitude = "flicked"
    EQ_FLICK_RETURN       = 0.30  # back to center threshold
    EQ_FLICK_TIMEOUT_MS   = 500   # window between flicks

  EQ ramp animation:
    EQ_RAMP_MIN_MS        = 30    # snappiest ramp (fast flick)
    EQ_RAMP_MAX_MS        = 100   # gentlest ramp (slow flick)
    EQ_RAMP_TICK_MS       = 16    # ~60 Hz update rate
    Easing: cubic ease-out (1 - (1-t)^3)

  EQ values:
    EQ_NEUTRAL_MACRO      = 107.9 # 0 dB position
    EQ_CUT_HALF_MACRO     = 53.95 # -19 dB position (mid/high kill target)
    EQ_BASS_BOOST_CAP     = 114.0 # +2 dB (encoder cap on bass)
    EQ_BOOST_PCT          = 0.15  # double-flick right headroom %

  Channel meter:
    EQ_METER_SEGMENTS     = 24    # LED block count
    EQ_METER_GREEN        = 15    # safe zone count
    EQ_METER_YELLOW       = 6     # loud zone count
    EQ_METER_RED          = 3     # clipping zone count
    EQ_METER_PEAK_HOLD_S  = 1.5   # peak indicator hold time
    EQ_METER_PEAK_FALL    = 0.8   # peak decay rate after hold

  OSC throttling:
    FX_WRITE_THROTTLE     = 0.025 # min seconds between FX writes
    EQ_WRITE_THROTTLE     = 0.020 # min seconds between EQ writes
    FX_WRITE_EPSILON_FRAC = 0.001 # skip writes below this delta

================================================================================
                          BASS CUT RELEASE BEHAVIOR
================================================================================

  Implemented since v9.7: When L1+O is released, Filter Freq + Filter
  Mode restore to the PRE-ENGAGE snapshot (the values they had
  immediately before the button was pressed), NOT the baseline.

  This mirrors how FX throw release works (always returns to pre-
  engage). Lock states no longer affect momentary release behavior —
  locks only affect L1-RELEASE recovery, not individual momentaries.

================================================================================
                          FUTURE FEATURES / IDEAS
================================================================================

  PHASE 4 — QUANTIZED BASS CUT RELEASE
    Hold L1+O for >1 second → engages quantized mode. System watches
    Ableton's beat position via OSC and auto-releases the bass cut
    exactly 10ms before bar 1. Requires beat tracking thread, timer
    scheduler, manual override cancellation. The "Ben Bohmer move"
    from the original vision doc.

  PANIC RESET
    L1+L3+R3 simultaneous = restore ALL FX macros AND EQ bands to
    baseline/neutral instantly. The "oh god what is happening" button.

  PER-BOOKMARK BASELINE
    Different dry FX state per song section. Save baseline A for the
    breakdown, baseline B for the drop, switch via bookmark navigation.

  EQ EXPANSION
    Upgrade from EQ Three to EQ Eight with sub-bass + high-shelf bands.
    Would require remapping macros and adding more gesture targets.

  Y AXIS SECONDARY USE (when not flicking)
    Currently Y only does double-flick band switching. Could later add
    a "Y hold = subtle gain trim" or "Y tilt = pan" feature, but only
    after the core gesture vocabulary is fully bedded in.

  OLED SECONDARY DISPLAY (I2C/SPI)
    Mirror EQ status to a small dedicated screen so main UI can hide
    behind Ableton during performance.

  TAP TEMPO
    Long-press START to enter tap mode, collect 4 taps, average, send
    /live/song/set/tempo. All timing primitives already exist.

================================================================================
                            VERSION HISTORY
================================================================================

  v9.11 DUAL-AXIS DOUBLE-FLICK GESTURES — Y axis switched from hold-to-
        switch to double-flick (mirrors X gesture pattern). Loop wraps
        with no borders. Flick timeout reduced to 500ms for snappier
        feel. Encoder tuned to 0.6s sweep with curve exp 1.2 (slight
        start easing, mostly linear). Smart kill/normalize on X
        double-flick LEFT, smart restore/boost on RIGHT (bass blocked
        at ≥0 dB for safety). Cross-axis Y-freezes-X protection.

  v9.10 2-COLUMN UI + REAL CHANNEL METER — Major UI redesign: EQ stack
        on the left (1/4 width column, DJM-900 channel strip layout),
        nav info on the right (3/4 width). Big single DJM-900 style
        channel meter beside EQ showing real audio output level from
        Ableton (via /live/track/output_meter_left/right listeners).
        Peak hold indicator with decay. Faster encoder (0.9s sweep).
        Bigger FX knobs (48→56px). Removed per-band VU meters and
        active band indicator dots.

  v9.9  VERTICAL EQ — DJM-900 vertical layout, axis swap (Y=band nav
        via hold-to-switch, X=value encoder), smart kill/normalize on
        X double-flick LEFT, sticky 0 dB detent, cubic ease-out ramps
        (30-100ms), per-band VU meters, active band indicator dots,
        dB tick labels on knobs.

  v9.8  ENCODER EQ — joystick rewired as velocity-based encoder, axis-
        dominance suppression, bigger deadzone, longer flick timeout,
        snappier EQ smoothing, dedicated 60Hz EQ ramp thread, DJM-900
        white/silver knob visual, resizable window.

  v9.7  EQ MACHINE — full 3-band kill EQ subsystem. R3 toggles EQ mode.
        Right stick controls selected band gain with snap-to-zero,
        double-flick X switches bands (with wrapping), double-flick Y
        performs quick kill/restore actions with animated ramps.
        Empirical values: 0 dB = macro 107.9, -19 dB = macro 53.95.
        Bass-cut-release-to-pre-engage memo implemented (was baseline).
        EQ panel added above FX panel.

  v9.6  Button remap (L1+□ throw / L1+△ scene), throw→pre-engage,
        L1+D-pad bookmarks, SELECT safety reconciliation,
        bass cut value fix (42.3 = 200 Hz).

  v9.5  (rolled back) — value-space confusion broke macros.

  v9.4  Round knobs, Ableton colours, momentary FX, fetch lock.

  v9.3  Acceleration + listener mode + FX Send baseline bug fix.

  v9.2  Right-stick rotation, Delay FB on D-pad, Ableton value strings.

  v9.1  View follows L1, baseline, locks, smart recovery.

  v9.0  Phase 2 — Joystick → macro control.

  v8.x  Foundation — controller watchdog, UX polish, OSC hardening.

================================================================================
                              DEPENDENCIES
================================================================================

  Python 3.12.x (tested) on Windows 10/11.

  Required packages (install via pip):
    pygame              - controller input (joystick/gamepad)
    python-osc          - OSC client + server

  Ableton-side requirement:
    AbletonOSC          - https://github.com/ideoforms/AbletonOSC
                          Install in Ableton's Remote Scripts folder.
                          Configure to use ports 11000 (recv) / 11001 (send).

  Hardware:
    Any USB gamepad with PS-style layout (12+ buttons, 4 axes, 1 D-pad).
    Verified compatible:
      - PlayStation 2 controllers via USB adapter (DragonRise Inc., etc.)
      - PlayStation 3 DualShock 3 via USB
      - PlayStation 4 DualShock 4 via USB/Bluetooth
      - Generic xinput/dinput gamepads with same button layout

  Ableton session requirements:
    - One audio Return or audio track named exactly "~ FX Macros"
      containing an Audio Effect Rack (device index 0) with 8 macros
      named: Filter Freq, Filter Mode, Filter Res, Stutter,
             Reverb Size, FX Send, Delay FB, Width
    - One audio Return or audio track named exactly "~ EQ Macros"
      containing an Audio Effect Rack (device index 0) with 3 macros
      named: EQ Low, EQ Mid, EQ High
      (mapped to an EQ Three device's three band gains)
    - Scenes prefixed with § become bookmarks
    - Tracks prefixed with * become group lead tracks

================================================================================
"""

import sys
import time
import math
import threading
import tkinter as tk

import pygame
from pythonosc import udp_client
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer

# ═══════════════════════════════════════════════════════════════════════════
#  VERSION
# ═══════════════════════════════════════════════════════════════════════════

VERSION = "9.11"

# ═══════════════════════════════════════════════════════════════════════════
#  OSC NETWORKING
# ═══════════════════════════════════════════════════════════════════════════

OSC_HOST         = "127.0.0.1"
OSC_SEND_PORT    = 11000
OSC_RECEIVE_PORT = 11001

# ═══════════════════════════════════════════════════════════════════════════
#  ABLETON SESSION LIMITS
# ═══════════════════════════════════════════════════════════════════════════

MAX_SCENES       = 128
MAX_TRACKS       = 64

# ═══════════════════════════════════════════════════════════════════════════
#  PREFIX CONVENTIONS
# ═══════════════════════════════════════════════════════════════════════════

BOOKMARK_PREFIX  = "§"
GROUP_PREFIX     = "*"

# ═══════════════════════════════════════════════════════════════════════════
#  FX RACK IDENTITY
# ═══════════════════════════════════════════════════════════════════════════

FX_TRACK_NAME        = "~ FX Macros"
FX_RACK_DEVICE_INDEX = 0

FX_MACRO_NAMES_EXPECTED = [
    "Filter Freq", "Filter Mode", "Filter Res", "Stutter",
    "Reverb Size", "FX Send",     "Delay FB",   "Width",
]

FX_SLOT_FILTER_FREQ  = 0
FX_SLOT_FILTER_MODE  = 1
FX_SLOT_FILTER_RES   = 2
FX_SLOT_STUTTER      = 3
FX_SLOT_REVERB_SIZE  = 4
FX_SLOT_FX_SEND      = 5
FX_SLOT_DELAY_FB     = 6
FX_SLOT_WIDTH        = 7

# ═══════════════════════════════════════════════════════════════════════════
#  EQ RACK IDENTITY
# ═══════════════════════════════════════════════════════════════════════════

EQ_TRACK_NAME        = "~ EQ Macros"
EQ_RACK_DEVICE_INDEX = 0

EQ_MACRO_NAMES_EXPECTED = ["EQ Low", "EQ Mid", "EQ High"]

EQ_SLOT_LOW  = 0
EQ_SLOT_MID  = 1
EQ_SLOT_HIGH = 2

# Empirical macro values
EQ_MACRO_MIN          = 0.0
EQ_MACRO_MAX          = 127.0
EQ_NEUTRAL_MACRO      = 107.9
EQ_CUT_HALF_MACRO     = 53.95
EQ_BASS_BOOST_CAP     = 114.0

# Encoder-style continuous control
EQ_AXIS_DEAD_ZONE     = 0.18
EQ_SWEEP_SECONDS      = 0.6     # v9.11: was 0.9 — fast overall sweep
EQ_SMOOTHING_FACTOR   = 0.40
EQ_DOMINANCE_RATIO    = 1.3
EQ_ENCODER_CURVE_EXP  = 1.2     # v9.11: slight easing at start, mostly linear

# v9.9: Sticky 0 dB detent
EQ_DETENT_RANGE       = 3.0
EQ_DETENT_MIN_FACTOR  = 0.15

# v9.9: Band navigation (Option D — hold Y to switch)
EQ_NAV_THRESHOLD      = 0.50
EQ_NAV_HOLD_MS        = 150
EQ_NAV_REPEAT_MS      = 350

# v9.10: DJM-900 style channel meter (real audio output level)
EQ_METER_SEGMENTS     = 24      # chunky LED segments, vertical
EQ_METER_GREEN        = 15      # bottom green zone (safe)
EQ_METER_YELLOW       = 6       # mid yellow zone (loud)
EQ_METER_RED          = 3       # top red zone (clipping)
EQ_METER_PEAK_HOLD_S  = 1.5     # peak indicator holds this long
EQ_METER_PEAK_FALL    = 0.8     # then decays at this rate (units/sec)

# Double-flick gesture detection
EQ_FLICK_EXTREME      = 0.85
EQ_FLICK_RETURN       = 0.30
EQ_FLICK_TIMEOUT_MS   = 500     # v9.11: snappier double-flick window

# Animated ramp (60Hz thread)
EQ_RAMP_MIN_MS        = 30
EQ_RAMP_MAX_MS        = 100
EQ_RAMP_TICK_MS       = 16

EQ_BOOST_PCT          = 0.15
EQ_SNAP_ZONE          = 0.05

# ═══════════════════════════════════════════════════════════════════════════
#  MOMENTARY EFFECT VALUES
# ═══════════════════════════════════════════════════════════════════════════

BASS_CUT_MODE_VALUE  = 0.0
BASS_CUT_FREQ_VALUE  = 42.3

# ═══════════════════════════════════════════════════════════════════════════
#  FX POLLING & LISTENERS
# ═══════════════════════════════════════════════════════════════════════════

FX_SAFETY_POLL_INTERVAL = 2.0
FX_LISTEN_REGISTERED    = False
EQ_LISTEN_REGISTERED    = False

# ═══════════════════════════════════════════════════════════════════════════
#  STICK SWEEP TUNING + ACCELERATION (FX)
# ═══════════════════════════════════════════════════════════════════════════

FX_SWEEP_SECONDS = {
    "Filter Freq":  1.5,
    "Filter Res":   3.0,
    "Reverb Size":  5.0,
    "FX Send":      1.0,
}

FX_AXIS_DEAD_ZONE = 0.08

FX_ACCEL_RAMP_S    = 1.0
FX_ACCEL_MAX_MULT  = 4.0

# ═══════════════════════════════════════════════════════════════════════════
#  D-PAD / DELAY FB STEPPING
# ═══════════════════════════════════════════════════════════════════════════

FX_DELAY_FB_CLAMP_FRAC = 0.92
FX_DELAY_FB_STEPS      = 20
FX_DELAY_FB_DEBOUNCE   = 0.18

# ═══════════════════════════════════════════════════════════════════════════
#  OSC WRITE THROTTLING
# ═══════════════════════════════════════════════════════════════════════════

FX_WRITE_THROTTLE      = 0.025
FX_WRITE_EPSILON_FRAC  = 0.001

EQ_WRITE_THROTTLE      = 0.020

# ═══════════════════════════════════════════════════════════════════════════
#  RIGHT STICK ROTATION
# ═══════════════════════════════════════════════════════════════════════════

RIGHT_STICK_ROTATED_90 = True

# ═══════════════════════════════════════════════════════════════════════════
#  RECOVERY BEHAVIOUR (L1 RELEASE)
# ═══════════════════════════════════════════════════════════════════════════

FX_RECOVERY_BEHAVIOUR = {
    FX_SLOT_FILTER_FREQ:  "filter",
    FX_SLOT_FILTER_MODE:  "skip",
    FX_SLOT_FILTER_RES:   "skip",
    FX_SLOT_STUTTER:      "fixed:0.0",
    FX_SLOT_REVERB_SIZE:  "skip",
    FX_SLOT_FX_SEND:      "wet",
    FX_SLOT_DELAY_FB:     "skip",
    FX_SLOT_WIDTH:        "skip",
}

FX_SEND_DRY_VALUE = 0.0
FX_RECOVERY_FLASH_S = 0.6

# ═══════════════════════════════════════════════════════════════════════════
#  NAVIGATION + VOLUME + OTHER
# ═══════════════════════════════════════════════════════════════════════════

AUTO_RESCAN_INTERVAL = 8.0

ANALOG_THRESHOLD     = 0.55
HOLD_SCROLL_DELAY    = 0.50
HOLD_SCROLL_RATE     = 0.18
SMOOTHING_FACTOR     = 0.18

VOL_DEAD_ZONE        = 0.12
VOL_SENSITIVITY      = 0.004
ABLETON_UNITY        = 0.85
VOL_MIN              = 0.0
VOL_MAX              = 1.0
VOL_CHANGE_THRESHOLD = 0.003

DPAD_DEBOUNCE           = 0.30
R3_DOUBLE_CLICK_WINDOW  = 0.40
QUERY_DEFER_TIME        = 0.04
UI_REFRESH_MS           = 25

WATCHDOG_INTERVAL      = 1.0
IDLE_REPROBE_AFTER     = 5.0
BLINK_PERIOD_MS        = 500

ABLETON_ERROR_THROTTLE = 2.0

SELECT_RECONCILE_INTERVAL = 0.10

# ═══════════════════════════════════════════════════════════════════════════
#  BUTTON INDICES
# ═══════════════════════════════════════════════════════════════════════════

BTN_TRIANGLE = 0
BTN_CIRCLE   = 1
BTN_CROSS    = 2
BTN_SQUARE   = 3
BTN_L1       = 4
BTN_R1       = 5
BTN_L2       = 6
BTN_R2       = 7
BTN_SELECT   = 8
BTN_START    = 9
BTN_L3       = 10
BTN_R3       = 11

AXIS_LEFT_X  = 0
AXIS_LEFT_Y  = 1
AXIS_RIGHT_X = 2
AXIS_RIGHT_Y = 3

# ═══════════════════════════════════════════════════════════════════════════
#  THREAD LOCKS
# ═══════════════════════════════════════════════════════════════════════════

_lock        = threading.RLock()
_fetch_lock  = threading.Lock()

# ═══════════════════════════════════════════════════════════════════════════
#  SHARED STATE
# ═══════════════════════════════════════════════════════════════════════════

state = {
    "scene":        0,
    "track":        0,
    "track_group":  0,

    "bookmarks":       [],
    "bookmark_cursor": 0,

    "groups":          [],
    "group_cursor":    0,

    "r2_held":      False,
    "select_held":  False,
    "l1_held":      False,

    "flash_scene":  False,
    "flash_track":  False,
    "flash_bmark":  False,
    "flash_group":  False,
    "flash_until":  0.0,

    "last_action":  "Starting up…",

    "controller_connected": False,
    "controller_name":      "—",

    "_last_input_at":  0.0,
    "_last_reprobe":   0.0,
    "_last_select_reconcile": 0.0,

    "_last_dpad_v": 0.0,
    "_last_dpad_h": 0.0,

    "_lx_held_since":   0.0,
    "_ly_held_since":   0.0,
    "_lx_last_dir":     0,
    "_ly_last_dir":     0,
    "_lx_last_repeat":  0.0,
    "_ly_last_repeat":  0.0,

    "_group_memory": {},

    "fx_track_index":     -1,
    "fx_track_name":      "",
    "fx_macro_names":     [""] * 8,
    "fx_macro_values":    [0.0] * 8,
    "fx_macro_mins":      [0.0] * 8,
    "fx_macro_maxs":      [1.0] * 8,
    "fx_macro_param_ids": [0] * 8,
    "fx_ready":           False,

    "fx_macro_value_strings": ["—"] * 8,

    "fx_baseline":             [0.0] * 8,
    "fx_baseline_ready":       False,
    "fx_baseline_captured_at": 0.0,
    "fx_filter_locked":        False,
    "fx_wet_locked":           False,
    "_fx_recovery_until":      [0.0] * 8,

    "_pre_l1_track":         -1,

    "_fx_last_write_at":  [0.0] * 8,
    "_fx_last_write_val": [0.0] * 8,
    "_fx_last_dpad_h":    0.0,
    "_fx_active_slot":    -1,
    "_fx_active_until":   0.0,

    "_accel_since": {"lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0},
    "_accel_last_dir": {"lx": 0, "ly": 0, "rx": 0, "ry": 0},

    "_momentary_stutter_active":      False,
    "_momentary_bass_cut_active":     False,
    "_momentary_fx_throw_active":     False,
    "_momentary_bass_cut_snapshot":   {"freq": 0.0, "mode": 0.0},
    "_momentary_fx_throw_snapshot":   {"fx_send": 0.0},

    "eq_track_index":      -1,
    "eq_track_name":       "",
    "eq_macro_names":      [""] * 3,
    "eq_macro_values":     [EQ_NEUTRAL_MACRO] * 3,
    "eq_macro_mins":       [0.0] * 3,
    "eq_macro_maxs":       [127.0] * 3,
    "eq_macro_param_ids":  [0] * 3,
    "eq_macro_value_strings": ["—"] * 3,
    "eq_ready":            False,

    "eq_mode_active":      False,
    "eq_selected_band":    EQ_SLOT_MID,
    "eq_armed_band":       -1,
    "eq_armed_until":      0.0,

    # Gesture detection (X axis = value actions in v9.9)
    "_eq_flick_x_state":   "idle",
    "_eq_flick_x_dir":     0,
    "_eq_flick_x_time":    0.0,
    "_eq_flick_x_returned_time": 0.0,

    # Y gesture state (kept for compat, unused in v9.9)
    "_eq_flick_y_state":   "idle",
    "_eq_flick_y_dir":     0,
    "_eq_flick_y_time":    0.0,
    "_eq_flick_y_returned_time": 0.0,

    # v9.11: band navigation now uses double-flick on Y axis
    # (hold-to-switch removed — see _eq_flick_y_state for the new gesture)
    
    # EQ ramp animation
    "_eq_ramp_active":     [False] * 3,
    "_eq_ramp_start_val":  [0.0] * 3,
    "_eq_ramp_target_val": [0.0] * 3,
    "_eq_ramp_start_time": [0.0] * 3,
    "_eq_ramp_duration":   [0.0] * 3,

    "_eq_last_write_at":   [0.0] * 3,
    "_eq_last_write_val":  [0.0] * 3,

    "_eq_encoder_last_tick": 0.0,
      # v9.10: real audio meter on EQ track output (DJM channel meter)
    "eq_meter_left":       0.0,
    "eq_meter_right":      0.0,
    "eq_meter_peak":       0.0,
    "eq_meter_peak_time":  0.0,

    "_real_track_count":  MAX_TRACKS,
    "_real_scene_count":  MAX_SCENES,

    "next_group_name": "—",
    "prev_group_name": "—",

    "_r3_last_click":      0.0,
    "_query_requested_at": 0.0,
    "_vol_last_sent":  0.0,
    "_vol_last_value": ABLETON_UNITY,
}

ableton = {
    "bpm":             120.0,
    "is_playing":      False,
    "track_name":      "—",
    "scene_name":      "—",
    "track_volume":    ABLETON_UNITY,
    "clip_name":       "—",
    "clip_empty":      False,
    "all_scene_names": [],
    "all_track_names": [],
    "all_scene_colors": [],
    "all_track_colors": [],
    "clip_color":       0,
    "fx_track_color":   0,
    "eq_track_color":   0,
}

_smoothed_lx = 0.0
_smoothed_ly = 0.0
_smoothed_rx = 0.0
_smoothed_ry = 0.0
_smoothed_eq_rx = 0.0
_smoothed_eq_ry = 0.0

osc          = None
_osc_server  = None
_ctrl_handle = None

def _set_controller_handle(h):
    global _ctrl_handle
    with _lock:
        _ctrl_handle = h

def _get_controller_handle():
    with _lock:
        return _ctrl_handle

_last_ableton_error_msg  = ""
_last_ableton_error_time = 0.0

# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def db_from_vol(vol):
    if vol <= 0:
        return "-∞ dB"
    db = 20 * math.log10(vol / ABLETON_UNITY)
    return f"{db:+.1f} dB"

def clamp(val, lo, hi):
    return max(lo, min(hi, val))

def flash(key):
    with _lock:
        state[key]           = True
        state["flash_until"] = time.perf_counter() + 0.6

def clear_flashes_if_expired():
    with _lock:
        if time.perf_counter() > state["flash_until"]:
            state["flash_scene"] = False
            state["flash_track"] = False
            state["flash_bmark"] = False
            state["flash_group"] = False

def hybrid_curve(value):
    if value == 0:
        return 0.0
    return (abs(value) ** 1.8) * (1.0 if value > 0 else -1.0)

def smooth_axis(previous, current, factor=None):
    f = factor if factor is not None else SMOOTHING_FACTOR
    return previous * (1.0 - f) + current * f

def mark_controller_input():
    with _lock:
        state["_last_input_at"] = time.perf_counter()

def int_to_hex_color(color_int, fallback="#666666"):
    if color_int is None:
        return fallback
    try:
        color_int = int(color_int) & 0xFFFFFF
    except (TypeError, ValueError):
        return fallback
    if color_int == 0:
        return fallback
    return f"#{color_int:06x}"

def reset_accel_state():
    with _lock:
        for k in state["_accel_since"]:
            state["_accel_since"][k]    = 0.0
            state["_accel_last_dir"][k] = 0

def compute_accel_multiplier(axis_key, current_dir, now):
    with _lock:
        last_dir = state["_accel_last_dir"][axis_key]
        since    = state["_accel_since"][axis_key]

        if current_dir == 0:
            state["_accel_since"][axis_key]    = 0.0
            state["_accel_last_dir"][axis_key] = 0
            return 1.0

        if current_dir != last_dir:
            state["_accel_since"][axis_key]    = now
            state["_accel_last_dir"][axis_key] = current_dir
            return 1.0

        elapsed = now - since

    mult = 1.0 + (elapsed / FX_ACCEL_RAMP_S)
    return min(mult, FX_ACCEL_MAX_MULT)

# ═══════════════════════════════════════════════════════════════════════════
#  EQ HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def eq_visual_position(macro_value):
    if macro_value <= EQ_NEUTRAL_MACRO:
        return (macro_value / EQ_NEUTRAL_MACRO) * 0.5
    else:
        boost_range = EQ_MACRO_MAX - EQ_NEUTRAL_MACRO
        return 0.5 + ((macro_value - EQ_NEUTRAL_MACRO) / boost_range) * 0.5

def eq_encoder_delta(stick_value, dt):
    abs_v = abs(stick_value)
    if abs_v < EQ_AXIS_DEAD_ZONE:
        return 0.0
    normalized = (abs_v - EQ_AXIS_DEAD_ZONE) / (1.0 - EQ_AXIS_DEAD_ZONE)
    normalized = clamp(normalized, 0.0, 1.0)
    shaped = normalized ** EQ_ENCODER_CURVE_EXP
    macro_range = EQ_MACRO_MAX - EQ_MACRO_MIN
    velocity = (macro_range / EQ_SWEEP_SECONDS) * shaped
    sign = 1.0 if stick_value > 0 else -1.0
    return velocity * sign * dt

# ═══════════════════════════════════════════════════════════════════════════
#  OSC SEND
# ═══════════════════════════════════════════════════════════════════════════

def setup_osc():
    global osc
    osc = udp_client.SimpleUDPClient(OSC_HOST, OSC_SEND_PORT)
    print(f"  ✅ OSC sender  → {OSC_HOST}:{OSC_SEND_PORT}")

def osc_select_track(track_idx):
    osc.send_message("/live/view/set/selected_track", [track_idx])

def osc_update_view():
    with _lock:
        track = state["track"]
        scene = state["scene"]
    osc.send_message("/live/view/set/selected_track", [track])
    osc.send_message("/live/view/set/selected_scene", [scene])

def osc_launch_clip():
    with _lock:
        track = state["track"]
        scene = state["scene"]
    osc.send_message("/live/clip_slot/fire", [track, scene])

def osc_stop_clip():
    with _lock:
        track = state["track"]
        scene = state["scene"]
    osc.send_message("/live/clip/stop", [track, scene])

def osc_stop_track():
    with _lock:
        track = state["track"]
    osc.send_message("/live/track/stop_all_clips", [track])

def osc_launch_scene():
    with _lock:
        scene = state["scene"]
    osc.send_message("/live/scene/fire", [scene])

def osc_arm_track():
    with _lock:
        track = state["track"]
    osc.send_message("/live/track/set/arm", [track, 1])

def osc_set_volume(vol):
    with _lock:
        track = state["track"]
    osc.send_message("/live/track/set/volume", [track, vol])

def osc_play():
    osc.send_message("/live/song/start_playing", [])

def osc_stop():
    osc.send_message("/live/song/stop_playing", [])

def osc_query_position():
    with _lock:
        track = state["track"]
        scene = state["scene"]
    osc.send_message("/live/track/get/name",   [track])
    osc.send_message("/live/scene/get/name",   [scene])
    osc.send_message("/live/clip/get/name",    [track, scene])
    osc.send_message("/live/track/get/volume", [track])
    osc.send_message("/live/clip/get/color",   [track, scene])

def schedule_position_query():
    state["_query_requested_at"] = time.perf_counter()

def osc_query_group_previews():
    with _lock:
        groups = list(state["groups"])
        gc     = state["group_cursor"]
    if not groups:
        return
    if gc + 1 < len(groups):
        osc.send_message("/live/track/get/name", [groups[gc + 1]["track_index"]])
    if gc - 1 >= 0:
        osc.send_message("/live/track/get/name", [groups[gc - 1]["track_index"]])

def osc_query_track_color(track_idx):
    osc.send_message("/live/track/get/color", [track_idx])

def osc_query_scene_color(scene_idx):
    osc.send_message("/live/scene/get/color", [scene_idx])

def osc_query_fx_macro_names():
    with _lock:
        track_idx = state["fx_track_index"]
    if track_idx < 0:
        return
    osc.send_message("/live/device/get/parameters/name",
                     [track_idx, FX_RACK_DEVICE_INDEX])

def osc_query_fx_macro_values():
    with _lock:
        track_idx = state["fx_track_index"]
    if track_idx < 0:
        return
    osc.send_message("/live/device/get/parameters/value",
                     [track_idx, FX_RACK_DEVICE_INDEX])

def osc_query_fx_macro_mins():
    with _lock:
        track_idx = state["fx_track_index"]
    if track_idx < 0:
        return
    osc.send_message("/live/device/get/parameters/min",
                     [track_idx, FX_RACK_DEVICE_INDEX])

def osc_query_fx_macro_maxs():
    with _lock:
        track_idx = state["fx_track_index"]
    if track_idx < 0:
        return
    osc.send_message("/live/device/get/parameters/max",
                     [track_idx, FX_RACK_DEVICE_INDEX])

def osc_query_fx_macro_value_strings():
    with _lock:
        track_idx = state["fx_track_index"]
        param_ids = list(state["fx_macro_param_ids"])
        ready     = state["fx_ready"]
    if track_idx < 0 or not ready:
        return
    for slot, pid in enumerate(param_ids):
        with _lock:
            if not state["fx_macro_names"][slot]:
                continue
        osc.send_message("/live/device/get/parameter/value_string",
                         [track_idx, FX_RACK_DEVICE_INDEX, pid])

def osc_register_fx_listeners():
    global FX_LISTEN_REGISTERED
    with _lock:
        track_idx = state["fx_track_index"]
        param_ids = list(state["fx_macro_param_ids"])
        names     = list(state["fx_macro_names"])
    if track_idx < 0:
        return
    count = 0
    for slot, (pid, name) in enumerate(zip(param_ids, names)):
        if not name:
            continue
        osc.send_message("/live/device/start_listen/parameter/value",
                         [track_idx, FX_RACK_DEVICE_INDEX, pid])
        osc.send_message("/live/device/start_listen/parameter/value_string",
                         [track_idx, FX_RACK_DEVICE_INDEX, pid])
        count += 2
    FX_LISTEN_REGISTERED = True
    print(f"  📡 FX listeners registered: {count} listeners armed.")

def osc_stop_fx_listeners():
    global FX_LISTEN_REGISTERED
    with _lock:
        track_idx = state["fx_track_index"]
        param_ids = list(state["fx_macro_param_ids"])
        names     = list(state["fx_macro_names"])
    if track_idx < 0 or not FX_LISTEN_REGISTERED:
        return
    for slot, (pid, name) in enumerate(zip(param_ids, names)):
        if not name:
            continue
        try:
            osc.send_message("/live/device/stop_listen/parameter/value",
                             [track_idx, FX_RACK_DEVICE_INDEX, pid])
            osc.send_message("/live/device/stop_listen/parameter/value_string",
                             [track_idx, FX_RACK_DEVICE_INDEX, pid])
        except Exception:
            pass
    FX_LISTEN_REGISTERED = False
    print("  📡 FX listeners stopped.")

def osc_set_fx_macro(slot, value):
    with _lock:
        track_idx = state["fx_track_index"]
        param_ids = list(state["fx_macro_param_ids"])
    if track_idx < 0:
        return
    if slot < 0 or slot >= len(param_ids):
        return
    param_id = param_ids[slot]
    osc.send_message("/live/device/set/parameter/value",
                     [track_idx, FX_RACK_DEVICE_INDEX, param_id, float(value)])

# ═══════════════════════════════════════════════════════════════════════════
#  EQ OSC SEND
# ═══════════════════════════════════════════════════════════════════════════

def osc_query_eq_macro_names():
    with _lock:
        track_idx = state["eq_track_index"]
    if track_idx < 0:
        return
    osc.send_message("/live/device/get/parameters/name",
                     [track_idx, EQ_RACK_DEVICE_INDEX])

def osc_query_eq_macro_values():
    with _lock:
        track_idx = state["eq_track_index"]
    if track_idx < 0:
        return
    osc.send_message("/live/device/get/parameters/value",
                     [track_idx, EQ_RACK_DEVICE_INDEX])

def osc_query_eq_macro_mins():
    with _lock:
        track_idx = state["eq_track_index"]
    if track_idx < 0:
        return
    osc.send_message("/live/device/get/parameters/min",
                     [track_idx, EQ_RACK_DEVICE_INDEX])

def osc_query_eq_macro_maxs():
    with _lock:
        track_idx = state["eq_track_index"]
    if track_idx < 0:
        return
    osc.send_message("/live/device/get/parameters/max",
                     [track_idx, EQ_RACK_DEVICE_INDEX])

def osc_query_eq_macro_value_strings():
    with _lock:
        track_idx = state["eq_track_index"]
        param_ids = list(state["eq_macro_param_ids"])
        ready     = state["eq_ready"]
    if track_idx < 0 or not ready:
        return
    for slot, pid in enumerate(param_ids):
        with _lock:
            if not state["eq_macro_names"][slot]:
                continue
        osc.send_message("/live/device/get/parameter/value_string",
                         [track_idx, EQ_RACK_DEVICE_INDEX, pid])

def osc_register_eq_listeners():
    global EQ_LISTEN_REGISTERED
    with _lock:
        track_idx = state["eq_track_index"]
        param_ids = list(state["eq_macro_param_ids"])
        names     = list(state["eq_macro_names"])
    if track_idx < 0:
        return
    count = 0
    for slot, (pid, name) in enumerate(zip(param_ids, names)):
        if not name:
            continue
        osc.send_message("/live/device/start_listen/parameter/value",
                         [track_idx, EQ_RACK_DEVICE_INDEX, pid])
        osc.send_message("/live/device/start_listen/parameter/value_string",
                         [track_idx, EQ_RACK_DEVICE_INDEX, pid])
        count += 2
    EQ_LISTEN_REGISTERED = True
    print(f"  📡 EQ listeners registered: {count} listeners armed.")

def osc_stop_eq_listeners():
    global EQ_LISTEN_REGISTERED
    with _lock:
        track_idx = state["eq_track_index"]
        param_ids = list(state["eq_macro_param_ids"])
        names     = list(state["eq_macro_names"])
    if track_idx < 0 or not EQ_LISTEN_REGISTERED:
        return
    for slot, (pid, name) in enumerate(zip(param_ids, names)):
        if not name:
            continue
        try:
            osc.send_message("/live/device/stop_listen/parameter/value",
                             [track_idx, EQ_RACK_DEVICE_INDEX, pid])
            osc.send_message("/live/device/stop_listen/parameter/value_string",
                             [track_idx, EQ_RACK_DEVICE_INDEX, pid])
        except Exception:
            pass
    EQ_LISTEN_REGISTERED = False
    print("  📡 EQ listeners stopped.")

def osc_set_eq_macro(slot, value):
    with _lock:
        track_idx = state["eq_track_index"]
        param_ids = list(state["eq_macro_param_ids"])
    if track_idx < 0:
        return
    if slot < 0 or slot >= len(param_ids):
        return
    param_id = param_ids[slot]
    osc.send_message("/live/device/set/parameter/value",
                     [track_idx, EQ_RACK_DEVICE_INDEX, param_id, float(value)])
def osc_register_eq_meter_listener():
    """Register listeners for EQ track output meter (L+R audio peak)."""
    with _lock:
        track_idx = state["eq_track_index"]
    if track_idx < 0:
        return
    try:
        osc.send_message("/live/track/start_listen/output_meter_left",  [track_idx])
        osc.send_message("/live/track/start_listen/output_meter_right", [track_idx])
        print(f"  📊 EQ meter listeners armed on track {track_idx}")
    except Exception as e:
        print(f"  ⚠  Meter listener register failed: {e}")

def osc_stop_eq_meter_listener():
    with _lock:
        track_idx = state["eq_track_index"]
    if track_idx < 0:
        return
    try:
        osc.send_message("/live/track/stop_listen/output_meter_left",  [track_idx])
        osc.send_message("/live/track/stop_listen/output_meter_right", [track_idx])
    except Exception:
        pass
    
# ═══════════════════════════════════════════════════════════════════════════
#  OSC RECEIVE HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_bpm(address, *args):
    if args:
        with _lock:
            ableton["bpm"] = round(float(args[0]), 1)

def on_is_playing(address, *args):
    if args:
        with _lock:
            ableton["is_playing"] = bool(args[0])

def on_track_name(address, *args):
    if len(args) < 2:
        return
    try:
        idx  = int(args[0])
        name = str(args[1]).strip() if args[1] else "—"
    except (ValueError, IndexError):
        return
    with _lock:
        if idx == state["track"]:
            ableton["track_name"] = name or "—"
        groups = state["groups"]
        gc     = state["group_cursor"]
        if groups:
            next_idx = groups[gc + 1]["track_index"] if gc + 1 < len(groups) else -1
            prev_idx = groups[gc - 1]["track_index"] if gc - 1 >= 0 else -1
            if idx == next_idx:
                state["next_group_name"] = groups[gc + 1]["name"][:14]
            elif idx == prev_idx:
                state["prev_group_name"] = groups[gc - 1]["name"][:14]
        if 0 <= idx < len(ableton["all_track_names"]):
            ableton["all_track_names"][idx] = name

def on_scene_name(address, *args):
    if len(args) < 2:
        return
    try:
        idx  = int(args[0])
        name = str(args[1]).strip() if args[1] else ""
    except (ValueError, IndexError):
        return
    with _lock:
        if idx == state["scene"]:
            ableton["scene_name"] = name or "—"
        if 0 <= idx < len(ableton["all_scene_names"]):
            ableton["all_scene_names"][idx] = name

def on_track_color(address, *args):
    if len(args) < 2:
        return
    try:
        idx       = int(args[0])
        color_int = int(args[1])
    except (ValueError, IndexError):
        return
    with _lock:
        while len(ableton["all_track_colors"]) <= idx:
            ableton["all_track_colors"].append(0)
        ableton["all_track_colors"][idx] = color_int
        if idx == state["fx_track_index"]:
            ableton["fx_track_color"] = color_int
        if idx == state["eq_track_index"]:
            ableton["eq_track_color"] = color_int

def on_scene_color(address, *args):
    if len(args) < 2:
        return
    try:
        idx       = int(args[0])
        color_int = int(args[1])
    except (ValueError, IndexError):
        return
    with _lock:
        while len(ableton["all_scene_colors"]) <= idx:
            ableton["all_scene_colors"].append(0)
        ableton["all_scene_colors"][idx] = color_int

def on_clip_color(address, *args):
    if len(args) < 3:
        return
    try:
        track_idx = int(args[0])
        scene_idx = int(args[1])
        color_int = int(args[2])
    except (ValueError, IndexError):
        return
    with _lock:
        if track_idx == state["track"] and scene_idx == state["scene"]:
            ableton["clip_color"] = color_int

def on_track_volume(address, *args):
    if args:
        with _lock:
            ableton["track_volume"] = clamp(float(args[-1]), VOL_MIN, VOL_MAX)
def on_track_meter_left(address, *args):
    """v9.10: EQ track output meter (left channel peak, 0-1)."""
    if len(args) < 2:
        return
    try:
        track_id = int(args[0])
        value    = float(args[1])
    except (ValueError, IndexError):
        return
    with _lock:
        if track_id == state["eq_track_index"]:
            state["eq_meter_left"] = clamp(value, 0.0, 1.0)

def on_track_meter_right(address, *args):
    """v9.10: EQ track output meter (right channel peak, 0-1)."""
    if len(args) < 2:
        return
    try:
        track_id = int(args[0])
        value    = float(args[1])
    except (ValueError, IndexError):
        return
    with _lock:
        if track_id == state["eq_track_index"]:
            state["eq_meter_right"] = clamp(value, 0.0, 1.0)
def on_clip_name(address, *args):
    with _lock:
        if not args:
            ableton["clip_name"]  = "— empty —"
            ableton["clip_empty"] = True
            return
        name = str(args[-1]).strip()
        if name in ("", "None"):
            ableton["clip_name"]  = "— empty —"
            ableton["clip_empty"] = True
        else:
            ableton["clip_name"]  = name
            ableton["clip_empty"] = False

def on_scene_count(address, *args):
    if args:
        with _lock:
            state["_real_scene_count"]    = int(args[0])
            ableton["all_scene_names"]    = [""] * state["_real_scene_count"]
            ableton["all_scene_colors"]   = [0]  * state["_real_scene_count"]

def on_track_count(address, *args):
    if args:
        with _lock:
            state["_real_track_count"]    = int(args[0])
            ableton["all_track_names"]    = [""] * state["_real_track_count"]
            ableton["all_track_colors"]   = [0]  * state["_real_track_count"]

def on_ableton_error(address, *args):
    global _last_ableton_error_msg, _last_ableton_error_time
    if not args:
        return
    msg = str(args[0])
    now = time.perf_counter()
    if msg == _last_ableton_error_msg and (now - _last_ableton_error_time) < ABLETON_ERROR_THROTTLE:
        return
    _last_ableton_error_msg  = msg
    _last_ableton_error_time = now
    print(f"  ⚠  Ableton: {msg}")

def _extract_fx_param_list(args):
    if len(args) < 3:
        return None
    try:
        track_id  = int(args[0])
        device_id = int(args[1])
    except (ValueError, IndexError):
        return None
    with _lock:
        if track_id != state["fx_track_index"]:
            return None
        if device_id != FX_RACK_DEVICE_INDEX:
            return None
    return list(args[2:])

def _extract_eq_param_list(args):
    if len(args) < 3:
        return None
    try:
        track_id  = int(args[0])
        device_id = int(args[1])
    except (ValueError, IndexError):
        return None
    with _lock:
        if track_id != state["eq_track_index"]:
            return None
        if device_id != EQ_RACK_DEVICE_INDEX:
            return None
    return list(args[2:])

def on_fx_macro_names(address, *args):
    params = _extract_fx_param_list(args)
    if params is None:
        return
    all_names   = [str(p) for p in params]
    found_names = [""] * 8
    found_ids   = [0]  * 8
    found_count = 0
    for slot, expected in enumerate(FX_MACRO_NAMES_EXPECTED):
        for idx, n in enumerate(all_names):
            if n == expected:
                found_names[slot] = n
                found_ids[slot]   = idx
                found_count      += 1
                break
    with _lock:
        state["fx_macro_names"]     = found_names
        state["fx_macro_param_ids"] = found_ids
    print(f"  ⚡ FX macros mapped: {found_count}/8")
    for i, (n, pid) in enumerate(zip(found_names, found_ids)):
        marker = "" if n else "  ⚠ NOT FOUND"
        print(f"     slot {i}: param[{pid}] = {n!r}{marker}")

def on_fx_macro_values(address, *args):
    params = _extract_fx_param_list(args)
    if params is None:
        return
    try:
        all_values = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with _lock:
        param_ids  = list(state["fx_macro_param_ids"])
        new_values = [
            all_values[pid] if 0 <= pid < len(all_values) else 0.0
            for pid in param_ids
        ]
        state["fx_macro_values"] = new_values
        if not state["fx_ready"] and any(state["fx_macro_names"]):
            state["fx_ready"] = True
        if not state["fx_baseline_ready"] and state["fx_ready"]:
            state["fx_baseline"]             = list(new_values)
            state["fx_baseline_ready"]       = True
            state["fx_baseline_captured_at"] = time.perf_counter()
            state["last_action"]             = "✓ Baseline auto-captured on startup"
            print(f"  ✓ Baseline auto-captured: {[round(v,2) for v in new_values]}")

def on_fx_macro_mins(address, *args):
    params = _extract_fx_param_list(args)
    if params is None:
        return
    try:
        all_mins = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with _lock:
        param_ids = list(state["fx_macro_param_ids"])
        state["fx_macro_mins"] = [
            all_mins[pid] if 0 <= pid < len(all_mins) else 0.0
            for pid in param_ids
        ]

def on_fx_macro_maxs(address, *args):
    params = _extract_fx_param_list(args)
    if params is None:
        return
    try:
        all_maxs = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with _lock:
        param_ids = list(state["fx_macro_param_ids"])
        state["fx_macro_maxs"] = [
            all_maxs[pid] if 0 <= pid < len(all_maxs) else 1.0
            for pid in param_ids
        ]

def on_fx_param_value(address, *args):
    if len(args) < 4:
        return
    try:
        track_id  = int(args[0])
        device_id = int(args[1])
        param_id  = int(args[2])
        value     = float(args[3])
    except (ValueError, IndexError):
        return
    with _lock:
        fx_track  = state["fx_track_index"]
        eq_track  = state["eq_track_index"]
    if track_id == fx_track and device_id == FX_RACK_DEVICE_INDEX:
        with _lock:
            slot_match = -1
            for slot, pid in enumerate(state["fx_macro_param_ids"]):
                if pid == param_id and state["fx_macro_names"][slot]:
                    slot_match = slot
                    break
            if slot_match < 0:
                return
            state["fx_macro_values"][slot_match] = value
            if not state["fx_ready"]:
                state["fx_ready"] = True
    elif track_id == eq_track and device_id == EQ_RACK_DEVICE_INDEX:
        with _lock:
            slot_match = -1
            for slot, pid in enumerate(state["eq_macro_param_ids"]):
                if pid == param_id and state["eq_macro_names"][slot]:
                    slot_match = slot
                    break
            if slot_match < 0:
                return
            state["eq_macro_values"][slot_match] = value
            if not state["eq_ready"]:
                state["eq_ready"] = True

def on_fx_param_value_string(address, *args):
    if len(args) < 4:
        return
    try:
        track_id  = int(args[0])
        device_id = int(args[1])
        param_id  = int(args[2])
        value_str = str(args[3])
    except (ValueError, IndexError):
        return
    with _lock:
        fx_track  = state["fx_track_index"]
        eq_track  = state["eq_track_index"]
    if track_id == fx_track and device_id == FX_RACK_DEVICE_INDEX:
        with _lock:
            for slot, pid in enumerate(state["fx_macro_param_ids"]):
                if pid == param_id and state["fx_macro_names"][slot]:
                    state["fx_macro_value_strings"][slot] = value_str
                    return
    elif track_id == eq_track and device_id == EQ_RACK_DEVICE_INDEX:
        with _lock:
            for slot, pid in enumerate(state["eq_macro_param_ids"]):
                if pid == param_id and state["eq_macro_names"][slot]:
                    state["eq_macro_value_strings"][slot] = value_str
                    return

# ═══════════════════════════════════════════════════════════════════════════
#  EQ RECEIVE HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_eq_macro_names(address, *args):
    params = _extract_eq_param_list(args)
    if params is None:
        return
    all_names   = [str(p) for p in params]
    found_names = [""] * 3
    found_ids   = [0]  * 3
    found_count = 0
    for slot, expected in enumerate(EQ_MACRO_NAMES_EXPECTED):
        for idx, n in enumerate(all_names):
            if n == expected:
                found_names[slot] = n
                found_ids[slot]   = idx
                found_count      += 1
                break
    with _lock:
        state["eq_macro_names"]     = found_names
        state["eq_macro_param_ids"] = found_ids
    print(f"  ◇ EQ macros mapped: {found_count}/3")
    for i, (n, pid) in enumerate(zip(found_names, found_ids)):
        marker = "" if n else "  ⚠ NOT FOUND"
        print(f"     slot {i}: param[{pid}] = {n!r}{marker}")

def on_eq_macro_values(address, *args):
    params = _extract_eq_param_list(args)
    if params is None:
        return
    try:
        all_values = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with _lock:
        param_ids  = list(state["eq_macro_param_ids"])
        new_values = [
            all_values[pid] if 0 <= pid < len(all_values) else EQ_NEUTRAL_MACRO
            for pid in param_ids
        ]
        state["eq_macro_values"] = new_values
        if not state["eq_ready"] and any(state["eq_macro_names"]):
            state["eq_ready"] = True

def on_eq_macro_mins(address, *args):
    params = _extract_eq_param_list(args)
    if params is None:
        return
    try:
        all_mins = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with _lock:
        param_ids = list(state["eq_macro_param_ids"])
        state["eq_macro_mins"] = [
            all_mins[pid] if 0 <= pid < len(all_mins) else 0.0
            for pid in param_ids
        ]

def on_eq_macro_maxs(address, *args):
    params = _extract_eq_param_list(args)
    if params is None:
        return
    try:
        all_maxs = [float(p) for p in params]
    except (ValueError, TypeError):
        return
    with _lock:
        param_ids = list(state["eq_macro_param_ids"])
        state["eq_macro_maxs"] = [
            all_maxs[pid] if 0 <= pid < len(all_maxs) else 127.0
            for pid in param_ids
        ]

# ═══════════════════════════════════════════════════════════════════════════
#  OSC SERVER
# ═══════════════════════════════════════════════════════════════════════════

def start_osc_server():
    global _osc_server
    d = Dispatcher()
    d.map("/live/song/get/tempo",                     on_bpm)
    d.map("/live/song/get/is_playing",                on_is_playing)
    d.map("/live/track/get/name",                     on_track_name)
    d.map("/live/track/get/color",                    on_track_color)
    d.map("/live/scene/get/name",                     on_scene_name)
    d.map("/live/scene/get/color",                    on_scene_color)
    d.map("/live/track/get/volume",                   on_track_volume)
    d.map("/live/clip/get/name",                      on_clip_name)
    d.map("/live/clip/get/color",                     on_clip_color)
    d.map("/live/song/get/num_scenes",                on_scene_count)
    d.map("/live/song/get/num_tracks",                on_track_count)
    d.map("/live/device/get/parameters/name",         on_combined_param_names)
    d.map("/live/device/get/parameters/value",        on_combined_param_values)
    d.map("/live/device/get/parameters/min",          on_combined_param_mins)
    d.map("/live/device/get/parameters/max",          on_combined_param_maxs)
    d.map("/live/device/get/parameter/value",         on_fx_param_value)
    d.map("/live/device/get/parameter/value_string",  on_fx_param_value_string)
    d.map("/live/track/get/output_meter_left",        on_track_meter_left)
    d.map("/live/track/get/output_meter_right",       on_track_meter_right)
    d.map("/live/error",                              on_ableton_error)
    ThreadingOSCUDPServer.allow_reuse_address = True
    try:
        _osc_server = ThreadingOSCUDPServer((OSC_HOST, OSC_RECEIVE_PORT), d)
    except OSError as e:
        print(f"  ❌ OSC receiver could not bind to port {OSC_RECEIVE_PORT}: {e}")
        return
    print(f"  ✅ OSC receiver ← {OSC_HOST}:{OSC_RECEIVE_PORT}")
    _osc_server.serve_forever()

# ═══════════════════════════════════════════════════════════════════════════
#  COMBINED PARAM HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def on_combined_param_names(address, *args):
    if len(args) < 3:
        return
    try:
        track_id = int(args[0])
    except (ValueError, IndexError):
        return
    with _lock:
        fx_track = state["fx_track_index"]
        eq_track = state["eq_track_index"]
    if track_id == fx_track:
        on_fx_macro_names(address, *args)
    elif track_id == eq_track:
        on_eq_macro_names(address, *args)

def on_combined_param_values(address, *args):
    if len(args) < 3:
        return
    try:
        track_id = int(args[0])
    except (ValueError, IndexError):
        return
    with _lock:
        fx_track = state["fx_track_index"]
        eq_track = state["eq_track_index"]
    if track_id == fx_track:
        on_fx_macro_values(address, *args)
    elif track_id == eq_track:
        on_eq_macro_values(address, *args)

def on_combined_param_mins(address, *args):
    if len(args) < 3:
        return
    try:
        track_id = int(args[0])
    except (ValueError, IndexError):
        return
    with _lock:
        fx_track = state["fx_track_index"]
        eq_track = state["eq_track_index"]
    if track_id == fx_track:
        on_fx_macro_mins(address, *args)
    elif track_id == eq_track:
        on_eq_macro_mins(address, *args)

def on_combined_param_maxs(address, *args):
    if len(args) < 3:
        return
    try:
        track_id = int(args[0])
    except (ValueError, IndexError):
        return
    with _lock:
        fx_track = state["fx_track_index"]
        eq_track = state["eq_track_index"]
    if track_id == fx_track:
        on_fx_macro_maxs(address, *args)
    elif track_id == eq_track:
        on_eq_macro_maxs(address, *args)

# ═══════════════════════════════════════════════════════════════════════════
#  DISCOVERY
# ═══════════════════════════════════════════════════════════════════════════

def fetch_all_names():
    if not _fetch_lock.acquire(blocking=False):
        print("  ℹ  Fetch already running — skipping.")
        return
    try:
        print("  📚 Requesting session counts…")
        osc.send_message("/live/song/get/num_scenes", [])
        osc.send_message("/live/song/get/num_tracks", [])
        time.sleep(0.6)
        with _lock:
            scene_count = state["_real_scene_count"]
            track_count = state["_real_track_count"]
        print(f"  ℹ  {scene_count} scenes, {track_count} tracks")
        print(f"  📚 Fetching scene names + colors…")
        for i in range(min(scene_count, 256)):
            osc.send_message("/live/scene/get/name",  [i])
            osc.send_message("/live/scene/get/color", [i])
            time.sleep(0.012)
        time.sleep(0.4)
        rebuild_bookmarks()
        print(f"  📚 Fetching track names + colors…")
        for i in range(min(track_count, 64)):
            osc.send_message("/live/track/get/name",  [i])
            osc.send_message("/live/track/get/color", [i])
            time.sleep(0.012)
        time.sleep(0.4)
        rebuild_groups()
        rebuild_fx_track()
        rebuild_eq_track()
        with _lock:
            fx_idx = state["fx_track_index"]
            eq_idx = state["eq_track_index"]
        if fx_idx >= 0:
            print(f"  ⚡ Loading FX macro metadata from track {fx_idx}…")
            osc_query_fx_macro_names()
            time.sleep(0.4)
            osc_query_fx_macro_mins()
            time.sleep(0.2)
            osc_query_fx_macro_maxs()
            time.sleep(0.2)
            osc_query_fx_macro_values()
            time.sleep(0.3)
            osc_query_fx_macro_value_strings()
            time.sleep(0.3)
            osc_query_track_color(fx_idx)
            osc_register_fx_listeners()
        if eq_idx >= 0:
            print(f"  ◇ Loading EQ macro metadata from track {eq_idx}…")
            osc_query_eq_macro_names()
            time.sleep(0.4)
            osc_query_eq_macro_mins()
            time.sleep(0.2)
            osc_query_eq_macro_maxs()
            time.sleep(0.2)
            osc_query_eq_macro_values()
            time.sleep(0.3)
            osc_query_eq_macro_value_strings()
            time.sleep(0.3)
            osc_query_track_color(eq_idx)
            osc_register_eq_listeners()
            osc_register_eq_meter_listener()
        osc_query_position()
        with _lock:
            bm_count = len(state["bookmarks"])
            gr_count = len(state["groups"])
        print(
            f"  ✅ Ready — "
            f"{bm_count} bookmarks | {gr_count} groups | "
            f"FX: {'YES (t' + str(fx_idx) + ')' if fx_idx >= 0 else 'NO'} | "
            f"EQ: {'YES (t' + str(eq_idx) + ')' if eq_idx >= 0 else 'NO'}"
        )
        osc_query_group_previews()
    finally:
        _fetch_lock.release()

def rebuild_bookmarks():
    with _lock:
        all_scenes    = list(ableton["all_scene_names"])
        was_empty     = not state["bookmarks"]
        current_scene = state["scene"]
    bmarks = []
    for idx, name in enumerate(all_scenes):
        if name.startswith(BOOKMARK_PREFIX):
            bmarks.append({"name": name[len(BOOKMARK_PREFIX):].strip(), "scene_index": idx})
    print(f"  § {len(bmarks)} bookmark(s) found")
    with _lock:
        state["bookmarks"] = bmarks
        if not bmarks:
            state["bookmark_cursor"] = 0
            return
        if was_empty:
            state["bookmark_cursor"] = 0
            state["scene"]           = bmarks[0]["scene_index"]
        else:
            _sync_bookmark_cursor_locked(current_scene)

def _sync_bookmark_cursor_locked(scene_idx):
    bmarks = state["bookmarks"]
    if not bmarks:
        return
    best = 0
    for i, bm in enumerate(bmarks):
        if bm["scene_index"] <= scene_idx:
            best = i
    state["bookmark_cursor"] = best

def rebuild_groups():
    with _lock:
        all_tracks    = list(ableton["all_track_names"])
        current_track = state["track"]
    groups = []
    for idx, name in enumerate(all_tracks):
        if name.startswith(GROUP_PREFIX):
            groups.append({"name": name[len(GROUP_PREFIX):].strip(), "track_index": idx})
    print(f"  * {len(groups)} group(s) found")
    with _lock:
        state["groups"] = groups
        if not groups:
            return
        best = 0
        for i, g in enumerate(groups):
            if g["track_index"] <= current_track:
                best = i
        state["group_cursor"] = best
        state["track_group"]  = best
        gc = state["group_cursor"]
        state["prev_group_name"] = groups[gc - 1]["name"][:14] if gc > 0 else "—"
        state["next_group_name"] = groups[gc + 1]["name"][:14] if gc + 1 < len(groups) else "—"

def rebuild_fx_track():
    with _lock:
        all_tracks = list(ableton["all_track_names"])
    fx_idx = -1
    for idx, name in enumerate(all_tracks):
        if name.strip() == FX_TRACK_NAME:
            fx_idx = idx
            break
    with _lock:
        state["fx_track_index"] = fx_idx
        state["fx_track_name"]  = FX_TRACK_NAME if fx_idx >= 0 else ""
        if fx_idx < 0:
            state["fx_ready"] = False
    if fx_idx >= 0:
        print(f"  ⚡ FX track found at index {fx_idx}")
    else:
        print(f"  ⚠  '{FX_TRACK_NAME}' not found — FX panel inactive")

def rebuild_eq_track():
    with _lock:
        all_tracks = list(ableton["all_track_names"])
    eq_idx = -1
    for idx, name in enumerate(all_tracks):
        if name.strip() == EQ_TRACK_NAME:
            eq_idx = idx
            break
    with _lock:
        state["eq_track_index"] = eq_idx
        state["eq_track_name"]  = EQ_TRACK_NAME if eq_idx >= 0 else ""
        if eq_idx < 0:
            state["eq_ready"] = False
    if eq_idx >= 0:
        print(f"  ◇ EQ track found at index {eq_idx}")
    else:
        print(f"  ℹ  '{EQ_TRACK_NAME}' not found — EQ panel inactive (optional)")


# ═══════════════════════════════════════════════════════════════════════════
#  POLLING
# ═══════════════════════════════════════════════════════════════════════════

_last_known_track_count = 0
_last_known_scene_count = 0
_last_fx_safety_poll    = 0.0

def polling_loop():
    global _last_known_track_count, _last_known_scene_count, _last_fx_safety_poll
    tick = 0

    while True:
        try:
            now = time.perf_counter()

            with _lock:
                req = state["_query_requested_at"]
            if req > 0 and (now - req) >= QUERY_DEFER_TIME:
                osc_query_position()
                with _lock:
                    state["_query_requested_at"] = 0.0

            if tick % 7 == 0:
                osc.send_message("/live/song/get/tempo",      [])
                time.sleep(0.02)
                osc.send_message("/live/song/get/is_playing", [])
                time.sleep(0.02)

            if tick % 5 == 0:
                with _lock:
                    track = state["track"]
                osc.send_message("/live/track/get/volume", [track])
                time.sleep(0.02)

            if now - _last_fx_safety_poll >= FX_SAFETY_POLL_INTERVAL:
                with _lock:
                    fx_idx = state["fx_track_index"]
                    eq_idx = state["eq_track_index"]
                if fx_idx >= 0:
                    osc_query_fx_macro_values()
                if eq_idx >= 0:
                    osc_query_eq_macro_values()
                _last_fx_safety_poll = now

            if tick % 50 == 0:
                osc.send_message("/live/song/get/num_tracks", [])
                osc.send_message("/live/song/get/num_scenes", [])
                time.sleep(0.1)

                with _lock:
                    tc = state["_real_track_count"]
                    sc = state["_real_scene_count"]

                if tc != _last_known_track_count or sc != _last_known_scene_count:
                    if _last_known_track_count != 0:
                        print(
                            f"  🔄 Session changed "
                            f"({tc} tracks, {sc} scenes) — rescanning…"
                        )
                        threading.Thread(
                            target=fetch_all_names, daemon=True
                        ).start()
                    _last_known_track_count = tc
                    _last_known_scene_count = sc

            tick += 1
            time.sleep(0.15)

        except Exception as e:
            print(f"  ⚠  Polling error: {e}")
            time.sleep(1.0)

# ═══════════════════════════════════════════════════════════════════════════
#  EQ RAMP ANIMATION — DEDICATED 60Hz THREAD
# ═══════════════════════════════════════════════════════════════════════════

def eq_ramp_loop():
    """Dedicated thread for EQ ramp animation at ~60 Hz."""
    tick_interval = EQ_RAMP_TICK_MS / 1000.0

    while True:
        try:
            time.sleep(tick_interval)
            tick_eq_ramps()
        except Exception as e:
            print(f"  ⚠  EQ ramp loop error: {e}")
            time.sleep(0.5)

def tick_eq_ramps():
    """
    Update active EQ ramps at ~60 Hz.
    v9.9: cubic ease-out for smoother, click-free transitions.
    """
    with _lock:
        active_any = any(state["_eq_ramp_active"])
    if not active_any:
        return

    now = time.perf_counter()
    writes = []

    with _lock:
        for slot in range(3):
            if not state["_eq_ramp_active"][slot]:
                continue

            start_val   = state["_eq_ramp_start_val"][slot]
            target_val  = state["_eq_ramp_target_val"][slot]
            start_time  = state["_eq_ramp_start_time"][slot]
            duration    = state["_eq_ramp_duration"][slot]

            elapsed = now - start_time
            if elapsed >= duration:
                final_val = target_val
                state["_eq_ramp_active"][slot] = False
                state["eq_macro_values"][slot] = final_val
                writes.append((slot, final_val))
            else:
                progress = elapsed / duration
                # Cubic ease-out (smoother than exponential, no clicks)
                eased = 1.0 - (1.0 - progress) ** 3
                current_val = start_val + (target_val - start_val) * eased
                state["eq_macro_values"][slot] = current_val
                writes.append((slot, current_val))

    for slot, val in writes:
        osc_set_eq_macro(slot, val)

def start_eq_ramp(slot, target_val, flick_duration_s):
    """
    Start an animated ramp for an EQ band.
    v9.9: snappier range (30-100ms) via EQ_RAMP_MIN_MS / EQ_RAMP_MAX_MS.
    """
    fd_ms = flick_duration_s * 1000.0
    fd_clamped = clamp(fd_ms, 30.0, 200.0)
    t = (fd_clamped - 30.0) / 170.0
    ramp_ms = EQ_RAMP_MIN_MS + t * (EQ_RAMP_MAX_MS - EQ_RAMP_MIN_MS)
    ramp_duration_s = ramp_ms / 1000.0

    with _lock:
        current_val = state["eq_macro_values"][slot]
        state["_eq_ramp_active"][slot]     = True
        state["_eq_ramp_start_val"][slot]  = current_val
        state["_eq_ramp_target_val"][slot] = target_val
        state["_eq_ramp_start_time"][slot] = time.perf_counter()
        state["_eq_ramp_duration"][slot]   = ramp_duration_s

# ═══════════════════════════════════════════════════════════════════════════
#  NAVIGATION
# ═══════════════════════════════════════════════════════════════════════════

def navigate_scene(direction):
    with _lock:
        old   = state["scene"]
        limit = state["_real_scene_count"] - 1
        new   = clamp(old + direction, 0, limit)
        if new == old:
            state["last_action"] = "⚠ First scene" if direction < 0 else "⚠ Last scene"
            do_flash = "flash_scene"
        else:
            state["scene"]        = new
            _sync_bookmark_cursor_locked(new)
            state["last_action"]  = f"Scene {'↓' if direction > 0 else '↑'}  [{new + 1}]"
            ableton["clip_name"]  = "…"
            ableton["clip_empty"] = False
            schedule_position_query()
            do_flash = None

    if do_flash:
        flash(do_flash)
    else:
        osc_update_view()

def navigate_track(direction):
    with _lock:
        old   = state["track"]
        limit = state["_real_track_count"] - 1
        new   = clamp(old + direction, 0, limit)
        if new == old:
            state["last_action"] = "⚠ First track" if direction < 0 else "⚠ Last track"
            do_flash = "flash_track"
        else:
            state["track"] = new
            for i, g in enumerate(state["groups"]):
                if g["track_index"] <= new:
                    state["track_group"]  = i
                    state["group_cursor"] = i
            if state["groups"]:
                state["_group_memory"][state["group_cursor"]] = new
            state["last_action"]  = f"Track {'→' if direction > 0 else '←'}  [{new + 1}]"
            ableton["track_name"] = "…"
            ableton["clip_name"]  = "…"
            ableton["clip_empty"] = False
            schedule_position_query()
            do_flash = None

    if do_flash:
        flash(do_flash)
    else:
        osc_update_view()

def navigate_bookmark(direction):
    now = time.perf_counter()
    with _lock:
        if now - state["_last_dpad_v"] < DPAD_DEBOUNCE:
            return
        state["_last_dpad_v"] = now
        bmarks   = state["bookmarks"]
        do_nav   = False
        do_flash = None

        if not bmarks:
            state["last_action"] = "⚠ No bookmarks (prefix scenes with §)"
            do_flash = "flash_bmark"
        else:
            cursor           = state["bookmark_cursor"]
            current_scene    = state["scene"]
            current_bm_scene = bmarks[cursor]["scene_index"]

            if direction < 0 and current_scene > current_bm_scene:
                bm = bmarks[cursor]
                state["scene"]        = bm["scene_index"]
                state["last_action"]  = (
                    f"▸ {bm['name']}  [snap back, scene {bm['scene_index'] + 1}]"
                )
                ableton["clip_name"]  = "…"
                ableton["clip_empty"] = False
                schedule_position_query()
                do_nav = True
            else:
                old = cursor
                new = clamp(old + direction, 0, len(bmarks) - 1)
                if new == old:
                    state["last_action"] = "⚠ First bookmark" if direction < 0 else "⚠ Last bookmark"
                    do_flash = "flash_bmark"
                else:
                    state["bookmark_cursor"] = new
                    bm                       = bmarks[new]
                    state["scene"]           = bm["scene_index"]
                    state["last_action"]     = (
                        f"▸ {bm['name']}  [scene {bm['scene_index'] + 1}]"
                    )
                    ableton["clip_name"]  = "…"
                    ableton["clip_empty"] = False
                    schedule_position_query()
                    do_nav = True

    if do_flash:
        flash(do_flash)
    elif do_nav:
        osc_update_view()

def navigate_track_group(direction, force_lead=False):
    now = time.perf_counter()
    with _lock:
        if now - state["_last_dpad_h"] < DPAD_DEBOUNCE:
            return
        state["_last_dpad_h"] = now
        groups   = state["groups"]
        do_nav   = False
        do_flash = None

        if groups:
            old_gc = state["group_cursor"]
            new_gc = clamp(old_gc + direction, 0, len(groups) - 1)
            if new_gc == old_gc:
                state["last_action"] = "⚠ First group" if direction < 0 else "⚠ Last group"
                do_flash = "flash_group"
            else:
                state["group_cursor"] = new_gc
                g = groups[new_gc]

                if force_lead:
                    target = g["track_index"]
                    mode_tag = " ⊕ lead"
                else:
                    target = state["_group_memory"].get(new_gc, g["track_index"])
                    mode_tag = " ⤴ memory" if new_gc in state["_group_memory"] else " ⊕ lead"

                state["track"]       = clamp(target, 0, state["_real_track_count"] - 1)
                state["track_group"] = new_gc
                state["prev_group_name"] = (
                    groups[new_gc - 1]["name"][:14] if new_gc > 0 else "—"
                )
                state["next_group_name"] = (
                    groups[new_gc + 1]["name"][:14] if new_gc + 1 < len(groups) else "—"
                )
                arrow = "→" if direction > 0 else "←"
                state["last_action"]  = f"Group {arrow}  {g['name']}{mode_tag}"
                ableton["track_name"] = "…"
                ableton["clip_name"]  = "…"
                ableton["clip_empty"] = False
                schedule_position_query()
                do_nav = True
        else:
            FALLBACK_SIZE = 4
            max_groups    = state["_real_track_count"] // FALLBACK_SIZE
            old_g = state["track_group"]
            new_g = clamp(old_g + direction, 0, max_groups - 1)
            if new_g == old_g:
                state["last_action"] = "⚠ Group min" if direction < 0 else "⚠ Group max"
                do_flash = "flash_track"
            else:
                state["track_group"] = new_g
                if force_lead:
                    target = new_g * FALLBACK_SIZE
                else:
                    target = state["_group_memory"].get(new_g, new_g * FALLBACK_SIZE)
                state["track"]       = clamp(target, 0, state["_real_track_count"] - 1)
                arrow = "→" if direction > 0 else "←"
                state["last_action"]  = f"Group {arrow}  [{new_g + 1}]"
                ableton["track_name"] = "…"
                ableton["clip_name"]  = "…"
                ableton["clip_empty"] = False
                schedule_position_query()
                do_nav = True

    if do_flash:
        flash(do_flash)
    if do_nav:
        osc_update_view()
        osc_query_group_previews()

# ═══════════════════════════════════════════════════════════════════════════
#  ACTIONS
# ═══════════════════════════════════════════════════════════════════════════

def action_launch_clip():
    with _lock:
        if state["r2_held"]:
            state["last_action"] = "🔒 Safety gate ON"
            return
        state["last_action"] = "▶  Launch Clip"
    osc_launch_clip()

def action_stop_clip():
    with _lock:
        state["last_action"] = "■  Stop Clip"
    osc_stop_clip()

def action_stop_track():
    with _lock:
        state["last_action"] = "⏹  Stop Track"
    osc_stop_track()

def action_launch_scene():
    with _lock:
        if state["r2_held"]:
            state["last_action"] = "🔒 Safety gate ON"
            return
        state["last_action"] = "▶▶ Launch Scene"
    osc_launch_scene()

def action_arm_track():
    with _lock:
        state["last_action"] = "●  Arm Track"
    osc_arm_track()

def action_transport_toggle():
    with _lock:
        playing = ableton["is_playing"]
    if playing:
        osc_stop()
        with _lock:
            state["last_action"] = "⏹  Transport Stop"
    else:
        osc_play()
        with _lock:
            state["last_action"] = "▶  Transport Play"

def action_volume_mute_toggle():
    """SELECT+R3 = volume mute toggle."""
    now = time.perf_counter()
    with _lock:
        last = state["_r3_last_click"]
        if (now - last) <= R3_DOUBLE_CLICK_WINDOW and last > 0:
            ableton["track_volume"] = 0.0
            state["last_action"]    = "🔇 Muted  (SELECT+R3 once to reset)"
            state["_r3_last_click"] = 0.0
            vol = 0.0
        else:
            ableton["track_volume"] = ABLETON_UNITY
            state["last_action"]    = "↺  Volume reset  0 dB"
            state["_r3_last_click"] = now
            vol = ABLETON_UNITY
    osc_set_volume(vol)

def action_force_refresh():
    with _lock:
        state["last_action"] = "🔄 Full refresh (Ableton + colours + controller)…"
    threading.Thread(target=fetch_all_names,    daemon=True).start()
    threading.Thread(target=reprobe_controller, daemon=True,
                     kwargs={"reason": "manual refresh"}).start()

# ═══════════════════════════════════════════════════════════════════════════
#  BASELINE & LOCKS
# ═══════════════════════════════════════════════════════════════════════════

def action_save_baseline():
    with _lock:
        if not state["fx_ready"]:
            state["last_action"] = "⚠ Baseline: FX not ready yet"
            return
        current = list(state["fx_macro_values"])
        state["fx_baseline"]             = current
        state["fx_baseline_ready"]       = True
        state["fx_baseline_captured_at"] = time.perf_counter()
        state["last_action"]             = "✓ Baseline SAVED"
    print(f"  ✓ Baseline manually saved: {[round(v,2) for v in current]}")

def action_toggle_filter_lock():
    with _lock:
        state["fx_filter_locked"] = not state["fx_filter_locked"]
        locked = state["fx_filter_locked"]
        state["last_action"] = "🔒 Filter LOCKED" if locked else "🔓 Filter unlocked"
    print(f"  {'🔒 FILTER LOCK ON' if locked else '🔓 FILTER LOCK OFF'}")

def action_toggle_wet_lock():
    with _lock:
        state["fx_wet_locked"] = not state["fx_wet_locked"]
        locked = state["fx_wet_locked"]
        state["last_action"] = "🔒 Wet LOCKED" if locked else "🔓 Wet unlocked"
    print(f"  {'🔒 WET LOCK ON' if locked else '🔓 WET LOCK OFF'}")

def fx_recover_on_l1_release():
    with _lock:
        if not state["fx_ready"]:
            return
        if not state["fx_baseline_ready"]:
            state["last_action"] = "⚠ Recovery skipped — no baseline captured"
            return

        baseline      = list(state["fx_baseline"])
        current       = list(state["fx_macro_values"])
        wet_locked    = state["fx_wet_locked"]
        filter_locked = state["fx_filter_locked"]

    writes = []

    for slot in range(8):
        behaviour = FX_RECOVERY_BEHAVIOUR.get(slot, "skip")

        if behaviour == "skip":
            continue

        if behaviour.startswith("fixed:"):
            try:
                target = float(behaviour.split(":", 1)[1])
            except ValueError:
                continue

        elif behaviour == "wet":
            if wet_locked:
                continue
            if slot == FX_SLOT_FX_SEND:
                target = FX_SEND_DRY_VALUE
            else:
                target = baseline[slot]

        elif behaviour == "filter":
            if filter_locked:
                continue
            target = baseline[slot]

        else:
            continue

        if abs(target - current[slot]) < 0.0001:
            continue

        writes.append((slot, target))

    now = time.perf_counter()
    with _lock:
        for slot, target in writes:
            state["fx_macro_values"][slot] = target
            state["_fx_last_write_at"][slot]  = now
            state["_fx_last_write_val"][slot] = target
            state["_fx_recovery_until"][slot] = now + FX_RECOVERY_FLASH_S

        if filter_locked and wet_locked:
            tag = "filter+wet HELD"
        elif filter_locked:
            tag = "filter HELD"
        elif wet_locked:
            tag = "wet HELD"
        else:
            tag = "full reset"
        state["last_action"] = f"⬇ FX recovered  ({tag}, {len(writes)} writes)"

    for slot, target in writes:
        osc_set_fx_macro(slot, target)

# ═══════════════════════════════════════════════════════════════════════════
#  MOMENTARY FX BUTTONS
# ═══════════════════════════════════════════════════════════════════════════

def is_macro_under_momentary_control(slot):
    with _lock:
        if slot == FX_SLOT_STUTTER and state["_momentary_stutter_active"]:
            return True
        if slot in (FX_SLOT_FILTER_FREQ, FX_SLOT_FILTER_MODE) and state["_momentary_bass_cut_active"]:
            return True
        if slot == FX_SLOT_FX_SEND and state["_momentary_fx_throw_active"]:
            return True
    return False

# ── STUTTER (L1 + X) ──

def momentary_stutter_on():
    with _lock:
        if state["_momentary_stutter_active"]:
            return
        if not state["fx_ready"]:
            return
        state["_momentary_stutter_active"] = True
        state["last_action"] = "💥 STUTTER (held)"
        max_val = state["fx_macro_maxs"][FX_SLOT_STUTTER]
    osc_set_fx_macro(FX_SLOT_STUTTER, max_val)

def momentary_stutter_off():
    with _lock:
        if not state["_momentary_stutter_active"]:
            return
        state["_momentary_stutter_active"] = False
        state["last_action"] = "Stutter released"
    osc_set_fx_macro(FX_SLOT_STUTTER, 0.0)

# ── BASS CUT (L1 + O) ──

def momentary_bass_cut_on():
    with _lock:
        if state["_momentary_bass_cut_active"]:
            return
        if not state["fx_ready"]:
            return
        state["_momentary_bass_cut_snapshot"] = {
            "freq": state["fx_macro_values"][FX_SLOT_FILTER_FREQ],
            "mode": state["fx_macro_values"][FX_SLOT_FILTER_MODE],
        }
        state["_momentary_bass_cut_active"] = True
        state["last_action"] = "🔻 BASS CUT (held)"
        min_f = state["fx_macro_mins"][FX_SLOT_FILTER_FREQ]
        max_f = state["fx_macro_maxs"][FX_SLOT_FILTER_FREQ]
    target_freq = clamp(BASS_CUT_FREQ_VALUE, min_f, max_f)
    osc_set_fx_macro(FX_SLOT_FILTER_MODE, BASS_CUT_MODE_VALUE)
    osc_set_fx_macro(FX_SLOT_FILTER_FREQ, target_freq)

def momentary_bass_cut_off():
    with _lock:
        if not state["_momentary_bass_cut_active"]:
            return
        state["_momentary_bass_cut_active"] = False
        snapshot = state["_momentary_bass_cut_snapshot"]
        restore_freq = snapshot["freq"]
        restore_mode = snapshot["mode"]
        state["last_action"] = (
            f"Bass cut released → restored to {restore_freq:.1f}/{restore_mode:.1f}"
        )
    osc_set_fx_macro(FX_SLOT_FILTER_FREQ, restore_freq)
    osc_set_fx_macro(FX_SLOT_FILTER_MODE, restore_mode)

# ── FX SEND THROW (L1 + □) ──

def momentary_fx_throw_on():
    with _lock:
        if state["_momentary_fx_throw_active"]:
            return
        if not state["fx_ready"]:
            return
        state["_momentary_fx_throw_snapshot"] = {
            "fx_send": state["fx_macro_values"][FX_SLOT_FX_SEND]
        }
        state["_momentary_fx_throw_active"] = True
        state["last_action"] = "🌫 FX THROW (held)"
        max_val = state["fx_macro_maxs"][FX_SLOT_FX_SEND]
    osc_set_fx_macro(FX_SLOT_FX_SEND, max_val)

def momentary_fx_throw_off():
    with _lock:
        if not state["_momentary_fx_throw_active"]:
            return
        state["_momentary_fx_throw_active"] = False
        target = state["_momentary_fx_throw_snapshot"]["fx_send"]
        state["last_action"] = f"FX throw released → restored to {target:.2f}"
    osc_set_fx_macro(FX_SLOT_FX_SEND, target)

def force_off_all_momentaries():
    momentary_stutter_off()
    momentary_bass_cut_off()
    momentary_fx_throw_off()

# ═══════════════════════════════════════════════════════════════════════════
#  EQ MODE — TOGGLE, ACTIONS, GESTURE ENGINE (v9.9)
# ═══════════════════════════════════════════════════════════════════════════

def action_toggle_eq_mode():
    """R3 in nav layer: toggle EQ mode on/off."""
    with _lock:
        if not state["eq_ready"]:
            state["last_action"] = "⚠ EQ not ready (track ~ EQ Macros not found)"
            return

        state["eq_mode_active"] = not state["eq_mode_active"]
        if state["eq_mode_active"]:
            # Reset all gesture state on entry
            state["_eq_flick_x_state"] = "idle"
            state["_eq_flick_x_dir"]   = 0
            state["_eq_flick_y_state"] = "idle"
            state["_eq_flick_y_dir"]   = 0
            state["eq_armed_band"]     = -1
            state["_eq_encoder_last_tick"] = time.perf_counter()
            band_name = EQ_MACRO_NAMES_EXPECTED[state["eq_selected_band"]]
            state["last_action"] = f"◇ EQ MODE ON — {band_name}  [X=value, Y=switch band]"
        else:
            state["last_action"] = "◇ EQ MODE OFF"

def eq_switch_band(direction):
    """direction: +1 = next (toward HIGH), -1 = prev (toward LOW). Wraps."""
    with _lock:
        cur = state["eq_selected_band"]
        new = (cur + direction) % 3
        state["eq_selected_band"] = new
        state["eq_armed_band"]    = -1
        state["_eq_encoder_last_tick"] = time.perf_counter()
        band_name = EQ_MACRO_NAMES_EXPECTED[new]
        state["last_action"] = f"◇ → {band_name}"
    print(f"  ◇ EQ band switched to {band_name}")

def eq_arm_band(direction):
    """First flick — show which band is armed (kept for compat, unused in v9.9 nav)."""
    with _lock:
        cur = state["eq_selected_band"]
        armed = (cur + direction) % 3
        state["eq_armed_band"]  = armed
        state["eq_armed_until"] = time.perf_counter() + (EQ_FLICK_TIMEOUT_MS / 1000.0)
        band_name = EQ_MACRO_NAMES_EXPECTED[armed]
        state["last_action"] = f"◇ → {band_name} armed (flick again)"

def eq_action_kill(band, flick_duration_s):
    """
    v9.11 — Double-flick LEFT — SMART kill/normalize.
      - If value > 0 dB → normalize back to 0 dB
      - If value ≤ 0 dB → KILL (bass = -inf, mid/high = -19 dB)

    At exactly 0 dB, LEFT-flick triggers kill (aggressive but predictable).
    """
    with _lock:
        current = state["eq_macro_values"][band]
        band_name = EQ_MACRO_NAMES_EXPECTED[band]

    if current > EQ_NEUTRAL_MACRO + 0.5:
        # Above neutral → normalize back to 0 dB
        start_eq_ramp(band, EQ_NEUTRAL_MACRO, flick_duration_s)
        with _lock:
            state["last_action"] = f"↓ {band_name} normalized (0 dB)"
    else:
        # At or below neutral → kill
        if band == EQ_SLOT_LOW:
            target = EQ_MACRO_MIN
            action_text = "💥 BASS KILLED"
        else:
            target = EQ_CUT_HALF_MACRO
            action_text = f"⬇ {band_name} cut (-19 dB)"

        start_eq_ramp(band, target, flick_duration_s)
        with _lock:
            state["last_action"] = action_text

def eq_action_boost_or_restore(band, flick_duration_s):
    """
    v9.11 — Double-flick RIGHT — SMART restore/boost.
      - If value < 0 dB → restore to 0 dB
      - If value ≥ 0 dB + Mid/High → add 15% of remaining headroom (asymptotic)
      - If value ≥ 0 dB + LOW (bass) → BLOCKED (safety, no action)
    """
    with _lock:
        current = state["eq_macro_values"][band]
        band_name = EQ_MACRO_NAMES_EXPECTED[band]

    if current < EQ_NEUTRAL_MACRO - 0.5:
        # Below neutral → restore to 0 dB
        start_eq_ramp(band, EQ_NEUTRAL_MACRO, flick_duration_s)
        with _lock:
            state["last_action"] = f"↑ {band_name} restored (0 dB)"
    elif band == EQ_SLOT_LOW:
        # Bass + at/above neutral → blocked for speaker/listener safety
        with _lock:
            state["last_action"] = "🚫 Bass boost blocked (use stick for safe +2 dB)"
    else:
        # Mid/High + at/above neutral → +15% of remaining headroom
        remaining = EQ_MACRO_MAX - current
        boost = remaining * EQ_BOOST_PCT
        target = clamp(current + boost, EQ_NEUTRAL_MACRO, EQ_MACRO_MAX)
        start_eq_ramp(band, target, flick_duration_s)
        with _lock:
            state["last_action"] = f"↑ {band_name} boosted (+{boost:.2f} macro)"

# ── X GESTURE STATE MACHINE (value actions in v9.9) ──

def update_eq_x_gesture(stick_x, now):
    """
    v9.9 — X axis double-flick detection for VALUE actions.
    LEFT  → eq_action_kill (smart: normalize if above 0 dB, kill if at/below)
    RIGHT → eq_action_boost_or_restore

    Returns True if gesture in progress (caller pauses encoder).
    """
    with _lock:
        gesture_state = state["_eq_flick_x_state"]
        gesture_dir   = state["_eq_flick_x_dir"]
        gesture_time  = state["_eq_flick_x_time"]
        selected_band = state["eq_selected_band"]
        timeout_s     = EQ_FLICK_TIMEOUT_MS / 1000.0

    abs_x = abs(stick_x)
    dir_x = 1 if stick_x > 0 else (-1 if stick_x < 0 else 0)

    if gesture_state == "idle":
        if abs_x >= EQ_FLICK_EXTREME:
            with _lock:
                state["_eq_flick_x_state"] = "flicked"
                state["_eq_flick_x_dir"]   = dir_x
                state["_eq_flick_x_time"]  = now
                state["eq_armed_band"]     = selected_band
                state["eq_armed_until"]    = now + timeout_s
            band_name = EQ_MACRO_NAMES_EXPECTED[selected_band]
            arrow = "→ boost/restore" if dir_x > 0 else "← cut/normalize"
            with _lock:
                state["last_action"] = f"◇ {band_name} {arrow} armed"
            return True

    elif gesture_state == "flicked":
        if abs_x < EQ_FLICK_RETURN:
            with _lock:
                state["_eq_flick_x_state"] = "returned"
                state["_eq_flick_x_returned_time"] = now
            return True
        elif (now - gesture_time) > timeout_s:
            with _lock:
                state["_eq_flick_x_state"] = "idle"
                state["_eq_flick_x_dir"]   = 0
                state["eq_armed_band"]     = -1
                state["last_action"] = "✗ EQ action timeout"
            return False
        return True

    elif gesture_state == "returned":
        if abs_x >= EQ_FLICK_EXTREME and dir_x == gesture_dir:
            # Double-flick confirmed!
            flick_duration = now - gesture_time
            if gesture_dir < 0:
                eq_action_kill(selected_band, flick_duration)
            else:
                eq_action_boost_or_restore(selected_band, flick_duration)
            with _lock:
                state["_eq_flick_x_state"] = "idle"
                state["_eq_flick_x_dir"]   = 0
                state["eq_armed_band"]     = -1
            return True
        elif (now - gesture_time) > timeout_s:
            with _lock:
                state["_eq_flick_x_state"] = "idle"
                state["_eq_flick_x_dir"]   = 0
                state["eq_armed_band"]     = -1
                state["last_action"] = "✗ EQ action timeout"
            return False
        return True

    return False

# ── BAND NAVIGATION VIA Y AXIS (hold-to-switch, Option D) ──

def update_eq_y_gesture_v911(stick_y, now):
    """
    v9.11 — Y axis double-flick BAND NAVIGATION (replaces hold-to-switch).

    Pattern: extreme → center → extreme (same direction) → SWITCH band.

    UP (positive Y)   → next band UP    (MID→HIGH→LOW→MID loop, no borders)
    DOWN (negative Y) → next band DOWN  (MID→LOW→HIGH→MID loop, no borders)

    During first flick, the target band lights up amber (armed).
    Failed flick or timeout → reset, no action.

    Returns True if gesture in progress (caller should freeze X encoder).
    """
    with _lock:
        gesture_state = state["_eq_flick_y_state"]
        gesture_dir   = state["_eq_flick_y_dir"]
        gesture_time  = state["_eq_flick_y_time"]
        selected_band = state["eq_selected_band"]
        timeout_s     = EQ_FLICK_TIMEOUT_MS / 1000.0

    abs_y = abs(stick_y)
    dir_y = 1 if stick_y > 0 else (-1 if stick_y < 0 else 0)

    if gesture_state == "idle":
        if abs_y >= EQ_FLICK_EXTREME:
            # First flick detected — arm target band
            target_band = (selected_band + dir_y) % 3
            with _lock:
                state["_eq_flick_y_state"] = "flicked"
                state["_eq_flick_y_dir"]   = dir_y
                state["_eq_flick_y_time"]  = now
                state["eq_armed_band"]     = target_band
                state["eq_armed_until"]    = now + timeout_s
            band_name = EQ_MACRO_NAMES_EXPECTED[target_band]
            arrow = "↑" if dir_y > 0 else "↓"
            with _lock:
                state["last_action"] = f"◇ {arrow} {band_name} armed (flick again)"
            return True

    elif gesture_state == "flicked":
        if abs_y < EQ_FLICK_RETURN:
            # Returned to center — waiting for second flick
            with _lock:
                state["_eq_flick_y_state"] = "returned"
                state["_eq_flick_y_returned_time"] = now
            return True
        elif (now - gesture_time) > timeout_s:
            # Timeout — abort
            with _lock:
                state["_eq_flick_y_state"] = "idle"
                state["_eq_flick_y_dir"]   = 0
                state["eq_armed_band"]     = -1
                state["last_action"] = "✗ Band switch timeout"
            return False
        return True

    elif gesture_state == "returned":
        if abs_y >= EQ_FLICK_EXTREME and dir_y == gesture_dir:
            # Second flick confirmed — switch band!
            eq_switch_band(gesture_dir)
            with _lock:
                state["_eq_flick_y_state"] = "idle"
                state["_eq_flick_y_dir"]   = 0
                state["eq_armed_band"]     = -1
            return True
        elif (now - gesture_time) > timeout_s:
            with _lock:
                state["_eq_flick_y_state"] = "idle"
                state["_eq_flick_y_dir"]   = 0
                state["eq_armed_band"]     = -1
                state["last_action"] = "✗ Band switch timeout"
            return False
        return True

    return False

# ── ENCODER-STYLE CONTINUOUS CONTROL (X axis in v9.9) ──

def eq_drive_continuous_encoder(stick_x, now):
    """
    v9.9 — Encoder-style EQ control via X axis.

    Right = boost (positive delta), Left = cut (negative delta).
    Release = value HOLDS at current position.

    Includes sticky 0 dB detent: slows down when crossing neutral.
    """
    with _lock:
        selected_band = state["eq_selected_band"]
        current_val   = state["eq_macro_values"][selected_band]
        last_tick     = state["_eq_encoder_last_tick"]
        last_at       = state["_eq_last_write_at"][selected_band]
        last_val      = state["_eq_last_write_val"][selected_band]

    if last_tick <= 0.0:
        dt = 0.0
    else:
        dt = now - last_tick
        if dt > 0.1:
            dt = 0.0

    with _lock:
        state["_eq_encoder_last_tick"] = now

    if abs(stick_x) < EQ_AXIS_DEAD_ZONE:
        return
    if dt <= 0.0:
        return

    delta = eq_encoder_delta(stick_x, dt)
    if delta == 0.0:
        return

    # Sticky 0 dB detent — slow down near neutral
    distance_from_neutral = abs(current_val - EQ_NEUTRAL_MACRO)
    if distance_from_neutral < EQ_DETENT_RANGE:
        detent_factor = distance_from_neutral / EQ_DETENT_RANGE
        delta *= max(EQ_DETENT_MIN_FACTOR, detent_factor)

    new_val = current_val + delta

    is_bass = (selected_band == EQ_SLOT_LOW)
    upper_cap = EQ_BASS_BOOST_CAP if is_bass else EQ_MACRO_MAX
    new_val = clamp(new_val, EQ_MACRO_MIN, upper_cap)

    if (now - last_at) < EQ_WRITE_THROTTLE:
        return
    if abs(new_val - last_val) < 0.3:
        return

    with _lock:
        state["eq_macro_values"][selected_band]    = new_val
        state["_eq_last_write_at"][selected_band]  = now
        state["_eq_last_write_val"][selected_band] = new_val

    osc_set_eq_macro(selected_band, new_val)

# ═══════════════════════════════════════════════════════════════════════════
#  CONTROLLER WATCHDOG
# ═══════════════════════════════════════════════════════════════════════════

def soft_check_controller():
    ctrl = _get_controller_handle()
    if ctrl is None:
        return False
    try:
        if pygame.joystick.get_count() < 1:
            return False
        if not ctrl.get_init():
            return False
        _ = ctrl.get_numaxes()
        return True
    except Exception:
        return False

def reprobe_controller(reason="watchdog"):
    try:
        pygame.joystick.quit()
        pygame.joystick.init()

        n = pygame.joystick.get_count()
        if n == 0:
            _set_controller_handle(None)
            with _lock:
                was_connected = state["controller_connected"]
                state["controller_connected"] = False
                state["controller_name"]      = "—"
                state["_last_reprobe"]        = time.perf_counter()
            if was_connected:
                print(f"  ⚠  Controller LOST ({reason})")
            return None

        ctrl = pygame.joystick.Joystick(0)
        ctrl.init()
        name = ctrl.get_name()
        _set_controller_handle(ctrl)
        with _lock:
            was_connected = state["controller_connected"]
            state["controller_connected"] = True
            state["controller_name"]      = name
            state["_last_input_at"]       = time.perf_counter()
            state["_last_reprobe"]        = time.perf_counter()

        if not was_connected:
            print(f"  ✅ Controller FOUND: {name}  ({reason})")
        return ctrl

    except Exception as e:
        _set_controller_handle(None)
        with _lock:
            state["controller_connected"] = False
            state["controller_name"]      = "—"
            state["_last_reprobe"]        = time.perf_counter()
        print(f"  ⚠  Controller re-probe error ({reason}): {e}")
        return None

def watchdog_loop():
    while True:
        try:
            time.sleep(WATCHDOG_INTERVAL)
            now = time.perf_counter()

            with _lock:
                connected      = state["controller_connected"]
                last_input_at  = state["_last_input_at"]
                last_reprobe   = state["_last_reprobe"]

            if not connected:
                reprobe_controller(reason="auto-retry")
                continue

            if last_input_at == 0.0:
                continue

            idle_for         = now - last_input_at
            since_last_probe = now - last_reprobe

            if idle_for >= IDLE_REPROBE_AFTER and since_last_probe >= IDLE_REPROBE_AFTER:
                if soft_check_controller():
                    with _lock:
                        state["_last_reprobe"] = now
                else:
                    print(f"  ⚠  Soft check failed after {idle_for:.1f}s idle — full reprobe")
                    reprobe_controller(reason=f"silent disconnect ({idle_for:.1f}s idle)")

        except Exception as e:
            print(f"  ⚠  Watchdog error: {e}")
            time.sleep(1.0)

# ═══════════════════════════════════════════════════════════════════════════
#  SELECT BUTTON SAFETY RECONCILIATION
# ═══════════════════════════════════════════════════════════════════════════

def reconcile_select_state(controller):
    """Force-release SELECT if a ghost button-up event was dropped."""
    if controller is None:
        return
    now = time.perf_counter()
    with _lock:
        last_check = state["_last_select_reconcile"]
    if now - last_check < SELECT_RECONCILE_INTERVAL:
        return
    with _lock:
        state["_last_select_reconcile"] = now

    try:
        physical_select = bool(controller.get_button(BTN_SELECT))
    except Exception:
        return

    with _lock:
        software_select = state["select_held"]

    if software_select and not physical_select:
        with _lock:
            state["select_held"] = False
            state["last_action"] = "SELECT auto-released (ghost detected)"
        print("  ⚠  SELECT ghost release detected — force-cleared")

# ═══════════════════════════════════════════════════════════════════════════
#  BUTTON HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

def handle_button_down(button):
    with _lock:
        l1_held     = state["l1_held"]
        select_held = state["select_held"]
        fx_track    = state["fx_track_index"]

    # FX-LAYER MOMENTARY EFFECTS
    if l1_held:
        if button == BTN_CROSS:
            momentary_stutter_on()
            return
        if button == BTN_CIRCLE:
            momentary_bass_cut_on()
            return
        if button == BTN_TRIANGLE:
            action_launch_scene()
            return
        if button == BTN_SQUARE:
            momentary_fx_throw_on()
            return
        if button == BTN_L3:
            action_toggle_filter_lock()
            return
        if button == BTN_R3:
            action_toggle_wet_lock()
            return

    # SELECT + R1: save baseline
    if select_held and button == BTN_R1:
        action_save_baseline()
        return

    # SELECT + R3: volume mute toggle
    if select_held and button == BTN_R3:
        action_volume_mute_toggle()
        return

    # R3 alone in nav layer: toggle EQ mode
    if not l1_held and not select_held and button == BTN_R3:
        action_toggle_eq_mode()
        return

    # NORMAL NAV-LAYER BUTTONS
    if   button == BTN_CROSS:    action_launch_clip()
    elif button == BTN_CIRCLE:   action_stop_clip()
    elif button == BTN_TRIANGLE: action_launch_scene()
    elif button == BTN_SQUARE:   action_arm_track()
    elif button == BTN_L2:       action_stop_track()
    elif button == BTN_L1:
        with _lock:
            state["l1_held"]     = True
            state["_pre_l1_track"] = state["track"]
            state["last_action"] = "⚡ FX mode ON  →  view: ~ FX Macros"
        if fx_track >= 0:
            osc_select_track(fx_track)
    elif button == BTN_R2:
        with _lock:
            state["r2_held"]     = True
            state["last_action"] = "🔒 Safety ON"
    elif button == BTN_SELECT:
        with _lock:
            state["select_held"] = True
            state["last_action"] = "SELECT held"
    elif button == BTN_START:
        if select_held:
            action_force_refresh()
        else:
            action_transport_toggle()

def handle_button_up(button):
    if button == BTN_CROSS:
        momentary_stutter_off()
        return
    if button == BTN_CIRCLE:
        momentary_bass_cut_off()
        return
    if button == BTN_SQUARE:
        momentary_fx_throw_off()
        return

    if button == BTN_R2:
        with _lock:
            state["r2_held"]     = False
            state["last_action"] = "🔒 Safety OFF"
    elif button == BTN_SELECT:
        with _lock:
            state["select_held"] = False
            state["last_action"] = "SELECT off"
    elif button == BTN_L1:
        with _lock:
            state["l1_held"]     = False
            return_to = state["_pre_l1_track"]
            state["_pre_l1_track"] = -1
            state["last_action"] = "⚡ FX mode OFF — recovering…"

        force_off_all_momentaries()
        reset_accel_state()
        fx_recover_on_l1_release()

        if return_to >= 0:
            osc_select_track(return_to)

# ═══════════════════════════════════════════════════════════════════════════
#  FX MACRO STICK CONTROL
# ═══════════════════════════════════════════════════════════════════════════

def _fx_get_slot_info(slot):
    with _lock:
        if not state["fx_ready"]:
            return None
        if slot < 0 or slot >= 8:
            return None
        name = state["fx_macro_names"][slot]
        if not name:
            return None
        val      = state["fx_macro_values"][slot]
        min_val  = state["fx_macro_mins"][slot]
        max_val  = state["fx_macro_maxs"][slot]
    sweep = FX_SWEEP_SECONDS.get(name, 3.0)
    return name, val, min_val, max_val, sweep

def fx_drive_macro(slot, stick_value, dt, accel_mult=1.0):
    if abs(stick_value) < FX_AXIS_DEAD_ZONE:
        return
    if is_macro_under_momentary_control(slot):
        return

    info = _fx_get_slot_info(slot)
    if info is None:
        return
    name, current, min_val, max_val, sweep_s = info

    macro_range = max_val - min_val
    if macro_range <= 0 or sweep_s <= 0:
        return

    delta = stick_value * (macro_range / sweep_s) * dt * accel_mult
    target = clamp(current + delta, min_val, max_val)

    now = time.perf_counter()
    with _lock:
        last_at  = state["_fx_last_write_at"][slot]
        last_val = state["_fx_last_write_val"][slot]

    if abs(target - last_val) < macro_range * FX_WRITE_EPSILON_FRAC:
        return
    if (now - last_at) < FX_WRITE_THROTTLE:
        return

    with _lock:
        state["fx_macro_values"][slot]    = target
        state["_fx_last_write_at"][slot]  = now
        state["_fx_last_write_val"][slot] = target
        state["_fx_active_slot"]          = slot
        state["_fx_active_until"]         = now + 0.4
        state["last_action"] = f"⚡ {name}"

    osc_set_fx_macro(slot, target)

def fx_step_delay_fb(direction):
    now = time.perf_counter()
    with _lock:
        if now - state["_fx_last_dpad_h"] < FX_DELAY_FB_DEBOUNCE:
            return
        state["_fx_last_dpad_h"] = now

    info = _fx_get_slot_info(FX_SLOT_DELAY_FB)
    if info is None:
        return
    name, current, min_val, max_val, _ = info

    macro_range = max_val - min_val
    if macro_range <= 0:
        return

    step_size = macro_range / FX_DELAY_FB_STEPS
    current_step = round((current - min_val) / step_size)
    new_step     = clamp(current_step + direction, 0, FX_DELAY_FB_STEPS)
    target       = min_val + new_step * step_size

    cap = min_val + macro_range * FX_DELAY_FB_CLAMP_FRAC
    capped = False
    if target > cap:
        target = cap
        capped = True

    target = clamp(target, min_val, max_val)

    if abs(target - current) < macro_range * FX_WRITE_EPSILON_FRAC:
        with _lock:
            state["last_action"] = f"⚠ Delay FB at {'MAX (capped 92%)' if direction > 0 else 'MIN'}"
        return

    with _lock:
        state["fx_macro_values"][FX_SLOT_DELAY_FB]    = target
        state["_fx_last_write_at"][FX_SLOT_DELAY_FB]  = now
        state["_fx_last_write_val"][FX_SLOT_DELAY_FB] = target
        state["_fx_active_slot"]                      = FX_SLOT_DELAY_FB
        state["_fx_active_until"]                     = now + 0.4
        cap_note = "  (capped 92%)" if capped else ""
        state["last_action"] = (
            f"⚡ Delay FB {'→' if direction > 0 else '←'}  "
            f"step {new_step}/{FX_DELAY_FB_STEPS}{cap_note}"
        )

    osc_set_fx_macro(FX_SLOT_DELAY_FB, target)

# ═══════════════════════════════════════════════════════════════════════════
#  AXIS HANDLERS
# ═══════════════════════════════════════════════════════════════════════════

_axis_last_tick = 0.0

def handle_axes_navigation(controller):
    global _smoothed_lx, _smoothed_ly
    now = time.perf_counter()

    _smoothed_lx = smooth_axis(_smoothed_lx, controller.get_axis(AXIS_LEFT_X))
    _smoothed_ly = smooth_axis(_smoothed_ly, controller.get_axis(AXIS_LEFT_Y))
    lx = hybrid_curve(_smoothed_lx)
    ly = hybrid_curve(_smoothed_ly)

    dir_x = 1 if lx > ANALOG_THRESHOLD else (-1 if lx < -ANALOG_THRESHOLD else 0)
    with _lock:
        last_dir_x    = state["_lx_last_dir"]
        held_since_x  = state["_lx_held_since"]
        last_repeat_x = state["_lx_last_repeat"]

    if dir_x != last_dir_x:
        with _lock:
            state["_lx_last_dir"]    = dir_x
            state["_lx_held_since"]  = now if dir_x != 0 else 0.0
            state["_lx_last_repeat"] = now
        if dir_x != 0:
            navigate_track(dir_x)
    elif dir_x != 0:
        if (now - held_since_x  >= HOLD_SCROLL_DELAY and
                now - last_repeat_x >= HOLD_SCROLL_RATE):
            navigate_track(dir_x)
            with _lock:
                state["_lx_last_repeat"] = now

    dir_y = 1 if ly > ANALOG_THRESHOLD else (-1 if ly < -ANALOG_THRESHOLD else 0)
    with _lock:
        last_dir_y    = state["_ly_last_dir"]
        held_since_y  = state["_ly_held_since"]
        last_repeat_y = state["_ly_last_repeat"]

    if dir_y != last_dir_y:
        with _lock:
            state["_ly_last_dir"]    = dir_y
            state["_ly_held_since"]  = now if dir_y != 0 else 0.0
            state["_ly_last_repeat"] = now
        if dir_y != 0:
            navigate_scene(dir_y)
    elif dir_y != 0:
        if (now - held_since_y  >= HOLD_SCROLL_DELAY and
                now - last_repeat_y >= HOLD_SCROLL_RATE):
            navigate_scene(dir_y)
            with _lock:
                state["_ly_last_repeat"] = now

def handle_axes_fx(controller, dt):
    global _smoothed_lx, _smoothed_ly, _smoothed_rx, _smoothed_ry

    now = time.perf_counter()

    raw_lx = controller.get_axis(AXIS_LEFT_X)
    raw_ly = controller.get_axis(AXIS_LEFT_Y)
    raw_rx = controller.get_axis(AXIS_RIGHT_X)
    raw_ry = controller.get_axis(AXIS_RIGHT_Y)

    _smoothed_lx = smooth_axis(_smoothed_lx, raw_lx)
    _smoothed_ly = smooth_axis(_smoothed_ly, raw_ly)
    _smoothed_rx = smooth_axis(_smoothed_rx, raw_rx)
    _smoothed_ry = smooth_axis(_smoothed_ry, raw_ry)

    lx = hybrid_curve(_smoothed_lx)
    ly = -hybrid_curve(_smoothed_ly)
    rx = hybrid_curve(_smoothed_rx)
    ry = hybrid_curve(_smoothed_ry)

    if RIGHT_STICK_ROTATED_90:
        fx_send_input    = -rx
        reverb_size_input = ry
        fx_send_dir = 1 if fx_send_input > FX_AXIS_DEAD_ZONE else \
                      (-1 if fx_send_input < -FX_AXIS_DEAD_ZONE else 0)
        rev_size_dir = 1 if reverb_size_input > FX_AXIS_DEAD_ZONE else \
                       (-1 if reverb_size_input < -FX_AXIS_DEAD_ZONE else 0)
        accel_fxsend  = compute_accel_multiplier("rx", fx_send_dir, now)
        accel_revsize = compute_accel_multiplier("ry", rev_size_dir, now)
    else:
        fx_send_input    = -ry
        reverb_size_input = rx
        fx_send_dir = 1 if fx_send_input > FX_AXIS_DEAD_ZONE else \
                      (-1 if fx_send_input < -FX_AXIS_DEAD_ZONE else 0)
        rev_size_dir = 1 if reverb_size_input > FX_AXIS_DEAD_ZONE else \
                       (-1 if reverb_size_input < -FX_AXIS_DEAD_ZONE else 0)
        accel_fxsend  = compute_accel_multiplier("ry", fx_send_dir, now)
        accel_revsize = compute_accel_multiplier("rx", rev_size_dir, now)

    lx_dir = 1 if lx > FX_AXIS_DEAD_ZONE else (-1 if lx < -FX_AXIS_DEAD_ZONE else 0)
    ly_dir = 1 if ly > FX_AXIS_DEAD_ZONE else (-1 if ly < -FX_AXIS_DEAD_ZONE else 0)
    accel_lx = compute_accel_multiplier("lx", lx_dir, now)
    accel_ly = compute_accel_multiplier("ly", ly_dir, now)

    fx_drive_macro(FX_SLOT_FILTER_FREQ,  ly,                dt, accel_ly)
    fx_drive_macro(FX_SLOT_FILTER_RES,   lx,                dt, accel_lx)
    fx_drive_macro(FX_SLOT_FX_SEND,      fx_send_input,     dt, accel_fxsend)
    fx_drive_macro(FX_SLOT_REVERB_SIZE,  reverb_size_input, dt, accel_revsize)

def handle_axes_eq(controller, dt):
    """
    v9.11 — EQ mode axis handling.

    Y axis (up/down): DOUBLE-FLICK to switch band (mirrors X gesture pattern)
                      UP   → next band up (HIGH direction, wraps)
                      DOWN → next band down (LOW direction, wraps)
    X axis (left/right): ENCODER (continuous value control) + double-flick actions
                         RIGHT held → boost
                         LEFT  held → cut
                         RIGHT 2x   → restore/boost-15%
                         LEFT  2x   → kill/normalize

    Y gesture FREEZES X encoder during the entire double-flick window.
    Axis dominance suppression prevents accidental cross-axis triggers.

    Right stick is physically rotated 90°.
    """
    global _smoothed_eq_rx, _smoothed_eq_ry

    now = time.perf_counter()

    raw_rx = controller.get_axis(AXIS_RIGHT_X)
    raw_ry = controller.get_axis(AXIS_RIGHT_Y)

    _smoothed_eq_rx = smooth_axis(_smoothed_eq_rx, raw_rx, factor=EQ_SMOOTHING_FACTOR)
    _smoothed_eq_ry = smooth_axis(_smoothed_eq_ry, raw_ry, factor=EQ_SMOOTHING_FACTOR)

    rx_curved = hybrid_curve(_smoothed_eq_rx)
    ry_curved = hybrid_curve(_smoothed_eq_ry)

    # Physical rotation correction
    if RIGHT_STICK_ROTATED_90:
        eq_y_input = -rx_curved   # physical up/down → Y axis (band switch)
        eq_x_input =  ry_curved   # physical left/right → X axis (value)
    else:
        eq_y_input = -ry_curved
        eq_x_input =  rx_curved

    # 1. Process Y double-flick gesture (band navigation)
    y_in_gesture = update_eq_y_gesture_v911(eq_y_input, now)

    # 2. AXIS-DOMINANCE SUPPRESSION
    abs_x = abs(eq_x_input)
    abs_y = abs(eq_y_input)
    y_dominates = (abs_y > EQ_AXIS_DEAD_ZONE and
                   abs_y > abs_x * EQ_DOMINANCE_RATIO)

    if y_in_gesture or y_dominates:
        # Y gesture active OR Y is dominating → freeze X encoder
        # Also cancel any pending X gesture so we don't double-trigger
        with _lock:
            state["_eq_encoder_last_tick"] = now
            if y_in_gesture:
                state["_eq_flick_x_state"] = "idle"
                state["_eq_flick_x_dir"]   = 0
        return

    # 3. Process X double-flick gesture (value actions)
    x_in_gesture = update_eq_x_gesture(eq_x_input, now)

    # 4. Continuous encoder (only if no X gesture is active)
    if not x_in_gesture:
        eq_drive_continuous_encoder(eq_x_input, now)
    else:
        with _lock:
            state["_eq_encoder_last_tick"] = now
def handle_right_joystick_volume(controller):
    global _smoothed_ry
    with _lock:
        if not state["select_held"]:
            return

    _smoothed_ry = smooth_axis(_smoothed_ry, controller.get_axis(AXIS_RIGHT_Y))
    ry  = hybrid_curve(_smoothed_ry)
    now = time.perf_counter()

    if abs(ry) < VOL_DEAD_ZONE:
        return

    delta = -ry * VOL_SENSITIVITY
    should_send = False

    with _lock:
        new_vol = clamp(ableton["track_volume"] + delta, VOL_MIN, VOL_MAX)
        if new_vol == ableton["track_volume"]:
            return
        ableton["track_volume"] = new_vol
        if (now - state["_vol_last_sent"] > 0.02 and
                abs(new_vol - state["_vol_last_value"]) > VOL_CHANGE_THRESHOLD):
            state["_vol_last_sent"]  = now
            state["_vol_last_value"] = new_vol
            should_send = True
        state["last_action"] = f"Vol  {db_from_vol(new_vol)}"

    if should_send:
        osc_set_volume(new_vol)

def handle_dpad(controller):
    """D-pad routing: Nav layer = U/D bookmarks + L/R groups; FX layer = U/D bookmarks + L/R Delay FB."""
    if controller.get_numhats() == 0:
        return
    h, v = controller.get_hat(0)

    with _lock:
        l1     = state["l1_held"]
        r2_hld = state["r2_held"]

    if l1:
        if   v == 1:  navigate_bookmark(-1)
        elif v == -1: navigate_bookmark(+1)
        if   h == 1:  fx_step_delay_fb(+1)
        elif h == -1: fx_step_delay_fb(-1)
        return

    if   v == 1:  navigate_bookmark(-1)
    elif v == -1: navigate_bookmark(+1)
    if   h == 1:  navigate_track_group(+1, force_lead=r2_hld)
    elif h == -1: navigate_track_group(-1, force_lead=r2_hld)

# ═══════════════════════════════════════════════════════════════════════════
#  CONTROLLER THREAD
# ═══════════════════════════════════════════════════════════════════════════

def controller_loop():
    global _axis_last_tick
    try:
        pygame.init()
    except Exception as e:
        print(f"  ⚠  pygame init error: {e}")

    reprobe_controller(reason="startup")
    _axis_last_tick = time.perf_counter()

    while True:
        ctrl = _get_controller_handle()

        if ctrl is None:
            time.sleep(0.2)
            _axis_last_tick = time.perf_counter()
            continue

        try:
            for event in pygame.event.get():
                if event.type in (pygame.JOYBUTTONDOWN,
                                  pygame.JOYBUTTONUP,
                                  pygame.JOYHATMOTION,
                                  pygame.JOYAXISMOTION,
                                  pygame.JOYBALLMOTION):
                    mark_controller_input()

                if event.type == pygame.JOYBUTTONDOWN:
                    handle_button_down(event.button)
                elif event.type == pygame.JOYBUTTONUP:
                    handle_button_up(event.button)
                elif event.type == pygame.JOYDEVICEREMOVED:
                    _set_controller_handle(None)
                    with _lock:
                        state["controller_connected"] = False
                        state["controller_name"]      = "—"

            ctrl = _get_controller_handle()
            if ctrl is None:
                continue

            reconcile_select_state(ctrl)

            now = time.perf_counter()
            dt = now - _axis_last_tick
            _axis_last_tick = now
            if dt > 0.5:
                dt = 0.0

            with _lock:
                l1 = state["l1_held"]
                select_held = state["select_held"]
                eq_mode = state["eq_mode_active"]

            # Right-stick priority:
            # 1. L1 → FX layer
            # 2. SELECT → volume control
            # 3. EQ mode → EQ control
            # 4. Default → nothing

            if l1:
                handle_axes_fx(ctrl, dt)
            else:
                handle_axes_navigation(ctrl)

                if select_held:
                    handle_right_joystick_volume(ctrl)
                elif eq_mode:
                    handle_axes_eq(ctrl, dt)

            handle_dpad(ctrl)
            clear_flashes_if_expired()
            pygame.time.wait(8)

        except Exception as e:
            print(f"  ⚠  Controller loop error: {e}")
            _set_controller_handle(None)
            with _lock:
                state["controller_connected"] = False
                state["controller_name"]      = "—"
            time.sleep(0.3)

    # ═══════════════════════════════════════════════════════════════════════════
#  COLOUR PALETTE
# ═══════════════════════════════════════════════════════════════════════════

ABL_BG          = "#1f1f1f"
ABL_PANEL       = "#2c2c2c"
ABL_PANEL_DARK  = "#1a1a1a"
ABL_CELL        = "#252525"
ABL_CELL_ALT    = "#2a2a2a"
ABL_DIVIDER     = "#3a3a3a"

ABL_TEXT        = "#cfcfcf"
ABL_TEXT_DIM    = "#8a8a8a"
ABL_TEXT_FAINT  = "#5a5a5a"

ABL_ORANGE      = "#ff6c2c"
ABL_BLUE        = "#4a9eff"
ABL_YELLOW      = "#f4d22b"
ABL_GREEN       = "#65d96a"
ABL_RED         = "#ff3b30"
ABL_PURPLE      = "#b878dc"

BLINK_BG_BRIGHT = "#ff3b30"
BLINK_BG_DIM    = "#3a1818"

ABL_CELL_HOT    = "#3a3416"
ABL_CELL_REC    = "#1a3a1a"
ABL_CELL_LOCK   = "#2a2a3a"
ABL_CELL_MOMENT = "#3a1a1a"

# DJM-900 EQ palette (silver/white metallic)
EQ_KNOB_RING_OUTER   = "#0d0d0d"
EQ_KNOB_RING_DARK    = "#1a1a1a"
EQ_KNOB_BODY_DARK    = "#3a3a3a"
EQ_KNOB_BODY_MID     = "#5a5a5a"
EQ_KNOB_BODY_LIGHT   = "#8a8a8a"
EQ_KNOB_BODY_RIM     = "#2a2a2a"
EQ_KNOB_INDICATOR    = "#ffffff"
EQ_KNOB_DETENT       = "#cccccc"
EQ_KNOB_ARC_BG       = "#2a2a2a"
EQ_KNOB_ARC_ACTIVE   = "#dddddd"

EQ_GLOW_SELECTED     = "#454545"
EQ_GLOW_ARMED        = "#5a4a1a"

EQ_LABEL_COLOR       = "#cfcfcf"
EQ_LABEL_SELECTED    = "#ffffff"
EQ_LABEL_ARMED       = "#f4d22b"

EQ_BAND_COLORS = {
    EQ_SLOT_LOW:  EQ_LABEL_COLOR,
    EQ_SLOT_MID:  EQ_LABEL_COLOR,
    EQ_SLOT_HIGH: EQ_LABEL_COLOR,
}
EQ_SELECTED_BG = "#2c2c2c"
EQ_ARMED_BG    = "#3a3416"
EQ_MODE_BG     = "#2a1a2a"

# ═══════════════════════════════════════════════════════════════════════════
#  TYPOGRAPHY
# ═══════════════════════════════════════════════════════════════════════════

F_LABEL_TINY  = ("Segoe UI", 7,  "bold")
F_LABEL_SMALL = ("Segoe UI", 8,  "bold")
F_BODY        = ("Segoe UI", 9,  "normal")
F_BODY_BOLD   = ("Segoe UI", 9,  "bold")
F_VALUE       = ("Segoe UI", 9,  "bold")
F_VALUE_BIG   = ("Segoe UI", 12, "bold")
F_TITLE       = ("Segoe UI", 11, "bold")
F_TRACK_NAME  = ("Segoe UI", 13, "bold")
F_MONO        = ("Consolas", 9,  "bold")
F_EQ_BAND     = ("Segoe UI", 10, "bold")

# ═══════════════════════════════════════════════════════════════════════════
#  DIRTY-CACHE LABEL SETTER
# ═══════════════════════════════════════════════════════════════════════════

_ui_cache = {}

def set_label(widget, key, text, **kwargs):
    cache_key = (key, text, tuple(sorted(kwargs.items())))
    if _ui_cache.get(key) != cache_key:
        widget.config(text=text, **kwargs)
        _ui_cache[key] = cache_key

# ═══════════════════════════════════════════════════════════════════════════
#  FX KNOB DRAWING
# ═══════════════════════════════════════════════════════════════════════════

_knob_cache = {}

def draw_knob(canvas, slot, value_frac, color, active=False, locked=False, moment=False):
    cache_key = (round(value_frac, 3), color, active, locked, moment)
    if _knob_cache.get(slot) == cache_key:
        return
    _knob_cache[slot] = cache_key

    canvas.delete("all")

    pad = 4
    size = int(canvas['width']) - pad * 2
    cx = pad + size // 2
    cy = pad + size // 2
    r_outer = size // 2
    r_inner = max(4, r_outer - 5)

    canvas.create_arc(
        cx - r_outer, cy - r_outer,
        cx + r_outer, cy + r_outer,
        start=225, extent=-270,
        style="arc", outline=ABL_DIVIDER, width=2
    )

    if value_frac > 0:
        active_color = color
        if active:
            active_color = ABL_YELLOW
        elif moment:
            active_color = ABL_RED
        canvas.create_arc(
            cx - r_outer, cy - r_outer,
            cx + r_outer, cy + r_outer,
            start=225, extent=-(270 * value_frac),
            style="arc", outline=active_color, width=3
        )

    if moment:
        body_fill = ABL_CELL_MOMENT
        body_outline = ABL_RED
    elif locked:
        body_fill = ABL_CELL_LOCK
        body_outline = ABL_YELLOW
    elif active:
        body_fill = ABL_CELL_HOT
        body_outline = ABL_YELLOW
    else:
        body_fill = "#2a2a2a"
        body_outline = "#444444"

    canvas.create_oval(
        cx - r_inner, cy - r_inner,
        cx + r_inner, cy + r_inner,
        fill=body_fill, outline=body_outline
    )

    angle_deg = 225 - 270 * value_frac
    angle_rad = math.radians(angle_deg)
    ix = cx + r_inner * 0.75 * math.cos(angle_rad)
    iy = cy - r_inner * 0.75 * math.sin(angle_rad)
    indicator_color = color
    if moment:
        indicator_color = ABL_RED
    elif active:
        indicator_color = ABL_YELLOW
    canvas.create_line(cx, cy, ix, iy, fill=indicator_color, width=2)

# ═══════════════════════════════════════════════════════════════════════════
#  v9.9 EQ KNOB — DJM-900 STYLE WITH dB TICK LABELS
# ═══════════════════════════════════════════════════════════════════════════

_eq_knob_cache = {}

def draw_eq_knob(canvas, band_idx, visual_pos, selected=False, armed=False):
    """
    v9.9 — DJM-900 style EQ knob with dB tick labels around perimeter.
    visual_pos: 0.0 = far left (-inf dB), 0.5 = top (0 dB), 1.0 = far right (+6 dB)
    """
    cache_key = (round(visual_pos, 3), selected, armed)
    if _eq_knob_cache.get(band_idx) == cache_key:
        return
    _eq_knob_cache[band_idx] = cache_key

    canvas.delete("all")

    w = int(canvas['width'])
    h = int(canvas['height'])
    cx = w // 2
    cy = h // 2

    # Leave room for dB tick labels
    r_outer  = min(w, h) // 2 - 10
    r_ring   = r_outer - 2
    r_body1  = r_outer - 7
    r_body2  = r_outer - 11
    r_body3  = r_outer - 15
    r_cap    = max(3, r_outer - 20)

    # Outer shadow ring
    canvas.create_oval(
        cx - r_outer, cy - r_outer,
        cx + r_outer, cy + r_outer,
        fill=EQ_KNOB_RING_OUTER, outline=EQ_KNOB_RING_DARK, width=1
    )

    # Inactive background arc
    canvas.create_arc(
        cx - r_ring, cy - r_ring,
        cx + r_ring, cy + r_ring,
        start=225, extent=-270,
        style="arc", outline=EQ_KNOB_ARC_BG, width=2
    )

    # Active arc indicator
    if abs(visual_pos - 0.5) > 0.005:
        if visual_pos < 0.5:
            extent = (0.5 - visual_pos) * 270
            start_angle = 90
        else:
            extent = -(visual_pos - 0.5) * 270
            start_angle = 90
        canvas.create_arc(
            cx - r_ring, cy - r_ring,
            cx + r_ring, cy + r_ring,
            start=start_angle, extent=extent,
            style="arc", outline=EQ_KNOB_ARC_ACTIVE, width=2
        )

    # Perimeter tick marks every 30°
    for tick_angle_deg in range(225, -46, -30):
        tick_rad = math.radians(tick_angle_deg)
        outer_x = cx + (r_ring + 1) * math.cos(tick_rad)
        outer_y = cy - (r_ring + 1) * math.sin(tick_rad)
        inner_x = cx + (r_ring - 2) * math.cos(tick_rad)
        inner_y = cy - (r_ring - 2) * math.sin(tick_rad)
        canvas.create_line(inner_x, inner_y, outer_x, outer_y,
                           fill=EQ_KNOB_BODY_LIGHT, width=1)

    # Prominent center detent at 12 o'clock
    canvas.create_line(cx, cy - (r_ring + 2), cx, cy - (r_ring - 3),
                       fill=EQ_KNOB_DETENT, width=2)

    # dB tick labels around perimeter
    label_r = r_outer + 6
    # Bottom-left = -∞
    lx = cx + label_r * math.cos(math.radians(225))
    ly = cy - label_r * math.sin(math.radians(225))
    canvas.create_text(lx, ly, text="−∞", fill=EQ_KNOB_BODY_LIGHT,
                       font=("Segoe UI", 6, "bold"))
    # Top = 0
    canvas.create_text(cx, cy - label_r, text="0", fill=EQ_KNOB_DETENT,
                       font=("Segoe UI", 6, "bold"))
    # Bottom-right = +6
    rx = cx + label_r * math.cos(math.radians(-45))
    ry = cy - label_r * math.sin(math.radians(-45))
    canvas.create_text(rx, ry, text="+6", fill=EQ_KNOB_BODY_LIGHT,
                       font=("Segoe UI", 6, "bold"))

    # Metallic body layers
    canvas.create_oval(
        cx - r_body1, cy - r_body1,
        cx + r_body1, cy + r_body1,
        fill=EQ_KNOB_BODY_DARK, outline=EQ_KNOB_BODY_RIM, width=1
    )
    canvas.create_oval(
        cx - r_body2, cy - r_body2,
        cx + r_body2, cy + r_body2,
        fill=EQ_KNOB_BODY_MID, outline=""
    )

    # Selected/armed glow ring
    if armed:
        canvas.create_oval(
            cx - r_body2 - 1, cy - r_body2 - 1,
            cx + r_body2 + 1, cy + r_body2 + 1,
            outline=EQ_LABEL_ARMED, width=2
        )
    elif selected:
        canvas.create_oval(
            cx - r_body2 - 1, cy - r_body2 - 1,
            cx + r_body2 + 1, cy + r_body2 + 1,
            outline=EQ_LABEL_SELECTED, width=1
        )

    canvas.create_oval(
        cx - r_body3, cy - r_body3,
        cx + r_body3, cy + r_body3,
        fill=EQ_KNOB_BODY_LIGHT, outline=""
    )

    # White indicator line
    angle_deg = 225 - 270 * visual_pos
    angle_rad = math.radians(angle_deg)
    line_inner_x = cx + (r_cap + 1) * math.cos(angle_rad)
    line_inner_y = cy - (r_cap + 1) * math.sin(angle_rad)
    line_outer_x = cx + (r_body1 - 1) * math.cos(angle_rad)
    line_outer_y = cy - (r_body1 - 1) * math.sin(angle_rad)
    canvas.create_line(line_inner_x, line_inner_y,
                       line_outer_x, line_outer_y,
                       fill=EQ_KNOB_INDICATOR, width=3)

    # Center cap
    canvas.create_oval(
        cx - r_cap, cy - r_cap,
        cx + r_cap, cy + r_cap,
        fill=EQ_KNOB_BODY_DARK, outline=EQ_KNOB_BODY_RIM, width=1
    )

# ═══════════════════════════════════════════════════════════════════════════
#  v9.10 DJM-900 CHANNEL METER — big chunky LED bar with peak hold
# ═══════════════════════════════════════════════════════════════════════════

_channel_meter_cache = {}

def draw_channel_meter(canvas, level, peak_level):
    """
    v9.10 — DJM-900 style channel output meter.
    24 chunky LED segments, gradient green→yellow→red bottom to top.
    Peak indicator: single bright segment that hovers, then falls.

    level:      current audio level (0.0 to 1.0)
    peak_level: held peak (0.0 to 1.0)
    """
    cache_key = (round(level, 3), round(peak_level, 3))
    if _channel_meter_cache.get("k") == cache_key:
        return
    _channel_meter_cache["k"] = cache_key

    canvas.delete("all")

    w = int(canvas['width'])
    h = int(canvas['height'])

    total = EQ_METER_SEGMENTS
    gap   = 2
    seg_h = max(2.0, (h - (total - 1) * gap) / total)

    lit      = int(level * total)
    peak_seg = int(peak_level * total) - 1
    if peak_seg < 0:
        peak_seg = -1

    # Color per segment
    for i in range(total):
        seg_bottom = h - i * (seg_h + gap)
        seg_top    = seg_bottom - seg_h

        if i < EQ_METER_GREEN:
            on_color  = "#22dd44"
            off_color = "#0c1e10"
        elif i < EQ_METER_GREEN + EQ_METER_YELLOW:
            on_color  = "#eecc22"
            off_color = "#1e1e0c"
        else:
            on_color  = "#ee2222"
            off_color = "#1e0c0c"

        is_lit  = (i < lit)
        is_peak = (i == peak_seg and peak_level > 0.02)

        if is_peak:
            fill = "#ffffff"  # bright white peak indicator
        elif is_lit:
            fill = on_color
        else:
            fill = off_color

        canvas.create_rectangle(
            2, seg_top, w - 2, seg_bottom,
            fill=fill, outline="", width=0
        )

def update_meter_peak(current, last_peak, last_peak_time, now):
    """v9.10: peak hold + decay logic. Returns (new_peak, new_peak_time)."""
    if current >= last_peak:
        return current, now
    elapsed = now - last_peak_time
    if elapsed < EQ_METER_PEAK_HOLD_S:
        return last_peak, last_peak_time
    fall_elapsed = elapsed - EQ_METER_PEAK_HOLD_S
    decayed = last_peak - EQ_METER_PEAK_FALL * fall_elapsed
    if decayed < current:
        return current, now
    return max(decayed, 0.0), last_peak_time

# ═══════════════════════════════════════════════════════════════════════════
#  UI BUILD
# ═══════════════════════════════════════════════════════════════════════════

def hline(parent, colour=ABL_DIVIDER, pady=4):
    tk.Frame(parent, bg=colour, height=1).pack(fill="x", padx=10, pady=pady)

def build_ui(root):
    root.title(f"FX Machine v{VERSION}  —  MIRA___OFC / Modulated_OFC")
    root.configure(bg=ABL_BG)
    root.resizable(True, True)
    root.minsize(700, 850)
    root.attributes("-topmost", True)

    # ── HEADER ──
    hdr = tk.Frame(root, bg=ABL_PANEL_DARK)
    hdr.pack(fill="x")
    inner = tk.Frame(hdr, bg=ABL_PANEL_DARK)
    inner.pack(fill="x", padx=10, pady=6)
    tk.Label(inner, text="FX MACHINE",
             bg=ABL_PANEL_DARK, fg=ABL_TEXT,
             font=("Segoe UI", 11, "bold"), anchor="w").pack(side="left")
    tk.Label(inner, text=f"v{VERSION}",
             bg=ABL_PANEL_DARK, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, anchor="e").pack(side="right")
    tk.Frame(root, bg=ABL_BLUE, height=2).pack(fill="x")

    # ── TRANSPORT ──
    trow = tk.Frame(root, bg=ABL_BG)
    trow.pack(fill="x", padx=10, pady=(6, 0))
    lbl_playing = tk.Label(trow, text="■ STOPPED", bg=ABL_BG, fg=ABL_RED,
                           font=F_VALUE, anchor="w")
    lbl_playing.pack(side="left")
    lbl_bpm = tk.Label(trow, text="120.0 BPM", bg=ABL_BG, fg=ABL_TEXT,
                       font=F_MONO, anchor="e")
    lbl_bpm.pack(side="right")

    hline(root, pady=5)

    # ══════════════════════════════════════════════════════════
    #  TOP 2-COLUMN AREA: EQ + METER (left) | NAV INFO (right)
    # ══════════════════════════════════════════════════════════
    top_area = tk.Frame(root, bg=ABL_BG)
    top_area.pack(fill="x", padx=8)

    # ─────── LEFT COLUMN: EQ STACK + DJM CHANNEL METER ───────
    eq_section = tk.Frame(top_area, bg=ABL_BG)
    eq_section.pack(side="left", fill="y", padx=(0, 8))

    eq_title_row = tk.Frame(eq_section, bg=ABL_BG)
    eq_title_row.pack(fill="x", pady=(0, 2))
    lbl_eq_title = tk.Label(eq_title_row, text="◇ EQ",
                            bg=ABL_BG, fg=ABL_TEXT,
                            font=F_LABEL_SMALL, anchor="w")
    lbl_eq_title.pack(side="left")
    lbl_eq_track = tk.Label(eq_title_row, text="—",
                            bg=ABL_BG, fg=ABL_TEXT_DIM,
                            font=F_LABEL_TINY, anchor="e")
    lbl_eq_track.pack(side="right")

    # Framed container (border around EQ + meter)
    eq_glow = tk.Frame(eq_section, bg=EQ_KNOB_RING_DARK, padx=2, pady=2)
    eq_glow.pack(fill="y")
    eq_body = tk.Frame(eq_glow, bg=ABL_PANEL_DARK)
    eq_body.pack(fill="y")

    # ── Knobs sub-column (HIGH / MID / LOW vertical) ──
    knobs_col = tk.Frame(eq_body, bg=ABL_PANEL_DARK)
    knobs_col.pack(side="left", fill="y", padx=2, pady=2)

    EQ_KNOB_SIZE_V910 = 78
    eq_cells = [None, None, None]
    display_order  = [EQ_SLOT_HIGH, EQ_SLOT_MID, EQ_SLOT_LOW]
    display_labels = {EQ_SLOT_LOW: "LOW", EQ_SLOT_MID: "MID", EQ_SLOT_HIGH: "HIGH"}

    for band_idx in display_order:
        cell = tk.Frame(knobs_col, bg=ABL_CELL, padx=6, pady=4)
        cell.pack(fill="x", pady=1)

        name_lbl = tk.Label(cell, text=display_labels[band_idx],
                            bg=ABL_CELL, fg=EQ_LABEL_COLOR,
                            font=F_EQ_BAND, anchor="center")
        name_lbl.pack(fill="x", pady=(0, 2))

        canvas = tk.Canvas(cell, width=EQ_KNOB_SIZE_V910,
                           height=EQ_KNOB_SIZE_V910,
                           bg=ABL_CELL, highlightthickness=0)
        canvas.pack()

        value_lbl = tk.Label(cell, text="0.00 dB", bg=ABL_CELL,
                             fg=ABL_TEXT, font=F_VALUE, anchor="center")
        value_lbl.pack(fill="x", pady=(2, 0))

        eq_cells[band_idx] = (cell, canvas, name_lbl, value_lbl)

    # ── DJM CHANNEL METER sub-column (big single meter) ──
    meter_col = tk.Frame(eq_body, bg=ABL_PANEL_DARK, padx=4, pady=2)
    meter_col.pack(side="left", fill="y")

    tk.Label(meter_col, text="OUT", bg=ABL_PANEL_DARK,
             fg=ABL_TEXT_DIM, font=F_LABEL_TINY).pack(pady=(2, 4))

    # Meter height ≈ 3 knob cells stacked
    meter_h = (EQ_KNOB_SIZE_V910 + 38) * 3
    eq_channel_meter = tk.Canvas(meter_col, width=24, height=meter_h,
                                  bg="#0a0a0a", highlightthickness=0)
    eq_channel_meter.pack(pady=(0, 2))

    # ─────── RIGHT COLUMN: NAV INFO ───────
    nav_section = tk.Frame(top_area, bg=ABL_BG)
    nav_section.pack(side="left", fill="both", expand=True)

    # Bookmark row
    brow = tk.Frame(nav_section, bg=ABL_CELL, padx=8, pady=4)
    brow.pack(fill="x")
    tk.Label(brow, text="BMARK", bg=ABL_CELL, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, width=8, anchor="w").pack(side="left")
    lbl_bookmark = tk.Label(brow, text="—", bg=ABL_CELL, fg=ABL_YELLOW,
                            font=F_BODY_BOLD, anchor="w")
    lbl_bookmark.pack(side="left", fill="x", expand=True)
    lbl_bm_pos = tk.Label(brow, text="", bg=ABL_CELL, fg=ABL_TEXT_DIM,
                          font=F_BODY)
    lbl_bm_pos.pack(side="right")

    # Group row
    grow2 = tk.Frame(nav_section, bg=ABL_CELL_ALT, padx=8, pady=4)
    grow2.pack(fill="x", pady=(2, 0))
    tk.Label(grow2, text="GROUP", bg=ABL_CELL_ALT, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, width=8, anchor="w").pack(side="left")
    lbl_group = tk.Label(grow2, text="—", bg=ABL_CELL_ALT, fg=ABL_PURPLE,
                         font=F_BODY_BOLD, anchor="w")
    lbl_group.pack(side="left", fill="x", expand=True)
    lbl_group_pos = tk.Label(grow2, text="", bg=ABL_CELL_ALT,
                             fg=ABL_TEXT_DIM, font=F_BODY)
    lbl_group_pos.pack(side="right")

    # Track block
    track_block = tk.Frame(nav_section, bg=ABL_PANEL, padx=10, pady=4)
    track_block.pack(fill="x", pady=(4, 0))
    tk.Label(track_block, text="TRACK", bg=ABL_PANEL, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, anchor="w").pack(fill="x")
    lbl_track_name = tk.Label(track_block, text="—",
                              bg=ABL_PANEL, fg=ABL_TEXT,
                              font=F_TRACK_NAME, anchor="w")
    lbl_track_name.pack(fill="x")

    # Scene
    scene_block = tk.Frame(nav_section, bg=ABL_BG, padx=10)
    scene_block.pack(fill="x", pady=(2, 0))
    tk.Label(scene_block, text="SCENE", bg=ABL_BG, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, anchor="w").pack(fill="x")
    lbl_scene_name = tk.Label(scene_block, text="—", bg=ABL_BG, fg=ABL_TEXT,
                              font=F_TITLE, anchor="w")
    lbl_scene_name.pack(fill="x")

    # Clip
    clip_block = tk.Frame(nav_section, bg=ABL_BG, padx=10)
    clip_block.pack(fill="x", pady=(2, 0))
    tk.Label(clip_block, text="CLIP", bg=ABL_BG, fg=ABL_TEXT_DIM,
             font=F_LABEL_TINY, anchor="w").pack(fill="x")
    lbl_clip_name = tk.Label(clip_block, text="—", bg=ABL_BG, fg=ABL_BLUE,
                             font=F_BODY_BOLD, anchor="w")
    lbl_clip_name.pack(fill="x")

    # Number grid (Scene/Track/Bmark)
    grid = tk.Frame(nav_section, bg=ABL_BG)
    grid.pack(fill="x", pady=(4, 0))

    def pos_col(parent, label, col, color=ABL_TEXT):
        f = tk.Frame(parent, bg=ABL_CELL, padx=6, pady=4)
        f.grid(row=0, column=col, padx=2, sticky="ew")
        parent.columnconfigure(col, weight=1)
        tk.Label(f, text=label, bg=ABL_CELL, fg=ABL_TEXT_DIM,
                 font=F_LABEL_TINY).pack()
        val = tk.Label(f, text="1", bg=ABL_CELL, fg=color, font=F_VALUE_BIG)
        val.pack()
        return val

    lbl_scene_num = pos_col(grid, "SCENE", 0)
    lbl_track_num = pos_col(grid, "TRACK", 1)
    lbl_bm_num    = pos_col(grid, "BMARK", 2, ABL_YELLOW)

    # Volume row
    vrow = tk.Frame(nav_section, bg=ABL_BG)
    vrow.pack(fill="x", padx=2, pady=(6, 0))
    lbl_volume = tk.Label(vrow, text="+0.0 dB", bg=ABL_BG, fg=ABL_TEXT,
                          font=F_VALUE_BIG, anchor="w")
    lbl_volume.pack(side="left")
    lbl_vol_mode = tk.Label(vrow, text="SELECT+R-stick", bg=ABL_BG,
                            fg=ABL_TEXT_FAINT, font=F_LABEL_TINY, anchor="e")
    lbl_vol_mode.pack(side="right")

    # Stop button
    btn_stop = tk.Button(nav_section, text="■ STOP TRACK (L2)",
                         bg=ABL_PANEL, fg=ABL_RED, font=F_BODY_BOLD,
                         activebackground="#3a0000", activeforeground=ABL_RED,
                         relief="flat", bd=0, pady=4, cursor="hand2",
                         command=action_stop_track)
    btn_stop.pack(fill="x", pady=(4, 4))

    # Modifier pills
    mrow = tk.Frame(nav_section, bg=ABL_BG)
    mrow.pack(fill="x", pady=(0, 2))

    def pill(parent, text):
        lbl = tk.Label(parent, text=text, bg=ABL_PANEL, fg=ABL_TEXT_FAINT,
                       font=F_LABEL_TINY, padx=5, pady=3)
        lbl.pack(side="left", padx=(0, 2))
        return lbl

    lbl_r2     = pill(mrow, "R2 SAFE")
    lbl_select = pill(mrow, "SEL")
    lbl_start  = pill(mrow, "PLAY")
    lbl_l1     = pill(mrow, "L1 FX")
    lbl_eq_pill = pill(mrow, "◇ EQ")

    # EQ status line (small, under pills)
    lbl_eq_status = tk.Label(nav_section, text="EQ inactive (R3 to toggle)",
                             bg=ABL_BG, fg=ABL_TEXT_FAINT,
                             font=F_LABEL_TINY, anchor="w")
    lbl_eq_status.pack(fill="x", pady=(2, 0))

    hline(root, pady=6)

    # ══════════════════════════════════════════════════════════
    #  FX MACHINE PANEL (full width below)
    # ══════════════════════════════════════════════════════════
    fx_section = tk.Frame(root, bg=ABL_BG)
    fx_section.pack(fill="x", padx=8, pady=(0, 2))

    fx_title_row = tk.Frame(fx_section, bg=ABL_BG)
    fx_title_row.pack(fill="x", pady=(0, 1))
    lbl_fx_title = tk.Label(fx_title_row, text="⚡ FX MACHINE",
                            bg=ABL_BG, fg=ABL_TEXT,
                            font=F_LABEL_SMALL, anchor="w")
    lbl_fx_title.pack(side="left")
    lbl_fx_track = tk.Label(fx_title_row, text="—",
                            bg=ABL_BG, fg=ABL_TEXT_DIM,
                            font=F_LABEL_TINY, anchor="e")
    lbl_fx_track.pack(side="right")

    fx_status_row = tk.Frame(fx_section, bg=ABL_BG)
    fx_status_row.pack(fill="x", pady=(0, 2))
    lbl_baseline = tk.Label(fx_status_row, text="✗ no baseline",
                            bg=ABL_BG, fg=ABL_TEXT_FAINT,
                            font=F_LABEL_TINY, anchor="w")
    lbl_baseline.pack(side="left")
    lbl_lock_wet = tk.Label(fx_status_row, text="wet: free",
                            bg=ABL_BG, fg=ABL_TEXT_FAINT,
                            font=F_LABEL_TINY, anchor="e")
    lbl_lock_wet.pack(side="right", padx=(0, 4))
    lbl_lock_filter = tk.Label(fx_status_row, text="filter: free",
                               bg=ABL_BG, fg=ABL_TEXT_FAINT,
                               font=F_LABEL_TINY, anchor="e")
    lbl_lock_filter.pack(side="right", padx=(0, 4))

    fx_glow = tk.Frame(fx_section, bg=ABL_BG, padx=2, pady=2)
    fx_glow.pack(fill="x")
    fx_inner = tk.Frame(fx_glow, bg=ABL_BG)
    fx_inner.pack(fill="x")

    fx_cells = []
    KNOB_SIZE = 56

    def make_knob_cell(parent, row, col, accent):
        cell = tk.Frame(parent, bg=ABL_CELL, padx=2, pady=2)
        cell.grid(row=row, column=col, padx=1, pady=1, sticky="nsew")
        parent.columnconfigure(col, weight=1)

        tk.Frame(cell, bg=accent, height=2).pack(fill="x")

        canvas = tk.Canvas(cell, width=KNOB_SIZE, height=KNOB_SIZE,
                           bg=ABL_CELL, highlightthickness=0)
        canvas.pack(pady=(2, 1))

        name_lbl = tk.Label(cell, text="—", bg=ABL_CELL, fg=ABL_TEXT_DIM,
                            font=F_LABEL_TINY, anchor="center")
        name_lbl.pack(fill="x")
        value_lbl = tk.Label(cell, text="--", bg=ABL_CELL, fg=accent,
                             font=F_VALUE, anchor="center")
        value_lbl.pack(fill="x")

        return cell, canvas, name_lbl, value_lbl

    for col in range(4):
        fx_cells.append(make_knob_cell(fx_inner, 0, col, ABL_ORANGE))
    for col in range(4):
        fx_cells.append(make_knob_cell(fx_inner, 1, col, ABL_BLUE))

    hline(root, pady=4)

    # Bottom row
    bot_row = tk.Frame(root, bg=ABL_BG)
    bot_row.pack(fill="x", padx=8, pady=(0, 2))

    lbl_ctrl = tk.Label(bot_row, text="● NO CTRL",
                        bg=ABL_PANEL, fg=ABL_RED,
                        font=F_LABEL_TINY, padx=5, pady=3)
    lbl_ctrl.pack(side="left")

    tk.Button(bot_row, text="⟳ REFRESH",
              bg=ABL_PANEL, fg=ABL_BLUE, font=F_LABEL_TINY,
              activebackground="#002a2a", activeforeground=ABL_BLUE,
              relief="flat", bd=0, pady=3, padx=8, cursor="hand2",
              command=action_force_refresh).pack(side="right")

    hline(root, pady=3)
    lbl_action = tk.Label(root, text="System ready",
                          bg=ABL_BG, fg=ABL_TEXT_DIM,
                          font=F_BODY, anchor="w")
    lbl_action.pack(fill="x", padx=10, pady=(0, 2))

    footer = tk.Label(root,
                      text="MIRA___OFC  ·  Modulated_OFC  ·  © Ayoub Agoujdad",
                      bg=ABL_BG, fg=ABL_TEXT_FAINT,
                      font=("Segoe UI", 7, "normal"), anchor="center")
    footer.pack(fill="x", padx=10, pady=(0, 4))

    return {
        "playing":          lbl_playing,
        "bpm":              lbl_bpm,
        "bookmark":         lbl_bookmark,
        "bm_pos":           lbl_bm_pos,
        "group":            lbl_group,
        "group_pos":        lbl_group_pos,
        "track_block":      track_block,
        "track_name":       lbl_track_name,
        "scene_name":       lbl_scene_name,
        "clip_name":        lbl_clip_name,
        "scene_num":        lbl_scene_num,
        "track_num":        lbl_track_num,
        "bm_num":           lbl_bm_num,
        "volume":           lbl_volume,
        "vol_mode":         lbl_vol_mode,
        "r2":               lbl_r2,
        "select":           lbl_select,
        "start":            lbl_start,
        "l1":               lbl_l1,
        "eq_pill":          lbl_eq_pill,
        "ctrl":             lbl_ctrl,
        "action":           lbl_action,
        "fx_title":         lbl_fx_title,
        "fx_track":         lbl_fx_track,
        "fx_glow":          fx_glow,
        "fx_cells":         fx_cells,
        "baseline":         lbl_baseline,
        "lock_filter":      lbl_lock_filter,
        "lock_wet":         lbl_lock_wet,
        "eq_title":         lbl_eq_title,
        "eq_track":         lbl_eq_track,
        "eq_glow":          eq_glow,
        "eq_cells":         eq_cells,
        "eq_status":        lbl_eq_status,
        "eq_channel_meter": eq_channel_meter,
    }
# ═══════════════════════════════════════════════════════════════════════════
#  UI UPDATE LOOP
# ═══════════════════════════════════════════════════════════════════════════

def _blink_on():
    ms_now = int(time.perf_counter() * 1000)
    return (ms_now // BLINK_PERIOD_MS) % 2 == 0

def update_ui(root, lbl):
    clear_flashes_if_expired()

    now = time.perf_counter()

    with _lock:
        s          = {k: v for k, v in state.items()
                      if not isinstance(v, (dict, list))}
        bmarks     = list(state["bookmarks"])
        groups     = list(state["groups"])
        abl        = dict(ableton)
        fx_idx     = state["fx_track_index"]
        fx_name    = state["fx_track_name"]
        fx_ready   = state["fx_ready"]
        fx_names   = list(state["fx_macro_names"])
        fx_strings = list(state["fx_macro_value_strings"])
        fx_values  = list(state["fx_macro_values"])
        fx_mins    = list(state["fx_macro_mins"])
        fx_maxs    = list(state["fx_macro_maxs"])
        l1_held    = state["l1_held"]
        ctrl_conn  = state["controller_connected"]
        ctrl_name  = state["controller_name"]
        active_slot   = state["_fx_active_slot"]
        active_until  = state["_fx_active_until"]
        recovery_until = list(state["_fx_recovery_until"])
        baseline_ready = state["fx_baseline_ready"]
        baseline_captured_at = state["fx_baseline_captured_at"]
        filter_locked = state["fx_filter_locked"]
        wet_locked    = state["fx_wet_locked"]

        moment_stutter   = state["_momentary_stutter_active"]
        moment_bass_cut  = state["_momentary_bass_cut_active"]
        moment_throw     = state["_momentary_fx_throw_active"]

        all_track_colors = list(ableton["all_track_colors"])
        all_scene_colors = list(ableton["all_scene_colors"])
        clip_color       = ableton["clip_color"]
        fx_track_color   = ableton["fx_track_color"]
        eq_track_color   = ableton["eq_track_color"]
        current_track    = state["track"]
        current_scene    = state["scene"]
        cursor_bmark     = s["bookmark_cursor"]
        cursor_group     = s["group_cursor"]

        eq_idx           = state["eq_track_index"]
        eq_name          = state["eq_track_name"]
        eq_ready         = state["eq_ready"]
        eq_mode_active   = state["eq_mode_active"]
        eq_selected_band = state["eq_selected_band"]
        eq_armed_band    = state["eq_armed_band"]
        eq_armed_until   = state["eq_armed_until"]
        eq_macro_values  = list(state["eq_macro_values"])
        eq_value_strings = list(state["eq_macro_value_strings"])

        # v9.10: real audio meter snapshot
        meter_left       = state["eq_meter_left"]
        meter_right      = state["eq_meter_right"]
        meter_peak       = state["eq_meter_peak"]
        meter_peak_time  = state["eq_meter_peak_time"]

    if active_slot >= 0 and now > active_until:
        with _lock:
            state["_fx_active_slot"] = -1
        active_slot = -1

    if eq_armed_band >= 0 and now > eq_armed_until:
        with _lock:
            state["eq_armed_band"] = -1
        eq_armed_band = -1

    # Transport
    if abl["is_playing"]:
        set_label(lbl["playing"], "playing", "▶ PLAYING", fg=ABL_GREEN)
    else:
        set_label(lbl["playing"], "playing", "■ STOPPED", fg=ABL_RED)
    set_label(lbl["bpm"], "bpm", f"{abl['bpm']:.1f} BPM")

    if bmarks:
        cur = cursor_bmark
        bm  = bmarks[cur]
        scene_idx = bm["scene_index"]
        scene_color_int = all_scene_colors[scene_idx] if scene_idx < len(all_scene_colors) else 0
        bm_color = int_to_hex_color(scene_color_int, ABL_YELLOW)
        fg = ABL_RED if s["flash_bmark"] else bm_color
        set_label(lbl["bookmark"], "bookmark", bm["name"], fg=fg)
        set_label(lbl["bm_pos"],   "bm_pos",   f"{cur + 1}/{len(bmarks)}")
        set_label(lbl["bm_num"],   "bm_num",   str(cur + 1), fg=fg)
    else:
        set_label(lbl["bookmark"], "bookmark", "no §-scenes", fg=ABL_TEXT_FAINT)
        set_label(lbl["bm_pos"],   "bm_pos",   "")
        set_label(lbl["bm_num"],   "bm_num",   "—", fg=ABL_TEXT_FAINT)

    if groups:
        gc = cursor_group
        g  = groups[gc]
        group_track_idx = g["track_index"]
        group_color_int = (all_track_colors[group_track_idx]
                           if group_track_idx < len(all_track_colors) else 0)
        gr_color = int_to_hex_color(group_color_int, ABL_PURPLE)
        fg = ABL_RED if s["flash_group"] else gr_color
        set_label(lbl["group"],     "group",     g["name"], fg=fg)
        set_label(lbl["group_pos"], "group_pos", f"{gc + 1}/{len(groups)}")
    else:
        set_label(lbl["group"],     "group",     "no *-tracks", fg=ABL_TEXT_FAINT)
        set_label(lbl["group_pos"], "group_pos", "")

    track_color_int = (all_track_colors[current_track]
                       if current_track < len(all_track_colors) else 0)
    track_color = int_to_hex_color(track_color_int, ABL_TEXT)
    set_label(lbl["track_name"], "track_name", abl["track_name"], fg=track_color)

    scene_color_int = (all_scene_colors[current_scene]
                       if current_scene < len(all_scene_colors) else 0)
    scene_color = int_to_hex_color(scene_color_int, ABL_TEXT)
    set_label(lbl["scene_name"], "scene_name", abl["scene_name"], fg=scene_color)

    clip = abl["clip_name"]
    clip_color_hex = int_to_hex_color(clip_color, ABL_BLUE)
    if clip == "…":
        set_label(lbl["clip_name"], "clip_name", "…", fg=ABL_TEXT_FAINT)
    elif abl["clip_empty"]:
        set_label(lbl["clip_name"], "clip_name", "— empty —", fg=ABL_TEXT_FAINT)
    else:
        set_label(lbl["clip_name"], "clip_name", clip, fg=clip_color_hex)

    set_label(lbl["scene_num"], "scene_num",
              str(s["scene"] + 1),
              fg=ABL_RED if s["flash_scene"] else ABL_TEXT)
    set_label(lbl["track_num"], "track_num",
              str(s["track"] + 1),
              fg=ABL_RED if s["flash_track"] else ABL_TEXT)

    vol = abl["track_volume"]
    vol_ratio = vol / ABLETON_UNITY
    if vol == 0.0:
        vc = ABL_RED
    elif vol_ratio > 1.05:
        vc = ABL_ORANGE
    elif vol_ratio > 0.95:
        vc = ABL_GREEN
    else:
        vc = ABL_BLUE
    set_label(lbl["volume"], "volume", db_from_vol(vol), fg=vc)

    if s["select_held"]:
        set_label(lbl["vol_mode"], "vol_mode", "● VOL", fg=ABL_BLUE)
    else:
        set_label(lbl["vol_mode"], "vol_mode", "SELECT+R-stick", fg=ABL_TEXT_FAINT)

    lbl["r2"].config(fg=ABL_RED if s["r2_held"] else ABL_TEXT_FAINT,
                     bg="#3a1818" if s["r2_held"] else ABL_PANEL)
    lbl["select"].config(fg=ABL_BLUE if s["select_held"] else ABL_TEXT_FAINT,
                         bg="#142838" if s["select_held"] else ABL_PANEL)
    lbl["start"].config(fg=ABL_GREEN if abl["is_playing"] else ABL_TEXT_FAINT,
                        bg="#1a2a1a" if abl["is_playing"] else ABL_PANEL)
    lbl["l1"].config(fg=ABL_YELLOW if l1_held else ABL_TEXT_FAINT,
                     bg="#3a3010" if l1_held else ABL_PANEL)
    lbl["eq_pill"].config(fg=ABL_PURPLE if eq_mode_active else ABL_TEXT_FAINT,
                          bg=EQ_MODE_BG if eq_mode_active else ABL_PANEL)

    set_label(lbl["action"], "action", s["last_action"])

    if ctrl_conn:
        lbl["ctrl"].config(text=f"● {ctrl_name[:16]}",
                           bg="#1a2a1a", fg=ABL_GREEN)
    else:
        bright = _blink_on()
        lbl["ctrl"].config(text="● NO CONTROLLER",
                           bg=BLINK_BG_BRIGHT if bright else BLINK_BG_DIM,
                           fg="#ffffff" if bright else ABL_TEXT)

    # ── v9.10 EQ STATUS UPDATE ──
    eq_track_color_hex = int_to_hex_color(eq_track_color, ABL_TEXT)
    if eq_idx < 0:
        set_label(lbl["eq_title"], "eq_title", "◇ EQ", fg=ABL_TEXT_FAINT)
        set_label(lbl["eq_track"], "eq_track", "—", fg=ABL_TEXT_FAINT)
        set_label(lbl["eq_status"], "eq_status",
                  "(no ~ EQ Macros track)", fg=ABL_TEXT_FAINT)
        lbl["eq_glow"].config(bg=EQ_KNOB_RING_DARK)
    elif not eq_ready:
        set_label(lbl["eq_title"], "eq_title", "◇ EQ", fg=ABL_TEXT_DIM)
        set_label(lbl["eq_track"], "eq_track", f"loading…  [t{eq_idx}]",
                  fg=ABL_TEXT_DIM)
        set_label(lbl["eq_status"], "eq_status", "loading EQ rack…",
                  fg=ABL_TEXT_DIM)
        lbl["eq_glow"].config(bg=EQ_KNOB_RING_DARK)
    elif eq_mode_active:
        set_label(lbl["eq_title"], "eq_title", "◇ EQ ACTIVE", fg=ABL_TEXT)
        set_label(lbl["eq_track"], "eq_track", f"[t{eq_idx}]", fg=ABL_TEXT)
        band_name = EQ_MACRO_NAMES_EXPECTED[eq_selected_band]
        set_label(lbl["eq_status"], "eq_status",
                  f"◇ {band_name}  •  ←/→ value  •  ↑/↓ band",
                  fg=ABL_TEXT)
        lbl["eq_glow"].config(bg=EQ_LABEL_SELECTED)
    else:
        set_label(lbl["eq_title"], "eq_title", "◇ EQ", fg=ABL_TEXT)
        set_label(lbl["eq_track"], "eq_track", f"[t{eq_idx}]",
                  fg=eq_track_color_hex)
        set_label(lbl["eq_status"], "eq_status",
                  "EQ inactive (R3 to toggle)", fg=ABL_TEXT_FAINT)
        lbl["eq_glow"].config(bg=EQ_KNOB_RING_DARK)

    # ── Draw 3 EQ knobs (HIGH / MID / LOW) ──
    for band_idx in range(3):
        cell, canvas, name_lbl, value_lbl = lbl["eq_cells"][band_idx]
        macro_val = eq_macro_values[band_idx] if band_idx < len(eq_macro_values) else EQ_NEUTRAL_MACRO
        value_str = eq_value_strings[band_idx] if band_idx < len(eq_value_strings) else "—"

        visual_pos = eq_visual_position(macro_val)
        is_selected = (eq_mode_active and band_idx == eq_selected_band)
        is_armed    = (eq_mode_active and band_idx == eq_armed_band)

        if is_armed:
            cell_bg = EQ_GLOW_ARMED
            label_color = EQ_LABEL_ARMED
        elif is_selected:
            cell_bg = EQ_GLOW_SELECTED
            label_color = EQ_LABEL_SELECTED
        else:
            cell_bg = ABL_CELL
            label_color = EQ_LABEL_COLOR

        if cell.cget("bg") != cell_bg:
            cell.config(bg=cell_bg)
            canvas.config(bg=cell_bg)
            name_lbl.config(bg=cell_bg)
            value_lbl.config(bg=cell_bg)

        draw_eq_knob(canvas, band_idx, visual_pos,
                     selected=is_selected, armed=is_armed)

        band_name = EQ_MACRO_NAMES_EXPECTED[band_idx]
        display_name = band_name.replace("EQ ", "").upper()
        set_label(name_lbl, f"eq_name_{band_idx}", display_name, fg=label_color)

        set_label(value_lbl, f"eq_value_{band_idx}",
                  value_str if value_str else "—", fg=label_color)

    # ── v9.10 DJM CHANNEL METER (single big meter, real audio) ──
    current_level = max(meter_left, meter_right)  # stereo peak
    new_peak, new_peak_time = update_meter_peak(
        current_level, meter_peak, meter_peak_time, now
    )
    if new_peak != meter_peak or new_peak_time != meter_peak_time:
        with _lock:
            state["eq_meter_peak"]      = new_peak
            state["eq_meter_peak_time"] = new_peak_time

    draw_channel_meter(lbl["eq_channel_meter"], current_level, new_peak)

    # ── FX PANEL UPDATE ──
    fx_color = int_to_hex_color(fx_track_color, ABL_TEXT)
    if fx_idx < 0:
        set_label(lbl["fx_title"], "fx_title", "⚡ FX MACHINE", fg=ABL_TEXT_FAINT)
        set_label(lbl["fx_track"], "fx_track",
                  f"add track '{FX_TRACK_NAME}'", fg=ABL_TEXT_FAINT)
        lbl["fx_glow"].config(bg=ABL_BG)
    elif not fx_ready:
        set_label(lbl["fx_title"], "fx_title", "⚡ FX MACHINE", fg=ABL_TEXT_DIM)
        set_label(lbl["fx_track"], "fx_track",
                  f"loading…  [t{fx_idx}]", fg=ABL_TEXT_DIM)
        lbl["fx_glow"].config(bg=ABL_BG)
    elif l1_held:
        set_label(lbl["fx_title"], "fx_title", "⚡ FX MODE ACTIVE", fg=ABL_YELLOW)
        set_label(lbl["fx_track"], "fx_track",
                  f"{fx_name}  [t{fx_idx}]", fg=ABL_YELLOW)
        lbl["fx_glow"].config(bg=ABL_YELLOW)
    else:
        set_label(lbl["fx_title"], "fx_title", "⚡ FX MACHINE", fg=ABL_TEXT)
        set_label(lbl["fx_track"], "fx_track",
                  f"{fx_name}  [t{fx_idx}]", fg=fx_color)
        lbl["fx_glow"].config(bg=ABL_BG)

    if baseline_ready:
        if (now - baseline_captured_at) < 1.0:
            set_label(lbl["baseline"], "baseline", "✓ BASELINE SAVED", fg=ABL_GREEN)
        else:
            set_label(lbl["baseline"], "baseline", "✓ baseline", fg=ABL_TEXT_DIM)
    else:
        set_label(lbl["baseline"], "baseline", "✗ no baseline", fg=ABL_TEXT_FAINT)

    if filter_locked:
        set_label(lbl["lock_filter"], "lock_filter", "🔒 filter", fg=ABL_YELLOW)
    else:
        set_label(lbl["lock_filter"], "lock_filter", "filter: free", fg=ABL_TEXT_FAINT)

    if wet_locked:
        set_label(lbl["lock_wet"], "lock_wet", "🔒 wet", fg=ABL_YELLOW)
    else:
        set_label(lbl["lock_wet"], "lock_wet", "wet: free", fg=ABL_TEXT_FAINT)

    for slot in range(8):
        cell, canvas, name_lbl, value_lbl = lbl["fx_cells"][slot]
        accent  = ABL_ORANGE if slot < 4 else ABL_BLUE
        name    = fx_names[slot] if slot < len(fx_names) else ""
        value_string = fx_strings[slot] if slot < len(fx_strings) else "—"

        is_active   = (slot == active_slot)
        is_recover  = (now < recovery_until[slot])
        is_locked   = ((slot == FX_SLOT_FX_SEND and wet_locked) or
                       (slot == FX_SLOT_FILTER_FREQ and filter_locked))
        is_moment   = ((slot == FX_SLOT_STUTTER and moment_stutter) or
                       (slot in (FX_SLOT_FILTER_FREQ, FX_SLOT_FILTER_MODE) and moment_bass_cut) or
                       (slot == FX_SLOT_FX_SEND and moment_throw))

        if slot < len(fx_values) and slot < len(fx_mins) and slot < len(fx_maxs):
            val = fx_values[slot]
            min_val = fx_mins[slot]
            max_val = fx_maxs[slot]
            macro_range = max_val - min_val
            if macro_range > 0:
                value_frac = (val - min_val) / macro_range
                value_frac = max(0.0, min(1.0, value_frac))
            else:
                value_frac = 0.0
        else:
            value_frac = 0.0

        if is_moment:
            cell_bg = ABL_CELL_MOMENT
        elif is_active:
            cell_bg = ABL_CELL_HOT
        elif is_recover:
            cell_bg = ABL_CELL_REC
        elif is_locked:
            cell_bg = ABL_CELL_LOCK
        else:
            cell_bg = ABL_CELL

        if cell.cget("bg") != cell_bg:
            cell.config(bg=cell_bg)
            canvas.config(bg=cell_bg)
            name_lbl.config(bg=cell_bg)
            value_lbl.config(bg=cell_bg)

        if name:
            draw_knob(canvas, slot, value_frac, accent,
                      active=is_active, locked=is_locked, moment=is_moment)
        else:
            draw_knob(canvas, slot, 0.0, ABL_TEXT_FAINT)

        if not name:
            expected = FX_MACRO_NAMES_EXPECTED[slot]
            set_label(name_lbl,  f"fx_name_{slot}",  expected, fg=ABL_TEXT_FAINT)
            set_label(value_lbl, f"fx_value_{slot}", "—",      fg=ABL_TEXT_FAINT)
        else:
            display_name = name
            if is_locked:
                display_name = "🔒 " + name
            elif is_moment:
                display_name = "💥 " + name
            set_label(name_lbl,  f"fx_name_{slot}", display_name, fg=ABL_TEXT_DIM)
            set_label(value_lbl, f"fx_value_{slot}", value_string, fg=accent)

    root.after(UI_REFRESH_MS, update_ui, root, lbl)

# ═══════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 64)
    print(f"  FX MACHINE v{VERSION}  —  MIRA___OFC / Modulated_OFC")
    print(f"  © Ayoub Agoujdad. Trademark registered. Non-commercial only.")
    print("=" * 64)

    setup_osc()

    threading.Thread(target=start_osc_server, daemon=True).start()
    threading.Thread(target=polling_loop,     daemon=True).start()
    threading.Thread(target=controller_loop,  daemon=True).start()
    threading.Thread(target=watchdog_loop,    daemon=True).start()
    threading.Thread(target=eq_ramp_loop,     daemon=True).start()

    time.sleep(0.5)
    threading.Thread(target=fetch_all_names,  daemon=True).start()
    osc_update_view()

    print("  Controls:")
    print("    NAV LAYER (default):")
    print("      L-stick: Scene/Track   D-pad U/D: Bookmarks  L/R: Groups")
    print("      X=Launch  O=Stop  △=Scene  □=Arm  L2=Stop track")
    print("      R3 = Toggle EQ mode    START=Play/Stop")
    print("      SELECT+R3=Volume mute  SELECT+START=Refresh")
    print("      SELECT+R1=Save baseline  SELECT+R-stick=Volume")
    print("    FX LAYER (hold L1):")
    print("      L-stick: Filter Freq/Res     R-stick: FX Send/Reverb Size")
    print("      D-pad U/D: Bookmarks         D-pad L/R: Delay FB step")
    print("      L3: filter lock  R3: wet lock")
    print("      L1+X: STUTTER  L1+O: BASS CUT  L1+△: LAUNCH SCENE  L1+□: FX THROW")
    print("    EQ MODE (R3 to toggle on/off):")
    print("      R-stick X (ENCODER): push RIGHT to boost, LEFT to cut, release = HOLD")
    print("      R-stick Y double-flick UP: switch band UP   (MID→HIGH→LOW→MID, no borders)")
    print("      R-stick Y double-flick DOWN: switch band DOWN (MID→LOW→HIGH→MID, no borders)")
    print("      R-stick X double-flick LEFT: kill (if ≤0dB) / normalize to 0 (if >0dB)")
    print("      R-stick X double-flick RIGHT: restore (if <0dB) / +15% headroom (mid/high) / blocked (bass)")
    print(f"  FX track: '{FX_TRACK_NAME}'  EQ track: '{EQ_TRACK_NAME}'")
    print(f"  v9.11: dual-axis double-flick gestures + faster encoder + bass safety")
    print("=" * 64)

    root = tk.Tk()
    root.geometry("760x900")
    lbl = build_ui(root)
    root.after(UI_REFRESH_MS, update_ui, root, lbl)

    def on_close():
        global _osc_server
        print("  Shutting down…")
        try:
            osc_stop_fx_listeners()
            osc_stop_eq_listeners()
            osc_stop_eq_meter_listener()
        except Exception as e:
            print(f"  ⚠  Listener stop error: {e}")
        if _osc_server is not None:
            _osc_server.shutdown()
            _osc_server = None
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

    print("  👋 Stopped.")
    pygame.quit()
    sys.exit(0)

if __name__ == "__main__":
    main()
