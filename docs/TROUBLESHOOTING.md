## docs/TROUBLESHOOTING.md

```markdown
# 🔧 FX Machine — Troubleshooting Guide

## What This Document Covers

This is the catch-all reference for problems you encounter while using
FX Machine. Every error message, every "why isn't this working"
situation, every weird behavior, with the cause and the fix.

The guide is organized by symptom, not by cause. You see a problem,
you look it up by what you observed, and you find the explanation and
the solution.

Before troubleshooting anything, run the diagnostic tool first:

```bash
python diagnose.py
```

It catches the most common setup issues automatically.

---

## Table of Contents

1. [Before You Start Troubleshooting](#before-you-start-troubleshooting)
2. [The Diagnostic Tool Workflow](#the-diagnostic-tool-workflow)
3. [Startup Problems](#startup-problems)
4. [Ableton Connection Problems](#ableton-connection-problems)
5. [Controller Detection Problems](#controller-detection-problems)
6. [EQ Mode Problems](#eq-mode-problems)
7. [FX Mode Problems](#fx-mode-problems)
8. [Meter Problems](#meter-problems)
9. [UI Problems](#ui-problems)
10. [Audio Problems](#audio-problems)
11. [Performance Problems](#performance-problems)
12. [Configuration Problems](#configuration-problems)
13. [Diagnostics Layer Problems](#diagnostics-layer-problems)
14. [Build and .exe Problems](#build-and-exe-problems)
15. [Shutdown Problems](#shutdown-problems)
16. [Log File Problems](#log-file-problems)
17. [Macro Discovery Problems](#macro-discovery-problems)
18. [Navigation Problems](#navigation-problems)
19. [Momentary Effect Problems](#momentary-effect-problems)
20. [Recovery Procedures](#recovery-procedures)
21. [Reading Log Files](#reading-log-files)
22. [Getting Help](#getting-help)
23. [Known Issues](#known-issues)
24. [Error Message Reference](#error-message-reference)

---

## Before You Start Troubleshooting

Most "FX Machine isn't working" problems fall into one of three
categories:

1. **Setup issues** — Ableton, AbletonOSC, or the racks aren't
   configured correctly. See [SETUP_ABLETON.md](SETUP_ABLETON.md).
2. **Environment issues** — Wrong Python version, missing packages,
   port conflicts, firewall blocks.
3. **Configuration issues** — TOML edits broke something, or default
   values don't fit your hardware.

Before deep troubleshooting:

### Step 1: Run the diagnostic tool

```bash
python diagnose.py
```

This catches ~80% of common issues automatically. If it shows red
errors, fix those first. If it shows only green checks, the basic
setup is sound.

### Step 2: Check the log files

```bash
notepad logs\fxmachine.log
```

Recent errors, warnings, and exceptions are logged here. Look at the
last 100 lines for anything that says "ERROR" or "WARNING".

### Step 3: Try the simplest reproduction

If something is broken, can you:
- Restart FX Machine? Did that fix it?
- Restart Ableton? Did that fix it?
- Restart your computer? Did that fix it?

These aren't elegant solutions, but they often work and they're fast
to try.

### Step 4: Compare to expected behavior

Are you sure what you're seeing is actually wrong? Some "problems"
are actually correct behavior:
- The UI thread shows 36 Hz when target is 40 Hz → this is NORMAL
  (Python overhead, not a bug)
- The CPU shows 30% during audio playback → this is mostly Ableton,
  not FX Machine (verify with task manager)
- The diagnostics log mentions "thread X% missed" → this is normal
  under load and harmless

---

## The Diagnostic Tool Workflow

`diagnose.py` runs 150+ automated health checks. Use it whenever
something seems wrong:

```bash
python diagnose.py            # full check
python diagnose.py --quick    # skip slow tests
python diagnose.py --verbose  # show every check
```

Exit codes:
- **0:** All checks passed — basic setup is sound
- **1:** Warnings only — investigate, but app should run
- **2:** Errors found — fix before running the app

### What the diagnostic checks

1. Python version (3.11+)
2. All required dependencies installed
3. Project file structure intact
4. Python syntax of every source file
5. All modules import successfully
6. TOML config files parse correctly
7. cfg singleton has all expected attributes
8. Every `cfg.X` reference in code resolves
9. Log folder is writable
10. Dead imports (potential bugs)
11. OSC ports available
12. Gamepad detected
13. Git status

### Interpreting output

```
━━━ Python Version ━━━
  ✓ Python 3.12.0 (tomllib available)

━━━ Third-Party Dependencies ━━━
  ✓ pygame 2.6.1
  ✓ python-osc 1.8.3
  ✓ psutil 5.9.0
```

Green checks = no problem. Move on.

```
━━━ TOML Configuration ━━━
  ✗ config/active.toml has syntax errors
      Line 47: Invalid value
```

Red error = fix this. The diagnostic tells you exactly which file
and which line.

```
━━━ OSC Port Availability ━━━
  ⚠ Receive port 11001 in use
      Is another FX Machine instance running?
```

Yellow warning = investigate, may not block the app.

---

## Startup Problems

### App doesn't start at all

```bash
python run.py
```

...and nothing happens, or you get an immediate error.

**Cause 1: Python not installed or not in PATH**

```
'python' is not recognized as an internal or external command
```

Fix: Install Python 3.11+ from [python.org](https://www.python.org/downloads/).
During installation, check "Add Python to PATH."

**Cause 2: Wrong Python version**

```
SyntaxError: invalid syntax
```

(near a line containing `tomllib`)

Fix: Python 3.10 or older doesn't have `tomllib`. Install Python 3.11+.

**Cause 3: Missing dependencies**

```
ModuleNotFoundError: No module named 'pygame'
```

Fix:
```bash
pip install pygame python-osc psutil
```

**Cause 4: Corrupted source files**

```
IndentationError: unexpected indent
SyntaxError: invalid syntax
```

Fix: Run `python diagnose.py` — it checks every source file's syntax.
The diagnostic tells you which file and line is broken.

### App starts but immediately closes

The window appears for a fraction of a second, then disappears.

**Cause: Unhandled exception during initialization**

Run from command line to see the error:
```bash
python run.py
```

Watch the console output. The traceback shows what went wrong.
Common causes:
- TOML config has bad values
- A required Ableton OSC endpoint doesn't exist
- File permissions on the logs folder

### App starts but the UI is blank

The window appears but shows no controls — just a grey background.

**Cause: Tkinter rendering issue**

Fix: Resize the window. Tkinter sometimes fails to lay out widgets
on first paint. Dragging the window edge forces a redraw.

If resizing doesn't help, restart the app.

### App starts but freezes immediately

The UI appears but nothing responds — no clicks, no keyboard input.

**Cause 1: Locked up in startup**

The session discovery thread may be blocked waiting for AbletonOSC
that never responds. The UI thread holds because of bad lock behavior.

Fix: Force-quit and restart. Then start the app BEFORE starting
Ableton, or ensure AbletonOSC is fully loaded before launching
FX Machine.

**Cause 2: Diagnostics layer crash**

If you enabled diagnostics and it has a bug, the install hook may
freeze the app at startup.

Fix: Edit `config/active.toml`, set `[diagnostics] enabled = false`,
restart.

---

## Ableton Connection Problems

### "Session: 0 scenes, 0 tracks"

The OSC client is sending queries but Ableton isn't responding with
real data.

**Cause 1: AbletonOSC not installed**

Fix: Follow [SETUP_ABLETON.md](SETUP_ABLETON.md) Step 1. Verify the
`AbletonOSC/` folder exists in your Remote Scripts directory and is
selected as a Control Surface in Ableton's preferences.

**Cause 2: AbletonOSC installed but Ableton wasn't restarted**

Fix: Close Ableton completely, restart it. AbletonOSC only loads on
Ableton startup.

**Cause 3: AbletonOSC ports differ from FX Machine's**

If AbletonOSC is configured to use ports other than 11000/11001,
FX Machine can't communicate with it.

Fix: Either change AbletonOSC's ports to match FX Machine's defaults
(11000 receive, 11001 send), or change FX Machine's ports in
`config/active.toml`:

```toml
[network]
osc_send_port = YOUR_NEW_PORT
osc_receive_port = YOUR_OTHER_PORT
```

### "FX track '~ FX Macros' not found in session"

The OSC connection works but FX Machine can't find the FX rack track.

**Cause: Track name doesn't match exactly**

Common mistakes:
- Extra space: `~  FX Macros` (two spaces between ~ and F)
- Trailing space: `~ FX Macros ` (space at the end)
- Wrong case: `~ fx macros` or `~ FX MACROS`
- Missing tilde: `FX Macros`
- Different prefix: `* FX Macros` instead of `~ FX Macros`

Fix: In Ableton, double-click the track name and retype it EXACTLY as:

```
~ FX Macros
```

Single space between tilde and FX. Case-sensitive. No leading or
trailing spaces.

### "EQ track '~ EQ Macros' not found in session"

Same issue, different track. Same fix — verify the exact name is
`~ EQ Macros`.

### "FX macros mapped: 0/8"

The track is found but no macros match the expected names.

**Cause: Macros aren't named correctly**

The 8 FX macros must be named EXACTLY:
1. `Filter Freq`
2. `Filter Mode`
3. `Filter Res`
4. `Stutter`
5. `Reverb Size`
6. `FX Send`
7. `Delay FB`
8. `Width`

Fix: For each macro in the rack:
1. Right-click the macro label
2. Select Rename
3. Type the exact name (case-sensitive)
4. Press Enter

After fixing all 8, press SELECT+START in FX Machine to refresh.

### "FX macros mapped: 5/8" (partial)

Some macros are correctly named, some aren't.

**Cause: Some macro names have typos**

Check the FX Machine console output:
```
slot 0: param[1] = 'Filter Freq'
slot 1: param[2] = 'Filter Mode'
slot 2: param[3] = 'Filter Res'
slot 3: MISSING 'Stutter'              ← this is wrong
slot 4: param[5] = 'Reverb Size'
slot 5: param[6] = 'FX Send'
slot 6: MISSING 'Delay FB'             ← this is wrong
slot 7: param[8] = 'Width'
```

The MISSING entries tell you which macro names need fixing.

### Ableton crashes when FX Machine starts

**Cause 1: AbletonOSC has a bug triggered by FX Machine's queries**

Fix: Update AbletonOSC to the latest version. If the problem persists,
file a bug report with AbletonOSC's developer.

**Cause 2: Too many OSC queries overwhelm Ableton**

Older versions of AbletonOSC are more fragile. Check that you're
running FX Machine v1.0.0 (which uses listener-based architecture,
not polling) — this should not overwhelm even old AbletonOSC versions.

### Ableton works but session changes don't reflect in FX Machine

You change a parameter in Ableton manually and FX Machine doesn't
see the change immediately.

**Cause: Listener event was missed**

UDP is unreliable. Sometimes a listener event from Ableton doesn't
arrive at FX Machine.

Fix: This is what the 2 Hz safety poll is for. Within 2 seconds, the
discrepancy will be detected and corrected. If you can't wait 2
seconds, press SELECT+START for a manual refresh.

---

## Controller Detection Problems

### "● NO CONTROLLER" shown in red

FX Machine doesn't see the gamepad.

**Cause 1: Gamepad not plugged in**

Fix: Plug in the gamepad before launching FX Machine. The watchdog
will detect it within ~5 seconds.

**Cause 2: Gamepad not recognized by Windows**

Fix: Open Windows Device Manager. Look for "Game Controllers" or
similar category. Your gamepad should appear there. If it shows a
yellow warning icon, Windows can't load its driver.

For PlayStation controllers on Windows, you may need:
- DS4Windows (PS4 controllers)
- DualSenseX (PS5 controllers)

For Xbox controllers, Windows usually has built-in drivers.

**Cause 3: Gamepad recognized but doesn't report input**

Fix: Open Windows' built-in "Set up USB game controllers" tool:
1. Win+R → type `joy.cpl` → Enter
2. Your gamepad should appear in the list
3. Click Properties → Test
4. Move the sticks and press buttons — they should light up

If they don't respond there, FX Machine can't see them either.
The problem is at the OS level, not FX Machine's.

### Gamepad sometimes disconnects mid-session

The "● NO CONTROLLER" warning flashes occasionally.

**Cause 1: USB power issue**

USB ports sometimes drop power. Try a different USB port, preferably
one directly on the motherboard (not a hub).

**Cause 2: Worn USB cable**

For wired controllers, the cable may be intermittent. Try a different
cable.

**Cause 3: Wireless interference**

For wireless controllers (Bluetooth/dongle), other 2.4 GHz devices
(wifi, microwaves, other Bluetooth) can cause interference. Move
the dongle closer or use wired connection.

### Controller works but sticks drift

The EQ value slowly changes when the stick is "centered."

**Cause: Stick calibration drift**

Old or worn controllers develop drift. The stick's resting position
isn't exactly 0,0 anymore.

Fix 1: Increase the dead zone in `config/active.toml`:
```toml
[eq.encoder]
dead_zone = 0.25   # was 0.18
```

Press SELECT+START to reload. If drift continues, increase further.

Fix 2: Replace the controller. Stick drift gets worse over time.

### Button presses register multiple times

Pressing X once triggers two clip launches.

**Cause: Hardware button bounce**

Cheap or worn buttons sometimes register multiple presses from a
single physical press.

Fix 1: Increase debounce values in TOML:
```toml
[navigation]
dpad_debounce = 0.40   # was 0.30

[fx.delay_fb]
debounce_s = 0.25      # was 0.18
```

Fix 2: Replace the controller. Button bounce is hardware degradation.

---

## EQ Mode Problems

### "EQ inactive (R3 to toggle)" but R3 doesn't activate

Pressing R3 doesn't turn EQ mode on.

**Cause 1: R3 button not detected**

Verify R3 works:
- The pill labeled "◇ EQ" in the UI should turn purple when R3 is
  pressed
- If it doesn't change, your gamepad isn't reporting R3

Some gamepads label R3 differently or don't have it. R3 is the
right stick CLICK (press the stick down).

Fix: If your gamepad doesn't have R3, you can remap the EQ toggle
to a different button by editing `src/controller/buttons.py`. Look
for `BTN_R3` and change it.

**Cause 2: Modifier keys held**

If SELECT or L1 is held, R3 does something different (volume mute /
wet lock). Make sure no modifier is held when you press R3.

### EQ mode active but stick doesn't change values

Right stick movement doesn't affect EQ.

**Cause 1: Wrong stick axis orientation**

If your gamepad reports the right stick axes rotated 90°, the
"horizontal value" axis maps to "vertical band switch" instead.

Diagnosis: In EQ mode, push the right stick UP. Does it change the
value or switch bands?
- Changes value → axes are correct, problem is elsewhere
- Switches bands → axes are rotated 90°

Fix: Edit `src/config.py` and change:
```python
RIGHT_STICK_ROTATED_90 = True
```
to:
```python
RIGHT_STICK_ROTATED_90 = False
```

Restart the app.

**Cause 2: Dead zone too large**

The stick movement is within the dead zone. Fix: decrease dead_zone:
```toml
[eq.encoder]
dead_zone = 0.10   # was 0.18
```

**Cause 3: Macros not actually mapped to EQ parameters**

The EQ Macros are renamed correctly but not actually mapped to EQ
Three's gain parameters.

Fix: In Ableton, verify the macro mappings:
1. Click the EQ rack to expand it
2. For each macro (EQ Low, EQ Mid, EQ High, Trim), move it manually
3. The corresponding device parameter should move
4. If nothing moves, the mapping is broken — remap it

### Bass boost doesn't go past +2 dB

You push the stick right on the bass band but the value caps before
reaching +6 dB.

**Cause: This is intentional — bass safety cap**

The bass band has a +2 dB safety cap to prevent speaker damage. This
is documented in [SIGNAL_CHAIN.md](SIGNAL_CHAIN.md) under "Bass Safety
System."

If you genuinely need more bass boost (studio work with known-good
speakers), increase the cap:
```toml
[eq.safety]
bass_boost_cap = 120.0   # was 114.0, this gives ~+4 dB
```

For live performance, leave it at the default.

### Bass double-flick right does nothing

"🚫 Bass boost blocked" appears in the status line.

**Cause: This is intentional — double-flick bass boost is blocked**

The double-flick boost gesture is blocked on the bass band specifically.
Use the continuous encoder (push the stick right and hold) to boost
bass up to the cap.

This is by design to prevent accidental bass over-boost.

### Double-flick gestures don't register

You flick the stick left-and-back-left but nothing happens.

**Cause 1: Flick speed not matching detection thresholds**

Default thresholds:
- Stick must reach 0.90 deflection (90%)
- Then return to below 0.22 (22%)
- Then reach 0.90 again
- All within 380ms

If your flicks don't meet these criteria, they're rejected.

Fix: Relax the thresholds:
```toml
[eq.flick]
extreme = 0.80           # was 0.90 — easier to reach
return_threshold = 0.30  # was 0.22 — don't have to return as far
timeout_ms = 500         # was 380 — more time allowed
```

**Cause 2: Cross-axis interference**

If you're flicking horizontally but also moving vertically, the Y axis
might claim dominance and suppress X gestures.

Fix: Try keeping the stick movement purely horizontal. If you can't,
relax the dominance ratio:
```toml
[eq.dominance]
ratio = 4.0   # was 3.0 — Y needs to be 4x larger than X to dominate
```

---

## FX Mode Problems

### Holding L1 doesn't enter FX mode

The "L1 FX" pill doesn't turn yellow when you press L1.

**Cause: L1 button not detected**

Verify L1 works by checking the pill in the UI. If pressing L1 has
no visual effect, your gamepad isn't reporting it.

Fix: Test in Windows' "joy.cpl" tool. If L1 doesn't register there,
the problem is hardware/driver, not FX Machine.

### FX mode active but knobs don't respond

You enter FX mode but stick movements don't change parameters.

**Cause 1: Wrong macros mapped**

Same issue as EQ — the FX macros must be named correctly AND mapped
to the right device parameters. Check both.

**Cause 2: Macros are correctly mapped but at extreme values**

If a macro is already at 0 or at max, moving the stick further in
that direction has no effect (clamping).

Fix: Move the stick in the OTHER direction first. If it responds,
the previous direction was just at the limit.

### FX Send Throw doesn't add wet effects

L1+□ activates the throw but you don't hear reverb/delay.

**Cause 1: FX Send macro mapped to wrong device**

The FX Send macro must map to the Gain parameter of the Utility
device INSIDE the Wet chain of the nested rack. There are TWO Utility
devices in the FX rack — make sure you mapped to the right one.

Fix: In Ableton, expand the FX rack → nested rack → Wet chain. The
first device in the Wet chain should be a Utility. Its Gain parameter
should be mapped to the FX Send macro.

**Cause 2: Reverb/Delay Dry/Wet set wrong**

The Reverb and Delay devices in the Wet chain must have Dry/Wet set
to 100% Wet. Otherwise they output their own dry signal which gets
added to the chain's dry path, causing weird effects.

Fix: Click each device in the Wet chain and set Dry/Wet to 100%.

**Cause 3: Audio not flowing through the FX track**

The FX Send macro works correctly but no audio is reaching the wet
chain because no audio is going through the FX rack at all.

Fix: Verify your audio routing. Audio must flow:
```
Instrument track → EQ Macros track → FX Macros track → Master
```

If your audio routing skips the FX Macros track, the FX rack does
nothing.

### Bass Cut doesn't cut the bass

L1+O activates Bass Cut but you don't hear the bass disappear.

**Cause: Filter Mode mapping incorrect**

The Bass Cut momentary works by:
1. Setting Filter Mode to HP (high-pass)
2. Setting Filter Freq to ~200 Hz

If Filter Mode isn't mapped correctly, HP mode doesn't activate.

Fix: In the FX rack, verify the Filter Mode macro is mapped to the
Auto Filter's filter type selector. Test by moving the macro manually
and watching the filter type change in the Auto Filter UI.

### Tails cut off when FX Send drops

You release the FX Send Throw and the reverb tail stops immediately
instead of ringing out.

**Cause: Reverb/Delay Dry/Wet not 100%**

Same as above — verify the Reverb and Delay devices in the Wet chain
have Dry/Wet set to 100%.

When set to less than 100% wet, the reverb outputs some dry signal
mixed with wet. When you cut FX Send, the input to those devices
stops, which means their dry output stops too — including any "dry"
contribution to what you thought were tails.

100% wet means the device only outputs its processed signal. The dry
path is handled separately by the empty Dry chain.

### Stutter doesn't stop when I release the button

L1+X activates Stutter, but releasing X doesn't deactivate it.

**Cause: Beat Repeat not configured correctly**

The Stutter macro should map to a parameter that, at 0, makes Beat
Repeat completely inactive. If you mapped it to a parameter that
doesn't have a true "off" state, the stutter persists.

Fix: Map Stutter to Beat Repeat's Volume parameter (not its
Activate, which may not produce silent off-state). When Volume = 0,
Beat Repeat outputs nothing regardless of other settings.

---

## Meter Problems

### Meter shows no activity

Audio is playing in Ableton but the FX Machine meter stays dark.

**Cause 1: Audio not flowing through ~ EQ Macros track**

The meter monitors the EQ track's output. If audio doesn't pass
through that track, the meter shows nothing.

Fix: Verify your routing. Audio must flow through the ~ EQ Macros
track for the meter to show levels.

**Cause 2: Meter listeners not registered**

Check the FX Machine console for:
```
EQ meter listeners armed on track 18
```

If this line is missing, the meter listeners failed to register.

Fix: Press SELECT+START to refresh. If still missing, restart the app.

**Cause 3: Reference offset too high**

If `meter.reference_offset_db` is too high (e.g., 24), all signals
show as silence on the display.

Fix: Reduce the offset:
```toml
[meter]
reference_offset_db = 8.7   # was something too high
```

### Meter is always in the red

Even quiet audio shows the meter near maximum.

**Cause: Reference offset too low**

The opposite of the above. If the offset is too low, even -50 dBFS
shows as a bright signal.

Fix: Increase the offset:
```toml
[meter]
reference_offset_db = 12.0   # was 8.7 or lower
```

Tune iteratively: play your typical audio, adjust the offset until
the meter sits in the middle (green/yellow zone) at normal levels.

### CLIP indicator stays lit constantly

The yellow/red CLIP indicator never turns off.

**Cause: Signal level genuinely exceeds the warning threshold**

This is correct behavior if your signal really is hot. The CLIP
indicator is telling you that the EQ track's output is above
+6 dB (default warn_db).

Fix the audio:
- Reduce TRIM
- Lower the input level in Ableton
- Reduce the master volume

OR raise the threshold if your reference is different:
```toml
[meter.clip]
warn_db = 9.0      # was 6.0 — only warn at higher levels
critical_db = 12.0 # was 9.0
```

### Peak indicator stuck at high value

The white peak indicator stays at the top of the meter.

**Cause: Peak hold time too long, or recent peak hasn't decayed**

If you had a brief loud transient, the peak indicator holds at that
level for `peak_hold_seconds` (default 1.5s), then decays at
`peak_fall_db_per_sec` (default 30 dB/s).

If you want faster decay:
```toml
[meter]
peak_hold_seconds = 0.5         # was 1.5 — shorter hold
peak_fall_db_per_sec = 60.0     # was 30.0 — faster decay
```

---

## UI Problems

### Window appears off-screen

You can't see the FX Machine window even though the app is running.

**Cause: Window position saved from a different monitor configuration**

When you connect/disconnect monitors, window positions can end up
outside the visible area.

Fix:
1. Right-click the app in the taskbar
2. Choose "Maximize" or "Move"
3. If "Move" is available, use arrow keys to drag the window onto
   the visible screen

Or in Windows 10/11: Win+Shift+Left/Right Arrow moves a window to the
adjacent monitor.

### Knobs don't redraw smoothly

The knobs jump in chunks instead of smoothly rotating.

**Cause 1: UI refresh rate too slow**

Default is 40 Hz (25ms per frame). If your system is slow, the actual
rate may be lower.

Fix: Check the diagnostics report:
```
✓ ui : 36.8 Hz / target 40.0 Hz
```

If the actual Hz is much lower than 40, the system is bottlenecked.
See [Performance Problems](#performance-problems).

**Cause 2: OSC write throttle filtering out updates**

The encoder writes are throttled to 15ms intervals (66 Hz). Combined
with the UI's 40 Hz refresh, you may see steppy movement.

This is normally not visible. If it bothers you:
```toml
[eq.osc]
write_throttle = 0.010   # was 0.015 — more frequent updates
```

### Labels show wrong colors

Track or scene names show in unexpected colors.

**Cause: Ableton's track/scene color is being applied**

FX Machine reads track/scene colors from Ableton and uses them to
color the UI labels. If a track is colored red in Ableton, its name
appears red in FX Machine.

This is by design (visual consistency with Ableton). If you don't
like it, change the track colors in Ableton or hard-code defaults
in `src/ui/updater.py`.

### Notification slot shows old messages

The notification text at the top of the FX panel doesn't update.

**Cause: Notification stayed past its duration**

Each notification has a duration (default 3 seconds). After the
duration expires, the slot should clear.

If a notification persists:
- Restart the app
- Check `src/ui/updater.py` for the notification rendering code

### Window resize is ugly

Resizing the window causes weird artifacts or misaligned widgets.

**Cause: Tkinter doesn't dynamically lay out**

FX Machine's UI is designed for a fixed window size. Resizing breaks
the layout because widgets don't reflow.

Fix: Keep the window at its default size (760×900). Or set the
size you want in `config/active.toml`:

```toml
[ui]
window_width = 800     # default 760
window_height = 950    # default 900
```

This is a RESTART setting.

---

## Audio Problems

### Audio sounds distorted

The audio coming out of Ableton (with FX Machine running) sounds
clipped or distorted.

**Cause 1: Internal clipping from EQ boost**

You boosted a band aggressively (e.g., +6 dB on high) and now the
internal signal exceeds digital headroom.

Fix:
- Reduce the EQ boost
- Or reduce TRIM to compensate (e.g., set TRIM to -3 dB)
- Or reduce the input level in Ableton before it hits the EQ rack

**Cause 2: Wet send too hot**

You set FX Send to maximum and the combined dry+wet signal exceeds
unity gain.

Fix:
- Reduce the wet level in Ableton (lower the Reverb output or Delay
  output)
- Reduce FX Send below maximum

**Cause 3: Multiple effects overlapping**

If you have stutter active during a throw, with EQ boost, the
combined effect can clip.

Fix: Use effects more sparingly. Don't stack everything at once.

### Audio has latency

Sounds delayed when you trigger them via gamepad.

**Cause 1: Ableton's audio buffer too large**

Larger buffers (1024 samples or higher) introduce noticeable latency.

Fix: In Ableton's preferences → Audio, reduce the buffer size to 256
or 128 samples. This requires more CPU but reduces latency.

**Cause 2: Wireless audio**

Bluetooth speakers/headphones add 100-200ms of latency. This is on
top of FX Machine's processing latency.

Fix: Use wired audio output for live performance.

### Tails sound granular or stuttery

The reverb tails or delay echoes have audible artifacts.

**Cause 1: CPU overload causing audio dropouts**

If Ableton can't keep up with the audio processing, it produces
glitches.

Fix: Check Ableton's CPU meter (top-right). If it's red, you're
overloading. Reduce:
- Number of active plugins
- Reverb quality (set to Eco)
- Sample rate (44.1 kHz instead of 48 kHz)
- Buffer size (might help if CPU is the bottleneck)

**Cause 2: USB audio interface dropouts**

If you use a USB audio interface, USB bandwidth issues can cause
dropouts. Try a different USB port, ideally one directly on the
motherboard.

### Mono signal from a stereo source

The audio becomes mono when going through the rack.

**Cause: Width macro set to 0**

The Width macro at 0 collapses the stereo signal to mono.

Fix: Set Width macro to ~64 (default middle = 100% stereo).

---

## Performance Problems

### App is sluggish

The UI feels laggy, responses are slow.

**Cause 1: CPU bottleneck**

Run with diagnostics enabled:
```toml
[diagnostics]
enabled = true
```

Then check the diagnostics log for the top functions by CPU time. If
one function dominates, that's your bottleneck.

If `draw_djm_meter` is the top function (>5% of CPU), you may have
an old version without the PhotoImage optimization. Verify you're
running v1.0.0.

**Cause 2: Too many threads / processes running**

Close other CPU-intensive apps. FX Machine + Ableton can use 30-50%
CPU during heavy use. Add a browser with 50 tabs, you're maxed out.

### CPU usage is very high

Task Manager shows FX Machine using 20%+ CPU.

**Cause 1: Diagnostics layer enabled**

The diagnostics adds 1-2% CPU. If you're not actively investigating,
disable it:
```toml
[diagnostics]
enabled = false
```

**Cause 2: Old build with un-optimized meter**

v1.0.0 includes the PhotoImage meter optimization that dramatically
reduces UI CPU. Earlier versions used 20% of one CPU core for meter
alone.

Verify: Check `src/config.py` for `VERSION = "1.0.0"` or higher.

**Cause 3: Garbage collection storms**

Python's garbage collector occasionally runs a full collection that
pauses the app briefly. If this happens often, memory pressure may
be high.

Fix: Restart the app to clear memory. If the issue persists, run
diagnostics and check the memory growth rate — if it's >1 MB/min,
something is leaking memory.

### Memory keeps growing

Task Manager shows FX Machine's memory increasing over time.

**Cause: Memory leak**

This shouldn't happen. v1.0.0 has bounded data structures everywhere
— the diagnostics layer alone uses <1 MB regardless of session length.

If you see growth >5 MB over a 1-hour session, there's a leak. Steps
to diagnose:

1. Enable diagnostics
2. Run a controlled session for 30 minutes
3. Check the diagnostics report's memory growth rate
4. Look at which functions appear in the outlier list

Report the issue with the diagnostics log attached.

### Network/disk activity spikes

The app intermittently makes Windows feel slow.

**Cause: Log rotation**

When the main log file hits 5 MB, it gets rotated (old log renamed,
new log created). This briefly disk-thrashes.

This is normal and happens infrequently (every few hours of active
use). Not a real problem.

---

## Configuration Problems

### TOML edits don't take effect

You edit `config/active.toml` but the change doesn't appear.

**Cause 1: You forgot to reload**

The app only re-reads the TOML when you press SELECT+START or click
the ⟳ REFRESH button. Editing the file doesn't automatically reload.

Fix: After editing, press SELECT+START.

**Cause 2: TOML syntax error in your edit**

If your edit broke the TOML syntax, the reload fails silently (well,
with a notification) and the old values stay in effect.

Fix: Check the notification slot in the UI. If it says "Config has
errors," your TOML is broken. Run:

```bash
python -c "import tomllib; tomllib.load(open('config/active.toml', 'rb')); print('OK')"
```

If you see a `TOMLDecodeError`, the error message tells you which line
is broken.

**Cause 3: You changed a RESTART value**

Some values require restarting the app (window size, OSC ports, hook
list, etc.). Changing them mid-session doesn't have any effect.

Fix: Restart the app. The notification slot tells you "N need restart"
when you've made restart-required changes.

### Wrong config file edited

You edited `config/default.toml` thinking changes would apply.

**Cause: default.toml is the template, active.toml is what gets read**

`default.toml` is the factory template. The app reads from
`active.toml`. Edits to `default.toml` only take effect if `active.toml`
doesn't exist (then the app re-creates `active.toml` from `default.toml`).

Fix:
- Edit `active.toml` directly going forward
- Or delete `active.toml` to force the app to recreate it from your
  modified `default.toml`

### Reset configuration to defaults

Your TOML is so messed up you want to start over.

Fix:
```bash
# Option 1: Copy default over active
copy config\default.toml config\active.toml

# Option 2: Delete active, let the app recreate it
del config\active.toml
```

Then launch the app — it'll regenerate `active.toml` from `default.toml`.

---

## Diagnostics Layer Problems

### Diagnostics enabled but no log file appears

You set `enabled = true` but `logs/diagnostics.log` doesn't exist.

**Cause 1: Logs folder doesn't exist or isn't writable**

Fix: Check that `logs/` exists in the app's folder. If not, create it
manually. If it exists but is read-only, fix permissions.

**Cause 2: Diagnostics failed to install**

Check the main log for `[diag.installer]` messages. If any failed,
the diagnostics might not be running.

```bash
findstr "diag.installer" logs\fxmachine.log
```

You should see install confirmation messages. If they're absent or
show errors, diagnostics didn't start.

**Cause 3: enabled value didn't reach the cfg singleton**

Verify:
```bash
python -c "from src.config_loader import init_config, cfg; init_config(); print('DIAG_ENABLED =', cfg.DIAG_ENABLED)"
```

Should print `True`. If it prints `False`, the TOML wasn't read
correctly.

### Functions not appearing in profiler output

You added a function to `timed_functions` but it doesn't appear in
the report.

**Cause 1: Typo in function path**

Check the spelling. The dotted path must exactly match the module
hierarchy. `src.ui.updater.update_ui` is correct.

**Cause 2: Function never called during session**

If the function exists but the code path that calls it didn't execute
during your session, it won't appear (0 calls = not shown).

Fix: Actually trigger the function. For UI functions, interact with
the UI. For OSC functions, send OSC traffic. Etc.

**Cause 3: Cross-module hook didn't catch caller**

The installer walks `sys.modules` to find all references. If a module
hadn't been imported yet at install time, the hook wouldn't have
caught it.

This shouldn't normally happen for FX Machine's main modules (they're
all imported at startup), but custom additions might miss the
installation window.

### Reporter writing duplicate lines

The diagnostics log shows the same line multiple times.

**Cause: Old reporter version using Python's logging module**

v1.0.0 uses direct file writes specifically to avoid this issue.
If you're seeing duplication, you may have an older version of
`reporter.py` that uses `self._text_logger.info()`.

Fix: Update to v1.0.0's `reporter.py` which uses `_write_text()`
exclusively.

### "_enter_buffered_busy" crash on shutdown

```
Fatal Python error: _enter_buffered_busy
```

**Cause: Diagnostics threads still writing to stdout when Python
finalizes**

Fix: Make sure `shutdown_diagnostics()` is called BEFORE
`root.destroy()` and BEFORE `sys.exit()` in `main.py`.

In v1.0.0, the on_close handler does this correctly. If you've
modified `main.py`, ensure the diagnostics shutdown is the SECOND
step (after setting the shutdown flag, before stopping OSC).

---

## Build and .exe Problems

### Build fails with "PyInstaller is not installed"

Fix:
```bash
pip install pyinstaller
```

### Build succeeds but .exe doesn't run

The .exe starts but immediately closes, or shows an error.

**Cause 1: Missing DLLs**

PyInstaller missed bundling a required DLL.

Fix: Run the inspector to see what's bundled:
```bash
python inspect_exe.py
```

If a required DLL is missing, add it to the spec file's `binaries=`
list.

**Cause 2: Hidden imports missing**

A dynamically-imported module wasn't detected.

Fix: Add to `hiddenimports=` in the spec file:
```python
hiddenimports=[
    'src.diagnostics.installer',
    'some_missing_module',
],
```

Rebuild.

**Cause 3: Antivirus blocking**

Some antivirus tools flag PyInstaller builds as suspicious.

Fix: Add the built folder to your antivirus exclusions, or scan the
.exe with VirusTotal to confirm it's a false positive.

### Built .exe missing config files

The .exe runs but complains about missing TOML files.

**Cause: build.py didn't copy config files**

Fix: Re-run `python build.py`. The script should copy all config files
automatically. If it didn't, check that `config/default.toml`,
`config/EXAMPLES.toml`, and `config/README.md` exist in the source
directory.

### Built .exe is much bigger than expected

The output folder is >100 MB.

**Cause 1: Onefile mode by accident**

Verify your spec file uses onedir, not onefile:
```python
exe = EXE(
    pyz, a.scripts,
    [],
    name='FX_Machine',
    # onefile would have `a.binaries, a.zipfiles, a.datas` here
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    name='FX_Machine',
)
```

Onefile bundles everything into the .exe. Onedir produces a folder.

**Cause 2: Unused packages bundled**

Run the inspector to see what's bundled. If there are large packages
you don't use, add them to `excludes=`:
```python
excludes=['matplotlib', 'numpy', 'PIL'],
```

---

## Shutdown Problems

### App doesn't close cleanly

Closing the window leaves a Python process running in the background.

**Cause: Threads not exiting**

Daemon threads should die when the main thread exits, but if they're
stuck in a blocking call (long sleep, blocked I/O), they may not
respond to shutdown signals immediately.

Fix: Force-quit via Task Manager. If this happens consistently,
there's a bug in the shutdown sequence.

### "_enter_buffered_busy" error on shutdown

See [Diagnostics Layer Problems](#diagnostics-layer-problems) section.

### Tkinter error: "can't invoke 'destroy' command"

```
_tkinter.TclError: can't invoke "destroy" command: application has been destroyed
```

**Cause: Race condition in shutdown sequence**

In v1.0.0, this is fixed by:
1. Idempotency guard on `on_close` (prevents double-execution)
2. `winfo_exists()` check before `root.destroy()`
3. try/except around the destroy call

If you're seeing this, you may have an older version of `main.py`.
Update to v1.0.0.

### Console window stays open after closing

If you built with `console=True` and the .exe exited, the console
window should close too.

If it stays open, there's likely an unhandled exception in the final
shutdown step. Check the console for the traceback.

---

## Log File Problems

### Log files growing too large

`logs/fxmachine.log` is gigabytes.

**Cause: Rotation isn't happening**

Log rotation is automatic (5 MB max, 10 backups). If rotation isn't
working, the file grows unbounded.

Fix: Check that the `logs/` folder is writable. Manual log rotation:
```bash
del logs\fxmachine.log
```

The app recreates it on next launch.

### Log file is empty

`fxmachine.log` exists but is empty (0 bytes).

**Cause 1: App crashed before any logs were written**

Fix: Run from command line to see what's happening:
```bash
python run.py
```

If errors appear in the console, that's what would normally go to
the log.

**Cause 2: Log handler isn't initialized**

The log handler is set up early in `main.py`. If it failed, no logs
get written.

Fix: Check `src/log_setup.py` for errors during initialization.

### Can't read log file - permission denied

The OS won't let you open the log file.

**Cause: File is open by another process**

The FX Machine app holds the log file open while running. To read it
mid-session:

```bash
# PowerShell — read while file is open
Get-Content logs\fxmachine.log -Tail 100
```

Or close FX Machine and open the log file normally.

### Diagnostics log shows weird characters

Unicode box-drawing characters (═ ║) appear as `Ô?Ô?` or similar.

**Cause: Console code page doesn't support Unicode**

The log file is correct (UTF-8 encoded). Your console is the problem.

Fix: Open the log in Notepad, VS Code, or any modern editor. They
handle Unicode correctly.

Or change the console code page:
```bash
chcp 65001
type logs\diagnostics.log
```

---

## Macro Discovery Problems

### Macros found in Ableton but not detected by FX Machine

You can see the macros in Ableton but FX Machine reports "MISSING".

**Cause 1: Discovery hasn't run**

After making changes in Ableton, FX Machine needs to rediscover the
session.

Fix: Press SELECT+START to refresh.

**Cause 2: Wrong rack track found**

Maybe you have TWO tracks named "~ FX Macros" by accident and the
wrong one was discovered.

Fix: Check the Ableton session for duplicate tracks. The discovery
uses the FIRST track found with the matching name.

### Macro values don't update in UI

You move a macro in Ableton manually but the UI doesn't reflect the
change.

**Cause 1: Listener not registered**

Check the console for "FX listeners registered: 16 listeners armed".
If absent, listeners aren't working.

Fix: SELECT+START to refresh.

**Cause 2: Listener was registered but Ableton crashed/restarted**

When Ableton restarts, all listeners are lost. FX Machine doesn't
automatically detect this.

Fix: SELECT+START to refresh after Ableton restart.

---

## Navigation Problems

### D-pad does nothing

Pressing D-pad up/down/left/right has no effect.

**Cause 1: D-pad not registered as a "hat" by pygame**

Some controllers report D-pad as buttons instead of a hat. pygame's
`get_numhats()` returns 0.

Diagnosis: Run the diagnostic:
```bash
python diagnose.py
```

Check the gamepad section. If hats = 0, your D-pad isn't recognized
as a hat.

Fix: For some controllers, you need a driver to map D-pad as hat:
- PlayStation: DS4Windows (PS4) or DualSenseX (PS5)
- Xbox: usually works out of the box
- Generic: try a different driver mode

### Bookmark navigation doesn't work

D-pad up/down shows "no bookmarks" or doesn't navigate.

**Cause: No § prefixed scenes**

Bookmarks are scenes whose names start with `§` (section sign).

Fix: In Ableton, rename your target scenes to start with `§`:
```
§ INTRO
§ DROP 1
§ BREAKDOWN
```

After renaming, SELECT+START to refresh.

### Group navigation doesn't work

D-pad left/right shows "no groups" or falls back to 4-track stepping.

**Cause: No * prefixed tracks**

Groups are tracks whose names start with `*` (asterisk).

Fix: In Ableton, rename your section lead tracks:
```
* KICK
* BASS
* SYNTH
```

After renaming, SELECT+START to refresh.

### Wrong track selected after navigation

Pressing D-pad goes to an unexpected track.

**Cause: Group memory**

FX Machine remembers which track you were viewing within each group.
When you return to that group, it takes you back to the last track,
not the lead track.

Fix: Hold R2 while pressing D-pad to force-jump to the lead track
of each group.

---

## Momentary Effect Problems

### Stutter sound is weak or not pronounced

L1+X activates Stutter but the effect is subtle.

**Cause: Beat Repeat parameters set conservatively**

The Stutter momentary only activates Beat Repeat (sets it to ON). The
actual stutter character (grid division, gate, decay) is set in Beat
Repeat's own UI.

Fix: In Ableton, open the Beat Repeat device. Tune:
- **Interval:** 1/16 or 1/8 for more obvious stuttering
- **Variation:** Higher values for more random stuttering
- **Volume:** Higher for more prominent effect

### Bass Cut leaks some bass

L1+O activates Bass Cut but you still hear some low end.

**Cause: HP filter at 200 Hz isn't steep enough**

Auto Filter's default rolloff is 12 dB/octave. Frequencies below 200 Hz
still have audible content.

Fix: In Auto Filter, increase the slope to 24 or 48 dB/octave for a
sharper cut. The bass will disappear more completely.

Or change the cutoff frequency in `src/config.py`:
```python
BASS_CUT_FREQ_VALUE = 60.0   # was 42.3 — higher cutoff = more cut
```

### FX Send Throw doesn't restore previous value

After releasing L1+□, the FX Send doesn't go back to where it was.

**Cause: Snapshot/restore not working correctly**

The momentary effect captures the current value when pressed and
restores it on release. If this isn't working:

1. Check `_momentary_fx_throw_snapshot` in state.py
2. Verify the press/release sequence in
   `src/engine/momentary.py`

In v1.0.0, this works correctly. If you see misbehavior, check that
you have the latest version.

---

## Recovery Procedures

### Hard reset

Something is fundamentally broken and you want to start over:

1. Close FX Machine
2. Delete `config/active.toml`
3. Delete `logs/` folder (optional, just cleans up)
4. Restart the app — it regenerates active.toml from default.toml

### Restore configuration from preset

Replace your config with a known-good preset:

```bash
copy config\EXAMPLES.toml config\active.toml
```

Then edit `active.toml` to extract just the preset you want.

### Reset Ableton listener state

If Ableton's listener state seems out of sync:

1. In FX Machine, press SELECT+START
2. This unregisters all listeners, rediscovers the session, and
   re-registers fresh listeners

### Force gamepad redetection

If the gamepad isn't being detected:

1. Unplug the gamepad
2. Wait 5 seconds
3. Plug it back in
4. Wait for the FX Machine watchdog to detect it (1-5 seconds)

If that doesn't work:
1. Close FX Machine
2. Unplug gamepad
3. Restart computer
4. Plug gamepad in BEFORE starting FX Machine

### Restart the OSC connection

If OSC seems stuck:

1. Close FX Machine
2. Close and reopen Ableton (this resets AbletonOSC)
3. Restart FX Machine

---

## Reading Log Files

### Main log: logs/fxmachine.log

Format:
```
01:17:04.694 [INFO ] fxmachine.main : Session started
01:17:04.711 [INFO ] fxmachine.config_loader : Config loaded
01:17:05.114 [INFO ] fxmachine.engine.polling : Session size changed
```

Columns:
- Timestamp (HH:MM:SS.ms)
- Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Module name (with `fxmachine.` prefix)
- Message

### What to look for

**Startup sequence:** Verify all expected log lines appear in the
first few seconds.

**Errors and warnings:** Search for `[ERROR]` or `[WARNING]`:
```bash
findstr "ERROR" logs\fxmachine.log
findstr "WARNING" logs\fxmachine.log
```

**Specific events:** Search for keywords:
```bash
findstr "FX track found" logs\fxmachine.log
findstr "EQ macros mapped" logs\fxmachine.log
findstr "Controller" logs\fxmachine.log
```

### Diagnostics log: logs/diagnostics.log

Already covered in [DIAGNOSTICS_GUIDE.md](DIAGNOSTICS_GUIDE.md).

### JSONL log: logs/diagnostics.jsonl

Machine-readable. Use Python to analyze:

```python
import json
with open("logs/diagnostics.jsonl") as f:
    events = [json.loads(line) for line in f if line.strip()]

# Find all warnings across all summaries
for event in events:
    if event.get("type") == "summary":
        for warning in event.get("warnings", []):
            print(event["timestamp"], warning)
```

---

## Getting Help

If you've exhausted the troubleshooting steps:

### 1. Run the diagnostic tool with verbose output

```bash
python diagnose.py --verbose > diagnostic_output.txt
```

### 2. Collect log files

- `logs/fxmachine.log`
- `logs/diagnostics.log` (if diagnostics was enabled)
- `logs/diagnostics.jsonl` (if diagnostics was enabled)

### 3. Note your environment

- Operating system version (Win 10/11, specific build)
- Python version (`python --version`)
- Ableton version
- AbletonOSC version
- Gamepad model
- Recent changes (TOML edits, code modifications, system updates)

### 4. Describe the problem precisely

- What you expected to happen
- What actually happened
- Steps to reproduce
- Whether it always happens or intermittently

### 5. Reach out

FX Machine is currently a personal project by Ayoub Agoujdad (MIRA).
Reach out via the project's distribution channels.

---

## Known Issues

### v1.0.0 known issues

**1. Right stick rotation hardcoded**

`RIGHT_STICK_ROTATED_90 = True` is a compile-time constant in
`src/config.py`. Users with non-rotated gamepads must edit source
code to change it.

Workaround: Edit `src/config.py` if needed.
Future fix: Make it a TOML setting.

**2. Some Tkinter widgets don't honor color changes immediately**

Occasionally, color updates to labels don't render until the next
window event (mouse move, etc.).

Workaround: None — visual annoyance only.
Future fix: PySide6 migration.

**3. PyInstaller false-positive antivirus flags**

Some antivirus tools flag PyInstaller-built executables as suspicious.

Workaround: Add to exclusions, or code-sign the .exe.
Future fix: Code signing for releases.

**4. Diagnostics inspector misses some details on first run**

The `inspect_exe.py` tool sometimes shows minor warnings about
optional DLLs being missing. Not a real issue.

Workaround: Ignore warnings about optional DLLs.

**5. Empty session shows weird counts**

If you launch FX Machine before Ableton has fully loaded a project,
the track/scene counts may show 0 momentarily.

Workaround: Wait until Ableton is fully loaded before starting
FX Machine. Or press SELECT+START to refresh.

---

## Error Message Reference

| Error | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'pygame'` | Dependencies not installed | `pip install pygame python-osc psutil` |
| `'python' is not recognized` | Python not in PATH | Reinstall Python, check "Add to PATH" |
| `SyntaxError` (in tomllib or source) | Old Python version | Install Python 3.11+ |
| `_tkinter.TclError: can't invoke "destroy"` | Race condition in shutdown | Update to v1.0.0 |
| `Fatal Python error: _enter_buffered_busy` | Threads writing during shutdown | Update to v1.0.0 |
| `OSError: [Errno 98] Address already in use` | Port conflict | Change OSC ports in TOML |
| `pygame.error: video system not initialized` | pygame torn down during shutdown | Normal — happens on clean shutdown |
| `tomllib.TOMLDecodeError` | TOML syntax error in active.toml | Fix the syntax error or delete active.toml |
| `KeyError: '_vol_last_sent'` | Missing state key (old bug) | Update to v1.0.0 |
| `PermissionError: [Errno 13]` | File permission issue | Check folder is writable |
| `AttributeError: 'cfg' object has no attribute 'X'` | TOML key in code but not in default.toml | Add the key to default.toml |
| `FileNotFoundError: ... 'FX_Machine.spec'` | Build script missing spec file | Generate with `python -m PyInstaller --name FX_Machine --onedir run.py` |
| `[diag.installer] OSC client send_message hook skipped` | Hook installed before st.osc ready | Normal during install — listener-based system handles this |
| `Listener stop error: ...` | OSC listener cleanup failed | Usually harmless, happens during fast restarts |
| `Controller LOST` | Gamepad disconnected | Reconnect the gamepad |
| `FX track '~ FX Macros' not found` | Track name mismatch | Verify exact name in Ableton |
| `Session size changed` | Tracks/scenes added or removed | Normal informational message |

---

*This document covers known issues and troubleshooting for FX Machine
v1.0.0. New issues discovered after release will be documented in
future versions of this guide. For the most up-to-date troubleshooting
information, check the project's distribution channels.*
```
