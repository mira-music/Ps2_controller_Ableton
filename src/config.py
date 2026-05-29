"""
================================================================================
  src/config.py — Architectural Constants (do not change at runtime)
================================================================================
  These constants describe FACTS about the system that never change:
    - Button index numbers (pygame conventions)
    - OSC paths
    - Macro slot indices
    - Empirically calibrated values (EQ_NEUTRAL_MACRO, etc.)
    - Default values that seed cfg singleton

  Tunable values (encoder feel, deadzones, gesture timings) live in
  config/active.toml via src/config_loader.py.
================================================================================
"""

#
# ═══════════════════════════════════════════════════════════════════════════
#  VERSION
# ═══════════════════════════════════════════════════════════════════════════

VERSION = "9.11"  # current shipped version; Build B in development

#
# ═══════════════════════════════════════════════════════════════════════════
#  OSC NETWORKING (defaults — overridable via TOML)
# ═══════════════════════════════════════════════════════════════════════════

OSC_HOST           = "127.0.0.1"
OSC_SEND_PORT      = 11000
OSC_RECEIVE_PORT   = 11001

# ═══════════════════════════════════════════════════════════════════════════
#  ABLETON SESSION LIMITS
# ═══════════════════════════════════════════════════════════════════════════

MAX_SCENES         = 256
MAX_TRACKS         = 256

# ═══════════════════════════════════════════════════════════════════════════
#  PREFIX CONVENTIONS
# ═══════════════════════════════════════════════════════════════════════════

BOOKMARK_PREFIX    = "§"
GROUP_PREFIX       = "*"

# ═══════════════════════════════════════════════════════════════════════════
#  FX RACK (unchanged from Build A)
# ═══════════════════════════════════════════════════════════════════════════

FX_TRACK_NAME      = "~ FX Macros"
FX_RACK_DEVICE_INDEX = 0

# Macro slot indices (0-7) within the FX rack
FX_SLOT_FILTER_FREQ = 0
FX_SLOT_FILTER_MODE = 1
FX_SLOT_FILTER_RES  = 2
FX_SLOT_STUTTER     = 3
FX_SLOT_REVERB_SIZE = 4
FX_SLOT_FX_SEND     = 5
FX_SLOT_DELAY_FB    = 6
FX_SLOT_WIDTH       = 7

# Expected macro names in order of slot (used for discovery validation)
FX_MACRO_NAMES_EXPECTED = [
    "Filter Freq",   # 0
    "Filter Mode",   # 1
    "Filter Res",    # 2
    "Stutter",       # 3
    "Reverb Size",   # 4
    "FX Send",       # 5
    "Delay FB",      # 6
    "Width",         # 7
]

# Per-macro sweep durations (defaults — overridable via TOML)
FX_SWEEP_SECONDS = {
    "Filter Freq":   1.5,
    "Filter Res":    3.0,
    "Reverb Size":   5.0,
    "FX Send":       1.0,
}

# Stick deadzone for FX layer
FX_AXIS_DEAD_ZONE = 0.08

# OSC write rate limiting for FX
FX_WRITE_THROTTLE      = 0.025
FX_WRITE_EPSILON_FRAC  = 0.001

# Acceleration (FX-layer stick driver)
FX_ACCEL_RAMP_S    = 1.0
FX_ACCEL_MAX_MULT  = 4.0

# Delay FB D-pad stepping
FX_DELAY_FB_DEBOUNCE   = 0.18
FX_DELAY_FB_STEPS      = 20
FX_DELAY_FB_CLAMP_FRAC = 0.92

# FX baseline + recovery
FX_RECOVERY_FLASH_S    = 0.4
FX_SEND_DRY_VALUE      = 0.0
FX_SAFETY_POLL_INTERVAL = 2.0
BASS_CUT_MODE_VALUE    = 0.0    # HP mode for bass cut momentary
BASS_CUT_FREQ_VALUE    = 42.3   # ≈200 Hz on Filter Freq macro

# L1-release behavior per FX slot
FX_RECOVERY_BEHAVIOUR = {
    FX_SLOT_FILTER_FREQ: "filter",    # restore to baseline unless filter-locked
    FX_SLOT_FILTER_MODE: "skip",      # leave as is
    FX_SLOT_FILTER_RES:  "skip",
    FX_SLOT_STUTTER:     "fixed:0.0", # always snap to 0
    FX_SLOT_REVERB_SIZE: "skip",      # keep reverb tail character
    FX_SLOT_FX_SEND:     "wet",       # snap to 0 unless wet-locked
    FX_SLOT_DELAY_FB:    "skip",      # keep delay character
    FX_SLOT_WIDTH:       "skip",
}

# ═══════════════════════════════════════════════════════════════════════════
#  EQ RACK
# ═══════════════════════════════════════════════════════════════════════════

EQ_TRACK_NAME      = "~ EQ Macros"
EQ_RACK_DEVICE_INDEX = 0

# Macro slot indices within the EQ rack
# NOTE: Build B added TRIM as slot 3. Total macros now = 4.
EQ_SLOT_LOW   = 0
EQ_SLOT_MID   = 1
EQ_SLOT_HIGH  = 2
EQ_SLOT_TRIM  = 3    # NEW in Build B — controls Utility gain BEFORE EQ Three

# Expected macro names in order of slot
EQ_MACRO_NAMES_EXPECTED = [
    "EQ Low",    # 0
    "EQ Mid",    # 1
    "EQ High",   # 2
    "Trim",      # 3 — NEW in Build B
]

# Total count for loops + arrays
EQ_MACRO_COUNT = 4   # was 3, now 4 with TRIM

# Empirically calibrated EQ Three macro values
# (DO NOT CHANGE — these were measured against Ableton's actual gain curve)
EQ_MACRO_MIN       = 0.0       # -∞ dB
EQ_MACRO_MAX       = 127.0     # +6 dB max boost
EQ_NEUTRAL_MACRO   = 107.9     # 0 dB neutral
EQ_CUT_HALF_MACRO  = 53.95     # -19 dB (mid/high kill target)

# ═══════════════════════════════════════════════════════════════════════════
#  TRIM (Utility Gain) — Empirically calibrated macro values
#  (DO NOT CHANGE — measured against Ableton's actual Utility Gain curve)
#
#  Measured points from user calibration:
#    macro   0  → -∞ dB
#    macro  64  →   0.0 dB    ← NEUTRAL POSITION (different from EQ!)
#    macro  96  →  +17.9 dB
#    macro 127  →  +35.0 dB
#
#  The curve from macro 64 to 127 is linear in dB:
#    35.0 dB / 63 macro units = 0.555 dB per macro unit
#
#  IMPORTANT: TRIM is a SEPARATE calibration from the EQ Three bands.
#  Do not confuse EQ_NEUTRAL_MACRO (107.9) with TRIM_NEUTRAL_MACRO (64.0).
# ═══════════════════════════════════════════════════════════════════════════

TRIM_NEUTRAL_MACRO = 64.0      # 0 dB neutral position for TRIM
TRIM_DB_PER_MACRO  = 0.555     # dB change per macro unit (above neutral)

# Bass safety cap (encoder cannot exceed this)
EQ_BASS_BOOST_CAP  = 114.0     # ≈+2 dB

# Double-flick boost percentage (asymptotic toward +6 dB)
EQ_BOOST_PCT       = 0.15

# Encoder defaults (overridable via TOML)
EQ_SWEEP_SECONDS      = 0.30
EQ_ENCODER_CURVE_EXP  = 1.0
EQ_SMOOTHING_FACTOR   = 0.55
EQ_AXIS_DEAD_ZONE     = 0.18
EQ_DOMINANCE_RATIO    = 3.0

# Gesture defaults
EQ_FLICK_EXTREME      = 0.90
EQ_FLICK_RETURN       = 0.22
EQ_FLICK_TIMEOUT_MS   = 380

# Detent defaults
EQ_DETENT_RANGE       = 1.0
EQ_DETENT_MIN_FACTOR  = 0.30

# OSC write rate limiting for EQ
EQ_WRITE_THROTTLE     = 0.015

# Ramp animation defaults
EQ_RAMP_MIN_MS        = 30
EQ_RAMP_MAX_MS        = 100
EQ_RAMP_TICK_MS       = 16     # 60 Hz — RESTART required to change

# Legacy meter constants (Build A — kept for current UI; redesigned in Build B Phase 2)
EQ_METER_PEAK_HOLD_S  = 1.5
EQ_METER_PEAK_FALL    = 30.0
EQ_METER_SEGMENTS     = 24      # current channel meter LED count
EQ_METER_GREEN        = 15      # safe zone (bottom segments)
EQ_METER_YELLOW       = 6       # loud zone
EQ_METER_RED          = 3       # clipping zone

# ═══════════════════════════════════════════════════════════════════════════
#  NAVIGATION + UI + TIMING (defaults — overridable via TOML)
# ═══════════════════════════════════════════════════════════════════════════

# Navigation
ANALOG_THRESHOLD      = 0.55
HOLD_SCROLL_DELAY     = 0.50
HOLD_SCROLL_RATE      = 0.18
SMOOTHING_FACTOR      = 0.20
DPAD_DEBOUNCE         = 0.30

# Volume
VOL_DEAD_ZONE         = 0.18
VOL_SENSITIVITY       = 0.012
ABLETON_UNITY         = 0.85
VOL_MIN               = 0.0
VOL_MAX               = 1.0
VOL_CHANGE_THRESHOLD  = 0.0005

# Timing
R3_DOUBLE_CLICK_WINDOW    = 0.40
QUERY_DEFER_TIME          = 0.05
WATCHDOG_INTERVAL         = 1.0
IDLE_REPROBE_AFTER        = 5.0
SELECT_RECONCILE_INTERVAL = 0.10

# UI
UI_REFRESH_MS         = 25
BLINK_PERIOD_MS       = 500

# Ableton error throttling
ABLETON_ERROR_THROTTLE = 2.0

# ═══════════════════════════════════════════════════════════════════════════
#  BUTTON + AXIS INDICES (pygame conventions for PlayStation-style gamepad)
# ═══════════════════════════════════════════════════════════════════════════

# Face buttons
BTN_TRIANGLE = 0
BTN_CIRCLE   = 1
BTN_CROSS    = 2
BTN_SQUARE   = 3

# Shoulder buttons
BTN_L1 = 4
BTN_R1 = 5
BTN_L2 = 6
BTN_R2 = 7

# Center
BTN_SELECT = 8
BTN_START  = 9

# Stick buttons
BTN_L3 = 10
BTN_R3 = 11

# Stick axes
AXIS_LEFT_X  = 0
AXIS_LEFT_Y  = 1
AXIS_RIGHT_X = 2
AXIS_RIGHT_Y = 3

RIGHT_STICK_ROTATED_90 = True