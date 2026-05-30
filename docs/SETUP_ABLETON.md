## docs/SETUP_ABLETON.md

# 🎚️ FX Machine — Ableton Live Setup Guide

## What This Document Covers

This guide walks you through every step of setting up Ableton Live
to work with FX Machine — installing AbletonOSC, creating the two
required racks (~ EQ Macros and ~ FX Macros), mapping macros to
device parameters, understanding the naming conventions, setting up
bookmarks and groups, and verifying everything works.

This is the document you follow the FIRST time you set up FX Machine.
After setup is complete, you won't need to do it again unless you
create a new Ableton project from scratch or change your rack
structure.

If something isn't working after following this guide, see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and fixes.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Step 1 — Install AbletonOSC](#step-1--install-abletonosc)
3. [Step 2 — Verify AbletonOSC is Working](#step-2--verify-abletonosc-is-working)
4. [Step 3 — Create the EQ Macros Track](#step-3--create-the-eq-macros-track)
5. [Step 4 — Build the EQ Rack](#step-4--build-the-eq-rack)
6. [Step 5 — Map the EQ Macros](#step-5--map-the-eq-macros)
7. [Step 6 — Verify the EQ Rack](#step-6--verify-the-eq-rack)
8. [Step 7 — Create the FX Macros Track](#step-7--create-the-fx-macros-track)
9. [Step 8 — Build the FX Rack — Outer Layer](#step-8--build-the-fx-rack--outer-layer)
10. [Step 9 — Build the FX Rack — Wet/Dry Inner Layer](#step-9--build-the-fx-rack--wetdry-inner-layer)
11. [Step 10 — Map the FX Macros](#step-10--map-the-fx-macros)
12. [Step 11 — Verify the FX Rack](#step-11--verify-the-fx-rack)
13. [Step 12 — Route Audio Through the Racks](#step-12--route-audio-through-the-racks)
14. [Step 13 — Set Up Bookmarks](#step-13--set-up-bookmarks)
15. [Step 14 — Set Up Groups](#step-14--set-up-groups)
16. [Step 15 — First Launch of FX Machine](#step-15--first-launch-of-fx-machine)
17. [Step 16 — Verify Full Connection](#step-16--verify-full-connection)
18. [Understanding the Naming Conventions](#understanding-the-naming-conventions)
19. [Common Setup Mistakes](#common-setup-mistakes)
20. [Advanced — Using Return Tracks Instead of Audio Tracks](#advanced--using-return-tracks-instead-of-audio-tracks)
21. [Advanced — Multiple Channel Strips](#advanced--multiple-channel-strips)
22. [Saving as a Template](#saving-as-a-template)
23. [Updating an Existing Project](#updating-an-existing-project)
24. [Port Configuration](#port-configuration)
25. [Troubleshooting AbletonOSC](#troubleshooting-abletonosc)

---

## Prerequisites

Before you begin, make sure you have:

- **Ableton Live 10, 11, or 12** (any edition — Intro, Standard, Suite)
- **AbletonOSC** Remote Script (we'll install it in Step 1)
- **FX Machine** installed and runnable (`python run.py` works, or the
  portable .exe is extracted)
- **A USB gamepad** plugged in and recognized by Windows
- **~30 minutes** for the initial setup (subsequent projects reuse
  the template)

### Ableton device requirements

The FX rack uses these specific Ableton devices:

| Device | Rack | Required edition |
|---|---|---|
| **EQ Three** | EQ Macros | All editions (Intro+) |
| **Utility** | EQ Macros (TRIM) + FX Macros (Send + Width) | All editions |
| **Auto Filter** | FX Macros | All editions |
| **Beat Repeat** | FX Macros | Standard+ (not in Intro) |
| **Reverb** (Dark Hall preset) | FX Macros | Standard+ |
| **Delay** (Long Digi Delay preset) | FX Macros | Standard+ |

If you have Ableton Intro, you can still use the EQ section. The FX
rack requires Standard or Suite for Beat Repeat, Reverb, and Delay.
You can substitute equivalent third-party plugins if needed, but the
macro names must match exactly.

---

## Step 1 — Install AbletonOSC

AbletonOSC is a Remote Script that exposes Ableton Live's internal
API as OSC endpoints. FX Machine communicates exclusively through it.

### Download

Go to [github.com/ideoforms/AbletonOSC](https://github.com/ideoforms/AbletonOSC)
and download the latest release (ZIP file).

### Install

1. **Locate your Remote Scripts folder:**

   | OS | Path |
   |---|---|
   | Windows | `C:\ProgramData\Ableton\Live 12\Resources\MIDI Remote Scripts\` |
   | macOS | `/Applications/Ableton Live 12.app/Contents/App-Resources/MIDI Remote Scripts/` |

   Note: The exact path depends on your Ableton version (10, 11, 12)
   and installation location. The `ProgramData` folder on Windows is
   hidden by default — type the path directly into the File Explorer
   address bar.

   For Ableton 11: replace `Live 12` with `Live 11 Suite` (or `Standard`).

2. **Extract the AbletonOSC folder** from the ZIP into the Remote
   Scripts folder. After extraction, you should see:

   ```
   MIDI Remote Scripts/
   ├── AbletonOSC/
   │   ├── __init__.py
   │   ├── abletonosc.py
   │   └── ... (other files)
   ├── Push/
   ├── Push2/
   └── ... (other Remote Scripts)
   ```

3. **Restart Ableton Live** (if it was running).

4. **Activate the script** in Ableton's preferences:
   - Open Preferences → **Link, Tempo & MIDI** (Ableton 11) or
     **Link / Tempo / MIDI** (Ableton 12)
   - Under **Control Surface**, find an empty slot
   - Select **AbletonOSC** from the dropdown
   - Input and Output can remain set to "None" (AbletonOSC uses
     network sockets, not MIDI ports)

5. **Verify in Ableton's log window** (View → Show Log Window, if
   available) that AbletonOSC reports it's listening on port 11000.

---

## Step 2 — Verify AbletonOSC is Working

Before setting up any racks, verify that AbletonOSC is actually
running and responding to OSC messages.

### Quick test from command line

With Ableton running and AbletonOSC active:

```bash
python -c "
from pythonosc import udp_client
c = udp_client.SimpleUDPClient('127.0.0.1', 11000)
c.send_message('/live/song/get/tempo', [])
print('Message sent — check Ableton for response')
"
```

If AbletonOSC is working, Ableton will receive the tempo query. You
won't see the response in this test (it goes to port 11001 which
nothing is listening on yet), but the absence of an error means the
connection is alive.

### Full test with FX Machine

```bash
python run.py
```

Watch the console output. You should see:

```
OSC sender ready → 127.0.0.1:11000
OSC receiver listening ← 127.0.0.1:11001
```

Within a few seconds:

```
Session: 8 scenes, 21 tracks
```

If you see the track/scene count, AbletonOSC is working. If you see
errors or the counts never appear, see
[Troubleshooting AbletonOSC](#troubleshooting-abletonosc) below.

### Port conflicts

FX Machine uses:
- **Port 11000** — sends TO Ableton (AbletonOSC default receive port)
- **Port 11001** — receives FROM Ableton (AbletonOSC default send port)

If another application is using these ports, you'll see bind errors.
See [Port Configuration](#port-configuration) for how to change them.

---

## Step 3 — Create the EQ Macros Track

The EQ rack lives on a track named exactly `~ EQ Macros`. The tilde
(`~`) prefix is a convention that sorts the track to the bottom of
Ableton's track list and visually distinguishes it from your
instrument/audio tracks.

### Create the track

1. In Ableton, create a new **Audio Track** (Ctrl+T / Cmd+T)
2. **Rename it** to exactly: `~ EQ Macros`
   - Double-click the track name to edit
   - Type `~ EQ Macros` exactly as shown (space after the tilde)
   - Press Enter to confirm

### Important naming rules

- The name must be **exactly** `~ EQ Macros` (case-sensitive)
- There must be a space between `~` and `EQ`
- "Macros" is plural with a capital M
- Do NOT add extra spaces, special characters, or numbers
- FX Machine searches for this exact string during discovery

### Positioning

You can place the track anywhere in your session. FX Machine finds it
by name, not by position. However, placing it after your instrument
tracks (toward the right side of the session) keeps your workspace
clean.

---

## Step 4 — Build the EQ Rack

The EQ rack is an Audio Effect Rack containing four macros mapped to
two devices: a Utility (for TRIM) and an EQ Three (for LOW/MID/HIGH).

### Device chain order

```
~ EQ Macros (Audio Track)
│
└── Audio Effect Rack    ← this is what we're building
    │
    ├── Utility          ← TRIM (gain before EQ)
    │   Gain parameter → mapped to macro "Trim"
    │
    └── EQ Three         ← 3-band EQ
        GainLow  → mapped to macro "EQ Low"
        GainMid  → mapped to macro "EQ Mid"
        GainHi   → mapped to macro "EQ High"
```

### Step-by-step

1. **Select the `~ EQ Macros` track**

2. **Add an Audio Effect Rack:**
   - From the browser, drag **Audio Effect Rack** onto the track
   - Or: press Ctrl+G (Cmd+G) on an empty track to create a rack
   
3. **Add a Utility device FIRST (for TRIM):**
   - From the browser → Audio Effects → Utility
   - Drag it into the rack's device chain
   - This MUST be the first device in the chain (before EQ Three)
   - The Utility's **Gain** parameter is what TRIM controls

4. **Add an EQ Three AFTER the Utility:**
   - From the browser → Audio Effects → EQ Three
   - Drag it into the rack's device chain, to the RIGHT of Utility
   - This creates the chain: Utility → EQ Three

5. **Verify the device order:**
   The chain should read left-to-right as:
   ```
   [Utility] → [EQ Three]
   ```
   If they're in the wrong order, drag to reposition.

### Why Utility before EQ Three?

TRIM controls the input gain BEFORE equalization. On a real DJM-900
NXS2, the TRIM knob sits at the top of the channel strip and adjusts
the level entering the EQ section. Putting Utility first replicates
this signal flow: gain adjustment → frequency shaping.

---

## Step 5 — Map the EQ Macros

Now we connect the rack's macros to the device parameters.

### Show the macro controls

1. Click the **Audio Effect Rack** title bar to select it
2. If you don't see the macro knobs, click the **Macro** button
   (or the "Show/Hide Macro Controls" button) on the rack

You should see 8 macro knobs labeled "Macro 1" through "Macro 8."
We'll use the first 4.

### Map macro 1 → EQ Low

1. Click on the **EQ Three** device to expand it
2. Find the **GainLow** parameter (the leftmost gain knob)
3. **Right-click** on GainLow → **Map to Macro 1**
4. The macro knob now controls GainLow
5. **Rename the macro:** Right-click Macro 1's label → **Rename**
   → type exactly: `EQ Low`

### Map macro 2 → EQ Mid

1. Find EQ Three's **GainMid** parameter
2. Right-click → **Map to Macro 2**
3. Rename Macro 2 to exactly: `EQ Mid`

### Map macro 3 → EQ High

1. Find EQ Three's **GainHi** parameter
2. Right-click → **Map to Macro 3**
3. Rename Macro 3 to exactly: `EQ High`

### Map macro 4 → Trim

1. Click on the **Utility** device to expand it
2. Find the **Gain** parameter
3. Right-click → **Map to Macro 4**
4. Rename Macro 4 to exactly: `Trim`

### Critical naming rules for macros

FX Machine searches for these exact macro names during session
discovery. If a name doesn't match, the macro won't be found and
that band won't be controllable.

| Macro # | Name (exact) | Maps to | Device |
|---|---|---|---|
| 1 | `EQ Low` | GainLow | EQ Three |
| 2 | `EQ Mid` | GainMid | EQ Three |
| 3 | `EQ High` | GainHi | EQ Three |
| 4 | `Trim` | Gain | Utility |

- Case matters: `EQ Low` not `eq low` or `EQ LOW`
- Space matters: `EQ Low` not `EQLow` or `EQ  Low`
- No trailing spaces or special characters

### Macro range (important for EQ calibration)

Leave the macro min/max ranges at their defaults (0-127 for EQ Three
gains, 0-127 for Utility Gain). FX Machine's calibration constants
(EQ_NEUTRAL_MACRO = 107.9, TRIM_NEUTRAL_MACRO = 64.0) were measured
against these default ranges. Changing the macro min/max will break
the dB calibration.

If you need to limit the EQ range, use FX Machine's safety caps
(`cfg.EQ_BASS_BOOST_CAP`, `cfg.TRIM_MAX_DB`) rather than changing
the Ableton macro range.

---

## Step 6 — Verify the EQ Rack

Before moving to the FX rack, verify the EQ rack works correctly.

### Manual verification in Ableton

1. Move Macro 1 (EQ Low) left and right — the EQ Three's GainLow
   should move correspondingly
2. Move Macro 4 (Trim) — the Utility's Gain should move
3. Set all macros to their center position (approximately 50% for
   EQ, approximately 50% for Trim)

### Verification with FX Machine

1. Start FX Machine: `python run.py`
2. Wait for discovery to complete (you should see "EQ macros mapped: 4/4"
   in the console)
3. Enter EQ mode (press R3 on the gamepad)
4. Push the right stick left and right — the selected band's value
   should change in both the FX Machine UI and in Ableton
5. Double-flick up/down to switch bands — verify all four (LOW, MID,
   HIGH, TRIM) respond correctly

If any band doesn't respond:
- Check the macro name spelling in Ableton
- Check that the macro is mapped to the correct parameter
- Check the console for warnings like "MISSING 'EQ Low'"

---

## Step 7 — Create the FX Macros Track

The FX rack lives on a track named exactly `~ FX Macros`.

### Create the track

1. Create a new **Audio Track** (Ctrl+T / Cmd+T)
2. Rename it to exactly: `~ FX Macros`
3. Place it near the `~ EQ Macros` track (convention, not required)

### Same naming rules apply

- Exactly `~ FX Macros` (case-sensitive, space after tilde)
- FX Machine searches for this exact string

---

## Step 8 — Build the FX Rack — Outer Layer

The FX rack is more complex than the EQ rack. It uses a nested
rack-within-a-rack structure to achieve the wet/dry send/return
behavior described in [SIGNAL_CHAIN.md](SIGNAL_CHAIN.md).

### Outer rack structure

```
~ FX Macros (Audio Track)
│
└── Audio Effect Rack (outer)
    │
    ├── Auto Filter        ← on the main signal path
    │
    ├── Beat Repeat        ← on the main signal path
    │
    ├── [Nested Rack]      ← wet/dry sub-rack (Step 9)
    │
    └── Utility            ← stereo width control
```

### Step-by-step — Outer layer

1. **Select the `~ FX Macros` track**

2. **Add an Audio Effect Rack:**
   - Drag Audio Effect Rack from the browser
   - This is the OUTER rack

3. **Add Auto Filter (first in chain):**
   - Browser → Audio Effects → Auto Filter
   - Drag into the rack's device chain
   - Set the filter to a neutral state (frequency fully open,
     resonance at minimum)

4. **Add Beat Repeat (second in chain):**
   - Browser → Audio Effects → Beat Repeat
   - Drag to the RIGHT of Auto Filter
   - Set it to OFF (we'll control it via the Stutter macro)

5. **Leave space for the nested rack** (we'll add it in Step 9)

6. **Add Utility (last in chain):**
   - Browser → Audio Effects → Utility
   - Drag to the far RIGHT of the chain
   - This controls stereo width on the combined output
   - Set Width to 100% (default = no change)

Current chain should look like:
```
[Auto Filter] → [Beat Repeat] → ... → [Utility (Width)]
```

---

## Step 9 — Build the FX Rack — Wet/Dry Inner Layer

This is the most important step. The nested wet/dry rack is what makes
the "throw and tail" technique work. Read
[SIGNAL_CHAIN.md](SIGNAL_CHAIN.md) for the full explanation of WHY
this topology is used.

### Create the nested rack

1. **In the outer rack's chain**, between Beat Repeat and the Width
   Utility, add a NEW Audio Effect Rack (drag from browser)
   
2. **This inner rack should now have one chain.** We need TWO chains:
   one Dry (empty passthrough) and one Wet (with effects).

### Create the Dry chain

The default chain that was created when you added the inner rack IS
your Dry chain:

1. **Rename the chain** to `Dry` (right-click the chain name → Rename)
2. **Leave it completely empty** — no devices. Audio passes through
   unmodified.

### Create the Wet chain

1. **Right-click** in the chain list area of the inner rack
2. Select **Create Chain**
3. A new empty chain appears
4. **Rename it** to `Wet`

### Add devices to the Wet chain

With the `Wet` chain selected, add these devices IN ORDER:

1. **Utility (FX Send control):**
   - This controls HOW MUCH signal enters the wet processing
   - Set Gain to **-inf dB** initially (no wet signal)
   - This is the critical device — FX Send macro maps to its Gain

2. **Reverb (Dark Hall):**
   - Browser → Audio Effects → Reverb
   - Load the "Dark Hall" preset (or any long reverb)
   - Set Decay Time to something long (5-30 seconds)
   - Set Dry/Wet to **100% Wet** (the dry path is handled by the
     Dry chain, not by this reverb's own dry/wet)

3. **Delay (Long Digi Delay):**
   - Browser → Audio Effects → Delay
   - Load "Long Digi Delay" preset (or any tempo-synced delay)
   - Set Feedback to a moderate amount (~30-50%)
   - Set Dry/Wet to **100% Wet** (same reason as reverb)

### Verify the inner rack structure

The inner rack should now have TWO chains:

```
[Nested Wet/Dry Rack]
│
├── Chain "Dry"  → (empty — audio passes through)
│
└── Chain "Wet"
    ├── Utility         ← FX Send (gain into wet path)
    ├── Reverb          ← Dark Hall (100% wet)
    └── Delay           ← Long Digi Delay (100% wet)
```

### Why this works

When FX Send = 0 (Utility gain at -inf):
- Dry chain passes audio through unchanged
- Wet chain receives NO input (Utility blocks it)
- BUT: any reverb/delay tails already in the wet chain continue
  to decay naturally — they don't cut off

When FX Send = max (Utility gain at 0 dB):
- Dry chain still passes audio through
- Wet chain receives FULL input through the Utility
- Reverb and delay process the signal and add their wet output
- Combined output = dry + wet

This is NOT a wet/dry crossfade. It's a SEND LEVEL. The dry signal
is always present at 100%. The wet signal is added ON TOP based on
the Utility's gain. This exactly replicates how Pioneer's send/return
loop works on the DJM-900 NXS2.

### Verify with a quick test

1. Play some audio through the track
2. In the inner rack, manually turn up the Wet chain's Utility Gain
   from -inf to 0 dB
3. You should hear reverb/delay being added ON TOP of the dry signal
4. Turn the Utility Gain back to -inf
5. The reverb and delay should continue ringing out (tails decaying)
   while the dry signal returns to clean

If the tails cut off when you drop the gain, something is wrong with
the routing — most likely the reverb/delay Dry/Wet is not set to 100%.

---

## Step 10 — Map the FX Macros

Now connect the outer rack's 8 macros to the device parameters.

### The 8 macro mappings

| Macro # | Name (exact) | Maps to | Device | Location |
|---|---|---|---|---|
| 1 | `Filter Freq` | Frequency | Auto Filter | Outer rack |
| 2 | `Filter Mode` | Filter Type | Auto Filter | Outer rack |
| 3 | `Filter Res` | Resonance | Auto Filter | Outer rack |
| 4 | `Stutter` | Activate / Volume | Beat Repeat | Outer rack |
| 5 | `Reverb Size` | Decay Time | Reverb | Wet chain (inner rack) |
| 6 | `FX Send` | Gain | Utility | Wet chain (inner rack) |
| 7 | `Delay FB` | Feedback | Delay | Wet chain (inner rack) |
| 8 | `Width` | Width | Utility | Outer rack (last device) |

### Mapping procedure (same as EQ)

For each macro:

1. Find the target device parameter
2. Right-click the parameter → **Map to Macro N**
3. Right-click the macro label → **Rename** → type the exact name

### Filter Freq mapping detail

Auto Filter's Frequency parameter should be mapped with the full
range (20 Hz to 20 kHz). The macro's min/max should cover the full
filter sweep. Leave at default unless you specifically want to
restrict the range.

### Filter Mode mapping detail

Auto Filter's filter type selector (LP/HP/BP/Notch) maps to a macro
that FX Machine uses as a simple toggle:
- Macro value 0 = HP (high-pass mode, used by Bass Cut momentary)
- Macro value 127 = LP (low-pass mode, default)

Map this to whatever Auto Filter uses for its filter type switch.
The exact parameter name varies by Ableton version.

### Stutter mapping detail

Beat Repeat is tricky because it needs to be completely silent when
inactive. Map the Stutter macro to Beat Repeat's **Volume** or
**Activate** parameter (whichever gives clean on/off behavior in
your version of Ableton). When Stutter = 0, Beat Repeat should
produce no output. When Stutter = max, Beat Repeat should be active
at full volume.

### FX Send mapping detail — the most important one

The FX Send macro maps to the **Gain** parameter of the Utility
device inside the Wet chain of the inner rack. NOT the outer rack's
Utility (that's Width).

This is the parameter that controls how much signal enters the wet
processing chain. When FX Send = 0, the Utility's gain is at -inf
and no signal reaches the reverb/delay. When FX Send = max, full
signal enters.

Make sure you're mapping to the CORRECT Utility — there are two
Utility devices in the rack (one for FX Send in the Wet chain,
one for Width at the end of the outer chain). Map FX Send to the
one INSIDE the Wet chain.

---

## Step 11 — Verify the FX Rack

### In Ableton

1. Play audio through the `~ FX Macros` track
2. Move Macro 1 (Filter Freq) — the Auto Filter should sweep
3. Move Macro 6 (FX Send) from 0 to max — you should hear reverb
   and delay being added
4. Drop FX Send back to 0 — the dry signal returns clean, but
   reverb/delay tails continue ringing

### With FX Machine

1. Start FX Machine: `python run.py`
2. Wait for "FX macros mapped: 8/8" in the console
3. Hold L1 (enter FX mode)
4. Move the left stick up/down — Filter Freq should sweep
5. Press L1 + □ (FX Send Throw) — the UI should show "FX THROW"
   and you should hear wet effects added
6. Release □ — the throw ends, tails ring out

If any macro doesn't respond:
- Check the macro name spelling
- Check that the macro is mapped to the correct parameter
- Check for "MISSING" warnings in the FX Machine console

---

## Step 12 — Route Audio Through the Racks

The racks need to actually process your audio. There are several
routing approaches:

### Approach A — Return track routing (recommended)

Use Ableton's send/return system:

1. Place both `~ EQ Macros` and `~ FX Macros` on **Return Tracks**
   (instead of regular Audio Tracks)
2. Route your instrument tracks to send to Return A (EQ) and the
   output of Return A feeds into Return B (FX), or use a series
   routing within a single return

**Advantage:** Clean separation. Your instrument tracks don't need
to know about the racks. Just route audio to the return.

### Approach B — Track insert routing

Place the racks directly on audio/group tracks:

1. Put the EQ rack on your master group track
2. Put the FX rack after it on the same track
3. All audio flowing through that group gets processed

**Advantage:** Simple. No return track setup needed.
**Disadvantage:** Every track through that group gets the same EQ/FX.

### Approach C — Dedicated processing track

1. Create a track that all your instruments route to BEFORE the master
2. Put the EQ rack and FX rack on this processing track
3. The processing track outputs to Master

This is the approach described in the README:

```
All instrument tracks ──▶ Return A
                              │
                              ▼
                       ~ EQ Macros      (TRIM + 3-band EQ)
                              │
                              ▼
                       ~ FX Macros      (filter / reverb / delay / stutter)
                              │
                              ▼
                          Master
```

### Which approach to use?

For a DJ-style performance (one main audio stream being processed),
**Approach A** or **Approach C** is best. You want all audio going
through one EQ → FX chain, like a real mixer channel strip.

For a production-style setup (multiple independent instruments),
you might want the racks on a group track that only certain
instruments route through.

---

## Step 13 — Set Up Bookmarks

Bookmarks let you jump to specific scenes using the D-pad. Scenes
prefixed with `§` become bookmark targets.

### Creating bookmarks

1. In Ableton's session view, find the scenes you want as jump targets
2. **Rename each target scene** to start with `§` (section sign)
3. Example scene names:
   ```
   § INTRO
   § DROP 1
   § BREAKDOWN
   § DROP 2
   § OUTRO
   ```

### How to type the § character

- **Windows:** Hold Alt and type `0167` on the numpad, then release Alt
- **Alternatively:** Copy § from this document and paste it into the
  scene name
- **Windows character map:** Start → Character Map → search for
  "section sign"

### How bookmarks work in FX Machine

- **D-pad UP:** Previous bookmark
- **D-pad DOWN:** Next bookmark
- The bookmark cursor wraps: going past the last bookmark returns
  to the first

FX Machine discovers bookmarks during session discovery by scanning
all scene names for the `§` prefix. The prefix is stripped for display
(so `§ DROP 1` shows as `DROP 1` in the UI).

### Bookmark order

Bookmarks are ordered by scene index (top to bottom in Ableton's
session view). Moving a scene in Ableton changes its bookmark order.
Press SELECT+START in FX Machine to refresh after reordering scenes.

---

## Step 14 — Set Up Groups

Groups let you jump between track sections using the D-pad (left/right).
Tracks prefixed with `*` become group lead tracks.

### Creating groups

1. Identify the first track of each logical section in your session
2. **Rename each lead track** to start with `*` (asterisk)
3. Example track names:
   ```
   * KICK
   * BASS
   * SYNTH
   * VOCALS
   * FX RETURNS
   ```

### How groups work in FX Machine

- **D-pad RIGHT:** Next group (jump to the lead track of the next group)
- **D-pad LEFT:** Previous group
- **D-pad RIGHT + R2 held:** Jump to the GROUP LEAD track specifically
  (force-lead mode), ignoring the "memory" of which track you were
  last viewing in that group

### Group memory

FX Machine remembers which track you were viewing within each group.
When you return to a group via D-pad, it takes you back to the last
track you were on in that group — not necessarily the lead track.
Hold R2 while pressing D-pad to force-jump to the lead track.

### No groups defined

If no tracks have the `*` prefix, the D-pad left/right falls back to
a simple 4-track stepping mode (jumps in groups of 4 tracks).

---

## Step 15 — First Launch of FX Machine

With the racks built and named correctly:

```bash
python run.py
```

### What to watch for in the console

```
Session: 8 scenes, 21 tracks                    ← Ableton connected
2 bookmark(s) found                               ← § scenes detected
7 group(s) found                                  ← * tracks detected
FX track found at index 20                        ← ~ FX Macros found
EQ track found at index 18                        ← ~ EQ Macros found
FX macros mapped: 8/8                             ← all 8 FX macros found
EQ macros mapped: 4/4                             ← all 4 EQ macros found
Session listeners registered                      ← listener-based updates active
FX listeners registered: 16 listeners armed       ← FX live updates active
EQ listeners registered: 8 listeners armed        ← EQ live updates active
EQ meter listeners armed on track 18              ← channel meter active
Ready — 2 bookmarks | 7 groups | FX: YES | EQ: YES
```

If you see "FX macros mapped: 8/8" and "EQ macros mapped: 4/4", setup
is complete. Every macro was found and matched by name.

### Partial matches

If you see something like "FX macros mapped: 7/8", one macro name
didn't match. The console will show which slot is MISSING:

```
  slot 0: param[1] = 'Filter Freq'
  slot 1: param[2] = 'Filter Mode'
  slot 2: param[3] = 'Filter Res'
  slot 3: MISSING 'Stutter'            ← this one wasn't found
  slot 4: param[5] = 'Reverb Size'
  ...
```

Fix the macro name in Ableton to match exactly, then press SELECT+START
in FX Machine to refresh.

---

## Step 16 — Verify Full Connection

Run through this checklist to verify everything works:

### EQ verification

1. Press R3 to enter EQ mode
2. Push right stick left/right → selected band's value changes
3. Watch the dB readout update in both FX Machine and Ableton
4. Double-flick Y up/down → band switches (LOW → MID → HIGH → TRIM)
5. Double-flick X left on a band above 0 dB → normalizes to 0 dB
6. Double-flick X left on a band at 0 dB → kills the band

### FX verification

1. Hold L1 to enter FX mode
2. Push left stick up → Filter Freq sweeps
3. Press L1+X → Stutter activates (you hear Beat Repeat)
4. Release X → Stutter stops
5. Press L1+□ → FX Send Throw (reverb/delay swell)
6. Release □ → FX Send returns to previous level, tails ring out
7. Press L1+O → Bass Cut (high-pass filter at 200 Hz)
8. Release O → filter returns to previous state

### Meter verification

1. Play audio in Ableton that routes through the ~ EQ Macros track
2. The channel meter in FX Machine should show LED activity
3. If audio is loud enough, the CLIP indicator should turn yellow/red

### Navigation verification

1. Push left stick up/down → scene number changes
2. Push left stick left/right → track number changes
3. Press D-pad up/down → bookmark navigation
4. Press D-pad left/right → group navigation

---

## Understanding the Naming Conventions

### Track names

| Prefix | Meaning | Example |
|---|---|---|
| `~` | System track (FX Machine rack) | `~ FX Macros`, `~ EQ Macros` |
| `*` | Group lead track | `* KICK`, `* SYNTH` |
| (none) | Regular track | `Clap`, `Hi-Hat` |

### Scene names

| Prefix | Meaning | Example |
|---|---|---|
| `§` | Bookmark (D-pad jump target) | `§ DROP 1`, `§ OUTRO` |
| (none) | Regular scene | `Verse 1`, `Chorus` |

### Macro names (must match exactly)

**EQ rack macros:**
```
EQ Low       (not "Eq Low", not "EQ LOW", not "eq low")
EQ Mid
EQ High
Trim         (not "TRIM", not "trim")
```

**FX rack macros:**
```
Filter Freq
Filter Mode
Filter Res
Stutter
Reverb Size
FX Send
Delay FB
Width
```

---

## Common Setup Mistakes

### "FX track not found in session"

**Cause:** The track is not named exactly `~ FX Macros`.

**Fix:** Check for:
- Extra spaces: `~  FX Macros` (two spaces)
- Missing tilde: `FX Macros`
- Wrong case: `~ fx macros` or `~ Fx Macros`
- Trailing space: `~ FX Macros ` (space at the end)

Double-click the track name and retype it carefully.

### "FX macros mapped: 0/8"

**Cause:** The rack has no macros, or macros are not renamed.

**Fix:** Make sure you:
1. Have an Audio Effect Rack (not just individual devices)
2. Have mapped parameters to the macro knobs
3. Have renamed each macro to the exact expected name

### "EQ macros mapped: 3/4" (Trim missing)

**Cause:** The fourth macro (Trim) isn't mapped or is misspelled.

**Fix:** In the EQ rack:
1. Verify there's a Utility device before the EQ Three
2. Verify the Utility's Gain parameter is mapped to a macro
3. Verify the macro is renamed to exactly `Trim` (capital T, no extra characters)

### Reverb/delay tails cut off when FX Send drops

**Cause:** The reverb and/or delay devices have their Dry/Wet set to
less than 100%.

**Fix:** Inside the Wet chain:
- Set the Reverb's Dry/Wet to **100%**
- Set the Delay's Dry/Wet to **100%**

The dry path is provided by the separate Dry chain — the effects
themselves should be fully wet.

### FX Send doesn't seem to do anything

**Cause:** The FX Send macro is mapped to the wrong Utility device.

**Fix:** There are TWO Utility devices:
- One inside the Wet chain (this is FX Send — controls gain into wet)
- One at the end of the outer chain (this is Width — controls stereo)

Make sure FX Send maps to the Utility INSIDE the Wet chain, not the
one at the end of the outer chain.

### Audio doesn't flow through the racks

**Cause:** The tracks exist but aren't in the audio routing path.

**Fix:** Verify that your instrument tracks are routed to send audio
through the ~ EQ Macros and ~ FX Macros tracks. See
[Step 12](#step-12--route-audio-through-the-racks) for routing options.

### "Baseline auto-captured" shows all zeros

**Cause:** The FX macro values were all at zero when the app started.
This is normal if the racks are in their default state.

**Fix:** Set your preferred default FX state in Ableton (e.g., filter
fully open, reverb at a moderate size), then press SELECT+R1 in
FX Machine to manually save the baseline.

---

## Advanced — Using Return Tracks Instead of Audio Tracks

You can place the racks on Ableton's Return tracks (Send/Return system)
instead of regular Audio tracks. This is the cleanest routing approach:

### Setup

1. Create **Return Track A** (if it doesn't exist already)
2. Rename it to `~ EQ Macros`
3. Build the EQ rack on it (same as Steps 4-5)
4. Create **Return Track B**
5. Rename it to `~ FX Macros`
6. Build the FX rack on it (same as Steps 8-10)

### Routing

1. On each instrument track you want processed, set **Send A** to
   a healthy level (0 dB or unity)
2. On Return Track A (~ EQ Macros), set the output to route to
   Return Track B (~ FX Macros)
3. Return Track B outputs to Master

### Advantage

This approach means your instrument tracks' main outputs go directly
to Master (dry) while the processed version goes through the
EQ → FX chain. You can blend them using the send level. This gives
you even more flexibility than the "all-or-nothing" channel strip
approach.

### FX Machine compatibility

FX Machine finds racks by track name, not by track type. Return tracks
work identically to audio tracks for discovery purposes. The only
difference is that return tracks have indices that start after all
regular tracks in AbletonOSC's numbering.

---

## Advanced — Multiple Channel Strips

FX Machine currently supports ONE EQ rack and ONE FX rack. If you
want multiple channel strips (e.g., one per deck in a multi-deck DJ
setup), you would need to:

1. Create multiple pairs of racks with unique names
2. Modify FX Machine's discovery code to find all of them
3. Add a way to switch between active channel strips

This is not implemented in v1.0.0 but is architecturally feasible.
The discovery code in `src/osc/discovery.py` could be extended to
search for `~ EQ Macros 1`, `~ EQ Macros 2`, etc.

---

## Saving as a Template

Once your racks are set up correctly, save the project as an Ableton
template so you don't have to repeat this process for every new project:

### Ableton 11/12

1. File → **Save Live Set as Template...**
2. Give it a name like "FX Machine Template"
3. For new projects, create from this template

### Manual template

1. Save the project as a regular .als file in a known location
2. For new projects, open this file and "Save As" with a new name
3. Your racks, routing, and prefixed track/scene names carry over

### What to include in the template

- The `~ EQ Macros` track with the complete EQ rack
- The `~ FX Macros` track with the complete FX rack
- A few `§`-prefixed scenes (you'll rename them per project)
- A few `*`-prefixed group lead tracks (adjust per project)
- A test audio clip to verify routing works
- Audio routing from at least one track through the racks

---

## Updating an Existing Project

If you have a project that was created before FX Machine, you can add
the racks to it:

1. Open the existing project
2. Follow Steps 3-11 to create and configure both racks
3. Route your existing tracks through the racks (Step 12)
4. Add `§` and `*` prefixes to scenes and tracks as desired
5. Save the project

Existing tracks, clips, and automation are not affected. The racks
are purely additive.

### Importing racks from another project

If you already have the racks in another project:

1. Open the source project
2. Select the `~ EQ Macros` track
3. Right-click → **Export Track as ALS** (or drag to browser)
4. Open the target project
5. Drag the exported track into the session
6. Repeat for `~ FX Macros`

The macro mappings and device chain are preserved in the export.

---

## Port Configuration

### Default ports

| Port | Direction | Default | Used by |
|---|---|---|---|
| 11000 | FX Machine → Ableton | AbletonOSC default | OSC commands |
| 11001 | Ableton → FX Machine | AbletonOSC default | OSC responses |

### Changing ports

If another application uses these ports:

**In FX Machine:** Edit `config/active.toml`:
```toml
[network]
osc_host = "127.0.0.1"
osc_send_port = 11000      # change this
osc_receive_port = 11001   # change this
```

**In AbletonOSC:** Edit AbletonOSC's configuration to match. Check
the AbletonOSC documentation for how to change its ports — this varies
by version.

Both sides must agree on the port numbers. If FX Machine sends to
port 12000 but AbletonOSC listens on 11000, nothing will work.

### Network interface

By default, both use `127.0.0.1` (localhost). This means FX Machine
and Ableton must run on the same computer. Running them on different
machines is possible by changing the host address, but that introduces
network latency and is not recommended for live performance.

---

## Troubleshooting AbletonOSC

### "OSC sender ready" but no session data appears

**Possible causes:**
1. AbletonOSC is not installed or not activated in Ableton's preferences
2. Port conflict — another app is using port 11000
3. Firewall blocking localhost UDP traffic (rare but possible)

**Diagnosis:**
```bash
python diagnose.py
```

Check the "OSC Port Availability" section. If port 11001 can't be bound,
another instance of FX Machine (or another OSC app) is already using it.

### "Ableton error: Unknown OSC address"

**Cause:** FX Machine is sending an OSC command that AbletonOSC doesn't
support. This usually happens with very old versions of AbletonOSC or
with Ableton versions that don't support certain features.

**Fix:** Update AbletonOSC to the latest version from GitHub.

### Session discovery takes more than 10 seconds

**Possible causes:**
1. Very large session (100+ tracks, 50+ scenes) — each track/scene
   requires individual OSC queries
2. Ableton is under heavy CPU load and responding slowly
3. AbletonOSC is overloaded

**Mitigation:** FX Machine builds in sleep delays between queries to
avoid flooding Ableton. If discovery is too slow, the system still works
— the UI just shows "loading..." indicators longer.

### Listener events not arriving

**Symptom:** Tempo, transport state, or macro values don't update in
real-time — they only update on the 2-second safety poll.

**Possible cause:** AbletonOSC version doesn't support the
`start_listen` commands FX Machine uses.

**Fix:** Update AbletonOSC. FX Machine uses:
- `/live/song/start_listen/tempo`
- `/live/song/start_listen/is_playing`
- `/live/song/start_listen/num_tracks`
- `/live/song/start_listen/num_scenes`
- `/live/device/start_listen/parameter/value`
- `/live/track/start_listen/output_meter_left`

All of these are supported in AbletonOSC v2.0+. Older versions may
not support them.

### Meter shows no activity

**Symptom:** The channel meter stays dark even though audio is playing.

**Possible causes:**
1. The `~ EQ Macros` track is not in the audio routing path
2. Audio is not actually flowing through the track
3. Meter listeners failed to register

**Diagnosis:** Check the console for:
```
EQ meter listeners armed on track 18
```

If this line doesn't appear, the EQ track wasn't found or the listener
registration failed. Press SELECT+START to refresh.

If the line appears but the meter is still dark, check that audio is
actually routed through the track in Ableton. Solo the `~ EQ Macros`
track and verify you hear audio.

---

*This document describes the Ableton Live setup for FX Machine v1.0.0.
The rack structure and naming conventions are stable and unlikely to
change. Future versions may support additional racks or alternative
naming schemes — check the main README for updates.*
```
