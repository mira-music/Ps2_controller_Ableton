##  docs/ARCHITECTURE.md

```markdown
# 🏗️ FX Machine — Architecture Deep Dive

## What This Document Covers

This guide explains how FX Machine works internally — the 5-thread
coordination model, the shared state system, the lock strategy, the
OSC communication lifecycle, the listener-based architecture, the
UI rendering pipeline, and the shutdown sequencing. Every design
decision is explained with the reasoning behind it.

If you're modifying the codebase, adding features, or debugging a
concurrency issue, this is the document you need. If you're just
using FX Machine to perform, you don't need any of this — the app
handles it all for you.

---

## Table of Contents

1. [System Overview](#system-overview)
2. [The 5-Thread Model](#the-5-thread-model)
3. [Thread Lifecycle and Startup Sequence](#thread-lifecycle-and-startup-sequence)
4. [Shared State Architecture](#shared-state-architecture)
5. [The Lock Strategy — Three Rules](#the-lock-strategy--three-rules)
6. [The State Snapshot Pattern](#the-state-snapshot-pattern)
7. [OSC Communication Architecture](#osc-communication-architecture)
8. [Listener-Based Architecture](#listener-based-architecture)
9. [The OSC Roundtrip — From Stick to Sound](#the-osc-roundtrip--from-stick-to-sound)
10. [The Session Discovery Handshake](#the-session-discovery-handshake)
11. [The Config Singleton Pattern](#the-config-singleton-pattern)
12. [The TOML Hot-Reload System](#the-toml-hot-reload-system)
13. [The UI Rendering Pipeline](#the-ui-rendering-pipeline)
14. [The Dirty-Cache Pattern](#the-dirty-cache-pattern)
15. [The PhotoImage Meter — Why and How](#the-photoimage-meter--why-and-how)
16. [The Diagnostics Integration](#the-diagnostics-integration)
17. [Shutdown Sequencing](#shutdown-sequencing)
18. [Error Recovery Model](#error-recovery-model)
19. [Module Dependency Graph](#module-dependency-graph)
20. [Thread Communication Patterns](#thread-communication-patterns)
21. [Memory Model](#memory-model)
22. [Latency Budget](#latency-budget)
23. [Concurrency Hazards and Mitigations](#concurrency-hazards-and-mitigations)
24. [Adding a New Feature — Where Things Go](#adding-a-new-feature--where-things-go)
25. [Why Not X — Design Alternatives Considered](#why-not-x--design-alternatives-considered)

---

## System Overview

FX Machine is a bridge between a USB gamepad and Ableton Live. The
gamepad provides physical input (sticks, buttons, D-pad). Ableton
provides the audio engine and parameter control. FX Machine sits
in the middle and translates one into the other via OSC (Open Sound
Control), while presenting a visual UI that reflects the current state.

```
┌────────────┐     USB      ┌─────────────────┐     OSC/UDP     ┌──────────────┐
│  USB       │ ──────────── │   FX Machine    │ ──────────────── │  Ableton     │
│  Gamepad   │   pygame     │   (Python)      │  localhost:     │  Live        │
│            │   events     │                 │  11000 (send)   │  + AbletonOSC│
│  2 sticks  │              │  5 threads      │  11001 (recv)   │              │
│  12 buttons│              │  1 UI window    │                 │  Audio       │
│  1 D-pad   │              │  1 state dict   │                 │  engine      │
│            │              │  1 config file  │                 │              │
└────────────┘              └─────────────────┘                 └──────────────┘
```

The data flow is bidirectional:

**Outbound (gamepad → Ableton):**
Stick moves → axis value → gesture engine processes → OSC message sent → Ableton parameter changes → audio changes

**Inbound (Ableton → UI):**
Audio plays → Ableton computes levels → AbletonOSC sends meter data → OSC received → state updated → UI redraws

Both directions happen simultaneously, continuously, at different
rates, in different threads. The architecture exists to make this
work reliably without race conditions, deadlocks, or dropped data.

---

## The 5-Thread Model

FX Machine runs 5 daemon threads plus the main thread (Tkinter UI).
Each thread has a specific responsibility and runs at a specific
frequency.

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   MAIN THREAD (Tkinter UI, ~40 Hz)                              │
│   ├─ Owns the Tkinter root window                               │
│   ├─ Reads state snapshot under lock every 25 ms                 │
│   ├─ Renders knobs, meters, labels via dirty-cache pattern       │
│   ├─ Schedules itself via root.after()                           │
│   └─ Runs on_close() when user closes the window                │
│                                                                 │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     │  reads/writes state[*] via st._lock
                     │
                     ▼
              ┌─────────────────────┐
              │  shared state dict  │
              │  protected by RLock │
              └─────────────────────┘
                ▲    ▲    ▲    ▲    ▲
                │    │    │    │    │
┌───────────────┘    │    │    │    └───────────────┐
│                    │    │    │                    │
│  Controller        │    │    │         Watchdog   │
│  Thread            │    │    │         Thread     │
│  ~125 Hz           │    │    │         ~1 Hz      │
│                    │    │    │                    │
│  pygame.event      │    │    │  Controller       │
│  .get() polling    │    │    │  health checks    │
│  Gesture engine    │    │    │  Ghost-event      │
│  Button dispatch   │    │    │  reconciliation   │
│  Axis processing   │    │    │  Auto-reprobe     │
│  D-pad routing     │    │    │  after idle       │
│                    │    │    │                    │
└────────────────────┘    │    └────────────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
   OSC Server Thread          Polling Thread
   (event-driven)             ~2 Hz
                              
   pythonosc                  Safety re-polls
   ThreadingOSC               FX/EQ macro values
   UDPServer                  (listener-driven
                               values don't need
   Receives from               polling anymore)
   Ableton and                
   updates state              Deferred position
                               queries after
   Dispatches to               navigation
   on_* handlers              
                              Session size
                               change detection

              + EQ Ramp Thread (~60 Hz)
                Animates kill/normalize/boost
                Cubic ease-out value transitions
                Runs independently of UI thread
```

### Why these specific threads?

**Controller (125 Hz):** pygame events must be polled — there's no
callback mechanism. 125 Hz (8ms sleep) is the sweet spot: higher
frequencies don't improve perceived responsiveness (humans can't
distinguish 8ms from 4ms latency on a stick), lower frequencies cause
visible stutter on fast flicks.

**OSC Server (event-driven):** pythonosc's `ThreadingOSCUDPServer`
spawns its own thread(s) internally to handle incoming UDP packets.
We start it and let it run. Each incoming message dispatches to our
`on_*` handler functions which update shared state under lock.

**Polling (2 Hz):** Originally ran at 6.6 Hz and polled Ableton for
tempo, transport, volume, and session counts every iteration. In
v1.0.0, those values are pushed via listeners, so polling now serves
as a safety net — catching drift from missed listener events and
handling deferred position queries. 2 Hz is sufficient for this role.

**EQ Ramp (60 Hz):** When a double-flick gesture fires (kill, normalize,
boost, restore), the target value doesn't snap — it animates via cubic
ease-out over 30-100ms. The ramp thread drives this animation at 60 Hz
(16ms tick), which is smooth enough to look fluid and high enough to not
miss the short ramp durations.

**Watchdog (1 Hz):** Checks whether the controller is still connected.
If the gamepad goes silent for 5+ seconds, performs a soft check; if
that fails, does a full pygame.joystick reprobe. Also reconciles ghost
SELECT button-up events that pygame sometimes drops.

### Why not more threads? Why not fewer?

**Why not one thread?** Single-threaded would mean the UI freezes during
OSC communication, or the controller stops responding during UI redraws.
The 20ms latency budget for stick-to-sound doesn't allow for blocking
I/O in the input path.

**Why not two threads (input + UI)?** You'd still need the ramp
animation to run independently (it can't be driven by the UI thread
because Tkinter's `root.after()` is jittery and not precise enough
for sub-frame animations). And the watchdog needs to run independently
of controller input (that's the whole point — detecting when input
stops).

**Why not eight threads?** Each additional thread adds lock contention
and coordination complexity. Five threads is the minimum that satisfies
the independence requirements. More would add complexity without benefit.

---

## Thread Lifecycle and Startup Sequence

The startup sequence in `main.py` is carefully ordered:

```python
def main():
    # 1. Initialize logging (before anything can log)
    init_logging()
    install_crash_handler()

    # 2. Load TOML config (before anything reads cfg.*)
    init_config()

    # 3. Create OSC client (before any thread can send OSC)
    setup_osc()

    # 4. Start all 5 daemon threads
    threading.Thread(target=start_osc_server, daemon=True).start()
    threading.Thread(target=polling_loop,     daemon=True).start()
    threading.Thread(target=controller_loop,  daemon=True).start()
    threading.Thread(target=watchdog_loop,    daemon=True).start()
    threading.Thread(target=eq_ramp_loop,     daemon=True).start()

    # 5. Wait for OSC server to bind its port
    time.sleep(0.5)

    # 6. Start session discovery (runs in background)
    threading.Thread(target=fetch_all_names,  daemon=True).start()
    osc_update_view()

    # 7. Create Tkinter window and start the UI loop
    root = tk.Tk()
    lbl = build_ui(root)
    root.after(UI_REFRESH_MS, update_ui, root, lbl)

    # 8. Register close handler and enter mainloop
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

    # 9. After mainloop returns (window closed)
    pygame.quit()
    sys.exit(0)
```

### Why this order matters

**Step 3 before Step 4:** All threads need `st.osc` (the OSC client)
to send messages. `setup_osc()` creates it before any thread starts.

**Step 4 before Step 6:** The OSC server thread must be running before
`fetch_all_names()` sends queries, because the responses arrive on the
server thread.

**Step 5 (the 0.5s sleep):** Gives the OSC server thread time to bind
port 11001 and start accepting packets. Without this, early queries
would have no receiver and their responses would be lost. This is a
timing assumption — on slow systems, 0.5s might not be enough. A more
robust approach would use an `Event` that the server thread sets after
`serve_forever()` starts.

**Step 7 after Step 6:** Session discovery runs in the background while
Tkinter initializes. The UI shows "loading…" indicators until discovery
completes. This overlapping saves ~2 seconds of startup time.

### All threads are daemons

Every thread is started with `daemon=True`. This means they die
automatically when the main thread exits — Python doesn't wait for them.
The explicit shutdown sequence in `on_close()` stops them gracefully
before the main thread exits, but the daemon flag is a safety net in
case something prevents `on_close()` from running.

---

## Shared State Architecture

All runtime state lives in two dicts in `src/state.py`:

### `state` — mutable runtime state

```python
state = {
    # Navigation
    "track":            0,         # current track index
    "scene":            0,         # current scene index
    "bookmark_cursor":  0,
    "group_cursor":     0,
    
    # Modifiers
    "l1_held":          False,
    "r2_held":          False,
    "select_held":      False,
    
    # EQ
    "eq_mode_active":   False,
    "eq_selected_band": 1,         # 0=Low, 1=Mid, 2=High, 3=Trim
    "eq_macro_values":  [107.9, 107.9, 107.9, 64.0],
    "_eq_flick_x_state": "idle",   # gesture state machine
    
    # FX
    "fx_macro_values":  [0.0] * 8,
    "fx_baseline":      [0.0] * 8,
    "fx_filter_locked": False,
    "fx_wet_locked":    False,
    "_momentary_stutter_active": False,
    
    # Meter
    "eq_meter_left":    0.0,
    "eq_meter_right":   0.0,
    "meter_smoothed_db": -60.0,
    "clip_active":      False,
    
    # Shutdown
    "_shutting_down":   False,
    
    # ... ~80 more keys ...
}
```

### `ableton` — mirror of Ableton's state

```python
ableton = {
    "bpm":              120.0,
    "is_playing":       False,
    "track_name":       "—",
    "scene_name":       "—",
    "clip_name":        "—",
    "track_volume":     0.85,
    "all_track_names":  [],
    "all_scene_names":  [],
    "all_track_colors": [],
    "all_scene_colors": [],
}
```

### Why two dicts?

`state` contains values WE own — things we set and control. `ableton`
contains values Ableton owns — things we observe and display. This
separation makes it clear who's responsible for each value. When
debugging "why is the BPM wrong," you know to look at the OSC receive
handler for `/live/song/get/tempo`, not at anything in the engine layer.

### Naming conventions

Keys starting with `_` are internal implementation details (gesture
state machines, throttle timestamps, cache flags). They should not be
read by the UI or relied upon by external code. Keys without `_` are
the public interface.

### Module-level globals

Some state lives outside the dicts:

```python
osc = None             # SimpleUDPClient instance
_osc_server = None     # ThreadingOSCUDPServer instance
_ctrl_handle = None    # pygame.Joystick instance

# Smoothed axis values (survive across frames)
_smoothed_lx = 0.0
_smoothed_ly = 0.0
_smoothed_rx = 0.0
_smoothed_ry = 0.0
_smoothed_eq_rx = 0.0
_smoothed_eq_ry = 0.0
```

These are module-level because they're accessed by a single thread at
high frequency and don't need lock protection (only the controller
thread reads/writes the axis smoothing values).

---

## The Lock Strategy — Three Rules

All five threads read and write the shared `state` dict. Coordination
uses a single **reentrant lock (`RLock`)** in `st._lock`.

### Rule 1: Always hold the lock when reading or writing state

```python
# CORRECT
with st._lock:
    selected_band = st.state["eq_selected_band"]
    current_val   = st.state["eq_macro_values"][selected_band]

# WRONG — race condition
selected_band = st.state["eq_selected_band"]
current_val   = st.state["eq_macro_values"][selected_band]
# Another thread could change selected_band between these two reads
```

### Rule 2: NEVER call OSC functions while holding the lock

```python
# WRONG — holds lock during network I/O
with st._lock:
    osc.send_message("/live/device/set/parameter/value", [...])
    # Could take 5ms, blocks all other threads for that duration

# CORRECT — copy state into locals, release lock, then call OSC
with st._lock:
    track = st.state["track"]
    value = st.state["eq_macro_values"][slot]
osc.send_message("/live/device/set/parameter/value", [track, 0, pid, value])
```

This rule exists because OSC sends are UDP packets — they go through
the OS network stack, which can take 1-5ms on a loaded system. Holding
the lock for 5ms at 125 Hz would cause other threads to block for 62%
of their available time.

### Rule 3: Use RLock so nested calls don't self-deadlock

```python
def update_ui():
    with st._lock:
        snapshot_state()
        clear_flashes_if_expired()  # this function ALSO acquires st._lock

def clear_flashes_if_expired():
    with st._lock:   # OK with RLock — same thread can re-acquire
        ...
```

`RLock` (reentrant lock) allows the same thread to acquire the lock
multiple times without deadlocking. The lock is only truly released when
the outermost `with` block exits. `Lock` (non-reentrant) would deadlock
on the second acquisition because it doesn't know the same thread holds
it.

### Why a single lock?

Multiple fine-grained locks (one for EQ state, one for FX state, one
for navigation) would reduce contention but introduce the possibility
of deadlocks if two threads acquire locks in different orders.

With a single lock, deadlocks are impossible — there's nothing to
acquire in the wrong order. The trade-off is that the lock is "hotter"
(more threads contend for it), but since each acquisition holds the
lock for microseconds (just dict reads/writes), contention is negligible.

Measured in practice: the diagnostics layer would need lock contention
instrumentation to quantify exactly, but the UI thread's 36 Hz actual
rate vs 40 Hz target suggests at most ~10% of frame time is spent
waiting for the lock — likely less.

---

## The State Snapshot Pattern

The UI thread reads state at 40 Hz. If it acquired the lock, read one
value, released, acquired again, read another value, etc., it would:

1. Spend most of its time acquiring/releasing the lock
2. See inconsistent state (value A from time T, value B from time T+1ms)

The snapshot pattern solves both problems:

```python
def update_ui(root, lbl):
    # ONE lock acquisition, read EVERYTHING we need
    with st._lock:
        s          = {k: v for k, v in st.state.items()
                      if not isinstance(v, (dict, list))}
        bmarks     = list(st.state["bookmarks"])
        groups     = list(st.state["groups"])
        abl        = dict(st.ableton)
        fx_values  = list(st.state["fx_macro_values"])
        eq_values  = list(st.state["eq_macro_values"])
        # ... all other needed values ...
        meter_left = st.state["eq_meter_left"]
        meter_right = st.state["eq_meter_right"]
        prev_smoothed = st.state["meter_smoothed_db"]
        # ... etc ...
    
    # OUTSIDE THE LOCK — process everything using local copies
    # No other thread can interfere because we're working with
    # our own copies, not the shared state
    
    if abl["is_playing"]:
        set_label(lbl["playing"], "playing", "▶ PLAYING", fg=GREEN)
    
    # ... hundreds of lines of UI update logic ...
    
    # One final lock acquisition to write back computed values
    with st._lock:
        st.state["meter_smoothed_db"] = smoothed_db
        st.state["meter_peak_db"]     = new_peak_db
        # ... etc ...
```

The snapshot pattern gives us:

1. **Consistency:** All values are from the same instant in time
2. **Performance:** One lock acquisition instead of ~50
3. **Safety:** UI code can't accidentally mutate shared state because
   it's working with local copies
4. **Clarity:** The lock boundary is visible and explicit

### What gets snapshot vs what stays in state

**Snapshot (copied into locals):** Everything the UI reads. Simple values
are copied by value (ints, floats, bools, strings). Lists are copied via
`list()`. Dicts are copied via `dict()`.

**Stays in state (written back under lock):** Computed values that other
threads need to see — meter smoothing, peak hold, clip detection state.
These are written back in a single batch at the end.

---

## OSC Communication Architecture

FX Machine communicates with Ableton Live via AbletonOSC, a Remote
Script that exposes Ableton's API as OSC endpoints.

### Two-channel UDP communication

```
FX Machine                          Ableton
    │                                  │
    │  ──── send_message ──────────▶   │  port 11000 (Ableton receives)
    │       /live/device/set/...       │
    │                                  │
    │  ◀──── listener event ────────   │  port 11001 (FX Machine receives)
    │       /live/device/get/...       │
    │                                  │
```

Both channels use UDP — connectionless, no handshake, no acknowledgment.
If a packet is lost, neither side knows. This is by design: OSC for
real-time audio control prioritizes latency over reliability. A dropped
meter update is invisible (the next one arrives 11ms later). A dropped
parameter write is caught by the safety poll within 2 seconds.

### Outbound messages (FX Machine → Ableton)

Sent via `st.osc.send_message(address, [args])`:

| Category | Example Address | When Sent |
|---|---|---|
| Parameter write | `/live/device/set/parameter/value` | EQ/FX encoder moves, momentary effects |
| View navigation | `/live/view/set/selected_track` | Track/scene navigation |
| Transport | `/live/song/start_playing` | START button |
| Clip control | `/live/clip_slot/fire` | X button (launch clip) |
| Query | `/live/track/get/name` | After navigation, on refresh |
| Listener start | `/live/song/start_listen/tempo` | Once at startup |
| Listener stop | `/live/song/stop_listen/tempo` | On shutdown / refresh |

### Inbound messages (Ableton → FX Machine)

Received by the OSC server thread and dispatched to `on_*` handlers:

| Category | Example Address | Frequency |
|---|---|---|
| Meter data | `/live/track/get/output_meter_left` | ~30 Hz per channel |
| Parameter updates | `/live/device/get/parameter/value` | On change (listener) |
| Session metadata | `/live/song/get/tempo` | On change (listener) |
| Query responses | `/live/track/get/name` | On demand |
| Errors | `/live/error` | On invalid request |

### The unified dispatch handler

AbletonOSC uses the same OSC address for both FX and EQ parameter
updates (`/live/device/get/parameter/value`). pythonosc's Dispatcher
only allows one handler per address — mapping two handlers to the same
address silently overwrites the first.

FX Machine solves this with a unified handler that dispatches internally
by track index:

```python
def on_param_value(addr, *args):
    track_idx = int(args[0])
    if track_idx == fx_track:
        on_fx_param_value(addr, *args)
    elif track_idx == eq_track:
        on_eq_param_value(addr, *args)
```

This pattern is used for both `/live/device/get/parameter/value` and
`/live/device/get/parameter/value_string`.

---

## Listener-Based Architecture

v1.0.0 introduced listener-based session updates, replacing the
high-frequency polling that was causing unnecessary load on Ableton.

### What changed

**Before (polling at 6.6 Hz):**

```python
# Every 150ms, regardless of whether anything changed:
st.osc.send_message("/live/song/get/tempo", [])
st.osc.send_message("/live/song/get/is_playing", [])
st.osc.send_message("/live/song/get/num_tracks", [])
st.osc.send_message("/live/song/get/num_scenes", [])
st.osc.send_message("/live/track/get/volume", [track_idx])
```

This generated ~33 outbound messages/second and ~33 response messages/
second = 66 OSC operations/second of pure overhead for values that
change less than once per minute.

**After (listener registration):**

```python
# Once at startup:
st.osc.send_message("/live/song/start_listen/tempo", [])
st.osc.send_message("/live/song/start_listen/is_playing", [])
st.osc.send_message("/live/song/start_listen/num_tracks", [])
st.osc.send_message("/live/song/start_listen/num_scenes", [])
```

Ableton pushes updates only when values change. If BPM doesn't change
for 5 minutes, zero messages are sent for those 5 minutes.

### Impact on Ableton's CPU

| Metric | Before (polling) | After (listeners) |
|---|---|---|
| OSC outbound rate | 52 msg/s | 5 msg/s |
| Ableton CPU delta | +27% over baseline | +0% (invisible) |

The +27% was entirely Ableton processing our polling queries and
generating responses. With listeners, Ableton only does work when
a value actually changes.

### The safety net

The polling loop still runs at 2 Hz to catch rare cases where a
listener event is missed (UDP is unreliable) or where Ableton's internal
state drifts from what the listener last reported. This safety poll
re-queries FX and EQ macro values every `cfg.FX_SAFETY_POLL_INTERVAL`
seconds (default 2s).

### Listener lifecycle

```
Startup:
  fetch_all_names() → osc_register_session_listeners()
                    → osc_register_fx_listeners()
                    → osc_register_eq_listeners()
                    → osc_register_eq_meter_listener()

Manual refresh (SELECT+START):
  fetch_all_names() → osc_stop_session_listeners()   ← FIRST: unregister old
                    → osc_stop_fx_listeners()
                    → osc_stop_eq_listeners()
                    → osc_stop_eq_meter_listener()
                    → ... discovery ...
                    → osc_register_session_listeners() ← THEN: register new
                    → osc_register_fx_listeners()
                    → osc_register_eq_listeners()
                    → osc_register_eq_meter_listener()

Shutdown:
  on_close() → osc_stop_session_listeners()
             → osc_stop_fx_listeners()
             → osc_stop_eq_listeners()
             → osc_stop_eq_meter_listener()
```

The stop-before-register pattern in manual refresh prevents listener
leaks — without it, each refresh would accumulate another set of
listeners with Ableton, causing each parameter change to fire multiple
callback events.

---

## The OSC Roundtrip — From Stick to Sound

When you push the EQ stick right, here's the complete path from
physical movement to audible change:

```
T+0 ms:    Controller thread reads stick = (0, 0.8) via pygame
T+0.1 ms:  smooth_axis() applies exponential filter (factor=0.55)
T+0.2 ms:  hybrid_curve() applies x^1.8 sign-preserving shaping
T+0.5 ms:  Axis dominance check: |Y| > |X| × 3.0? → No, X wins
T+0.6 ms:  X gesture state machine: abs(stick) < 0.90? → Not a flick
T+0.7 ms:  eq_drive_continuous_encoder() called
T+0.8 ms:  eq_encoder_delta() computes velocity-based delta
T+1.0 ms:  Detent check (near neutral? slowdown if so)
T+1.1 ms:  Bass safety cap check (Low band only)
T+1.2 ms:  Throttle check (15ms since last write? → yes, proceed)
T+1.3 ms:  Epsilon check (change > 0.15 macro units? → yes, proceed)
T+1.4 ms:  state[eq_macro_values][band] updated under lock
T+1.5 ms:  osc_set_eq_macro(slot, value) called OUTSIDE lock
T+1.6 ms:  st.osc.send_message("/live/device/set/parameter/value", [...])
T+2.0 ms:  UDP packet arrives at Ableton (127.0.0.1:11000)
T+5.0 ms:  AbletonOSC receives, parses, dispatches
T+8.0 ms:  Ableton macro value updates internally
T+10 ms:   EQ Three device parameter changes
T+15 ms:   Audio buffer reflects new EQ curve
T+20 ms:   YOU HEAR THE CHANGE

Meanwhile, asynchronously:
T+50 ms:   AbletonOSC fires listener callback for the changed param
T+52 ms:   FX Machine OSC server receives the callback
T+53 ms:   on_param_value() dispatches to on_eq_param_value()
T+54 ms:   state[eq_macro_values][band] updated with Ableton's value
T+55 ms:   UI thread picks up the new value on its next snapshot
T+80 ms:   Knob position visually updates in the UI
```

**End-to-end latency budget:**

| Stage | Time |
|---|---|
| Controller event polling | ~8 ms (125 Hz loop) |
| Gesture processing | <1 ms |
| OSC throttle wait | 0-15 ms (worst case) |
| UDP send (localhost) | <1 ms |
| AbletonOSC processing | ~2-5 ms |
| Ableton parameter update | ~5-10 ms |
| Audio buffer rendering | ~5 ms (depends on buffer size) |
| **Total stick-to-sound** | **~15-40 ms** |

Well below the 50-100 ms threshold where humans perceive lag.

The visual feedback path (Ableton → OSC listener → state → UI draw)
adds another 30-60 ms but that's purely cosmetic — the audio change
happens independently of the visual update.

---

## The Session Discovery Handshake

When the app starts, it needs to learn Ableton's session structure.
This process takes ~5 seconds and happens in the background while the
UI shows "loading…" indicators.

```
T+0.0 s:   App launches, OSC client and server are up
T+0.5 s:   fetch_all_names() thread starts
T+0.5 s:     Stop any existing listeners (prevent leak on refresh)
T+0.5 s:     Query: how many scenes? how many tracks?
T+1.1 s:   Counts received: 8 scenes, 21 tracks
T+1.1 s:   Register session listeners (tempo, transport, counts)
T+1.1 s:   Fetch all scene names + colors (each takes ~12 ms)
T+1.6 s:   rebuild_bookmarks() — finds scenes prefixed with §
T+1.6 s:   Fetch all track names + colors
T+2.1 s:   rebuild_groups() — finds tracks prefixed with *
T+2.1 s:   rebuild_fx_track() — finds "~ FX Macros"
T+2.1 s:   rebuild_eq_track() — finds "~ EQ Macros"
T+2.2 s:   FX rack discovered at index 20
T+2.2 s:   Query FX macro names (8 parallel queries)
T+2.6 s:   FX macros mapped: 8/8
T+2.6 s:   Query FX min/max/values
T+2.9 s:   Baseline auto-captured from current values
T+2.9 s:   FX listeners registered (16: 8 values + 8 strings)
T+2.9 s:   EQ rack discovered at index 18
T+3.0 s:   EQ macro names mapped: 4/4 (Low, Mid, High, Trim)
T+3.4 s:   EQ listeners registered (8: 4 values + 4 strings)
T+3.5 s:   EQ meter listeners armed (track output L+R)
T+3.5 s:   Ready — all systems online
```

### The `_fetch_lock`

Discovery is protected by a non-reentrant `Lock` (not `RLock`). If
the user presses SELECT+START while discovery is already running, the
second call to `fetch_all_names()` tries `_fetch_lock.acquire(blocking=False)`,
gets `False`, logs "Fetch already running — skipping", and returns
immediately. This prevents concurrent discovery runs from racing each
other.

---

## The Config Singleton Pattern

The TOML hot-reload system relies on a singleton object `cfg`:

```python
# src/config_loader.py
class _RuntimeConfig:
    def __init__(self):
        self.EQ_SWEEP_SECONDS = 0.30
        self.EQ_AXIS_DEAD_ZONE = 0.18
        # ... ~55 more attributes ...

cfg = _RuntimeConfig()   # module-level singleton
```

Modules consume it by importing `cfg` and reading attributes:

```python
# src/engine/eq.py
from src.config_loader import cfg

def eq_drive_continuous_encoder(stick_x, now):
    if abs(stick_x) < cfg.EQ_AXIS_DEAD_ZONE:   # reads current value
        return
```

### Why this works for hot-reload

When `reload_config()` runs, it mutates `cfg` attributes in place:

```python
def _apply_toml(toml_data):
    for attr, path in _CFG_MAP:
        value = _nested_get(toml_data, path)
        if value != getattr(cfg, attr):
            setattr(cfg, attr, value)   # mutate the singleton
```

Because every module accesses `cfg.EQ_SWEEP_SECONDS` (not a cached
local copy), the next time any function reads it, it gets the new
value. No import refresh, no module reload, no thread restart.

### The critical difference

```python
# BAD — value cached at import time
from src.config import EQ_SWEEP_SECONDS
def encoder():
    delta = EQ_SWEEP_SECONDS * x   # always the old value

# GOOD — value read every call
from src.config_loader import cfg
def encoder():
    delta = cfg.EQ_SWEEP_SECONDS * x   # always the current value
```

`src/config.py` is used for **architectural constants** that genuinely
never change (button indices, OSC paths, empirically calibrated macro
values). `src/config_loader.py` is used for **tunable values** that
should respond to TOML edits.

---

## The TOML Hot-Reload System

The hot-reload system works in three stages:

### Stage 1: File read + parse

```python
with open(active_toml_path, "rb") as f:
    toml_data = tomllib.load(f)
```

If the file has a syntax error, `tomllib.TOMLDecodeError` is caught,
the current cfg values are preserved, and a notification is pushed to
the UI. The show is never broken by a typo.

### Stage 2: Diff + apply

```python
changes = _apply_toml(toml_data)
# changes = {"EQ_SWEEP_SECONDS": (0.30, 0.50), ...}
```

Only values that actually changed are logged and reported. Unchanged
values are skipped silently.

### Stage 3: Classify changes

Each changed attribute is classified as [LIVE] or [RESTART]:

```python
_RESTART_REQUIRED_ATTRS = {
    "UI_REFRESH_MS", "WINDOW_WIDTH", "WINDOW_HEIGHT",
    "OSC_HOST", "OSC_SEND_PORT", "OSC_RECEIVE_PORT",
    "DIAG_TIMED_FUNCTIONS", ...
}
```

[LIVE] values take effect immediately on the next read. [RESTART] values
are consumed once at startup (thread sleep intervals, window dimensions,
OSC port bindings) and can't change without restarting the app. The
reload function reports which changes require restart so the UI can
show a warning.

---

## The UI Rendering Pipeline

The Tkinter UI runs at ~40 Hz (25ms per frame) via `root.after()`:

```
Frame N:
  root.after(25ms, update_ui) triggers
  │
  ├─ Acquire st._lock
  ├─ Copy ALL needed state into local variables
  ├─ Release st._lock
  │
  ├─ Process meter math (ballistics, peak hold, clip detection)
  │
  ├─ For each EQ band (TRIM, HIGH, MID, LOW):
  │    ├─ Compute visual position
  │    ├─ Check dirty cache — skip if unchanged
  │    └─ draw_eq_knob() or draw_trim_knob() if changed
  │
  ├─ draw_djm_meter() — incremental PhotoImage update
  │
  ├─ For each FX macro (8 slots):
  │    ├─ Compute value fraction
  │    ├─ Check dirty cache — skip if unchanged
  │    └─ draw_knob() if changed
  │
  ├─ Update labels (set_label with diff checking)
  ├─ Update modifier pills (l1, r2, select, eq mode)
  ├─ Update notification slot
  │
  ├─ Acquire st._lock
  ├─ Write back computed meter values
  ├─ Release st._lock
  │
  ├─ Check _shutting_down flag
  └─ root.after(25ms, update_ui) — schedule next frame
```

### Why root.after() instead of a thread

Tkinter is NOT thread-safe. All widget operations (create, configure,
delete, redraw) MUST happen on the main thread. `root.after()` schedules
a callback on the main thread's event loop, ensuring all UI work happens
in the correct context. A separate UI thread would need Tkinter's
`thread_queue` mechanism, which adds complexity and latency.

---

## The Dirty-Cache Pattern

Each canvas renderer (draw_knob, draw_eq_knob, draw_djm_meter) uses
a dirty cache to avoid redrawing when nothing has changed:

```python
_knob_cache = {}

def draw_knob(canvas, slot, value_frac, color, active, locked, moment):
    cache_key = (round(value_frac, 3), color, active, locked, moment)
    if _knob_cache.get(slot) == cache_key:
        return   # nothing changed, skip the redraw
    _knob_cache[slot] = cache_key
    
    canvas.delete("all")
    # ... actually draw ...
```

The same pattern applies to labels:

```python
_ui_cache = {}

def set_label(widget, key, text, **kwargs):
    cache_key = (key, text, tuple(sorted(kwargs.items())))
    if _ui_cache.get(key) != cache_key:
        widget.config(text=text, **kwargs)
        _ui_cache[key] = cache_key
```

### Why this matters

At 40 Hz, `update_ui` runs 40 times per second. Without caching:
- 8 FX knobs × 40 frames = 320 canvas redraws/sec
- 4 EQ knobs × 40 frames = 160 canvas redraws/sec
- 30+ labels × 40 frames = 1200+ widget.config() calls/sec

With caching, most frames are no-ops — the vast majority of values
don't change between frames. Only the actively-moving elements (the
meter during audio playback, the knob being swept) actually redraw.

In a static moment (no controller input, no audio), the UI consumes
<0.1% CPU because every cache check returns early.

---

## The PhotoImage Meter — Why and How

The channel meter is the UI element that changes most frequently —
its value updates on every audio buffer (~30 Hz from each channel).
It needs to redraw almost every frame.

### The problem with canvas items

The original meter used `canvas.create_rectangle()` calls to draw
22 LED segments, each with rounded corners (via `_rounded_rect` which
creates 6-14 canvas items per corner). Total: ~340 canvas items
destroyed and recreated per frame.

Profiling revealed this consumed 7.18ms average per frame — 28% of
the 25ms frame budget. At 40 Hz, the meter alone used 20% of one
CPU core.

### The PhotoImage solution

Replace 340 canvas items with ONE canvas item — a `tk.PhotoImage`
bitmap. Instead of creating/destroying widget tree nodes, we paint
pixels directly into the bitmap via `photo.put(color, to=(x1, y1, x2, y2))`.

Per-frame cost:
- Old: 340 canvas operations (create + configure + z-order per item)
- New: 1-3 `photo.put()` calls (only changed segments)

### Incremental update strategy

Each frame, we compute which of the 22 LED segments changed state
("off" → "lit", "lit" → "peak", etc.) and only repaint those
segments. Most frames during audio playback see 1-3 segment changes
as the level fluctuates.

```python
new_states = ["off"] * 22  # computed from current smoothed_db
old_states = state["last_segment_states"]  # cached from previous frame

for seg_index in range(22):
    if new_states[seg_index] != old_states[seg_index]:
        color = seg_colors[seg_index][new_states[seg_index]]
        bitmap.put(color, to=(0, seg_top, led_width, seg_bottom))

state["last_segment_states"] = new_states
```

### Results

```
Before:  38,520 ms total    avg 6.26 ms    p99 18.05 ms
After:    1,024 ms total    avg 0.11 ms    p99  0.61 ms
```

45× faster average. System CPU dropped from 35% to 20%.

---

## The Diagnostics Integration

The diagnostics layer hooks into the architecture at specific points:

### Function timing hooks (monkey-patched)

16 functions are wrapped with timing shims via the installer. The
wrappers measure wall-clock time per call and report to the profiler.

### Thread health heartbeats (source-level)

Each daemon thread calls `record_thread_tick("name")` once per
iteration. This is the ONE place where the diagnostics layer touches
source files outside `src/diagnostics/`.

### OSC traffic hooks (monkey-patched)

The OSC client's `send_message` method is replaced with a wrapper
that records each outbound message. OSC server handlers are similarly
wrapped for inbound tracking.

### System sampler (independent thread)

The sampler runs its own daemon thread, polling `psutil` at 1 Hz.
It doesn't hook into any existing code — it just reads process-level
metrics from the OS.

See [DIAGNOSTICS_GUIDE.md](DIAGNOSTICS_GUIDE.md) for the complete
diagnostics documentation.

---

## Shutdown Sequencing

Clean shutdown is critical for a performance app. Crashing on exit
leaves a bad impression and can corrupt log files.

The shutdown sequence in `on_close()`:

```
Step 0: Idempotency guard — prevent double-execution if Tkinter
        fires WM_DELETE_WINDOW twice

Step 1: Set _shutting_down = True
        → Controller loop sees this and exits its while True
        → Other threads check this before doing work
        → Prevents _enter_buffered_busy stdout crash

Step 2: Stop diagnostics (sampler + reporter threads)
        → Must happen BEFORE OSC teardown so reporter doesn't
          crash trying to access torn-down state
        → Writes final summary to log files

Step 3: Stop OSC listeners (session + FX + EQ + meter)
        → Tells Ableton to stop sending us updates
        → Prevents new OSC callbacks from firing during teardown

Step 4: Shut down OSC server
        → ThreadingOSCUDPServer.shutdown() blocks until server exits
        → After this, no more UDP packets are processed

Step 5: Destroy Tkinter window
        → Guarded by winfo_exists() check
        → Wrapped in try/except for the case where Tkinter already
          cleaned up during the OSC shutdown blocking call
```

### The idempotency guard

```python
_close_state = [False]   # mutable list for closure compatibility

def on_close():
    if _close_state[0]:
        return
    _close_state[0] = True
```

Uses a mutable list (not a bool) because Python closures can mutate
but not reassign outer-scope variables without `nonlocal`. The list
mutation works without that keyword and is safe across re-entry.

### Why order matters

If you stop the OSC server BEFORE stopping listeners, Ableton is still
sending updates to a closed port. The updates fail silently (UDP), but
Ableton's OSC thread does unnecessary work.

If you destroy Tkinter BEFORE stopping diagnostics, the reporter thread
may try to log a final summary while the main thread's stdout is being
torn down — causing the `_enter_buffered_busy` fatal error.

If you don't set `_shutting_down` BEFORE everything else, the controller
thread wakes from its 8ms sleep, sees that pygame is being torn down,
tries to log "exiting cleanly," and hits the same stdout lock issue.

---

## Error Recovery Model

FX Machine is designed to survive failures gracefully:

### Ableton crashes

OSC sends fail silently (UDP, no ACK). The controller still responds.
The app keeps running. When Ableton restarts and AbletonOSC reconnects,
the next safety poll or manual refresh (SELECT+START) rediscovers the
session.

### Controller unplugged mid-gesture

Gesture state is held in memory. The watchdog detects the disconnect
within 5 seconds. When the controller is replugged, the gesture state
resets to "idle" — the partial gesture is lost (correct behavior, as
completing a half-gesture from a reconnected controller would be
unpredictable).

### TOML edited with syntax error

`reload_config()` catches the `TOMLDecodeError`, keeps current values
in memory, and pushes a notification to the UI. The show continues with
the last valid configuration.

### Two gestures fired simultaneously

The mutual exclusion system in `handle_axes_eq()` freezes the loser.
Only one axis owns the stick at a time. If both X and Y detect a flick
in the same frame, Y gets priority (checked first), and X's state is
reset to "idle."

### OSC listener missed

The 2 Hz safety poll re-queries macro values from Ableton. Any drift
caused by a missed listener event is corrected within 2 seconds.

### Diagnostics failure

Every diagnostics hook is wrapped in try/except. If the profiler has a
bug, the wrapped function still returns its result correctly. The user
never sees a diagnostics error — the worst case is missing data in the
log.

---

## Module Dependency Graph

```
run.py
  └── src.main
        ├── src.config (constants)
        ├── src.config_loader (cfg singleton)
        ├── src.state (shared state + locks)
        ├── src.log_setup (logging)
        ├── src.helpers (math utilities)
        │
        ├── src.osc.client (outbound OSC)
        ├── src.osc.server (inbound OSC handlers)
        ├── src.osc.discovery (session scanning)
        │
        ├── src.engine.eq (EQ gesture engine)
        ├── src.engine.fx (FX stick driver)
        ├── src.engine.navigation (scene/track movement)
        ├── src.engine.actions (button actions)
        ├── src.engine.momentary (stutter/bass cut/throw)
        ├── src.engine.polling (safety polls + ramp animation)
        │
        ├── src.controller.loop (main controller thread)
        ├── src.controller.buttons (button dispatch)
        ├── src.controller.axes (axis + D-pad handlers)
        ├── src.controller.watchdog (health + reprobe)
        │
        ├── src.ui.palette (colors + fonts)
        ├── src.ui.widgets (canvas renderers)
        ├── src.ui.builder (Tkinter construction)
        └── src.ui.updater (40 Hz update loop)

src.diagnostics (optional, self-contained)
  ├── __init__ (public API)
  ├── installer (hooks into all of the above via monkey-patch)
  ├── profiler, counters, osc_tracker, sampler, thread_health,
  │   rate_limiter (data collectors)
  ├── reporter (log writers)
  └── analyzer (post-session analysis)

analyze_diagnostics.py (standalone CLI tool)
  └── src.diagnostics.analyzer

diagnose.py (standalone health checker)
  └── reads src.* modules via AST inspection

build.py (standalone .exe builder)
  └── invokes PyInstaller
```

### Circular dependency prevention

No circular imports exist. The dependency graph is a DAG (directed
acyclic graph). Key rules:

- `state.py` imports only from `config.py` (no engine, no OSC, no UI)
- `helpers.py` imports from `state.py` and `config.py` only
- Engine modules import from `helpers.py`, `state.py`, `config.py`,
  `config_loader.py`, and `osc.client` — never from each other
- UI modules import from everything above but nothing imports from UI
- Diagnostics imports from everything but nothing imports from diagnostics

---

## Thread Communication Patterns

Threads communicate exclusively through the shared `state` dict. There
are no queues, no pipes, no condition variables, no events (except
`_shutting_down` which is a simple bool flag in the state dict).

### Pattern 1: Write-and-forget (controller → state → UI)

The controller thread writes a value, the UI thread reads it later:

```
Controller thread:  st.state["eq_macro_values"][1] = 95.3
                    (under lock, then releases)

UI thread:          val = snapshot["eq_macro_values"][1]
                    (reads 95.3 on next frame, maybe 25ms later)
```

No acknowledgment. No callback. The UI polls at its own rate.

### Pattern 2: Deferred query (navigation → polling → OSC → state → UI)

Navigation sets a "please query" flag; the polling loop notices and fires
the query; the OSC response updates state; the UI eventually reads it:

```
Controller: st.state["_query_requested_at"] = now
Polling:    if requested_at > 0 and elapsed >= defer_time:
                osc_query_position()
OSC recv:   on_clip_name() → st.ableton["clip_name"] = "KICK 3"
UI:         set_label(lbl["clip_name"], ..., abl["clip_name"])
```

The defer time (40ms default) debounces rapid navigation so we don't
send 10 queries when the user scrolls through 10 tracks.

### Pattern 3: Ramp animation (engine → ramp thread → OSC)

A gesture fires an action; the action sets ramp parameters; the ramp
thread animates the value; each frame writes to state AND sends OSC:

```
EQ engine:  start_eq_ramp(band=1, target=0.0, duration=0.05)
Ramp thread: while progress < 1.0:
                 eased = cubic_ease_out(progress)
                 value = start + (target - start) * eased
                 st.state["eq_macro_values"][1] = value
                 osc_set_eq_macro(1, value)
                 sleep(16ms)
```

---

## Memory Model

FX Machine's memory footprint is ~50 MB at runtime:

| Component | Memory | Notes |
|---|---|---|
| Python interpreter | ~15 MB | Baseline Python 3.12 |
| pygame | ~10 MB | SDL2 subsystem |
| Tkinter | ~8 MB | Tk runtime + widgets |
| Application code | ~5 MB | All .pyc modules loaded |
| State dicts | ~50 KB | Even with large session |
| Diagnostics (when enabled) | ~700 KB | Bounded data structures |
| PhotoImage bitmap | ~4 KB | One bitmap for meter |
| pythonosc | ~2 MB | OSC library |
| psutil (when available) | ~3 MB | System monitoring |
| **Total** | **~48-51 MB** | Stable after warmup |

Memory growth of 2-3 MB during the first few minutes is normal (Python's
memory allocator warming up, Tkinter caching font metrics, etc.). After
that, memory should be stable. Sustained growth beyond 5 MB suggests a
leak — use the diagnostics sampler to track the trajectory.

---

## Latency Budget

For a live performance instrument, latency is the most critical
specification. Here are the measured latencies for each path:

### Stick-to-sound (parameter change)

| Stage | Time | Cumulative |
|---|---|---|
| pygame event poll | 0-8 ms | 8 ms |
| Axis smoothing + gesture check | <1 ms | 9 ms |
| Throttle/epsilon gate | 0-15 ms | 24 ms |
| UDP send (localhost) | <1 ms | 25 ms |
| AbletonOSC dispatch | 2-5 ms | 30 ms |
| Ableton parameter update | 5-10 ms | 40 ms |
| **Total** | **15-40 ms** | |

Perceptual threshold: 50-100 ms. We're well under.

### Button press to action

| Stage | Time |
|---|---|
| pygame event dispatch | 0-8 ms |
| Button handler logic | <1 ms |
| OSC send | <1 ms |
| Ableton processing | 5-10 ms |
| **Total** | **6-20 ms** |

### Visual feedback (state change to UI update)

| Stage | Time |
|---|---|
| State write by any thread | <1 ms |
| UI snapshot (next frame) | 0-25 ms (waiting for next tick) |
| Dirty-cache check + draw | 1-5 ms |
| Tkinter render to screen | ~5 ms |
| **Total** | **6-35 ms** |

---

## Concurrency Hazards and Mitigations

### Hazard 1: Lock contention stalling the UI

**Risk:** If a thread holds `st._lock` for too long (e.g., during an
OSC send), the UI thread blocks on its snapshot acquisition.

**Mitigation:** Rule 2 (no OSC inside locks). All lock holds are
microsecond-scale dict operations. Measured UI miss rate: ~10%,
mostly from Tkinter overhead, not lock contention.

### Hazard 2: Race on EQ ramp + encoder

**Risk:** The encoder and a ramp animation both try to write
`eq_macro_values[band]` simultaneously.

**Mitigation:** The ramp sets `_eq_ramp_active[band] = True`. The
encoder checks this flag and skips writing while a ramp is active.
The ramp has priority because it was triggered by a deliberate gesture.

### Hazard 3: Stale smoothed values on mode switch

**Risk:** When switching from navigation to EQ mode, `_smoothed_eq_rx`
retains the last value from the previous EQ session, causing the first
encoder frame to process stale input.

**Mitigation:** `action_toggle_eq_mode()` resets `_smoothed_eq_rx = 0.0`
and `_smoothed_eq_ry = 0.0` on mode entry. The first frame starts fresh.

### Hazard 4: Listener registration leak

**Risk:** Each manual refresh registers new listeners without removing
old ones. After N refreshes, each parameter change fires N+1 callbacks.

**Mitigation:** `fetch_all_names()` calls `osc_stop_*_listeners()` at
the start, before re-registering. The stop functions are idempotent
(they check registration flags and no-op if not registered).

### Hazard 5: Baseline overwritten by auto-capture

**Risk:** User manually saves baseline via SELECT+R1. Between the save
and the next frame, the auto-capture code in `_handle_fx_macro_values()`
fires and overwrites the manual baseline.

**Mitigation:** `_handle_fx_macro_values()` re-checks `fx_baseline_ready`
inside the lock (not outside) before writing. If the manual save set
it to True between the outer check and the inner check, the auto-capture
is skipped.

### Hazard 6: Tkinter destroyed during shutdown race

**Risk:** `on_close()` calls `root.destroy()` but Tkinter already
cleaned up during the OSC server shutdown's blocking call.

**Mitigation:** `root.winfo_exists()` check before `destroy()`, plus
try/except around the entire call. The idempotency guard prevents
double-execution from Tkinter firing WM_DELETE_WINDOW twice.

---

## Adding a New Feature — Where Things Go

If you're adding a feature to FX Machine, here's where each type of
code belongs:

### New button action

1. Add the handler function in `src/engine/actions.py`
2. Wire it into `src/controller/buttons.py` in the appropriate layer
   (navigation, FX mode, SELECT modifier)
3. Update the state dict in `src/state.py` if new state is needed

### New continuous control (stick-driven)

1. Add the drive function in `src/engine/fx.py` or `src/engine/eq.py`
2. Wire it into `src/controller/axes.py`
3. Add any new state keys to `src/state.py`
4. Add the visual element to `src/ui/builder.py` (canvas or label)
5. Update `src/ui/updater.py` to read and render the new value

### New OSC query

1. Add the send function in `src/osc/client.py`
2. Add the receive handler in `src/osc/server.py`
3. Register the handler in `start_osc_server()`'s dispatcher mapping
4. If it's a listener-based value, add start/stop functions

### New tunable parameter

1. Add the key in `config/default.toml` with comments
2. Add the default value in `_RuntimeConfig.__init__()` in `config_loader.py`
3. Add the TOML-to-cfg mapping in `_CFG_MAP` in `config_loader.py`
4. Read it via `cfg.YOUR_VALUE` in the consuming module

### New widget

1. Add the drawing function in `src/ui/widgets.py`
2. Create the canvas/label in `src/ui/builder.py`
3. Drive it from `src/ui/updater.py`
4. Add its colors to `src/ui/palette.py`

---

## Why Not X — Design Alternatives Considered

### Why not MIDI instead of OSC?

MIDI is limited to 128 values (7-bit) per parameter. OSC supports
floating-point values with arbitrary precision. MIDI requires a virtual
port; OSC uses standard UDP sockets. AbletonOSC exposes Ableton's full
API; MIDI control requires manual mapping in Ableton's preferences.

### Why not asyncio instead of threads?

pygame is not async-compatible. Its event loop (`pygame.event.get()`)
is blocking and must run in a dedicated thread. Tkinter is also not
async-compatible — it has its own event loop that must be the main
thread. With two blocking event loops that can't be async, threads are
the only option.

### Why not a message queue between threads?

The state dict pattern is simpler than queues for our use case. Queues
add ordering guarantees we don't need (we always want the latest value,
not a FIFO of historical values). A queue-based design would require
the UI to drain all pending messages per frame, which is essentially
what the snapshot pattern already does — but with more code.

### Why not store state in a database?

A dict is ~1000× faster to read than SQLite. We read state 40 times
per second from the UI thread and 125 times per second from the
controller thread. Even an in-memory SQLite database would add
measurable latency.

### Why not use Python's `multiprocessing` instead of `threading`?

`multiprocessing` creates separate processes with their own memory
spaces. Sharing state between processes requires serialization (pickle,
shared memory, or managed objects), which is far more complex and slower
than a simple dict with a lock. The GIL is not a problem for our use
case because our threads spend most of their time in I/O waits (pygame,
UDP, Tkinter), not CPU-bound computation.

### Why not use a reactive framework (signals/slots, RxPy)?

The state dict with polling-based UI reads is simpler, more debuggable,
and has zero dependencies. Reactive frameworks add abstraction that's
powerful for complex data flow but unnecessary for our relatively simple
state-to-UI mapping. The dirty-cache pattern achieves the same result
(only update what changed) with less machinery.

---

*This document describes the architecture as shipped in FX Machine
v1.0.0. The planned PySide6 migration will replace the UI layer
(builder.py, updater.py, widgets.py) but the threading model, state
management, OSC communication, and engine logic will remain unchanged.*
```
