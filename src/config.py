"""
================================================================================
  src/config.py — All Constants
================================================================================
  Centralized constants for the FX Machine. Tunable values are grouped
  by subsystem.
  
  v9.11 baseline. In a future iteration these should move to a config.toml
  file for runtime customization without editing code.
================================================================================
"""

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
EQ_SWEEP_SECONDS      = 0.6     # v9.11: fast overall sweep
EQ_SMOOTHING_FACTOR   = 0.40
EQ_DOMINANCE_RATIO    = 1.3
EQ_ENCODER_CURVE_EXP  = 1.2     # v9.11: slight easing at start, mostly linear

# Sticky 0 dB detent
EQ_DETENT_RANGE       = 3.0
EQ_DETENT_MIN_FACTOR  = 0.15

# DJM-900 style channel meter (real audio output level)
EQ_METER_SEGMENTS     = 24
EQ_METER_GREEN        = 15
EQ_METER_YELLOW       = 6
EQ_METER_RED          = 3
EQ_METER_PEAK_HOLD_S  = 1.5
EQ_METER_PEAK_FALL    = 0.8

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
#  FX POLLING
# ═══════════════════════════════════════════════════════════════════════════

FX_SAFETY_POLL_INTERVAL = 2.0

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