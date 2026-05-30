"""
================================================================================
  src/config_loader.py — TOML Config Loading + Hot-Reload + Singleton
================================================================================
  Build B revision: added [diagnostics] section keys to _CFG_MAP so the
  diagnostics layer can read its tunables from the cfg singleton with the
  same hot-reload behavior as everything else.
================================================================================
"""

import sys
import shutil
import tomllib
from pathlib import Path
from src.log_setup import get_logger
from src import config as defaults

log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  PATH DETECTION
# ═══════════════════════════════════════════════════════════════════════════

def _get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).resolve().parent.parent

def _get_config_dir() -> Path:
    cfg_dir = _get_base_dir() / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir

def _get_active_path() -> Path:
    return _get_config_dir() / "active.toml"

def _get_default_path() -> Path:
    return _get_config_dir() / "default.toml"


# ═══════════════════════════════════════════════════════════════════════════
#  RUNTIME CONFIG SINGLETON
# ═══════════════════════════════════════════════════════════════════════════

class _RuntimeConfig:
    """Singleton holding all hot-reloadable tunable values."""

    def __init__(self):
        # ─── EQ encoder ───
        self.EQ_SWEEP_SECONDS      = defaults.EQ_SWEEP_SECONDS
        self.EQ_ENCODER_CURVE_EXP  = defaults.EQ_ENCODER_CURVE_EXP
        self.EQ_SMOOTHING_FACTOR   = defaults.EQ_SMOOTHING_FACTOR
        self.EQ_AXIS_DEAD_ZONE     = defaults.EQ_AXIS_DEAD_ZONE

        # ─── EQ dominance ───
        self.EQ_DOMINANCE_RATIO    = defaults.EQ_DOMINANCE_RATIO

        # ─── EQ flick ───
        self.EQ_FLICK_EXTREME      = defaults.EQ_FLICK_EXTREME
        self.EQ_FLICK_RETURN       = defaults.EQ_FLICK_RETURN
        self.EQ_FLICK_TIMEOUT_MS   = defaults.EQ_FLICK_TIMEOUT_MS

        # ─── EQ detent ───
        self.EQ_DETENT_RANGE       = defaults.EQ_DETENT_RANGE
        self.EQ_DETENT_MIN_FACTOR  = defaults.EQ_DETENT_MIN_FACTOR

        # ─── EQ OSC writes ───
        self.EQ_WRITE_THROTTLE     = defaults.EQ_WRITE_THROTTLE
        self.EQ_WRITE_EPSILON      = 0.15

        # ─── EQ ramp ───
        self.EQ_RAMP_MIN_MS        = defaults.EQ_RAMP_MIN_MS
        self.EQ_RAMP_MAX_MS        = defaults.EQ_RAMP_MAX_MS

        # ─── EQ safety ───
        self.EQ_BASS_BOOST_CAP     = defaults.EQ_BASS_BOOST_CAP
        self.EQ_BOOST_PCT          = defaults.EQ_BOOST_PCT

        # ─── TRIM ───
        self.TRIM_SWEEP_SECONDS    = 0.25
        self.TRIM_CURVE_EXP        = 1.0
        self.TRIM_SMOOTHING_FACTOR = 0.55
        self.TRIM_DEAD_ZONE        = 0.18
        self.TRIM_MAX_DB           = 9.0
        self.TRIM_WRITE_THROTTLE   = 0.015
        self.TRIM_WRITE_EPSILON    = 0.15
        self.TRIM_DETENT_RANGE     = 1.0
        self.TRIM_DETENT_MIN_FACTOR = 0.30

        # ─── Meter ───
        self.METER_REFERENCE_OFFSET_DB  = 18.0
        self.METER_RELEASE_DB_PER_SEC   = 20.0
        self.METER_PEAK_HOLD_SECONDS    = defaults.EQ_METER_PEAK_HOLD_S
        self.METER_PEAK_FALL_DB_PER_SEC = 30.0

        # ─── Meter clip ───
        self.METER_CLIP_WARN_DB         = 6.0
        self.METER_CLIP_CRITICAL_DB     = 9.0
        self.METER_CLIP_FLICKER_HZ      = 4.0
        self.METER_CLIP_FADEOUT_SECONDS = 0.5

        # ─── FX rack ───
        self.FX_FILTER_FREQ_SWEEP_S = defaults.FX_SWEEP_SECONDS.get("Filter Freq", 1.5)
        self.FX_FILTER_RES_SWEEP_S  = defaults.FX_SWEEP_SECONDS.get("Filter Res", 3.0)
        self.FX_REVERB_SIZE_SWEEP_S = defaults.FX_SWEEP_SECONDS.get("Reverb Size", 5.0)
        self.FX_SEND_SWEEP_S        = defaults.FX_SWEEP_SECONDS.get("FX Send", 1.0)
        self.FX_DEFAULT_SWEEP_S     = 3.0
        self.FX_AXIS_DEAD_ZONE      = defaults.FX_AXIS_DEAD_ZONE
        self.FX_ACCEL_RAMP_S        = defaults.FX_ACCEL_RAMP_S
        self.FX_ACCEL_MAX_MULT      = defaults.FX_ACCEL_MAX_MULT
        self.FX_WRITE_THROTTLE      = defaults.FX_WRITE_THROTTLE
        self.FX_WRITE_EPSILON_FRAC  = defaults.FX_WRITE_EPSILON_FRAC

        # ─── FX delay FB ───
        self.FX_DELAY_FB_STEPS      = defaults.FX_DELAY_FB_STEPS
        self.FX_DELAY_FB_CLAMP_FRAC = defaults.FX_DELAY_FB_CLAMP_FRAC
        self.FX_DELAY_FB_DEBOUNCE   = defaults.FX_DELAY_FB_DEBOUNCE

        # ─── Volume ───
        self.VOL_DEAD_ZONE          = defaults.VOL_DEAD_ZONE
        self.VOL_SENSITIVITY        = defaults.VOL_SENSITIVITY
        self.ABLETON_UNITY          = defaults.ABLETON_UNITY
        self.VOL_CHANGE_THRESHOLD   = defaults.VOL_CHANGE_THRESHOLD

        # ─── Navigation ───
        self.ANALOG_THRESHOLD       = defaults.ANALOG_THRESHOLD
        self.HOLD_SCROLL_DELAY      = defaults.HOLD_SCROLL_DELAY
        self.HOLD_SCROLL_RATE       = defaults.HOLD_SCROLL_RATE
        self.SMOOTHING_FACTOR       = defaults.SMOOTHING_FACTOR
        self.DPAD_DEBOUNCE          = defaults.DPAD_DEBOUNCE

        # ─── Timing ───
        self.R3_DOUBLE_CLICK_WINDOW    = defaults.R3_DOUBLE_CLICK_WINDOW
        self.QUERY_DEFER_TIME          = defaults.QUERY_DEFER_TIME
        self.FX_SAFETY_POLL_INTERVAL   = defaults.FX_SAFETY_POLL_INTERVAL
        self.WATCHDOG_INTERVAL         = defaults.WATCHDOG_INTERVAL
        self.IDLE_REPROBE_AFTER        = defaults.IDLE_REPROBE_AFTER
        self.SELECT_RECONCILE_INTERVAL = defaults.SELECT_RECONCILE_INTERVAL

        # ─── UI (RESTART) ───
        self.UI_REFRESH_MS           = defaults.UI_REFRESH_MS
        self.BLINK_PERIOD_MS         = defaults.BLINK_PERIOD_MS
        self.WINDOW_WIDTH            = 760
        self.WINDOW_HEIGHT           = 900

        # ─── Network (RESTART) ───
        self.OSC_HOST                = defaults.OSC_HOST
        self.OSC_SEND_PORT           = defaults.OSC_SEND_PORT
        self.OSC_RECEIVE_PORT        = defaults.OSC_RECEIVE_PORT

        # ─── Diagnostics (NEW in Build B) ───
        # Master controls
        self.DIAG_ENABLED                  = False
        self.DIAG_LOG_PATH                 = "logs/diagnostics.log"
        self.DIAG_JSONL_PATH               = "logs/diagnostics.jsonl"
        self.DIAG_SUMMARY_INTERVAL_S       = 10.0
        self.DIAG_SAMPLE_INTERVAL_S        = 1.0
        self.DIAG_SLOW_FUNCTION_MS         = 5.0
        self.DIAG_SLOW_FRAME_MS            = 50.0
        self.DIAG_OSC_WINDOW_S             = 5.0
        self.DIAG_JSONL_FORMAT             = "compact"
        self.DIAG_JSONL_INCLUDE_OSC_ARGS   = False

        # Warning thresholds
        self.DIAG_WARN_CLIP_RATE_PER_MIN   = 10
        self.DIAG_WARN_OSC_SEND_PER_SEC    = 200
        self.DIAG_WARN_OSC_RECV_PER_SEC    = 300
        self.DIAG_WARN_SINGLE_CALL_MS      = 100.0
        self.DIAG_WARN_CPU_PERCENT         = 25.0
        self.DIAG_WARN_MEMORY_GROWTH_MB    = 50.0
        self.DIAG_WARN_THREAD_MISS_FRAC    = 0.10

        # Rate limiting
        self.DIAG_RL_ENABLED               = False
        self.DIAG_RL_CLIP_NOTIF_PER_MIN    = 20
        self.DIAG_RL_OSC_PER_ADDR_PER_SEC  = 100
        self.DIAG_RL_COOLDOWN_S            = 5.0

        # Hooks (RESTART — applied at install time)
        self.DIAG_TIMED_FUNCTIONS          = []
        self.DIAG_TRACK_ALL_OSC_SENDS      = True
        self.DIAG_TRACK_ALL_OSC_RECEIVES   = True
        self.DIAG_TRACKED_OSC_ADDRESSES    = []


# The singleton
cfg = _RuntimeConfig()


# ═══════════════════════════════════════════════════════════════════════════
#  RESTART-REQUIRED REGISTRY
# ═══════════════════════════════════════════════════════════════════════════

_RESTART_REQUIRED_ATTRS = {
    "UI_REFRESH_MS",
    "BLINK_PERIOD_MS",
    "WINDOW_WIDTH",
    "WINDOW_HEIGHT",
    "OSC_HOST",
    "OSC_SEND_PORT",
    "OSC_RECEIVE_PORT",
    # Diagnostics restart-required
    "DIAG_LOG_PATH",
    "DIAG_JSONL_PATH",
    "DIAG_TIMED_FUNCTIONS",
    "DIAG_TRACK_ALL_OSC_SENDS",
    "DIAG_TRACK_ALL_OSC_RECEIVES",
    "DIAG_TRACKED_OSC_ADDRESSES",
}


# ═══════════════════════════════════════════════════════════════════════════
#  TOML → CFG MAPPING
# ═══════════════════════════════════════════════════════════════════════════

_CFG_MAP = [
    # EQ encoder
    ("EQ_SWEEP_SECONDS",      ["eq", "encoder", "sweep_seconds"]),
    ("EQ_ENCODER_CURVE_EXP",  ["eq", "encoder", "curve_exp"]),
    ("EQ_SMOOTHING_FACTOR",   ["eq", "encoder", "smoothing_factor"]),
    ("EQ_AXIS_DEAD_ZONE",     ["eq", "encoder", "dead_zone"]),

    # EQ dominance
    ("EQ_DOMINANCE_RATIO",    ["eq", "dominance", "ratio"]),

    # EQ flick
    ("EQ_FLICK_EXTREME",      ["eq", "flick", "extreme"]),
    ("EQ_FLICK_RETURN",       ["eq", "flick", "return_threshold"]),
    ("EQ_FLICK_TIMEOUT_MS",   ["eq", "flick", "timeout_ms"]),

    # EQ detent
    ("EQ_DETENT_RANGE",       ["eq", "detent", "range"]),
    ("EQ_DETENT_MIN_FACTOR",  ["eq", "detent", "min_factor"]),

    # EQ OSC
    ("EQ_WRITE_THROTTLE",     ["eq", "osc", "write_throttle"]),
    ("EQ_WRITE_EPSILON",      ["eq", "osc", "write_epsilon"]),

    # EQ ramp
    ("EQ_RAMP_MIN_MS",        ["eq", "ramp", "min_ms"]),
    ("EQ_RAMP_MAX_MS",        ["eq", "ramp", "max_ms"]),

    # EQ safety
    ("EQ_BASS_BOOST_CAP",     ["eq", "safety", "bass_boost_cap"]),
    ("EQ_BOOST_PCT",          ["eq", "safety", "mid_high_boost_pct"]),

    # TRIM
    ("TRIM_SWEEP_SECONDS",    ["trim", "sweep_seconds"]),
    ("TRIM_CURVE_EXP",        ["trim", "curve_exp"]),
    ("TRIM_SMOOTHING_FACTOR", ["trim", "smoothing_factor"]),
    ("TRIM_DEAD_ZONE",        ["trim", "dead_zone"]),
    ("TRIM_MAX_DB",           ["trim", "max_db"]),
    ("TRIM_WRITE_THROTTLE",   ["trim", "write_throttle"]),
    ("TRIM_WRITE_EPSILON",    ["trim", "write_epsilon"]),
    ("TRIM_DETENT_RANGE",     ["trim", "detent_range"]),
    ("TRIM_DETENT_MIN_FACTOR", ["trim", "detent_min_factor"]),

    # Meter
    ("METER_REFERENCE_OFFSET_DB",  ["meter", "reference_offset_db"]),
    ("METER_RELEASE_DB_PER_SEC",   ["meter", "release_db_per_sec"]),
    ("METER_PEAK_HOLD_SECONDS",    ["meter", "peak_hold_seconds"]),
    ("METER_PEAK_FALL_DB_PER_SEC", ["meter", "peak_fall_db_per_sec"]),

    # Meter clip
    ("METER_CLIP_WARN_DB",         ["meter", "clip", "warn_db"]),
    ("METER_CLIP_CRITICAL_DB",     ["meter", "clip", "critical_db"]),
    ("METER_CLIP_FLICKER_HZ",      ["meter", "clip", "flicker_hz"]),
    ("METER_CLIP_FADEOUT_SECONDS", ["meter", "clip", "fadeout_seconds"]),

    # FX
    ("FX_FILTER_FREQ_SWEEP_S", ["fx", "filter_freq_sweep_s"]),
    ("FX_FILTER_RES_SWEEP_S",  ["fx", "filter_res_sweep_s"]),
    ("FX_REVERB_SIZE_SWEEP_S", ["fx", "reverb_size_sweep_s"]),
    ("FX_SEND_SWEEP_S",        ["fx", "fx_send_sweep_s"]),
    ("FX_DEFAULT_SWEEP_S",     ["fx", "default_sweep_s"]),
    ("FX_AXIS_DEAD_ZONE",      ["fx", "axis_dead_zone"]),
    ("FX_ACCEL_RAMP_S",        ["fx", "accel_ramp_s"]),
    ("FX_ACCEL_MAX_MULT",      ["fx", "accel_max_mult"]),
    ("FX_WRITE_THROTTLE",      ["fx", "write_throttle"]),
    ("FX_WRITE_EPSILON_FRAC",  ["fx", "write_epsilon_frac"]),

    # FX delay FB
    ("FX_DELAY_FB_STEPS",      ["fx", "delay_fb", "steps"]),
    ("FX_DELAY_FB_CLAMP_FRAC", ["fx", "delay_fb", "clamp_frac"]),
    ("FX_DELAY_FB_DEBOUNCE",   ["fx", "delay_fb", "debounce_s"]),

    # Volume
    ("VOL_DEAD_ZONE",        ["volume", "dead_zone"]),
    ("VOL_SENSITIVITY",      ["volume", "sensitivity"]),
    ("ABLETON_UNITY",        ["volume", "ableton_unity"]),
    ("VOL_CHANGE_THRESHOLD", ["volume", "change_threshold"]),

    # Navigation
    ("ANALOG_THRESHOLD",  ["navigation", "analog_threshold"]),
    ("HOLD_SCROLL_DELAY", ["navigation", "hold_scroll_delay"]),
    ("HOLD_SCROLL_RATE",  ["navigation", "hold_scroll_rate"]),
    ("SMOOTHING_FACTOR",  ["navigation", "smoothing_factor"]),
    ("DPAD_DEBOUNCE",     ["navigation", "dpad_debounce"]),

    # Timing
    ("R3_DOUBLE_CLICK_WINDOW",    ["timing", "r3_double_click_window"]),
    ("QUERY_DEFER_TIME",          ["timing", "query_defer_time"]),
    ("FX_SAFETY_POLL_INTERVAL",   ["timing", "fx_safety_poll_interval"]),
    ("WATCHDOG_INTERVAL",         ["timing", "watchdog_interval"]),
    ("IDLE_REPROBE_AFTER",        ["timing", "idle_reprobe_after"]),
    ("SELECT_RECONCILE_INTERVAL", ["timing", "select_reconcile_interval"]),

    # UI (RESTART)
    ("UI_REFRESH_MS",   ["ui", "refresh_ms"]),
    ("BLINK_PERIOD_MS", ["ui", "blink_period_ms"]),
    ("WINDOW_WIDTH",    ["ui", "window_width"]),
    ("WINDOW_HEIGHT",   ["ui", "window_height"]),

    # Network (RESTART)
    ("OSC_HOST",         ["network", "osc_host"]),
    ("OSC_SEND_PORT",    ["network", "osc_send_port"]),
    ("OSC_RECEIVE_PORT", ["network", "osc_receive_port"]),

    # ─── Diagnostics (NEW in Build B) ───
    # Master controls
    ("DIAG_ENABLED",                ["diagnostics", "enabled"]),
    ("DIAG_LOG_PATH",               ["diagnostics", "log_path"]),
    ("DIAG_JSONL_PATH",             ["diagnostics", "jsonl_path"]),
    ("DIAG_SUMMARY_INTERVAL_S",     ["diagnostics", "summary_interval_s"]),
    ("DIAG_SAMPLE_INTERVAL_S",      ["diagnostics", "sample_interval_s"]),
    ("DIAG_SLOW_FUNCTION_MS",       ["diagnostics", "slow_function_threshold_ms"]),
    ("DIAG_SLOW_FRAME_MS",          ["diagnostics", "slow_frame_threshold_ms"]),
    ("DIAG_OSC_WINDOW_S",           ["diagnostics", "osc_traffic_window_s"]),
    ("DIAG_JSONL_FORMAT",           ["diagnostics", "jsonl_format"]),
    ("DIAG_JSONL_INCLUDE_OSC_ARGS", ["diagnostics", "jsonl_include_osc_args"]),

    # Warnings
    ("DIAG_WARN_CLIP_RATE_PER_MIN", ["diagnostics", "warnings", "clip_event_rate_per_min"]),
    ("DIAG_WARN_OSC_SEND_PER_SEC",  ["diagnostics", "warnings", "osc_send_rate_per_sec"]),
    ("DIAG_WARN_OSC_RECV_PER_SEC",  ["diagnostics", "warnings", "osc_recv_rate_per_sec"]),
    ("DIAG_WARN_SINGLE_CALL_MS",    ["diagnostics", "warnings", "single_call_warn_ms"]),
    ("DIAG_WARN_CPU_PERCENT",       ["diagnostics", "warnings", "cpu_warn_percent"]),
    ("DIAG_WARN_MEMORY_GROWTH_MB",  ["diagnostics", "warnings", "memory_growth_warn_mb"]),
    ("DIAG_WARN_THREAD_MISS_FRAC",  ["diagnostics", "warnings", "thread_miss_warn_fraction"]),

    # Rate limiting
    ("DIAG_RL_ENABLED",               ["diagnostics", "rate_limit", "enabled"]),
    ("DIAG_RL_CLIP_NOTIF_PER_MIN",    ["diagnostics", "rate_limit", "clip_notifications_per_min"]),
    ("DIAG_RL_OSC_PER_ADDR_PER_SEC",  ["diagnostics", "rate_limit", "osc_sends_per_address_per_sec"]),
    ("DIAG_RL_COOLDOWN_S",            ["diagnostics", "rate_limit", "cooldown_s"]),

    # Hooks (RESTART)
    ("DIAG_TIMED_FUNCTIONS",         ["diagnostics", "hooks", "timed_functions"]),
    ("DIAG_TRACK_ALL_OSC_SENDS",     ["diagnostics", "hooks", "track_all_osc_sends"]),
    ("DIAG_TRACK_ALL_OSC_RECEIVES",  ["diagnostics", "hooks", "track_all_osc_receives"]),
    ("DIAG_TRACKED_OSC_ADDRESSES",   ["diagnostics", "hooks", "tracked_osc_addresses"]),
]


# ═══════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _nested_get(d: dict, path: list):
    cur = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def _apply_toml(toml_data: dict) -> dict:
    changes = {}
    for attr, path in _CFG_MAP:
        value = _nested_get(toml_data, path)
        if value is None:
            continue
        current = getattr(cfg, attr)
        if value != current:
            setattr(cfg, attr, value)
            changes[attr] = (current, value)
    return changes


# ═══════════════════════════════════════════════════════════════════════════
#  FIRST-RUN SEEDING
# ═══════════════════════════════════════════════════════════════════════════

def _ensure_active_toml_exists() -> bool:
    active = _get_active_path()
    if active.exists():
        return False
    default = _get_default_path()
    if not default.exists():
        log.warning(
            "Neither config/active.toml nor config/default.toml exists. "
            "Running with hardcoded defaults from src/config.py."
        )
        return False
    try:
        shutil.copy2(default, active)
        log.info(f"First-run: created {active.name} from {default.name}")
        return True
    except Exception as e:
        log.error(f"Failed to seed active.toml from default.toml: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════

def init_config():
    log.info("Loading configuration…")
    _ensure_active_toml_exists()
    active = _get_active_path()
    if not active.exists():
        log.warning(f"No config file at {active}. Using hardcoded defaults.")
        return
    try:
        with open(active, "rb") as f:
            toml_data = tomllib.load(f)
        changes = _apply_toml(toml_data)
        log.info(f"Config loaded from {active} — {len(changes)} values overridden from defaults")
    except tomllib.TOMLDecodeError as e:
        log.error(
            f"Config file {active} has a syntax error: {e}. "
            f"Using hardcoded defaults. Fix the file and restart or reload."
        )
    except Exception as e:
        log.error(
            f"Unexpected error loading config: {e}. Using hardcoded defaults."
        )


def reload_config() -> dict:
    result = {
        "success": False,
        "error": None,
        "changes_applied": [],
        "restart_required": [],
    }

    active = _get_active_path()
    if not active.exists():
        result["error"] = f"Config file not found: {active.name}"
        log.warning(f"Reload failed — {result['error']}")
        return result

    try:
        with open(active, "rb") as f:
            toml_data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        result["error"] = f"TOML syntax error: {e}"
        log.warning(f"Reload failed — {result['error']} — keeping current values")
        return result
    except Exception as e:
        result["error"] = f"Unexpected error: {e}"
        log.warning(f"Reload failed — {result['error']} — keeping current values")
        return result

    changes = _apply_toml(toml_data)

    for attr, (old, new) in changes.items():
        change_tuple = (attr, old, new)
        if attr in _RESTART_REQUIRED_ATTRS:
            result["restart_required"].append(change_tuple)
            log.info(f"Reload: {attr} {old} → {new}  [RESTART REQUIRED to take effect]")
        else:
            result["changes_applied"].append(change_tuple)
            log.info(f"Reload: {attr} {old} → {new}  [applied]")

    result["success"] = True

    if not changes:
        log.info("Reload: no changes detected")
    else:
        log.info(
            f"Reload complete — {len(result['changes_applied'])} applied, "
            f"{len(result['restart_required'])} require restart"
        )

    return result


def get_summary() -> str:
    lines = ["Current config:"]
    for attr, _ in _CFG_MAP:
        value = getattr(cfg, attr, "?")
        marker = "  [RESTART]" if attr in _RESTART_REQUIRED_ATTRS else ""
        lines.append(f"  {attr:32} = {value}{marker}")
    return "\n".join(lines)