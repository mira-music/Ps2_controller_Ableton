"""
================================================================================
  src/diagnostics/installer.py — Monkey-Patch Hook Installer
================================================================================
  Installs all diagnostic observation hooks WITHOUT modifying any source
  files outside src/diagnostics/. Called once by install_if_enabled() in
  __init__.py when cfg.DIAG_ENABLED is True.

  What it installs:
    1. Profiler — instantiate, attach to diag singleton
    2. Counters — instantiate, attach
    3. OSC tracker — instantiate, attach
    4. System sampler — instantiate, START background thread, attach
    5. Thread health monitor — instantiate, attach
    6. Rate limiter — instantiate, register limits from config, attach
    7. Reporter — instantiate, START background thread, attach
    8. Function timing wrappers — for each entry in DIAG_TIMED_FUNCTIONS,
       monkey-patch the named function with a timing shim
    9. OSC client send wrapper — wraps st.osc.send_message
    10. OSC server dispatch wrapper — wraps every handler in the dispatcher
    11. Thread tick hooks — wraps the loop functions in controller, polling,
        eq_ramp, watchdog so they call thread_health.tick() each iteration

  How monkey-patching works:
    For a function "src.ui.updater.update_ui", we:
      1. Import src.ui.updater
      2. Save the original function reference
      3. Define a wrapper that times the call and forwards arguments
      4. Replace src.ui.updater.update_ui = wrapper

    When main.py later calls root.after(UI_REFRESH_MS, update_ui, root, lbl),
    Python looks up update_ui in the namespace and finds the wrapper.
    Wrapper measures, calls the original, returns the result.
    Original code never knew anything happened.

  Failure handling:
    Every install step is wrapped in try/except. If a hook fails to install
    (typo in function name, module not loaded yet, etc.) the error is
    logged and other hooks still install. A single bad hook never blocks
    the rest.

  Hook target resolution:
    DIAG_TIMED_FUNCTIONS contains strings like "src.engine.eq.eq_drive_continuous_encoder".
    We split on the rightmost "." to get module_path and function_name,
    then importlib.import_module(module_path) and getattr(module, function_name).

  OSC dispatch wrapping:
    The OSC server uses pythonosc.dispatcher.Dispatcher. Each handler is
    stored internally in the dispatcher's address-to-handler mapping. We
    have to wait until start_osc_server() has populated this mapping
    before we can wrap the handlers. The installer uses a delayed-install
    mechanism: it schedules the OSC server wrapping to happen ~1 second
    after install() returns, by which point the OSC server thread has
    started and registered all handlers.

  OSC client wrapping:
    Similar timing issue. setup_osc() creates st.osc as a SimpleUDPClient.
    We wrap st.osc.send_message after a short delay.
================================================================================
"""

import importlib
import sys
import time
import threading
import functools
from typing import Optional

from src.config_loader import cfg
from src.diagnostics import diag
from src.diagnostics.profiler import Profiler
from src.diagnostics.counters import Counters
from src.diagnostics.osc_tracker import OSCTracker
from src.diagnostics.sampler import SystemSampler, _PSUTIL_AVAILABLE
from src.diagnostics.thread_health import ThreadHealth, KNOWN_THREAD_TARGETS
from src.diagnostics.rate_limiter import RateLimiter


# Use the project's logging system (writes to logs/fxmachine.log alongside
# the main app logs). Diagnostics-specific messages still go to the
# diagnostics log via the reporter.
from src.log_setup import get_logger
log = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
#  HOOK INSTALLATION TRACKING
#
#  After install() runs, we keep references to the original functions so
#  the rest of the app can still find them (though nothing currently uses
#  this — it's there for potential future uninstall/reinstall support).
# ═══════════════════════════════════════════════════════════════════════════

# Map of "module.path.function" → original callable (pre-wrap)
_original_functions: dict[str, object] = {}

# Map of "module.path.function" → wrapper callable (post-wrap)
_installed_wrappers: dict[str, object] = {}

# Reference to original st.osc.send_message (for potential uninstall)
_original_osc_send = None

# Original OSC dispatcher handlers, keyed by address
_original_osc_handlers: dict = {}


# ═══════════════════════════════════════════════════════════════════════════
#  TIMING WRAPPER FACTORY
# ═══════════════════════════════════════════════════════════════════════════

def _make_timed_wrapper(name: str, original):
    """
    Create a timing-wrapper around an arbitrary callable.

    The wrapper:
      1. Records start time (perf_counter_ns, monotonic, ~ns precision)
      2. Calls original with all args/kwargs
      3. Records elapsed time
      4. Sends elapsed to profiler
      5. Returns whatever original returned

    If profiler.record() raises (shouldn't, but defensive), the exception
    is swallowed and original's return value is still returned. Diagnostics
    must never break the host code.

    Uses functools.wraps so the wrapper looks like the original to any
    introspection tool (e.g. help(), inspect.signature()).
    """

    @functools.wraps(original)
    def _wrapped(*args, **kwargs):
        start_ns = time.perf_counter_ns()
        try:
            return original(*args, **kwargs)
        finally:
            elapsed_ns = time.perf_counter_ns() - start_ns
            try:
                if diag.profiler is not None:
                    diag.profiler.record(name, elapsed_ns)
            except Exception:
                # Swallow — never let diagnostics crash the wrapped fn
                pass

    return _wrapped


def _install_function_hook(qualified_name: str) -> bool:
    """
    Wrap one function by its dotted path.

    CRITICAL: Also replaces the reference in every other loaded module that
    previously imported this function via `from X import Y`. Without this
    pass, the wrapper only intercepts calls that go through the original
    module (e.g. `src.ui.widgets.draw_djm_meter`), but most callers use
    `from src.ui.widgets import draw_djm_meter` which creates a local
    name in the caller's namespace pointing to the original function.

    Args:
        qualified_name: e.g. "src.ui.updater.update_ui"

    Returns:
        True on success, False on any failure (logged).
    """
    if "." not in qualified_name:
        log.warning(f"[diag.installer] invalid hook target '{qualified_name}' — no dot")
        return False

    module_path, func_name = qualified_name.rsplit(".", 1)

    # Import the target module
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        log.warning(f"[diag.installer] cannot import {module_path} for hook: {e}")
        return False

    # Get the function
    original = getattr(module, func_name, None)
    if original is None:
        log.warning(f"[diag.installer] {module_path} has no attribute '{func_name}'")
        return False

    if not callable(original):
        log.warning(f"[diag.installer] {qualified_name} is not callable")
        return False

    # Avoid double-wrapping
    if qualified_name in _installed_wrappers:
        log.debug(f"[diag.installer] {qualified_name} already wrapped, skipping")
        return True

    # Create wrapper
    wrapper = _make_timed_wrapper(qualified_name, original)

    # ── PRIMARY PATCH: replace on the origin module ─────────────────────
    try:
        setattr(module, func_name, wrapper)
    except Exception as e:
        log.warning(f"[diag.installer] cannot patch {qualified_name}: {e}")
        return False

    _original_functions[qualified_name] = original
    _installed_wrappers[qualified_name] = wrapper

    # ── CROSS-MODULE PATCH: replace references in importer modules ──────
    # Walk every currently-loaded module and find any attribute that
    # references the ORIGINAL function. Replace those references with the
    # wrapper. This catches `from src.ui.widgets import draw_djm_meter`
    # style imports where the caller has its own name pointing to the
    # original function object — by-identity comparison (`is`) ensures
    # we only patch the exact function, not other functions with the
    # same name.
    #
    # Skip the origin module itself (already patched above) and skip
    # the diagnostics package (don't patch our own infrastructure).
    importer_patches = 0
    for mod_name, mod_obj in list(sys.modules.items()):
        if mod_obj is None:
            continue
        if mod_obj is module:
            continue
        if mod_name.startswith("src.diagnostics"):
            continue

        # Walk the module's attribute dict looking for references to original
        try:
            mod_dict = vars(mod_obj)
        except TypeError:
            continue

        for attr_name, attr_value in list(mod_dict.items()):
            if attr_value is original:
                try:
                    setattr(mod_obj, attr_name, wrapper)
                    importer_patches += 1
                    log.debug(
                        f"[diag.installer]   also patched {mod_name}.{attr_name} "
                        f"(was importing {qualified_name})"
                    )
                except Exception:
                    # Read-only attribute, frozen module, etc. — skip silently
                    pass

    log.debug(
        f"[diag.installer] hooked {qualified_name} "
        f"(origin + {importer_patches} importer module(s))"
    )
    return True
    """
    Wrap one function by its dotted path.

    Args:
        qualified_name: e.g. "src.ui.updater.update_ui"

    Returns:
        True on success, False on any failure (logged).
    """
    if "." not in qualified_name:
        log.warning(f"[diag.installer] invalid hook target '{qualified_name}' — no dot")
        return False

    module_path, func_name = qualified_name.rsplit(".", 1)

    # Import the target module
    try:
        module = importlib.import_module(module_path)
    except Exception as e:
        log.warning(f"[diag.installer] cannot import {module_path} for hook: {e}")
        return False

    # Get the function
    original = getattr(module, func_name, None)
    if original is None:
        log.warning(f"[diag.installer] {module_path} has no attribute '{func_name}'")
        return False

    if not callable(original):
        log.warning(f"[diag.installer] {qualified_name} is not callable")
        return False

    # Avoid double-wrapping
    if qualified_name in _installed_wrappers:
        log.debug(f"[diag.installer] {qualified_name} already wrapped, skipping")
        return True

    # Create wrapper and replace
    wrapper = _make_timed_wrapper(qualified_name, original)
    try:
        setattr(module, func_name, wrapper)
    except Exception as e:
        log.warning(f"[diag.installer] cannot patch {qualified_name}: {e}")
        return False

    _original_functions[qualified_name] = original
    _installed_wrappers[qualified_name] = wrapper
    log.debug(f"[diag.installer] hooked {qualified_name}")
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  OSC CLIENT WRAPPER
# ═══════════════════════════════════════════════════════════════════════════

def _install_osc_client_hook():
    """
    Wrap st.osc.send_message to record every outbound OSC message.

    st.osc is set by setup_osc() in main.py, which runs BEFORE
    install_if_enabled() is called from run.py. So by the time we get
    here, st.osc should already exist.

    Defensive: if st.osc is None or send_message is missing, log and skip.
    """
    global _original_osc_send

    try:
        from src import state as st
    except Exception as e:
        log.warning(f"[diag.installer] cannot import src.state for OSC hook: {e}")
        return

    if st.osc is None:
        log.warning("[diag.installer] st.osc is None — OSC client hook skipped. "
                    "Was setup_osc() called before install_if_enabled()?")
        return

    if not hasattr(st.osc, "send_message"):
        log.warning("[diag.installer] st.osc has no send_message method — skipped")
        return

    if _original_osc_send is not None:
        log.debug("[diag.installer] OSC client already hooked")
        return

    _original_osc_send = st.osc.send_message

    def _wrapped_send(address, value=None):
        """
        Wrapper that records the send before forwarding.

        SimpleUDPClient.send_message has signature (address, value=None).
        We don't measure the actual UDP send time because it's microseconds
        and not interesting. We just count it and record the address.

        Payload size estimation: if value is a list/tuple we estimate
        based on element count; otherwise estimate as 0 (we don't have
        cheap access to the serialized OSC packet size).
        """
        # Estimate payload size cheaply (just the value count, not bytes)
        payload_bytes = 0
        if isinstance(value, (list, tuple)):
            payload_bytes = len(value) * 4   # rough estimate: 4 bytes per arg
        elif value is not None:
            payload_bytes = 4

        # Rate limiting check (per-address)
        if diag.rate_limiter is not None and diag.rate_limiter.is_enabled():
            if not diag.rate_limiter.should_allow_keyed("osc_per_address", address):
                # Suppressed by rate limit. Record the suppression as a counter.
                if diag.counters is not None:
                    diag.counters.increment("osc_sends_suppressed_by_rate_limit")
                # Do NOT forward to the real send_message — drop the message.
                return

        try:
            if diag.osc_tracker is not None:
                diag.osc_tracker.record_send(address, payload_bytes)
        except Exception:
            pass

        return _original_osc_send(address, value)

    try:
        st.osc.send_message = _wrapped_send
        log.info("[diag.installer] OSC client send_message wrapped")
    except Exception as e:
        log.warning(f"[diag.installer] failed to install OSC client hook: {e}")
        _original_osc_send = None


# ═══════════════════════════════════════════════════════════════════════════
#  OSC SERVER DISPATCHER WRAPPER
# ═══════════════════════════════════════════════════════════════════════════

def _install_osc_server_hook():
    """
    Wrap every handler registered in the OSC dispatcher so each
    incoming message is counted.

    The OSC server is started in main.py as a daemon thread that calls
    start_osc_server(), which creates the Dispatcher, registers handlers,
    then calls server.serve_forever(). The dispatcher is held by the
    server object as server.dispatcher.

    Timing: the OSC server thread is started before install_if_enabled()
    in run.py, but server.dispatcher and st._osc_server may not be set
    until start_osc_server() has actually run. We retry up to 5 seconds
    waiting for st._osc_server to be populated.

    pythonosc Dispatcher internals:
      - dispatcher._map is the address-to-handler dict
      - dispatcher._default_handler is for unmatched addresses
    """
    try:
        from src import state as st
    except Exception as e:
        log.warning(f"[diag.installer] cannot import src.state for OSC server hook: {e}")
        return

    # Wait for OSC server to be set up (it's started in a thread, races with us)
    max_wait_s = 5.0
    waited = 0.0
    poll_interval = 0.1
    while st._osc_server is None and waited < max_wait_s:
        time.sleep(poll_interval)
        waited += poll_interval

    if st._osc_server is None:
        log.warning(
            "[diag.installer] OSC server still not ready after 5s — "
            "receive-side hooks not installed. Diagnostics will still work "
            "for outbound traffic and other metrics."
        )
        return

    server = st._osc_server
    dispatcher = getattr(server, "dispatcher", None)
    if dispatcher is None:
        log.warning("[diag.installer] OSC server has no dispatcher attribute")
        return

    # Access the internal handler map. pythonosc uses _map.
    # Each entry: address_pattern → list of Handler objects
    handler_map = getattr(dispatcher, "_map", None)
    if handler_map is None:
        log.warning("[diag.installer] dispatcher has no _map — pythonosc version mismatch?")
        return

    wrapped_count = 0
    for address_pattern, handlers in handler_map.items():
        # handlers is a list of pythonosc.dispatcher.Handler objects
        # Each Handler has a .callback attribute (the actual function)
        for handler in handlers:
            original_callback = getattr(handler, "callback", None)
            if original_callback is None:
                continue
            # Skip if already wrapped (idempotent)
            if getattr(original_callback, "__diag_wrapped__", False):
                continue

            address_str = str(address_pattern)

            def _make_receive_wrapper(addr, orig_cb):
                """Closure captures address and original handler."""
                def _wrapped_receive(received_addr, *args):
                    try:
                        if diag.osc_tracker is not None:
                            # received_addr is the actual address that matched
                            # (may be more specific than the pattern, e.g.
                            # pattern "/live/track/get/name" matches itself)
                            payload_bytes = sum(
                                len(str(a)) for a in args if a is not None
                            )
                            diag.osc_tracker.record_recv(received_addr, payload_bytes)
                    except Exception:
                        pass
                    return orig_cb(received_addr, *args)

                _wrapped_receive.__diag_wrapped__ = True
                _original_osc_handlers[addr] = orig_cb
                return _wrapped_receive

            try:
                handler.callback = _make_receive_wrapper(address_str, original_callback)
                wrapped_count += 1
            except Exception as e:
                log.warning(f"[diag.installer] cannot wrap handler for {address_str}: {e}")

    log.info(f"[diag.installer] OSC server: wrapped {wrapped_count} receive handler(s)")


# ═══════════════════════════════════════════════════════════════════════════
#  THREAD HEALTH HOOKS
#
#  We can't easily wrap entire loop functions (controller_loop, polling_loop,
#  etc.) because they're long-running. Instead we use a different strategy:
#  install a monkey patch that adds a tick() call into the loop body via
#  the same wrapper mechanism. But wrapping the loop function only
#  measures the WHOLE loop's lifetime, not per-iteration.
#
#  Solution: wrap the per-iteration sleep functions instead.
#    - controller_loop calls pygame.time.wait(8) once per iteration
#    - polling_loop calls time.sleep(0.15) once per iteration
#    - eq_ramp_loop calls time.sleep(tick_s) once per iteration
#    - watchdog_loop calls time.sleep(cfg.WATCHDOG_INTERVAL) once per iteration
#
#  But monkey-patching pygame.time.wait or time.sleep globally is invasive
#  and would affect EVERY caller, not just the loops we care about.
#
#  Better solution: leave the per-thread tick infrastructure in place but
#  don't auto-hook. Threads can call diag.record_thread_tick() voluntarily
#  if they want monitoring. For Build B we accept partial coverage:
#    - ui_loop is already hooked via update_ui wrapper (one call per frame)
#      so we manually tick "ui" from inside that wrapper.
#    - Other threads aren't auto-monitored unless user adds the call.
#
#  This trade-off is fine. The most important thread to monitor (UI) IS
#  monitored. The others can be added later if a problem appears.
# ═══════════════════════════════════════════════════════════════════════════

def _make_timed_wrapper_with_thread_tick(name: str, thread_tick_name: str, original):
    """
    Variant of _make_timed_wrapper that also calls thread_health.tick()
    on each invocation. Used specifically for the update_ui wrapper so
    we can measure UI frame rate without modifying main.py.
    """
    @functools.wraps(original)
    def _wrapped(*args, **kwargs):
        # Tick the thread health monitor first (cheap)
        try:
            if diag.thread_health is not None:
                diag.thread_health.tick(thread_tick_name)
        except Exception:
            pass

        start_ns = time.perf_counter_ns()
        try:
            return original(*args, **kwargs)
        finally:
            elapsed_ns = time.perf_counter_ns() - start_ns
            try:
                if diag.profiler is not None:
                    diag.profiler.record(name, elapsed_ns)
            except Exception:
                pass

    return _wrapped


def _install_ui_thread_tick():
    """
    Replace the update_ui wrapper (already installed by _install_function_hook
    if "src.ui.updater.update_ui" was in DIAG_TIMED_FUNCTIONS) with a version
    that also ticks the UI thread. If update_ui wasn't in the hook list,
    install a tick-only wrapper for it.
    """
    target = "src.ui.updater.update_ui"

    try:
        module = importlib.import_module("src.ui.updater")
    except Exception as e:
        log.warning(f"[diag.installer] cannot import updater for UI tick: {e}")
        return

    # If we already wrapped this function for timing, get the ORIGINAL
    # back from our saved references so we can wrap it once with the
    # combined wrapper instead of double-wrapping.
    if target in _original_functions:
        original = _original_functions[target]
    else:
        original = getattr(module, "update_ui", None)
        if original is None:
            log.warning("[diag.installer] update_ui not found — UI tick skipped")
            return
        _original_functions[target] = original

    combined_wrapper = _make_timed_wrapper_with_thread_tick(target, "ui", original)
    try:
        setattr(module, "update_ui", combined_wrapper)
        _installed_wrappers[target] = combined_wrapper
        log.info("[diag.installer] update_ui wrapped with timing + UI thread tick")
    except Exception as e:
        log.warning(f"[diag.installer] cannot install UI tick wrapper: {e}")


# ═══════════════════════════════════════════════════════════════════════════
#  MAIN INSTALL ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════

def install():
    """
    Install the full diagnostics layer.

    Called by install_if_enabled() in __init__.py when cfg.DIAG_ENABLED.
    Idempotent — calling twice is safe (re-init resets state).

    Order of operations:
      1. Create collector instances
      2. Apply configuration to collectors
      3. Start background threads (sampler, reporter)
      4. Install function hooks (uses DIAG_TIMED_FUNCTIONS list)
      5. Install OSC client hook (st.osc.send_message wrap)
      6. Schedule OSC server hook (delayed — waits for server thread)
      7. Install UI thread tick
      8. Log a summary of what was installed
    """
    log.info("=" * 64)
    log.info("[diag.installer] Installing diagnostics layer…")
    log.info(f"[diag.installer] psutil available: {_PSUTIL_AVAILABLE}")

    # ── 1. Create collectors ────────────────────────────────────────────
    diag.profiler = Profiler(window_size=1000)
    diag.profiler.set_outlier_threshold_ms(cfg.DIAG_SLOW_FUNCTION_MS)

    diag.counters = Counters(default_window_s=60.0)

    diag.osc_tracker = OSCTracker(
        window_s=cfg.DIAG_OSC_WINDOW_S,
        track_all_sends=cfg.DIAG_TRACK_ALL_OSC_SENDS,
        track_all_receives=cfg.DIAG_TRACK_ALL_OSC_RECEIVES,
        tracked_addresses=cfg.DIAG_TRACKED_OSC_ADDRESSES,
    )

    diag.sampler = SystemSampler(
        interval_s=cfg.DIAG_SAMPLE_INTERVAL_S,
        buffer_size=600,
    )

    diag.thread_health = ThreadHealth(window_s=10.0)

    diag.rate_limiter = RateLimiter(enabled=cfg.DIAG_RL_ENABLED)
    # Register configured limits
    if cfg.DIAG_RL_CLIP_NOTIF_PER_MIN > 0:
        diag.rate_limiter.register_limit(
            "clip_notifications",
            max_per_window=cfg.DIAG_RL_CLIP_NOTIF_PER_MIN,
            window_s=60.0,
            cooldown_s=cfg.DIAG_RL_COOLDOWN_S,
        )
    if cfg.DIAG_RL_OSC_PER_ADDR_PER_SEC > 0:
        diag.rate_limiter.register_keyed_limit(
            "osc_per_address",
            max_per_window=cfg.DIAG_RL_OSC_PER_ADDR_PER_SEC,
            window_s=1.0,
            cooldown_s=cfg.DIAG_RL_COOLDOWN_S,
        )

    log.info("[diag.installer] Collectors instantiated")

    # ── 2. Start background sampler ─────────────────────────────────────
    try:
        diag.sampler.start()
        log.info(f"[diag.installer] Sampler started (interval {cfg.DIAG_SAMPLE_INTERVAL_S}s)")
    except Exception as e:
        log.warning(f"[diag.installer] sampler start failed: {e}")

    # ── 3. Install function timing hooks ────────────────────────────────
    hook_targets = list(cfg.DIAG_TIMED_FUNCTIONS)
    installed = 0
    failed = 0
    for target in hook_targets:
        if _install_function_hook(target):
            installed += 1
        else:
            failed += 1
    log.info(
        f"[diag.installer] Function hooks: {installed} installed, {failed} failed "
        f"(of {len(hook_targets)} requested)"
    )

    # ── 4. UI thread tick (must come AFTER update_ui is wrapped) ────────
    _install_ui_thread_tick()

    # ── 5. OSC client hook (deferred — waits for setup_osc() to run) ────
    def _deferred_osc_client_install():
        # Poll for st.osc to become available, up to 5 seconds
        from src import state as st
        for _ in range(50):
            if st.osc is not None:
                break
            time.sleep(0.1)
        _install_osc_client_hook()

    osc_client_thread = threading.Thread(
        target=_deferred_osc_client_install,
        name="diag.installer.osc_client",
        daemon=True,
    )
    osc_client_thread.start()
    log.info("[diag.installer] OSC client hook installation scheduled (background)")

    # ── 6. OSC server hook (deferred — runs in its own thread to wait
    #       for the server dispatcher to be ready) ────────────────────────
    def _deferred_osc_server_install():
        _install_osc_server_hook()

    osc_server_thread = threading.Thread(
        target=_deferred_osc_server_install,
        name="diag.installer.osc",
        daemon=True,
    )
    osc_server_thread.start()
    log.info("[diag.installer] OSC server hook installation scheduled (background)")

    # ── 7. Reporter (started last so initial setup is logged once) ──────
    # Import reporter here, not at module load, because reporter imports
    # diag and we don't want a circular at install time.
    try:
        from src.diagnostics.reporter import Reporter
        diag.reporter = Reporter(
            log_path=cfg.DIAG_LOG_PATH,
            jsonl_path=cfg.DIAG_JSONL_PATH,
            summary_interval_s=cfg.DIAG_SUMMARY_INTERVAL_S,
        )
        diag.reporter.start()
        log.info(f"[diag.installer] Reporter started "
                 f"(summary every {cfg.DIAG_SUMMARY_INTERVAL_S}s)")
    except Exception as e:
        log.warning(f"[diag.installer] reporter start failed: {e}")

    log.info("[diag.installer] Diagnostics installation complete")
    log.info("=" * 64)


def get_install_summary() -> dict:
    """Return summary of what's been installed. Used by reporter."""
    return {
        "functions_wrapped": len(_installed_wrappers),
        "osc_handlers_wrapped": len(_original_osc_handlers),
        "osc_client_wrapped": _original_osc_send is not None,
        "sampler_running": diag.sampler.is_running() if diag.sampler else False,
        "psutil_available": _PSUTIL_AVAILABLE,
    }