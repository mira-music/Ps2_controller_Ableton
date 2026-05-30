## docs/FOR_MUSICIANS.md

```markdown
# 🎧 FX Machine — For Musicians, Producers, and DJs

## What This Document Covers

This guide is written for people who use FX Machine to make music,
not to write code. If you're a DJ, producer, performer, or live
electronic musician — this is your starting point.

You don't need to understand Python, threads, OSC, or how Tkinter
works. You need to know: what does this thing do, why should I care,
how do I set it up, and how do I use it to make music sound better.

The other documents in this folder are reference manuals for
developers. This one is a manual for performers.

---

## Table of Contents

1. [What FX Machine Is](#what-fx-machine-is)
2. [Who This Is For](#who-this-is-for)
3. [What You Get](#what-you-get)
4. [What You Don't Get](#what-you-dont-get)
5. [The Hardware You Need](#the-hardware-you-need)
6. [What It Costs](#what-it-costs)
7. [Quick Start — Your First Session](#quick-start--your-first-session)
8. [Understanding the Layout](#understanding-the-layout)
9. [The Two Modes — EQ and FX](#the-two-modes--eq-and-fx)
10. [The Five Techniques That Define DJ Performance](#the-five-techniques-that-define-dj-performance)
11. [Technique 1 — The Bass Kill](#technique-1--the-bass-kill)
12. [Technique 2 — The Filter Sweep](#technique-2--the-filter-sweep)
13. [Technique 3 — The Throw](#technique-3--the-throw)
14. [Technique 4 — The Stutter Build](#technique-4--the-stutter-build)
15. [Technique 5 — The High-Pass Bass Cut](#technique-5--the-high-pass-bass-cut)
16. [Putting It All Together — A Transition](#putting-it-all-together--a-transition)
17. [The TRIM Knob — Gain Staging](#the-trim-knob--gain-staging)
18. [Navigating Your Session](#navigating-your-session)
19. [Bookmarks — Jump Between Sections](#bookmarks--jump-between-sections)
20. [Groups — Navigate Track Sections](#groups--navigate-track-sections)
21. [The Channel Meter — Watching Your Levels](#the-channel-meter--watching-your-levels)
22. [The CLIP Indicator — Avoiding Distortion](#the-clip-indicator--avoiding-distortion)
23. [Live Performance Workflow](#live-performance-workflow)
24. [Studio Workflow](#studio-workflow)
25. [Streaming and Recording Workflow](#streaming-and-recording-workflow)
26. [What Makes This Different from a MIDI Controller](#what-makes-this-different-from-a-midi-controller)
27. [Why a Gamepad Instead of a MIDI Mixer](#why-a-gamepad-instead-of-a-midi-mixer)
28. [Common Beginner Mistakes](#common-beginner-mistakes)
29. [Tuning the Feel to Your Style](#tuning-the-feel-to-your-style)
30. [Building Muscle Memory](#building-muscle-memory)
31. [Performance Tips from a DJ Who Built This](#performance-tips-from-a-dj-who-built-this)
32. [What This Tool Can't Do](#what-this-tool-cant-do)
33. [Combining With Other Tools](#combining-with-other-tools)
34. [The Philosophy Behind the Design](#the-philosophy-behind-the-design)

---

## What FX Machine Is

FX Machine turns a regular USB gamepad — a $20 controller — into a
performance instrument for Ableton Live. It gives you the feel of a
$2000 Pioneer DJM-900 NXS2 mixer's EQ and FX section, but using a
controller you probably already have.

You don't need to learn MIDI mapping. You don't need to memorize
keyboard shortcuts. You don't need a separate hardware mixer. You
pick up the gamepad, push the sticks, and Ableton responds the way
a real DJ mixer would respond.

If you've ever:
- Wanted to play with EQ kills during a live set
- Wished you could "throw" a reverb tail and let it ring out
- Tried to do filter sweeps via your trackpad and gave up
- Wanted to feel more like a DJ when playing your own productions
- Felt like Ableton's mouse-driven interface gets in the way of
  performing

FX Machine is for you.

---

## Who This Is For

**DJs who play original material:**

You produce your own tracks in Ableton. You want to perform them live
with the feel of a real DJ mixer. You don't want to bounce them down
to USB sticks and play them on CDJs — you want to keep the flexibility
of Live's session view.

**Producers transitioning to live performance:**

You've made music for years but never performed it. You want to start,
and you want a controller that feels musical without spending $1000
on a Maschine or Push.

**Live electronic musicians:**

You play hybrid sets (some live elements, some pre-produced loops).
You need to control effects in real time without taking your hands
off the keyboard or pad controller.

**Anyone tired of mouse-driven mixing:**

You're sick of clicking on tiny knobs with a mouse. You want a physical
interface that feels like an instrument.

---

## What You Get

**A DJM-900 NXS2 channel strip, on your laptop:**

- 3-band kill EQ (LOW / MID / HIGH) with full -∞ cuts
- TRIM knob for input gain (-∞ to +9 dB)
- Smooth, musical encoder feel (not snappy MIDI)
- Sticky 0 dB detent — find unity by feel

**A full FX section:**

- Filter (HP/LP) with frequency, mode, and resonance control
- Stutter (Beat Repeat)
- Reverb (Dark Hall) with adjustable size
- Delay (Long Digi) with stepped feedback control
- Stereo Width
- The Throw technique built in

**Performance gestures:**

- Double-flick gestures for kill / restore / boost
- Smart context-aware actions (the same gesture does different things
  based on current state)
- Momentary effects (hold a button → effect on, release → effect off)
- Snapshot/restore that takes you back exactly where you were

**Session navigation:**

- Scene/track navigation via stick
- Bookmark navigation via D-pad (jump between sections)
- Group navigation via D-pad (jump between track types)
- Hold-to-scroll for fast browsing

**Visual feedback:**

- Real-time channel meter (LED-style, with peak hold and CLIP)
- Live knob positions showing current values
- BPM, track name, scene name, clip name
- Modifier indicators (which buttons are held)

**Safety:**

- Bass boost capped at +2 dB (protects your speakers)
- Delay feedback capped at 92% (no infinite feedback)
- Filter lock and wet lock (intentional state preservation)
- Recovery on mode exit (your sound returns to baseline)

**Configurable feel:**

- 55+ tunable parameters via a plain-text config file
- Edit while the app is running, instant reload
- 5 preset profiles (Punchy Club, Studio Precise, Beginner Forgiving,
  Radio Safe, Vintage Analog)

---

## What You Don't Get

**Beat detection / tempo sync:**

FX Machine reads Ableton's BPM but doesn't generate beats. Your music
must already be in Ableton.

**Audio recording / playback engine:**

FX Machine doesn't make sound. It controls Ableton, which makes sound.
You need Ableton to play music.

**Track loading / library management:**

Like a real DJ mixer, FX Machine controls what you're playing —
not what's available to play. Your music lives in Ableton's session.

**Crossfading between decks:**

FX Machine is a single-channel controller. It controls one channel
strip. Crossfading two tracks is something you do in Ableton itself
(volume faders, clip launches).

**Effect chains beyond what's built in:**

The 8 FX macros are fixed (filter, stutter, reverb, delay, send, width).
You can substitute different devices, but the macro count is 8.

**MIDI output to hardware synths:**

FX Machine talks to Ableton via OSC, not MIDI. If you need MIDI output,
use Ableton's regular MIDI tools.

**iOS / Android / macOS support (currently):**

v1.0.0 is Windows-only. macOS and Linux support are possible but not
shipped.

---

## The Hardware You Need

**A USB gamepad:**

Almost any modern gamepad works. Verified to work:
- PlayStation 4 / PS5 controller (DualShock 4, DualSense)
- Xbox One / Xbox Series controller
- Generic USB gamepads (any 12-button layout with two analog sticks)

Cost: $20-70 for a new controller. Used controllers work fine.

You need:
- 2 analog sticks (left and right, both with X and Y axes)
- D-pad (up/down/left/right)
- At least 12 buttons (face buttons + shoulder + stick clicks + select/start)

Some controllers report axes in non-standard ways. The
`RIGHT_STICK_ROTATED_90` setting in `src/config.py` handles one
common case. Others may require minor code changes.

**A Windows 10 or 11 PC:**

Any modern PC from the last 5 years handles FX Machine + Ableton
fine. Even older hardware (2017 i5 laptop) works — verified during
development.

**Ableton Live (any edition):**

10, 11, or 12. Intro/Standard/Suite — any works, with some caveats:
- Intro doesn't include Beat Repeat (skip stutter feature)
- Intro doesn't include long reverbs/delays (use what's available)
- Standard and Suite have everything needed

**Audio output:**

Whatever you use with Ableton already works. Headphones, monitors,
PA system — FX Machine doesn't care, it just processes the audio
Ableton is playing.

---

## What It Costs

**$0.**

FX Machine is free for non-commercial use. The license forbids
selling it or commercializing it, but using it for your own
performances (paid or unpaid) is fine.

Other costs:
- USB gamepad: $20-70 (one-time)
- Ableton Live: you probably already have it
- AbletonOSC: free
- Python: free

If you're playing paid gigs, you're a "commercial user of the music
you make WITH FX Machine," not a "commercial user OF FX Machine
itself." The license allows the former, forbids the latter.

---

## Quick Start — Your First Session

Assuming you have:
- FX Machine installed and runnable
- A gamepad plugged in
- Ableton Live open
- AbletonOSC installed
- The `~ EQ Macros` and `~ FX Macros` tracks created with all
  macros mapped (see [SETUP_ABLETON.md](SETUP_ABLETON.md))

**First-time workflow:**

1. **Open Ableton Live** with your project

2. **Start FX Machine:**
   - From the .exe: double-click `FX_Machine.exe`
   - From source: `python run.py`

3. **Wait for connection** (about 3 seconds):
   - The UI window appears
   - The console shows "Session: N scenes, N tracks"
   - The track and scene names appear in the UI

4. **Play some audio in Ableton:**
   - Launch a clip
   - You should see the channel meter on the left side light up
   - This confirms audio is flowing through your `~ EQ Macros` track

5. **Try the EQ mode:**
   - Press R3 (right stick click) to enter EQ mode
   - Push the right stick LEFT and RIGHT — the value should change
   - The label "EQ ACTIVE" should appear in the UI
   - You should hear the EQ affecting your audio

6. **Try the FX mode:**
   - Hold L1 (left shoulder)
   - Push the LEFT stick UP — the Filter Freq should sweep up
   - Push the LEFT stick DOWN — the Filter Freq should sweep down
   - You should hear the filter affecting your audio

7. **Try a throw:**
   - Hold L1
   - Press SQUARE (□) and hold for ~1 second
   - You should hear reverb/delay added to the audio
   - Release SQUARE
   - The wet effects continue ringing out for several seconds

If all of these work, you're ready to perform.

---

## Understanding the Layout

The FX Machine window has three main sections:

```
┌──────────────────────────────────────────────────────────┐
│  TRANSPORT BAR                                            │
│  ■ STOPPED                                    124.0 BPM   │
├──────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐  ┌──────────────────────┐  │
│  │  EQ SECTION              │  │  NAVIGATION INFO     │  │
│  │                          │  │                      │  │
│  │  METER  ┌──┐             │  │  BMARK: SONG1 START  │  │
│  │  CLIP   │TR│             │  │  GROUP: KICK         │  │
│  │   +12   │IM│             │  │                      │  │
│  │    +9   └──┘             │  │  TRACK: * KICK       │  │
│  │    +6   ┌──┐             │  │  SCENE: §SONG1 START │  │
│  │    +3   │HI│             │  │  CLIP:  * KICK 3     │  │
│  │     0   └──┘             │  │                      │  │
│  │    -3                    │  │  SCENE 1  TRACK 1    │  │
│  │    -6   ┌──┐             │  │                      │  │
│  │    -9   │MD│             │  │  +0.0 dB             │  │
│  │   -12   └──┘             │  │                      │  │
│  │   -15                    │  │  ■ STOP TRACK (L2)   │  │
│  │   -18   ┌──┐             │  │                      │  │
│  │   -21   │LO│             │  │  Modifier pills:     │  │
│  │   -24   └──┘             │  │  R2 SAFE  SEL  PLAY  │  │
│  │   -27                    │  │  L1 FX  ◇ EQ          │  │
│  │   -30                    │  │                      │  │
│  └─────────────────────────┘  │  EQ status: inactive │  │
│                                └──────────────────────┘  │
├──────────────────────────────────────────────────────────┤
│  Notification area (warnings appear here)                 │
├──────────────────────────────────────────────────────────┤
│  ⚡ FX MACHINE                                            │
│  ✓ baseline    filter: free    wet: free                 │
│                                                           │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐         │
│  │ Filter │  │ Filter │  │ Filter │  │ Stutter│         │
│  │ Freq   │  │ Mode   │  │ Res    │  │   0    │         │
│  └────────┘  └────────┘  └────────┘  └────────┘         │
│                                                           │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐         │
│  │ Reverb │  │ FX Send│  │ Delay  │  │ Width  │         │
│  │ Size   │  │   0    │  │ FB     │  │  100   │         │
│  └────────┘  └────────┘  └────────┘  └────────┘         │
├──────────────────────────────────────────────────────────┤
│  ● USB Gamepad                          ⟳ REFRESH         │
├──────────────────────────────────────────────────────────┤
│  Action line: shows what the last action was              │
└──────────────────────────────────────────────────────────┘
```

### The EQ section (top left)

The 22-segment LED meter shows your audio level. Above the meter is
the CLIP indicator — yellow at +6 dB, red at +9 dB.

To the right of the meter are 4 knobs stacked vertically:
- **TRIM** (top): Input gain
- **HIGH**: High frequencies (treble)
- **MID**: Middle frequencies (vocals, body)
- **LOW** (bottom): Low frequencies (bass, kick)

Each knob shows its current dB value below it.

### The navigation info (top right)

Shows what's happening in your Ableton session:
- **BMARK:** Current bookmark name + position
- **GROUP:** Current group name + position
- **TRACK:** Selected track name (colored to match Ableton's color)
- **SCENE:** Selected scene name
- **CLIP:** Currently selected clip
- Position counters (which scene/track/bookmark you're at)
- Track volume in dB
- Stop button (also accessible via L2)
- Modifier pills (which buttons are held)

### The FX section (bottom)

8 macro knobs in two rows of 4:
- **Row 1:** Filter Freq, Filter Mode, Filter Res, Stutter
- **Row 2:** Reverb Size, FX Send, Delay FB, Width

Each knob shows its current value (Hz, percentage, dB, etc.).

The status row above the knobs shows:
- Baseline status (✓ baseline / ✗ no baseline)
- Filter lock state
- Wet lock state

### The transport and action lines

- **Top:** Playing/Stopped status and BPM
- **Bottom:** What just happened (last action)

---

## The Two Modes — EQ and FX

FX Machine has two performance modes:

### EQ Mode (toggle with R3)

Press R3 (right stick click) to ENTER EQ mode.
Press R3 again to EXIT.

When EQ mode is ON:
- Right stick controls the selected EQ band's value
- Double-flicking Y switches between bands (LOW → MID → HIGH → TRIM)
- Double-flicking X triggers kill/restore actions
- The UI shows "EQ ACTIVE"
- The selected band's knob has a white outline

When EQ mode is OFF:
- Right stick does nothing (unless SELECT is held for volume)
- No EQ manipulation possible

### FX Mode (hold L1)

Hold L1 (left shoulder) to ENTER FX mode.
Release L1 to EXIT.

When FX mode is HELD:
- Both sticks control FX macros
- Left stick: Filter Freq (Y) and Filter Res (X)
- Right stick: FX Send and Reverb Size (rotation-corrected)
- D-pad left/right: Delay FB step
- L1+X: Stutter (momentary)
- L1+O: Bass Cut (momentary)
- L1+□: FX Send Throw (momentary)
- L1+△: Launch scene
- L1+L3: Toggle filter lock
- L1+R3: Toggle wet lock

When L1 is released:
- Recovery happens: Filter Freq returns to baseline (unless locked),
  FX Send drops to 0 (unless locked), Stutter goes off

### Can both modes be active at once?

No. EQ mode and FX mode are mutually exclusive on the right stick.
While holding L1 (FX mode), the right stick controls FX even if EQ
mode was previously toggled on. When you release L1, EQ mode resumes
control of the right stick.

### Modifier hierarchy

When multiple modifiers are held, priority is:
1. **L1 (FX mode)** — highest priority for sticks
2. **SELECT** (modifier) — volume control if held
3. **EQ mode** — active when EQ is toggled on AND no other modifier is held
4. **None** — left stick navigates, right stick does nothing

---

## The Five Techniques That Define DJ Performance

If you learn nothing else from this guide, learn these five techniques.
They're the foundation of expressive electronic music performance.

1. **The Bass Kill** — Drop the low end for tension/release
2. **The Filter Sweep** — Build energy with rising/falling filter
3. **The Throw** — Send a wet swell that tails out under clean dry
4. **The Stutter Build** — Rhythmic repetition for tension
5. **The High-Pass Bass Cut** — Clean up mixes and transitions

Each of these has its own section below with step-by-step instructions.

---

## Technique 1 — The Bass Kill

**What it sounds like:**

The kick drum and bass disappear instantly. Only mid and high
frequencies remain. The track sounds "thin" — like it's playing
through a phone speaker. Brings the energy down dramatically.

**When to use it:**

- **Before a drop:** Kill the bass for 4-8 bars to build anticipation.
  When you restore the bass on the downbeat, it hits HARD.
- **During a transition:** Kill the bass on the outgoing track while
  bringing in a new track. No two basses fighting.
- **For dramatic effect:** Kill the bass during a breakdown or
  emotional moment. The absence speaks louder than presence.

**How to do it with FX Machine:**

1. **Press R3** to enter EQ mode
2. **Make sure LOW is selected** — if not, double-flick the right stick
   DOWN until LOW is highlighted
3. **Double-flick LEFT** (push the stick fully left, return to center,
   push fully left again, all within ~0.4 seconds)
4. The LOW band drops to -∞ dB and the bass disappears
5. The action line shows "💥 BASS KILLED"

**To bring the bass back:**

1. Still on LOW band
2. **Double-flick RIGHT** (push stick fully right, return, push right again)
3. The LOW band restores to 0 dB
4. The action line shows "↑ EQ Low restored (0 dB)"

**Timing tip:**

Bring the bass back ON the downbeat for maximum impact. Practice the
gesture timing so you can trigger it exactly when the beat hits.

**Common mistakes:**

- Hesitating between the two flicks (too slow — gesture times out)
- Not flicking far enough (must reach 90% deflection)
- Forgetting which band is selected (always look at the UI first)

---

## Technique 2 — The Filter Sweep

**What it sounds like:**

The track gets darker and muffled as you sweep down (low-pass filter
closing), or thinner and more hollow as you sweep up (high-pass
filter opening). Classic build-up and transition tool.

**When to use it:**

- **Long build-ups:** Slowly close the low-pass filter over 16-32
  bars before a drop. The audience hears the energy "compressing."
  Release to let it explode back.
- **Transitions:** Sweep filter down on the outgoing track, sweep up
  on the incoming track. Both tracks blend through the swept zone.
- **Texture changes:** Briefly close the filter for a "passing
  through a wall" effect, then re-open.

**How to do it with FX Machine:**

1. **Hold L1** to enter FX mode
2. **Push left stick DOWN** to sweep the Filter Freq down (low-pass
   closes)
3. **Push left stick UP** to sweep the Filter Freq up (low-pass opens)
4. Hold the stick to keep sweeping (with acceleration)
5. Release the stick to STOP at the current value
6. Release L1 to exit FX mode (filter returns to baseline unless
   filter lock is on)

**The acceleration:**

If you hold the stick in one direction, the sweep speeds up over time.
After 1 second of holding, it's twice as fast. After 3+ seconds, 4×
as fast. Change direction to reset the acceleration.

This means you can do both slow, deliberate sweeps AND fast, dramatic
ones with the same stick — just hold longer for fast or release/repress
for slow.

**Setting filter lock for sections:**

If you want the filter to STAY at your swept position when you release
L1:

1. While holding L1, swept to your desired position
2. Press L3 (left stick click)
3. The action line shows "🔒 Filter LOCKED"
4. Release L1 — filter stays where you left it

To unlock: hold L1 and press L3 again.

---

## Technique 3 — The Throw

**What it sounds like:**

You hold a button and a wet wash of reverb/delay swells up under the
dry signal. You release the button and the dry signal continues clean,
but the wet wash continues ringing for several seconds — a "tail" of
atmospheric sound that decays naturally.

This is THE signature DJ effect. If you've ever heard a vocal stab
echo through 8 bars of a track, that's a throw.

**When to use it:**

- **Vocal stabs:** Throw the wet effects on a vocal sample. The echo
  carries the vocal through subsequent bars.
- **Transitions:** Throw at the end of one track, let the tails ring
  into the next track.
- **Build-ups:** Stack multiple throws over the last 8 bars of a
  breakdown to create a wall of atmospheric sound.
- **Emotional peaks:** Throw on a melodic moment to give it space
  and grandeur.

**How to do it with FX Machine:**

1. **Hold L1** to enter FX mode
2. **Press and hold SQUARE (□)** — wet effects start swelling
3. **Hold for 1-2 bars** (let the wet build up)
4. **Release SQUARE** — wet stops being added, but tails continue
5. **Release L1** when done with FX mode

The dry signal continues uninterrupted throughout. Only the wet
effects change.

**Adjusting the reverb size:**

While in FX mode, the right stick controls Reverb Size (one axis)
and FX Send (the other, after rotation correction). For longer
reverb tails, increase Reverb Size before the throw. For shorter
tails, decrease it.

**Setting wet lock for sustained wet:**

If you want the wet effects to STAY active when you release L1:

1. While holding L1, set FX Send to some moderate level (e.g., 50%)
2. Press R3 (right stick click)
3. The action line shows "🔒 Wet LOCKED"
4. Release L1 — wet effects continue at the set level

Now every sound that plays gets wet processing until you unlock.

To unlock: hold L1 and press R3 again.

**Stacking throws:**

Multiple throws layer on top of each other in the wet effects buffer.
Throw 1, release. While Throw 1 is decaying, do Throw 2. Now you have
TWO decaying wet swells overlapping. Repeat for THREE, FOUR throws.

This is how you build "walls of tails" — massive atmospheric
processing that fills space.

---

## Technique 4 — The Stutter Build

**What it sounds like:**

The audio starts repeating in rapid rhythmic chunks. The same fragment
loops 8, 16, or 32 times per beat. The forward motion of the music
stops — instead, you hear a stuck moment of tension.

When you release the stutter, the music continues normally. The
contrast between stuck and flowing creates dramatic excitement.

**When to use it:**

- **Drop build-ups:** Stutter for the last 1-2 bars before a drop.
  The audience hears the music "freeze" and EXPECTS the drop to come.
- **Tension moments:** Stutter at the climax of a build, then release
  on the downbeat.
- **Glitch effects:** Brief stutters (less than a beat) add rhythmic
  variation to repetitive sections.

**How to do it with FX Machine:**

1. **Hold L1** to enter FX mode
2. **Press and hold X (cross)** — stutter activates immediately
3. **Hold for 1-2 beats or 1-2 bars** depending on the effect you want
4. **Release X** — stutter deactivates, music continues normally
5. Release L1 when done

**Setting up the stutter pattern in Ableton:**

The Stutter macro just turns Beat Repeat on/off. The actual stutter
character (how often it loops, how long each loop is, etc.) is set
in Beat Repeat's own UI.

For different stutter sounds:
- **Interval = 1/16:** Fast, busy stuttering
- **Interval = 1/8:** Moderate stuttering
- **Interval = 1/4:** Slow, beat-emphasizing stuttering
- **Gate = 1/16:** Each loop is one 1/16 note
- **Volume Decay = 0:** Each loop at full volume (most aggressive)
- **Volume Decay = high:** Loops fade out (less aggressive)

Experiment in Ableton to find your preferred stutter sound.

---

## Technique 5 — The High-Pass Bass Cut

**What it sounds like:**

Everything below ~200 Hz disappears. Kicks lose their thump. Bass
loses its body. The track sounds "thin" but in a different way than
the bass kill — instead of cutting only the LOW band, this cuts
everything below 200 Hz including some kick/bass body.

**When to use it:**

- **Mixing two tracks:** Cut bass on one track while bringing in
  another. Avoids muddy low-end conflicts.
- **Cleaning up busy mixes:** Briefly cut bass during overcrowded
  sections to make space.
- **Build-ups:** Cut bass for 4 bars, then release on the downbeat
  for impact (similar to bass kill but with a different sound).

**How to do it with FX Machine:**

1. **Hold L1** to enter FX mode
2. **Press and hold O (circle)** — bass cut activates
   - Filter switches to HP mode
   - Filter Freq jumps to ~200 Hz
3. **Hold for as long as you want bass cut** (typically 1-4 bars)
4. **Release O** — filter returns to where it was before
   - Mode goes back to LP (or whatever was there before)
   - Freq goes back to its previous value

The snapshot/restore means you don't have to "remember" what your
filter was doing — release the button and it goes back exactly where
it was.

**Bass kill vs bass cut — what's the difference?**

| | Bass Kill (EQ) | Bass Cut (FX) |
|---|---|---|
| How to do | EQ mode, double-flick LOW left | FX mode, hold L1+O |
| What's cut | Only the LOW EQ band (below ~200 Hz crossover) | Everything below 200 Hz via filter |
| Sound | Full silence in the bass band | Steep filter, slight resonance possible |
| Recovery | Manual (need to restore the LOW band) | Automatic (release button) |
| Use case | Big dramatic moments | Quick mixing/cleanup |

Bass kill is for "the bass is GONE." Bass cut is for "give me 4 bars
without low end."

---

## Putting It All Together — A Transition

Let's walk through using all five techniques in a single 32-bar
transition from Track A to Track B:

**Bars 1-8: Set up the transition (Track A only)**

- Both tracks playing? No, just Track A. Track B is in the next scene.
- You: Push LEFT stick UP (in FX mode) to slowly close the low-pass
  filter on Track A over 8 bars.
- Result: Track A gets progressively darker.

**Bars 9-16: Build tension (still Track A)**

- You: Continue holding L1. Press and hold SQUARE for a 2-bar throw.
  Wet effects swell up.
- Release SQUARE around bar 13. Wet tails continue decaying.
- Around bar 15, do ANOTHER throw. More wet stacked on top.
- You: Press R3 to enable wet lock. Release L1. Wet continues at
  current level.

**Bars 17-24: Crossfade (both tracks)**

- Launch Track B's clip (it starts playing on the next downbeat).
- Both tracks now playing simultaneously, but Track A is heavily
  filtered and wet, Track B is clean.
- You: Press R3 to enter EQ mode.
- You: Double-flick LOW band LEFT on Track A's channel — bass kills.
- Track A is now thin and wet, Track B is clean and full.

**Bars 25-28: Stutter build**

- You: Hold L1. Press and hold X for a 1-bar stutter on Track B.
- Bars 25-26: Stutter active. Tension builds.
- Release X around bar 27. Track B continues normally.

**Bars 29-32: The drop**

- Bar 29 downbeat: Stop Track A's clip (L2 on the correct track).
- Track B is now alone, playing clean.
- You: Hold L1, press R3 to disable wet lock (which was on from earlier).
- Release L1. FX Send drops to 0. Wet tails from Track A continue
  decaying for a few more bars.
- The transition is complete. Track B is the only thing playing,
  carried by the residual wet tails from Track A.

Each of these moves is one or two button presses. Together they form
a 32-bar musical journey. With practice, you can chain these
techniques fluidly during a live set.

---

## The TRIM Knob — Gain Staging

The TRIM knob (top of the EQ section) controls input gain BEFORE the
EQ. It's the most important knob for ensuring your audio sounds clean
and consistent.

**When to adjust TRIM:**

- **A/B-ing tracks:** Different tracks have different mastered loudness.
  Use TRIM to match them. Track A loud at 0 dB? Track B quiet — boost
  TRIM to +3 dB so they match.
- **Headroom for boosts:** Planning to boost the LOW band by +2 dB?
  Reduce TRIM by 2 dB first so the EQ doesn't clip internally.
- **Gain riding:** During quieter sections, push TRIM up for more
  presence. During louder sections, back it off.

**How to adjust TRIM:**

1. Press R3 to enter EQ mode
2. Make sure TRIM is selected (double-flick Y until TRIM is highlighted)
3. Push right stick LEFT/RIGHT to adjust
4. Watch the dB value update

**TRIM has special behavior:**

- Double-flicking only NORMALIZES to 0 dB (never kills, never boosts)
- The +9 dB cap is a hard limit (matches DJM-900 NXS2 behavior)
- The detent at 0 dB is more pronounced than the EQ bands

**Setting TRIM at the start of each track:**

Best practice: when you load a new track, briefly select TRIM and
adjust it so the channel meter sits around the same place as your
previous track. This makes consecutive tracks feel like they belong
to the same set, not like the volume jumps between them.

---

## Navigating Your Session

The left stick navigates your Ableton session.

**Track navigation (left stick X axis):**

- Push LEFT: previous track
- Push RIGHT: next track
- Hold: auto-scroll (after ~0.5 seconds)

**Scene navigation (left stick Y axis):**

- Push UP: previous scene
- Push DOWN: next scene
- Hold: auto-scroll

**Why this matters:**

The channel meter, the EQ, and the FX always operate on the SELECTED
track in Ableton. To process a different track's audio, navigate to
it first.

**Best practice:**

Set up your Ableton session so the `~ EQ Macros` and `~ FX Macros`
tracks process EVERYTHING (master group routing), not individual
instrument tracks. That way navigation doesn't change what's being
processed — it just changes what you're VIEWING in Ableton.

---

## Bookmarks — Jump Between Sections

If your session has scenes prefixed with `§` (e.g., `§ INTRO`,
`§ DROP 1`, `§ BREAKDOWN`), those become bookmark targets.

**To use bookmarks:**

- D-pad UP: previous bookmark
- D-pad DOWN: next bookmark
- The UI shows the current bookmark name

**Why this matters:**

Instead of scrolling through 50 scenes to find the one you want,
bookmark the important sections. Jump directly to them with one
D-pad press.

**Example bookmark layout for a DJ set:**

```
§ INTRO
(...other scenes...)
§ DROP 1
(...other scenes...)
§ BREAKDOWN 1
(...other scenes...)
§ DROP 2
(...other scenes...)
§ BREAKDOWN 2
(...other scenes...)
§ OUTRO
```

Six bookmarks for a typical 8-section set. D-pad up/down navigates
between them in seconds.

---

## Groups — Navigate Track Sections

If your session has tracks prefixed with `*` (e.g., `* KICK`,
`* SYNTH`, `* VOCALS`), those become group lead tracks.

**To use groups:**

- D-pad RIGHT: next group
- D-pad LEFT: previous group
- Hold R2 + D-pad: force-jump to the GROUP LEAD (ignoring memory)

**Why this matters:**

If you have 30 tracks organized into sections (drums, basses, synths,
vocals, FX returns), navigating one track at a time is slow. Groups
let you jump between sections.

**Group memory:**

FX Machine remembers which track you were viewing within each group.
When you return to that group, it goes back to that track — not the
lead track.

Example:
- You're on "Vocal 2" in the VOCALS group
- You D-pad right to KICK group, view "Kick Sub"
- You D-pad left back to VOCALS group
- FX Machine takes you to "Vocal 2" (where you were before)

Hold R2 to override this and jump to the group's lead track.

---

## The Channel Meter — Watching Your Levels

The 22-segment LED meter on the left shows the audio output level
of the `~ EQ Macros` track in real time.

**Reading the meter:**

- Bottom segments (yellow-green): -30 to -3 dB — safe range
- Middle segments (orange): 0 to +6 dB — getting loud
- Top segments (red): +9 to +12 dB — too loud, clipping likely

The brightest segment shows the PEAK (highest recent level). It
holds for 1.5 seconds, then decays.

**Typical reading during normal playback:**

- Peaks in the orange zone occasionally
- Sustained level in the yellow-green zone
- Red rarely if ever

**If the meter shows too much red:**

- Reduce TRIM
- Lower the master volume in Ableton
- Reduce the EQ boost if you have one applied

**If the meter shows almost nothing:**

- Increase TRIM
- Check that audio is actually routed through the `~ EQ Macros` track
- Verify Ableton's master volume isn't muted

---

## The CLIP Indicator — Avoiding Distortion

The CLIP box at the top of the meter has three states:

**Off (dark):** Signal level is fine. Below +6 dB.

**Yellow (warning):** Signal exceeded +6 dB. You're approaching the
limit. Consider reducing levels.

**Red, flickering (critical):** Signal exceeded +9 dB. Clipping is
imminent or actively happening. Reduce levels NOW.

**When the CLIP fades out:**

After the signal drops below the warning threshold, the CLIP indicator
fades out over 0.5 seconds. This brief persistence helps you NOTICE
that clipping happened even if you missed it in real-time.

**What if CLIP stays lit constantly:**

Your signal is sustained too hot. You're not just hitting transient
peaks — the average level is in the red zone. This will sound
distorted on most speakers.

Fix:
1. Reduce TRIM by 3-6 dB
2. Or reduce the EQ track's volume in Ableton
3. Or reduce the master volume in Ableton

---

## Live Performance Workflow

For actual gigs, your workflow:

**Before the show:**

1. Set up your Ableton session with the racks and routing
2. Set bookmarks for major sections of your set
3. Set groups for your track sections
4. Save a baseline (SELECT+R1) at your preferred starting FX state
5. Test all techniques work
6. Save the project

**At soundcheck:**

1. Connect to the venue's PA
2. Play through a section of your set
3. Adjust TRIM to match the venue's level expectations
4. Adjust the `meter.reference_offset_db` config value if the meter
   reading doesn't match what the venue's engineer is seeing
5. Test bass response — bass safety cap may need adjustment depending
   on the speakers
6. Save these settings as a preset profile (copy `active.toml` to
   `presets/this_venue.toml`)

**During the show:**

1. Don't touch the config files — use only the controller
2. Trust your muscle memory
3. If something goes wrong, the L1 release recovery gets you back
   to baseline
4. The CLIP indicator is your friend — watch it

**After the show:**

1. If diagnostics was enabled, run `python analyze_diagnostics.py`
   to see how the session went (CPU, OSC traffic, any warnings)
2. Save any setting tweaks for next time

---

## Studio Workflow

For studio use (production, not live):

**Different priorities than live:**

- Precision matters more than speed
- You have time to undo
- You can save and recall settings

**Recommended config changes:**

```toml
[eq.encoder]
sweep_seconds = 1.00     # slower, more controlled
curve_exp = 1.4          # very fine control near rest

[eq.detent]
range = 3.0              # wider sticky zone at 0 dB
min_factor = 0.15        # stronger pull to neutral

[fx]
filter_freq_sweep_s = 3.0    # slower sweeps
filter_res_sweep_s = 5.0
```

This is the "Studio Precise" preset in `EXAMPLES.toml`. Copy it into
your `active.toml`.

**Use FX Machine as a parameter controller:**

In the studio, FX Machine is great for capturing organic, hand-played
parameter movements that would be tedious to draw with a mouse.

- Enable automation recording in Ableton
- Play your track
- Use FX Machine to manipulate filter sweeps, EQ moves, etc.
- The movements get recorded as automation
- Edit/refine the automation in Ableton's arrangement view

---

## Streaming and Recording Workflow

For live streams and recording sessions:

**Different priorities:**

- No accidental clipping (broadcast standards are strict)
- Consistent loudness across the stream
- Visual feedback that you're "doing things" for viewers

**Recommended config:**

```toml
[eq.safety]
bass_boost_cap = 110.0    # less bass boost allowed

[trim]
max_db = 6.0              # less TRIM headroom

[meter.clip]
warn_db = 3.0             # warn earlier
critical_db = 6.0         # critical earlier
```

This is the "Radio/Stream Safe" preset.

**Setting up for stream visibility:**

If you're screen-recording your performance:
- Make the FX Machine window prominent
- The visual feedback (knobs moving, CLIP indicator, action line)
  shows viewers what you're doing
- Pair with a webcam showing you using the controller

**Recording the audio:**

FX Machine doesn't record — Ableton does. Make sure Ableton is set
to record to a file with appropriate settings (44.1 kHz, 24-bit).

---

## What Makes This Different from a MIDI Controller

A traditional MIDI controller has knobs and faders. You assign each
knob to a parameter in Ableton via MIDI mapping. Push the knob, the
parameter changes.

FX Machine is fundamentally different in three ways:

### 1. The gestures are intelligent

A MIDI knob maps directly to a value: turn it 50%, parameter goes to
50%. There's no logic, no context awareness, no "smart" behavior.

FX Machine's double-flick gestures are context-aware:
- Double-flick LEFT means "kill" if you're at neutral, or "normalize"
  if you're boosted
- Double-flick RIGHT means "restore" if you're cut, or "boost" if
  you're at neutral
- The same physical movement does the musically appropriate thing

This isn't possible with MIDI. MIDI doesn't have state machines.

### 2. The encoder feels like a real mixer

When you let go of a MIDI knob, it stays where you left it. When you
let go of a stick (spring-loaded), it returns to center. A naive
MIDI mapping of stick → parameter would mean parameters always return
to center when you release.

FX Machine's velocity-based encoder works like a real rotary encoder:
push the stick to ADJUST, release to HOLD. This feels exactly like a
DJM-900 NXS2's EQ knob.

### 3. The safety logic is built in

A MIDI controller will happily let you boost bass by +6 dB and blow
your subwoofer. FX Machine refuses — the bass cap is a hard limit
in software. Same for delay feedback runaway, same for L1-release
recovery preventing stuck states.

You CAN configure FX Machine to disable safeties if you want, but
they're on by default.

---

## Why a Gamepad Instead of a MIDI Mixer

A real DJ mixer like the DJM-900 NXS2 costs $2000-3000. A gamepad
costs $20-70. Why does the gamepad work?

**Physical interface elements:**

| Element | DJM-900 NXS2 | Gamepad |
|---|---|---|
| EQ knobs | 3 rotary encoders | 1 analog stick (X axis) |
| TRIM knob | 1 rotary encoder | Same stick, different band |
| FX section | Beat FX unit | Both sticks + buttons |
| Crossfader | 1 fader | (not implemented) |
| Channel faders | 4 faders | (not implemented) |
| Cue buttons | 4 buttons | (not implemented) |

The gamepad gives up some things (crossfader, channel faders, cue
buttons) but provides equivalent or better control for the EQ/FX
section through smart gesture mapping.

**What the gamepad gives you that the mixer doesn't:**

- Software-defined behavior (tunable via TOML)
- Visual feedback on screen (the UI shows what's happening)
- No physical degradation (no scratchy faders, no worn caps)
- Portable (fits in your bag)
- Affordable (replaceable if broken)
- Multi-mode (one stick controls EQ OR FX depending on context)

**What the mixer gives you that the gamepad can't:**

- Physical tactile feedback (rotary knobs feel different from sticks)
- Multiple channels (DJM has 4 channel strips)
- Dedicated faders for each track
- Headphone cueing
- Microphone input
- Booth monitoring controls
- Master output controls

**The honest comparison:**

For pure EQ and FX manipulation on ONE channel, the gamepad with
FX Machine is competitive with a real mixer. For multi-channel DJ
work with crossfading, cueing, and physical performance, a real
mixer is still better.

But: most "DJ performances" by producers playing their own material
don't actually need multi-channel mixing. They need creative effects
on the master output. FX Machine excels at this.

---

## Common Beginner Mistakes

### Mistake 1: Trying to use both EQ and FX simultaneously

You can't. EQ mode and FX mode are mutually exclusive on the right
stick. While holding L1 (FX mode), the right stick is for FX. When
you release L1, the right stick returns to whatever mode it was in
(EQ mode if toggled on, nothing if not).

**Workflow:** Set up your EQ in EQ mode first. Then enter FX mode for
filter sweeps and throws. The EQ state stays where you set it.

### Mistake 2: Forgetting which band is selected

You double-flick to kill the bass... but actually MID was selected
and you killed the mids instead.

**Fix:** Always glance at the UI before performing a kill. The
selected band has a white outline. The band name is shown in the
status line.

### Mistake 3: Holding L1 when you didn't mean to

L1 is the FX modifier. Accidentally holding it means your buttons
do something different than you expect. Pressing X with L1 held =
Stutter (not Launch Clip).

**Fix:** Build muscle memory for L1 = "I am about to do FX." If you
catch yourself doing the wrong thing, release L1 and try again.

### Mistake 4: Cranking the bass and damaging speakers

You disabled the bass safety because "I know what I'm doing." Then
you boosted bass by +6 dB on a hot signal, and your subwoofer voice
coil burned out.

**Fix:** Leave the bass safety on. The +2 dB default cap is plenty
for musical emphasis. If you need more bass, fix it at the source
(mastering, EQ in production).

### Mistake 5: Filter lock left on accidentally

You enabled filter lock for a section, then forgot to disable it.
For the rest of the set, the filter doesn't recover on L1 release.

**Fix:** Watch for the 🔒 indicator in the FX panel. If it shows
"🔒 filter" or "🔒 wet," you have a lock active. Disable when no
longer needed.

### Mistake 6: Doing too much at once

New users tend to use every technique on every transition. The
result is over-processed, exhausting music.

**Fix:** Less is more. One throw per transition is plenty. One bass
kill per drop. Save the stutter for special moments. The contrast
between processed and clean sections is what makes the processing
feel meaningful.

### Mistake 7: Not setting baselines

The L1 release recovery returns parameters to baseline. If you never
set a baseline, the recovery has nothing to recover TO.

**Fix:** Press SELECT+R1 at the start of your session to save your
preferred baseline state. The action line confirms "✓ BASELINE SAVED."

---

## Tuning the Feel to Your Style

The config file (`config/active.toml`) lets you customize how the
controller feels. Different musical styles want different feels.

**For aggressive club music (drum & bass, hard techno):**

```toml
[eq.encoder]
sweep_seconds = 0.20   # very fast
curve_exp = 0.85       # snappy response

[fx]
filter_freq_sweep_s = 0.8   # fast filter sweeps
fx_send_sweep_s = 0.6
```

This is the "Punchy Club" preset.

**For melodic/deep house:**

```toml
[eq.encoder]
sweep_seconds = 0.50   # smoother
curve_exp = 1.2        # gentler near rest

[fx]
filter_freq_sweep_s = 2.0   # slow, sweeping
reverb_size_sweep_s = 8.0
```

**For ambient/experimental:**

```toml
[eq.encoder]
sweep_seconds = 1.50   # very slow
curve_exp = 1.5        # extremely fine control

[eq.ramp]
min_ms = 80            # smooth transitions
max_ms = 300

[fx]
default_sweep_s = 8.0  # everything slow
```

**For studio production:**

Use the "Studio Precise" preset from `EXAMPLES.toml`.

---

## Building Muscle Memory

Like any instrument, FX Machine requires practice. Here's a learning
sequence:

**Week 1: Just navigate**

- Use left stick to scroll tracks and scenes
- Use D-pad for bookmarks and groups
- Launch clips with X, stop with O
- Don't touch the EQ or FX yet

Goal: Be able to navigate any session without looking at the gamepad.

**Week 2: EQ basics**

- Enter EQ mode (R3)
- Switch bands (Y double-flicks)
- Adjust values (X axis continuous)
- Kill and restore (X double-flicks)

Goal: Be able to switch bands and trigger kills without looking.

**Week 3: Filter sweeps**

- Enter FX mode (hold L1)
- Sweep the filter (left stick)
- Practice slow sweeps and fast sweeps
- Try the bass cut momentary (L1+O)

Goal: Smooth, controlled filter sweeps timed to the music.

**Week 4: Throws**

- The FX Send Throw (L1+□)
- Adjust reverb size beforehand
- Stack multiple throws
- Use wet lock for sustained sections

Goal: Confident throws timed to musical moments.

**Week 5: Stutter**

- The stutter momentary (L1+X)
- Practice short stutters (less than a beat)
- Practice long stutters (1-2 bars)
- Time releases to downbeats

Goal: Stutters that build tension and release on the beat.

**Week 6: Combinations**

- Filter sweep + throw together
- Bass kill + filter cut
- Stutter into a throw
- Full transitions using multiple techniques

Goal: Fluid combinations during transitions.

**Beyond Week 6:**

Use it in real performance. Mistakes happen. Recover gracefully (the
L1 release recovery is your friend). Develop your own style.

---

## Performance Tips from a DJ Who Built This

FX Machine was built by Ayoub Agoujdad (MIRA) for his own live
performances. Some practical tips from a working DJ:

**Tip 1: Trust the safety systems.**

The bass cap, the wet lock recovery, the delay feedback cap — these
exist because they SAVED ME during real shows. Don't disable them.

**Tip 2: Less is more.**

The audience hears the contrast between clean and processed. If
everything is heavily processed, nothing stands out. Use a throw
to PUNCTUATE a moment, not to fill space.

**Tip 3: Time your moves to the music.**

A throw on the downbeat hits hard. A throw on a random offbeat
sounds like a mistake. Practice locking your gestures to the beat
grid.

**Tip 4: The L1 release is your "undo" button.**

If something is going wrong, release L1. Filter goes back to baseline,
FX Send drops to 0, Stutter turns off. You're back to a clean state
without panic.

**Tip 5: Pre-set your reverb size.**

Don't change Reverb Size during a throw — set it BEFORE so it's
already at the size you want. Trying to adjust it mid-throw sounds
wonky.

**Tip 6: Save baselines for different sections.**

Different parts of your set may benefit from different FX baselines.
Big breakdowns: more wet on FX Send by default. Energetic drops:
filter mostly open. Use SELECT+R1 to save baselines before each
section.

**Tip 7: Watch the meter.**

The CLIP indicator turning yellow is your "back off" signal. Don't
ignore it. Audience volume tolerance has limits and venue PA systems
can be damaged.

**Tip 8: Practice transitions, not effects.**

Effects in isolation aren't impressive. Effects deployed during
transitions ARE impressive. Practice the choreography of "old track
out, new track in" with effects supporting the journey.

**Tip 9: Have a panic plan.**

If everything goes wrong (sound drops out, controller disconnects,
software freezes), what do you do? Have a plan. For me: pre-loaded
backup track on a USB stick in the venue's CDJ. If FX Machine fails,
plug in the USB and play normally.

**Tip 10: It's a tool, not a personality.**

FX Machine doesn't make you a DJ. Your taste in music, your sense
of timing, your understanding of the room — those make you a DJ.
FX Machine is just the brush. Learn to paint first.

---

## What This Tool Can't Do

Being clear about limitations:

**Beat matching:**

FX Machine doesn't beat-match. Your tracks need to be already aligned
in Ableton (which has built-in warping). FX Machine assumes you've
done that work.

**Sync to external clock:**

Currently no MIDI clock input/output. If you need to sync to external
hardware, use Ableton's Link or its built-in MIDI sync.

**Multi-deck mixing:**

Single-channel only. For mixing two decks like a traditional DJ
setup, you'd need TWO FX Machine instances controlling two channel
strips — not currently supported.

**Audio routing changes:**

FX Machine doesn't change Ableton's routing. If you want to swap
which channels go through the racks, do that in Ableton manually.

**Real-time pitch shifting:**

The DJM-900 NXS2 has a pitch fader. FX Machine doesn't expose pitch
control. Use Ableton's clip pitch warping for this.

**Recording the output:**

Recording is Ableton's job, not FX Machine's.

---

## Combining With Other Tools

FX Machine plays nicely with:

**Push 2 / 3:**

Use Push for clip launching, melodic playing, and pad performance.
Use FX Machine for the channel strip processing. They control
different things and don't conflict.

**MIDI keyboard:**

Same as Push — different roles. Keyboard for notes, FX Machine for
processing.

**Ableton's session view:**

You navigate it with FX Machine but launch clips with the keyboard
or mouse if you prefer. The combination is flexible.

**External audio interfaces:**

FX Machine doesn't care what audio interface you use. As long as
audio is flowing through Ableton, it works.

**Hardware mixers (after the laptop):**

You can run the laptop's master out into a hardware mixer for
additional processing. FX Machine processes inside the laptop, the
mixer adds whatever it adds after.

---

## The Philosophy Behind the Design

FX Machine was built around three principles:

### Principle 1: Feel matters more than features

A controller with 50 features that all feel wrong is worse than a
controller with 10 features that feel right. FX Machine has a small
feature set (3-band EQ + TRIM + 8 FX macros + navigation) but
obsesses over how each feature feels.

The velocity-based encoder, the cubic ease-out ramps, the asymptotic
boost, the sticky 0 dB detent — these are all "feel" improvements
that don't add features but make existing features more musical.

### Principle 2: Safety enables risk-taking

Performers take risks. Sometimes those risks go wrong. The safety
features (bass cap, delay cap, recovery on release, snapshot/restore)
exist so you can ATTEMPT things that might fail without catastrophic
consequences.

Knowing you have a safety net lets you reach for the trapeze.

### Principle 3: Configurability respects the user

Different performers have different styles. Different venues have
different requirements. Different musical genres have different needs.

The 55+ tunable parameters via TOML mean the controller can adapt
to YOU, instead of forcing you to adapt to the controller.

---

*FX Machine was built by Ayoub Agoujdad (performing as MIRA) for his
own live performances in Morocco's electronic music scene. It's
free for non-commercial use. The hope is that other producers and
DJs find it useful for performing their own music with the feel of
a real DJ mixer.*

*Made for live performance. By a DJ. For DJs.*
```

