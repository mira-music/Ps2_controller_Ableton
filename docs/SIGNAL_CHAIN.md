## docs/SIGNAL_CHAIN.md

```markdown
# 🎚️ FX Machine — Signal Chain and Audio Routing Guide

## What This Document Covers

This guide explains the audio signal chain that FX Machine implements
inside Ableton Live — why the racks are structured the way they are,
how the wet/dry routing actually works, why FX Send is gain (not mix),
how to build the racks from scratch with full understanding, and how
to use the throw-and-tail technique that defines the FX Machine sound.

This is a musical and conceptual document, not just a how-to. It
explains the WHY behind every architectural choice in the signal chain.
Understanding this will help you tune the system to your taste, build
variations on the rack design, and use the controller in ways that go
beyond the obvious.

If you just want step-by-step instructions for building the racks,
see [SETUP_ABLETON.md](SETUP_ABLETON.md). This document explains the
reasoning behind those instructions.

---

## Table of Contents

1. [The DJM-900 NXS2 as Reference](#the-djm-900-nxs2-as-reference)
2. [The Full Signal Chain Overview](#the-full-signal-chain-overview)
3. [Why EQ Comes Before FX](#why-eq-comes-before-fx)
4. [The EQ Rack — Anatomy](#the-eq-rack--anatomy)
5. [Why TRIM Comes Before EQ Three](#why-trim-comes-before-eq-three)
6. [The EQ Three — What It Actually Does](#the-eq-three--what-it-actually-does)
7. [The FX Rack — Overview](#the-fx-rack--overview)
8. [Outer Path Effects — Filter and Stutter](#outer-path-effects--filter-and-stutter)
9. [The Nested Wet/Dry Rack — The Critical Innovation](#the-nested-wetdry-rack--the-critical-innovation)
10. [FX Send Is Gain, Not Mix — Why This Matters](#fx-send-is-gain-not-mix--why-this-matters)
11. [The Wet Chain — Utility, Reverb, Delay](#the-wet-chain--utility-reverb-delay)
12. [Stereo Width — The Final Stage](#stereo-width--the-final-stage)
13. [How Audio Actually Flows Through the Rack](#how-audio-actually-flows-through-the-rack)
14. [The Throw-and-Tail Technique](#the-throw-and-tail-technique)
15. [Stacking Throws for Walls of Tails](#stacking-throws-for-walls-of-tails)
16. [The Bass Cut Technique](#the-bass-cut-technique)
17. [Filter Sweeps Through Wet Tails](#filter-sweeps-through-wet-tails)
18. [Stutter — Beat Repeat as a Performance Tool](#stutter--beat-repeat-as-a-performance-tool)
19. [The TRIM Knob — Gain Staging](#the-trim-knob--gain-staging)
20. [The Kill EQ — Frequency Carving](#the-kill-eq--frequency-carving)
21. [Smart Kill vs Smart Normalize](#smart-kill-vs-smart-normalize)
22. [The Asymptotic Boost — Musical Reasoning](#the-asymptotic-boost--musical-reasoning)
23. [Bass Safety — Why It Exists](#bass-safety--why-it-exists)
24. [Filter Lock and Wet Lock — Creative Use](#filter-lock-and-wet-lock--creative-use)
25. [Common Signal Chain Variations](#common-signal-chain-variations)
26. [Alternative Devices and Substitutions](#alternative-devices-and-substitutions)
27. [Building a Minimal Version](#building-a-minimal-version)
28. [Building an Extended Version](#building-an-extended-version)
29. [Gain Staging Throughout the Chain](#gain-staging-throughout-the-chain)
30. [Latency Considerations](#latency-considerations)
31. [Quality vs CPU Trade-Offs](#quality-vs-cpu-trade-offs)
32. [Why This Specific Approach Wins](#why-this-specific-approach-wins)

---

## The DJM-900 NXS2 as Reference

FX Machine's signal chain is modeled on the Pioneer DJM-900 NXS2 mixer's
channel strip. The DJM-900 NXS2 is the industry-standard club mixer —
it's what you'll find in nightclubs, festivals, and DJ booths worldwide.
Its signal flow has been refined over decades of professional use.

A single DJM-900 NXS2 channel strip looks like this from top to bottom:

```
┌─────────────────────────────────┐
│  TRIM knob (-∞ to +9 dB)        │  ← input gain
│  Sets the channel level         │
├─────────────────────────────────┤
│  HI EQ (-26 dB to +6 dB)        │  ← treble
│  MID EQ (-26 dB to +6 dB)       │  ← midrange
│  LOW EQ (-26 dB to +6 dB)       │  ← bass
│  (Kill EQ — full cuts at -∞)    │
├─────────────────────────────────┤
│  COLOR FX (filter/effect)       │  ← color/character processing
├─────────────────────────────────┤
│  CUE button                     │  ← headphone monitor
├─────────────────────────────────┤
│  CHANNEL FADER                  │  ← level fader
└─────────────────────────────────┘
         │
         ▼
   To Master / FX Send
         │
         ▼
   ┌──────────────┐
   │  BEAT FX     │  ← Pioneer's effects unit
   │  Filter,     │     (delay, reverb, echo,
   │  Reverb,     │      filter, stutter)
   │  Delay,      │
   │  Stutter...  │
   └──────────────┘
         │
         ▼
       Master out
```

FX Machine replicates this:
- **TRIM + HI + MID + LOW** → the EQ rack (with TRIM as the 4th macro)
- **BEAT FX** → the FX rack (filter, reverb, delay, stutter, etc.)

The order matters. The flow goes: input gain → frequency shaping →
effects → output. This is the standard signal flow of any analog
mixer channel strip, and it's what your audience expects when they
see DJ-style EQ and FX manipulation.

---

## The Full Signal Chain Overview

Here's the complete FX Machine signal chain, end to end:

```
                ┌─────────────────────────────┐
                │    Your instrument tracks    │
                │    (synths, samples, drums)  │
                └─────────────────────────────┘
                              │
                              ▼
                ┌─────────────────────────────┐
                │   Routing to processing path  │
                │   (sends or direct routing)  │
                └─────────────────────────────┘
                              │
                              ▼
        ╔══════════════════════════════════════════════╗
        ║          ~ EQ Macros (Audio Track)            ║
        ║  ┌──────────────────────────────────────────┐ ║
        ║  │  Audio Effect Rack                        │ ║
        ║  │                                            │ ║
        ║  │  ┌────────────┐    ┌───────────────────┐  │ ║
        ║  │  │  Utility   │ ─▶ │   EQ Three        │  │ ║
        ║  │  │  (TRIM)    │    │   (HI/MID/LOW)    │  │ ║
        ║  │  └────────────┘    └───────────────────┘  │ ║
        ║  │                                            │ ║
        ║  └──────────────────────────────────────────┘ ║
        ╚══════════════════════════════════════════════╝
                              │
                              ▼
        ╔══════════════════════════════════════════════╗
        ║         ~ FX Macros (Audio Track)             ║
        ║  ┌──────────────────────────────────────────┐ ║
        ║  │  Audio Effect Rack (OUTER)                │ ║
        ║  │                                            │ ║
        ║  │  ┌────────────┐    ┌─────────────┐        │ ║
        ║  │  │ Auto       │ ─▶ │ Beat Repeat │        │ ║
        ║  │  │ Filter     │    │ (Stutter)   │        │ ║
        ║  │  └────────────┘    └─────────────┘        │ ║
        ║  │                          │                │ ║
        ║  │                          ▼                │ ║
        ║  │  ┌──────────────────────────────────────┐  │ ║
        ║  │  │  Audio Effect Rack (NESTED — INNER) │  │ ║
        ║  │  │                                      │  │ ║
        ║  │  │  ┌─────────────┐                    │  │ ║
        ║  │  │  │ Dry chain   │ ─▶ (passthrough)   │  │ ║
        ║  │  │  └─────────────┘                    │  │ ║
        ║  │  │                                      │  │ ║
        ║  │  │  ┌─────────────────────────────────┐ │  │ ║
        ║  │  │  │ Wet chain                       │ │  │ ║
        ║  │  │  │                                 │ │  │ ║
        ║  │  │  │ ┌─────────┐  ┌─────────┐  ┌───┐ │ │  │ ║
        ║  │  │  │ │ Utility │─▶│ Reverb  │─▶│Del│ │ │  │ ║
        ║  │  │  │ │(FX Send)│  │(Dark Hl)│  │ay │ │ │  │ ║
        ║  │  │  │ └─────────┘  └─────────┘  └───┘ │ │  │ ║
        ║  │  │  └─────────────────────────────────┘ │  │ ║
        ║  │  │                                      │  │ ║
        ║  │  │       (Dry + Wet summed here)       │  │ ║
        ║  │  └──────────────────────────────────────┘  │ ║
        ║  │         │                                  │ ║
        ║  │         ▼                                  │ ║
        ║  │  ┌────────────┐                            │ ║
        ║  │  │  Utility   │ ─▶ (final stereo width)    │ ║
        ║  │  │  (Width)   │                            │ ║
        ║  │  └────────────┘                            │ ║
        ║  └──────────────────────────────────────────┘ ║
        ╚══════════════════════════════════════════════╝
                              │
                              ▼
                ┌─────────────────────────────┐
                │         Master Output        │
                │     (your speakers/PA/DAW)   │
                └─────────────────────────────┘
```

The audio flows top to bottom. Every sample passes through this entire
chain in sequence. At any moment, the user can:
- Adjust input gain (TRIM)
- Carve frequencies (HI/MID/LOW kill EQ)
- Sweep the filter
- Trigger the stutter
- Add wet effects (reverb/delay) via FX Send
- Adjust stereo width

All in real time, all via the gamepad.

---

## Why EQ Comes Before FX

The order EQ → FX (not FX → EQ) is deliberate and based on how
performers actually use these tools.

### Musical reasoning

**EQ shapes the SOURCE.** When you kill the bass on a track, you're
deciding what frequencies are present in the music being played. This
is a creative decision about the source material.

**FX shape the AMBIENCE.** Reverb, delay, filter sweeps — these add
atmosphere to whatever frequencies survived the EQ. They're decisions
about the SPACE the music exists in.

If FX came first, here's what would happen:

```
FX first:    Source → Reverb/Delay → EQ → Output

User wants to kill the bass:
  → Bass is sent into reverb/delay (creating bass tails)
  → Then EQ kills the bass
  → But the bass tails in the reverb are still ringing
  → Result: muddy low-end residue that the user can't remove
```

vs the correct order:

```
EQ first:    Source → EQ → Reverb/Delay → Output

User wants to kill the bass:
  → Bass is cut from the source BEFORE reverb sees it
  → Reverb only processes the surviving frequencies
  → Result: clean kill, no muddy residue
```

This is why every professional mixer puts EQ before FX. FX Machine
inherits this design from the DJM-900 NXS2.

### Technical reasoning

Effects like reverb and delay accumulate. If you feed them garbage
(unwanted frequencies), the garbage persists in their tails for seconds
or longer. Cleaning frequencies BEFORE they enter the effects keeps
the effects clean. Cleaning AFTER means the effects' tails carry the
unwanted frequencies you tried to remove.

This is especially critical for the throw-and-tail technique. When you
throw a wet swell, you want clean, musical reverb tails — not reverb
that's processing the bass you'd already decided to kill.

---

## The EQ Rack — Anatomy

The EQ rack is structurally simple — two devices in series:

```
EQ rack:
   [Utility] → [EQ Three]
       ↑           ↑
      TRIM      HI/MID/LOW
```

Four macros control these two devices:
- Macro 1: EQ Low  → EQ Three GainLow
- Macro 2: EQ Mid  → EQ Three GainMid
- Macro 3: EQ High → EQ Three GainHi
- Macro 4: Trim    → Utility Gain

### Why a Utility for TRIM instead of EQ Three's gain?

EQ Three has a "Gain" parameter on its output, but it's a fixed range
(-12 dB to +12 dB) intended as makeup gain for EQ adjustments. The
DJM-900 NXS2's TRIM knob has a much larger range (-∞ to +9 dB) and is
intended for input gain staging.

Ableton's Utility device gives us:
- Full -∞ to +35 dB range
- Linear-in-dB response (matches the DJM-900's analog gain curve)
- Stereo balance, mono summing, and other features we don't use but
  could expose in future versions

For FX Machine, we cap the visual range at +9 dB to match the DJM-900
NXS2 reference, but the underlying Utility has full range available
for safety headroom.

### The two-device chain

The two devices are wired in series — audio flows through Utility first,
then through EQ Three:

```
Input → Utility (TRIM) → EQ Three (HI/MID/LOW) → Output
```

TRIM happens first because it's input gain. You want to set the level
going INTO the EQ before the EQ shapes the frequencies. This matches
the standard mixer signal flow.

---

## Why TRIM Comes Before EQ Three

This ordering is not arbitrary. Here's the reasoning:

### Headroom management

If you boost the EQ (e.g., +6 dB on the low band) and the input was
already hot, the EQ can clip internally. By placing TRIM first, you
can reduce the input level BEFORE the EQ amplifies certain frequencies.

```
Input at +3 dB → EQ boosts low by +6 dB → Internal level reaches +9 dB
                                          → Risk of internal clipping

With TRIM at -3 dB:
Input at +3 dB → TRIM reduces to 0 dB → EQ boosts low by +6 dB
                                       → Internal level reaches +6 dB
                                       → Safe headroom
```

### Gain matching for A/B-ing tracks

When mixing between two tracks (DJ-style), they often have different
mastering loudness. TRIM lets you match levels before they hit the EQ
so that "0 dB" on the EQ display means the same thing for both tracks.

### Standard mixer signal flow

Every professional mixer (DJM-900, A&H Xone, RANE) puts the input gain
control before the EQ section. FX Machine follows this convention so
users with mixer experience feel at home immediately.

---

## The EQ Three — What It Actually Does

Ableton's EQ Three is a 3-band kill EQ specifically designed to emulate
DJ mixer-style EQs. Its key characteristics:

### Frequency band split

| Band | Frequency Range | Crossover |
|---|---|---|
| LOW | ~0 Hz - 200 Hz | -24 dB/octave to MID |
| MID | ~200 Hz - 2.5 kHz | -24 dB/octave between LOW and HIGH |
| HIGH | ~2.5 kHz - 20 kHz | -24 dB/octave from MID |

The exact crossover frequencies are tunable in EQ Three's interface
(Frequency Low and Frequency High knobs). FX Machine doesn't expose
these — it assumes you've set them to match your taste before performing.

### The "kill" behavior

EQ Three's gain knobs range from **-∞ dB (full kill)** to **+6 dB
(boost)**. The "-∞" is true silence — not just a heavy cut. This is
what makes it a "kill EQ" suitable for DJ-style frequency carving:

- Kill the bass → bass band drops to absolute silence (huge impact)
- Kill the mid → middle frequencies vanish (vocals disappear)
- Kill the high → cymbals/hihats vanish (dampened feel)

The kill is musical because it's INSTANT and COMPLETE. A 6 dB cut on
a normal EQ is barely noticeable. -∞ on a kill EQ is unmistakable.

### Why this specific EQ

Ableton has many EQ devices (EQ Eight, EQ Three, Cabinet, etc.). EQ Three
is chosen specifically because:

1. **It has the right behavior:** True kill at -∞, gentle boost up to +6 dB
2. **It's CPU-efficient:** Designed for live use, low overhead
3. **It's a fixed 3-band:** Matches the DJM-900 NXS2 layout exactly
4. **It ships with all Ableton editions:** No paywall

If you have different needs (e.g., parametric EQ with notch filtering),
you could substitute EQ Eight, but you'd lose the kill behavior and
the macro mapping would need adjustment.

### Calibration: macro 107.9 = 0 dB

The macro value 107.9 corresponds to 0 dB (unity gain) on EQ Three.
This was measured empirically — Ableton's macro-to-parameter mapping
for EQ Three is non-linear (logarithmic in dB), so 50% on the macro
isn't 0 dB. FX Machine uses this calibration constant
(`EQ_NEUTRAL_MACRO = 107.9` in `src/config.py`) to know where "neutral"
is for all the smart-kill and normalize logic.

DO NOT change the macro min/max ranges for EQ Three. The calibration
assumes default ranges (0-127). Changing them will break the dB
calibration and the smart-action logic will misbehave.

---

## The FX Rack — Overview

The FX rack is more complex than the EQ rack because it does multiple
things at once:

```
FX rack outer chain:
   [Auto Filter] → [Beat Repeat] → [Nested Rack] → [Utility (Width)]
        ↑               ↑                ↑                ↑
   Filter Freq/      Stutter      Wet/Dry routing      Width
   Mode/Res                       (see below)
```

Six of the eight FX macros control devices in the OUTER chain. Two
macros (FX Send and Reverb Size, and Delay FB) control devices in the
INNER nested rack.

### Outer chain devices

| Device | What it does | Macros |
|---|---|---|
| Auto Filter | Sweepable filter (HP/LP) | Filter Freq, Filter Mode, Filter Res |
| Beat Repeat | Tempo-synced stutter | Stutter |
| (Nested rack) | Wet/dry effects routing | FX Send, Reverb Size, Delay FB |
| Utility | Stereo width | Width |

### Inner nested rack devices (Wet chain only)

| Device | What it does | Macro |
|---|---|---|
| Utility (Wet path) | Send gain (input to wet processing) | FX Send |
| Reverb (Dark Hall) | Long reverb | Reverb Size |
| Delay (Long Digi) | Tempo-synced delay | Delay FB |

The Dry chain in the inner nested rack is intentionally EMPTY — it's
just a passthrough for the dry signal.

---

## Outer Path Effects — Filter and Stutter

These two effects are on the main signal path. Everything passes through
them, dry or wet, before reaching the wet/dry split.

### Auto Filter

Ableton's Auto Filter provides:
- **Frequency:** 20 Hz to 20 kHz, logarithmic
- **Filter type:** HP, LP, BP, Notch (we use HP and LP)
- **Resonance:** 0% to 100%
- **Drive:** Optional saturation (we leave at minimum)
- **Envelope follower:** Auto-modulation (we don't use)

FX Machine controls three parameters:
- **Filter Freq:** The cutoff frequency (the main sweep)
- **Filter Mode:** HP vs LP toggle
- **Filter Res:** Resonance amount

In neutral state (Filter Freq at maximum, LP mode), the filter is
inaudible — it's just a wire. As you sweep Filter Freq down, higher
frequencies get attenuated, creating the classic "filter sweep" sound.

In HP mode, the filter cuts LOWS as you sweep up (used by the Bass
Cut momentary).

### Beat Repeat (Stutter)

Ableton's Beat Repeat captures a slice of incoming audio and repeats
it tempo-synced. It produces the "stutter" effect heard in many DJ
sets — sudden rhythmic repetition that creates tension before a drop.

FX Machine maps the Stutter macro to Beat Repeat's volume/activate
parameter:
- Macro at 0 → Beat Repeat is silent (passes audio through unchanged)
- Macro at max → Beat Repeat is active (audio gets stuttered)

The stutter pattern (1/16, 1/8, 1/4 notes, etc.) is set in Beat Repeat's
interface — FX Machine doesn't control these via macros. Set the pattern
to your preference before performing.

### Why these are on the outer path

Filter and Stutter affect ALL audio — both dry and wet. This is
intentional:

**Filter sweeps through wet tails:** If you have reverb tails ringing
and then sweep the filter down, the tails get filtered along with the
dry signal. This is a hugely musical effect — the reverb sounds like
it's being pulled into a tunnel.

**Stutter affects wet effects:** When you trigger stutter while wet
effects are active, the stutter applies to the COMBINED dry+wet signal,
not just the dry. The result is a much more chaotic, layered stutter
that includes the reverb/delay character.

If Filter and Stutter were INSIDE the wet/dry split, they'd only affect
one path — losing this combined behavior.

---

## The Nested Wet/Dry Rack — The Critical Innovation

This is the most important and subtle part of the FX Machine signal
chain. It's also the most commonly misunderstood.

### The problem this solves

You want effects (reverb, delay) that:
1. Can be SENT TO without affecting the dry signal
2. Have TAILS that ring out after you stop sending to them
3. Can be sent to from a controller in real-time
4. Sound exactly like a Pioneer DJM-900 NXS2's FX section

A naive setup (just adding reverb and delay in series) gives you:
- ❌ Dry signal affected by reverb's own dry/wet mix
- ❌ Tails cut off when you reduce the wet amount
- ❌ No way to "throw" a send and let it tail

The nested wet/dry rack solves all four requirements.

### How it works structurally

```
Nested rack contains TWO chains:

  Chain "Dry":
    (completely empty)
    Audio enters → audio exits (unchanged)

  Chain "Wet":
    Audio enters → Utility (gain control) → Reverb → Delay → audio exits
```

The two chains run IN PARALLEL. Input audio gets duplicated into both
chains. Each chain processes independently. Their outputs get SUMMED
to produce the rack's output.

```
              Input
                │
                ▼
        ┌───────────────┐
        │ Nested rack   │
        │               │
        │   ┌────────┐  │
        │   │  Dry   │──┐
        │   │ (empty)│  │
        │   └────────┘  │
        │               │ ─── SUM ──▶ Output
        │   ┌────────┐  │
        │   │  Wet   │──┘
        │   │ (FX)   │
        │   └────────┘  │
        │               │
        └───────────────┘
```

### Why two chains instead of one with serial effects

If the effects were in a single chain:
```
Input → Reverb → Delay → Output
```
Then to control "how much effect," you'd use Reverb's Dry/Wet knob.
But that knob CROSSFADES — at 50%, you get 50% dry and 50% wet. The
dry path is being attenuated.

With the parallel chains:
```
Input → [Dry path (always 100%)] + [Wet path (variable)] → Output
```
The dry signal is ALWAYS at full level. The wet signal is ADDED on top
based on the Utility's gain in the wet chain. This is the difference
between a SEND and a MIX:

- **MIX (wet/dry crossfade):** Wet replaces dry partially
- **SEND (parallel paths):** Wet adds to dry

DJM-900 NXS2's send/return loop is a SEND, not a mix. FX Machine
replicates this.

---

## FX Send Is Gain, Not Mix — Why This Matters

This is the single most important conceptual point in the entire FX
Machine design. If you understand this, you understand why the rack
is structured the way it is.

### The Utility in the Wet chain

Inside the Wet chain, the FIRST device is a Utility set to control
gain. The FX Send macro maps to this Utility's Gain parameter.

```
Wet chain:
  Input → [Utility (Gain)] → [Reverb] → [Delay] → Output
              ↑
         FX Send macro
```

### What FX Send actually controls

The Utility's gain is set in dB:
- **FX Send = 0:** Utility gain = -∞ dB. No signal enters the wet chain.
  Reverb and delay receive silence as input. They have NOTHING to
  process going forward. But anything already in their tails continues
  to ring out (they're decaying signals, not active processes).
- **FX Send = max:** Utility gain = 0 dB (or +9 dB, depending on
  configuration). Full signal enters the wet chain. Reverb and delay
  process at full volume.
- **FX Send = halfway:** Utility gain = somewhere around -6 dB. Reduced
  signal enters the wet chain. Effects process at reduced volume.

### The critical insight

When FX Send drops to 0, **nothing new enters the wet chain**, but
**existing tails continue to decay naturally**. This is because:

1. The reverb/delay devices are still active — they're just not getting
   new input
2. Their internal buffers still contain audio from before the send dropped
3. As time passes, that audio decays through the reverb's natural decay
   time and the delay's feedback loop

Result: you can throw a wet swell, then cut FX Send to 0, and the tails
ring out for 5-30+ seconds depending on the reverb's decay time and the
delay's feedback amount.

### The wrong way (wet/dry mix)

If FX Send was implemented as a wet/dry mix on the reverb/delay devices:
- FX Send = 0 → wet/dry mix = 0% wet → wet signal is silenced INSTANTLY
- Tails cut off immediately
- No throw-and-tail technique possible

### The right way (send level)

FX Send as a gain on the input to the wet chain:
- FX Send = 0 → no new signal enters → existing tails decay naturally
- Tails ring out for seconds
- Throw-and-tail works exactly like a real DJM-900

This single architectural choice is what makes FX Machine feel like a
real DJ mixer instead of just a parameter controller.

---

## The Wet Chain — Utility, Reverb, Delay

Inside the Wet chain, three devices in series:

### 1. Utility (FX Send gain) — first

Controls how much signal enters the wet processing chain. This is the
device the FX Send macro maps to.

Settings:
- **Gain:** -∞ dB by default (no wet processing)
- Set this to -∞ initially so the wet chain is silent at startup

### 2. Reverb (Dark Hall preset) — second

A long, dense, hall-style reverb. Settings:
- **Dry/Wet:** **100% Wet** (CRITICAL — see below)
- **Decay Time:** 5-30 seconds (longer = more dramatic tails)
- **Diffusion Network:** Default
- **Stereo Width:** Default (100%)
- **Quality:** Eco or High (your CPU preference)

Why **100% Wet** is critical: the Wet chain is supposed to output
ONLY the wet processed signal. The dry signal is handled by the
separate Dry chain in the nested rack. If Reverb's Dry/Wet was at
less than 100%, the Reverb would output some dry signal too, which
would double-count the dry in the final sum.

### 3. Delay (Long Digi Delay preset) — third

A tempo-synced, longer-than-usual delay. Settings:
- **Dry/Wet:** **100% Wet** (same reason as reverb)
- **Delay Time:** Tempo-synced (e.g., 1/4 note, 1/2 note)
- **Feedback:** Moderate (~30-50%) — this is what the Delay FB macro
  controls
- **Mode:** Repitch or Fade (your preference)

The delay COMES AFTER the reverb in the chain. This means the reverb's
output gets DELAYED. You get reverbed-and-delayed sound — atmospheric
swells that echo through space.

If you flip the order (Delay → Reverb), you get delayed-and-reverbed
sound — discrete echoes that each get reverbed individually. Both are
musical, but the reverb-then-delay order gives the "atmospheric wash"
sound that fits DJ-style throws.

### Why these specific devices?

**Reverb (Dark Hall):** Long decay, dense reflections. Sounds like a
large physical space. Perfect for atmospheric swells. Other reverb
presets (Cathedral, Concert Hall) work too — pick what sounds good
to you.

**Delay (Long Digi Delay):** Tempo-synced, can have long delay times,
good feedback character. The "Digital" sound is clean — not lo-fi
or character-heavy. If you want a more vintage character, substitute
Echo or Filter Delay.

---

## Stereo Width — The Final Stage

After the wet/dry rack, one last Utility device controls the stereo
width of the COMBINED (dry + wet) output:

```
Outer chain final stage:
   ... → [Nested wet/dry rack] → [Utility (Width)] → Output
                                       ↑
                                   Width macro
```

The Utility's Width parameter:
- **0%:** Mono (all left/right information collapsed to center)
- **100%:** Original stereo (default — no change)
- **200%:** Exaggerated stereo (extreme widening)

Why this is on the outer path: width should apply to the FINAL sound,
including both dry and wet. If width was inside the wet chain, only
the wet effects would widen. If width was before the wet/dry split,
the wet effects would inherit the widened stereo and could become
phasey or unstable.

Width on the outer path, after the wet/dry sum, is mathematically
the correct place. It treats the entire processed channel as a
unified stereo signal.

---

## How Audio Actually Flows Through the Rack

Let's trace a single sample through the entire chain:

```
T=0: Sample enters the EQ rack
       │
       ▼
T=1: Sample passes through Utility (TRIM)
     - Gain applied based on TRIM macro
     - If TRIM = 0 dB, no change
     - If TRIM = +9 dB, sample amplitude × 2.82
       │
       ▼
T=2: Sample enters EQ Three
     - Split into LOW/MID/HIGH bands
     - Each band's gain applied based on macro
     - Bands recombined into single sample
     - If all macros at 0 dB, no change
     - If LOW macro at -∞, LOW band is silent
       │
       ▼
T=3: EQ rack output → FX rack input
       │
       ▼
T=4: Sample passes through Auto Filter
     - Filter type (HP/LP) based on Filter Mode macro
     - Cutoff frequency based on Filter Freq macro
     - Resonance based on Filter Res macro
     - If Freq at max + LP mode, filter is transparent
       │
       ▼
T=5: Sample passes through Beat Repeat
     - If Stutter macro = 0, sample passes through
     - If Stutter macro = max, sample may be captured and repeated
       │
       ▼
T=6: Sample enters the nested wet/dry rack
     - Duplicated into TWO copies (one for Dry chain, one for Wet chain)
       │
       ├──▶ Dry chain (passthrough)
       │      Sample exits Dry chain unchanged
       │      │
       │      ▼
       │   Goes to summing point
       │
       └──▶ Wet chain
              │
              ▼
            Utility (FX Send gain)
              - If FX Send = 0, sample becomes silence
              - If FX Send = max, sample at full level
              │
              ▼
            Reverb (Dark Hall)
              - Sample fed into reverb's internal buffer
              - Reverb outputs current reverberated audio
              │ (note: output reflects PAST input, not current)
              ▼
            Delay (Long Digi Delay)
              - Sample fed into delay's internal buffer
              - Delay outputs delayed audio
              │ (note: output reflects PAST input)
              ▼
            Wet chain output (= reverb+delay sound)
              │
              ▼
            Goes to summing point

T=7: Summing point combines Dry + Wet
     - Dry sample (unchanged from T=5)
     - Wet sample (from reverb/delay tails)
     - Output = Dry + Wet
       │
       ▼
T=8: Sample passes through Utility (Width)
     - Stereo width applied based on Width macro
     - If Width = 100%, no change
     - If Width = 0%, sample collapses to mono
       │
       ▼
T=9: Sample exits the FX rack → Master output → speakers
```

This entire path happens in microseconds, sample-by-sample, continuously.
At 48 kHz sample rate, this process repeats 48,000 times per second
per channel.

---

## The Throw-and-Tail Technique

This is THE signature move FX Machine is designed for. Understanding
it explains every signal chain decision.

### The setup

You're playing a track. The reverb and delay in the wet chain have:
- Reverb decay time: ~10 seconds
- Delay feedback: ~50%

FX Send is at 0 (no wet processing happening). Audio sounds clean and dry.

### The throw

You press L1 + □ on the gamepad. This triggers the "FX Send Throw"
momentary effect:
1. The current FX Send value is snapshotted (= 0)
2. FX Send is jammed to maximum
3. Full signal pours into the wet chain
4. Reverb and delay start building up wet sound

### Hold for 1-2 bars

You hold the button. Wet effects build up:
- Reverb is filling its decay buffer with a wash of sound
- Delay is bouncing the audio rhythmically with feedback

The audience hears a swelling wet wash growing under the dry signal.
This is the "throw."

### Release

You release □. The momentary effect's restore logic runs:
1. FX Send returns to its snapshot value (= 0)
2. No new signal enters the wet chain
3. The dry signal continues unchanged

But the reverb and delay buffers are FULL of wet sound from the throw.
They don't reset — they decay naturally:
- Reverb tail rings out over its 10-second decay time
- Delay continues to bounce, fading by ~50% feedback each repetition

The audience hears the dry signal continuing CLEAN, while the wet tails
ring out behind it. The throw "leaves" but its echo persists.

### The musical effect

This is the sound of a real DJ booth. Throwing a delay on a vocal
sample, then letting it echo through 8 bars of clean playing. Building
tension with a reverb swell, then dropping it to let the tail breathe
under the next section.

Without the nested wet/dry rack design, this would be impossible. With
it, the technique is built into the basic interaction of the controller.

---

## Stacking Throws for Walls of Tails

The throw-and-tail technique gets even more powerful when you stack
multiple throws:

### Throw 1

Press and release L1+□. A wet swell builds and starts decaying.

### Throw 2 (while throw 1 is still decaying)

Press and release L1+□ again. A NEW wet swell builds on top of the
decaying first one. The reverb buffer now contains BOTH swells layering
on top of each other.

### Throw 3, 4, 5...

Each throw adds another layer to the still-decaying wet pile. You can
build a massive wall of tails that persists for 30+ seconds.

### When to use this

- **Building tension before a drop:** Stack 4-5 throws over the last
  8 bars of a breakdown. The wall of tails fills the space. Then drop
  the bass and the tails carry the energy through the transition.
- **Transitioning between tracks:** Stack throws on the outgoing track
  while you mix in the new one. The tails bridge the two tracks.
- **Atmospheric sections:** Continuous slow throws create an ever-evolving
  background wash. The audience experiences it as ambient texture.

### The technical reason this works

Reverb is mathematically a LINEAR system. If you feed it two signals
simultaneously, its output is the sum of what it would output for each
signal separately. Multiple throws don't "fight" each other — they layer.

Delay is also linear (assuming feedback < 100%). Multiple inputs at
different times produce echoes at different positions in the delay
buffer, all decaying independently.

The wet chain happily accumulates dozens of throws if you want.
Limited only by your patience and the audience's tolerance for
atmospheric wash.

---

## The Bass Cut Technique

L1 + O on the gamepad triggers the "Bass Cut" momentary effect:

### What it does

1. Snapshots the current Filter Freq and Filter Mode values
2. Switches Filter Mode to HP (high-pass)
3. Sets Filter Freq to ≈200 Hz on the macro scale

Result: Everything below 200 Hz is filtered out. Kick drums lose their
thump. Bass lines lose their body. The track sounds "thin" or "scooped."

### When to use this

- **Cleaning up muddy mixes:** If the track has too much low-end
  competition (e.g., during a mix), bass cut creates space.
- **Build-ups:** Cut the bass for 4 bars before a drop. The audience
  hears the loss of body and EXPECTS the bass to come back. When you
  release the cut on the downbeat, the bass return hits hard.
- **Transitions:** Cut bass on outgoing track while bringing in a new
  track. Two basses fighting sounds bad. Cut one to make room.

### Release behavior

When you release the button:
1. Filter Freq returns to the snapshot value (whatever it was before)
2. Filter Mode returns to the snapshot value (LP or HP)
3. The full bass returns instantly

### Why it's a momentary (not a toggle)

You usually want bass cut for short periods — a bar or two, not
indefinitely. The momentary pattern enforces this: hold the button
while you want bass cut, release to restore. You don't have to
remember "did I leave bass cut on?" because the system can't be
left in a wrong state — releasing always restores.

---

## Filter Sweeps Through Wet Tails

This is one of FX Machine's most musical capabilities, made possible
by Auto Filter being on the outer path (after the wet/dry rack):

### The setup

1. Throw the FX Send (build up wet tails)
2. Release the throw (tails start decaying)
3. While tails are ringing, sweep the Filter Freq

### What happens

The filter processes the COMBINED (dry + wet) signal. As you sweep
the filter down (LP mode), high frequencies get filtered out from
both:
- The current dry signal
- The decaying wet tails

The wet tails "filter through" along with the dry. You can sweep them
into a thick, dark wash, then sweep back up to let them bloom.

### The musical effect

This is one of the most-used effects in deep house and progressive
techno. The filter sweep through the tails creates a sense of motion
and depth — the audience hears not just a filter, but a filter
modulating an entire atmospheric space.

### Why this requires the architecture

If the filter were INSIDE the wet chain (after the reverb/delay), it
would only filter the wet signal — the dry would remain unfiltered
and the contrast would be jarring.

If the filter were INSIDE the wet chain BEFORE the reverb/delay, the
reverb tails wouldn't include the filter character.

By placing the filter on the OUTER path AFTER the wet/dry sum, the
filter character applies to everything — dry signal AND wet tails as
they decay. This is the musically correct placement.

---

## Stutter — Beat Repeat as a Performance Tool

Beat Repeat (Stutter) is a unique device that captures a slice of
audio and repeats it rhythmically. In FX Machine, it's wired as a
momentary effect:

### The mechanics

When Stutter activates:
1. Beat Repeat starts running at the configured grid (typically 1/16
   or 1/8 notes)
2. Incoming audio is captured at the start of each grid division
3. The captured audio is repeated for the duration of that grid

When Stutter deactivates:
1. Beat Repeat goes silent
2. Audio passes through unmodified

### Why it's musical

Stutter creates RHYTHMIC TENSION. The repeated audio loses its
forward momentum — it becomes a stuck moment. The audience expects
the music to continue but instead hears the same fragment looping.

Used briefly (1-2 beats), it's a hiccup that adds excitement.
Used longer (a full bar), it's a tension build that demands release.
Used right before a drop, it's the cliché build-up effect everyone
recognizes.

### Where it sits in the chain

Stutter is on the OUTER path BEFORE the wet/dry rack. This means:
- The dry signal gets stuttered
- The wet effects receive the stuttered audio as input

If wet effects are also active when you stutter:
- Reverb tails of the stuttered audio are also stuttered (they were
  built from stuttered input)
- Delay echoes of the stuttered audio compound the stuttering effect

This can be musically chaotic — used sparingly, it adds intensity.
Used heavily, it becomes a wash of confused rhythmic fragments.

---

## The TRIM Knob — Gain Staging

TRIM controls input gain to the EQ section. Its musical use:

### Setting initial level

When you load a track, its loudness may not match what you've been
playing. TRIM lets you adjust the level so consecutive tracks have
similar perceived loudness. This is the same role TRIM serves on a
real DJ mixer.

### Headroom for boosts

If your track is already hot (peaking near 0 dBFS), boosting any EQ
band will cause internal clipping. Reduce TRIM by 3-6 dB before doing
big EQ boosts to give yourself headroom.

### Creative use — gain riding

You can use TRIM as a "drama" knob — riding it up during build-ups
and back down during breakdowns. Not the conventional use, but
musically valid.

### Why +9 dB max?

The DJM-900 NXS2's TRIM has a +9 dB ceiling. Going higher rarely
serves a musical purpose — if a track is so quiet it needs more than
+9 dB to match others, the track itself probably needs remastering.

The Utility device technically supports up to +35 dB. FX Machine
caps the visual range at +9 dB so the knob's full-right position is
meaningful (you've used all the available boost). The cap is
configurable via `cfg.TRIM_MAX_DB` if you need more headroom for
unusual situations.

### Why -∞ minimum?

A full TRIM cut to -∞ silences the channel completely. This is useful
for instant kills — emergency silence if something is wrong. The DJM-900
NXS2 also allows -∞ on TRIM for the same reason.

---

## The Kill EQ — Frequency Carving

The 3-band EQ is the core creative tool for DJ-style frequency
manipulation. Each band's role:

### LOW (~0 to 200 Hz)

Contains:
- Kick drum thump
- Bass line body
- Sub-bass texture

Kill the LOW: removes all low-frequency energy. The track sounds thin,
"scooped," like it's playing through a phone speaker. Used to clean
up bass conflicts or to dramatically drop energy.

### MID (~200 Hz to 2.5 kHz)

Contains:
- Vocal fundamentals
- Snare body
- Synth chords
- Guitar/piano body

Kill the MID: removes the "core" of most musical content. The track
becomes bass + cymbals with no middle. Sounds hollow and processed.
Used sparingly for specific effects.

### HIGH (~2.5 kHz to 20 kHz)

Contains:
- Cymbal shimmer
- Hi-hat ticks
- Vocal sibilance
- Synth harmonics

Kill the HIGH: removes the airiness and brightness. The track sounds
dull and dampened. Used for sense of "going underwater" or "passing
through a wall."

### Combined kills

Killing multiple bands simultaneously creates extreme effects:

- LOW + MID killed → only HIGH remaining → ambient shimmer
- MID + HIGH killed → only LOW remaining → just bass and kick
- HIGH alone killed → muffled but full → "behind a door" sound

These are tools — not always musical, but available when needed.

### The boost side

Boosting (up to +6 dB) is for emphasis, not creation. Use it sparingly:
- Boost LOW to emphasize bass during a drop
- Boost HIGH to add air during a breakdown
- Boost MID generally sounds bad (muddiness in the most-occupied range)

Bass boost is capped at +2 dB by safety (see Bass Safety section
below).

---

## Smart Kill vs Smart Normalize

The X-axis double-flick is context-aware:

### Above 0 dB → Normalize

If you're at +3 dB on a band and you double-flick LEFT:
- The action is "normalize" (pull back to 0 dB)
- The band ramps from +3 dB → 0 dB
- You went from boosted → neutral

This is the "I want to undo this boost" gesture.

### At or below 0 dB → Kill

If you're at 0 dB (or below) on a band and you double-flick LEFT:
- The action is "kill" (go to -∞ for bass, -19 dB for mid/high)
- The band ramps from 0 dB → kill target
- You went from neutral → silence

This is the "I want to cut this frequency band out" gesture.

### Why the same gesture does both

In a live performance context, the gesture you do is "pull this back."
Whether that means "back to neutral" or "back to silence" depends on
where you are.

A DJ thinking about an EQ doesn't think "kill" and "normalize" as two
separate operations. They think "cut this." The system figures out
what "cut this" musically means based on the current state.

### The 0.5 dB tolerance

The check uses `value > EQ_NEUTRAL + 0.5` to decide normalize vs kill.
The 0.5 dB tolerance prevents the action from misfiring when the value
has drifted slightly above or below exactly 0 dB. Without it, being at
+0.1 dB (essentially neutral) would normalize instead of kill, which
is musically wrong (the user clearly wants to kill, not adjust by
0.1 dB).

---

## The Asymptotic Boost — Musical Reasoning

The X-axis double-flick RIGHT boosts a band when already at or above 0 dB.
The boost amount is asymptotic:

```
boost = (headroom_remaining) × 0.15
```

Each flick adds 15% of the remaining headroom toward the maximum (+6 dB).

### The math

Starting from 0 dB (macro 107.9):
- Flick 1: headroom = 19.1, boost = 2.87, new value = 110.77 (~+0.9 dB)
- Flick 2: headroom = 16.23, boost = 2.43, new value = 113.20 (~+1.7 dB)
- Flick 3: headroom = 13.80, boost = 2.07, new value = 115.27 (~+2.4 dB)
- ...
- Flick 20: headroom = 1.1, boost = 0.17, new value = 126.07 (~+5.9 dB)

You approach +6 dB but never quite reach it. Each flick adds less than
the previous one.

### Why asymptotic?

**Prevents accidental over-boosting:** A fixed +3 dB boost per flick
would let you reach +6 dB in two flicks. That's too easy to do
accidentally and too easy to damage speakers with.

**Forces graduated thinking:** Each boost requires deliberate effort
and produces less effect than the last. This makes you think about
each boost decision rather than rapidly stacking them.

**Reaches the cap only via encoder:** If you want +6 dB exactly, use
the continuous encoder, not the double-flick. The double-flick boost
is for "a little more, with intention."

### The musical reasoning

In a live performance, you rarely want to "boost to maximum." You want
to "boost a bit more than before." The asymptotic curve matches this
musical intent — each gesture adds a smaller increment, so you can
gradually push toward the limit without overshooting.

---

## Bass Safety — Why It Exists

Low frequencies (below ~200 Hz) carry enormous energy compared to
mid and high frequencies. A small amount of bass at high volume can:

- **Damage subwoofers:** Voice coils are rated for specific power.
  Sustained high-power low frequencies can burn them out.
- **Hurt listeners:** Excessive sub-bass causes physical discomfort,
  nausea, or hearing damage at high SPLs.
- **Cause feedback:** In certain room configurations, boosted bass
  resonates and feeds back, creating runaway low-frequency tones.
- **Trip speaker protection:** Many PA systems have limiters that
  engage on excessive bass, ducking the entire mix.

For these reasons, FX Machine has three layers of bass protection:

### Layer 1: Encoder cap (+2 dB max)

```python
EQ_BASS_BOOST_CAP = 114.0  # macro value ≈ +2 dB
```

The continuous encoder cannot push the LOW band above +2 dB. You can
sweep the stick to the right indefinitely — the value clamps at the
cap. This prevents the "I held the stick too long" mistake.

### Layer 2: Double-flick boost BLOCKED

When the LOW band is at or above 0 dB and you double-flick RIGHT, the
action is REJECTED. The status line shows "🚫 Bass boost blocked (use
stick for safe +2 dB)."

This prevents the "I wanted to boost mid but my gesture went to the
wrong band" mistake from accidentally boosting bass.

### Layer 3: Double-flick LEFT goes to -∞

When you double-flick LEFT to kill the bass, it goes to full silence
(-∞ dB), not the -19 dB used for mid/high. Bass cuts in DJ-style
performance are EXPECTED to be absolute. A partial bass cut sounds
weak and unprofessional.

### Why these specific limits

The +2 dB cap was chosen because:
- It allows musical emphasis (a noticeable bass boost)
- It stays well below dangerous SPL levels
- It matches real-world DJ mixer EQ behavior (Pioneer's bass boost
  curves are gentle)

If you really need more bass boost (e.g., for studio work or quiet
home use), you can raise the cap in `config/active.toml`:

```toml
[eq.safety]
bass_boost_cap = 120.0   # ≈ +4 dB
```

But for live performance, leave it at the default. Your audience's
ears (and your speakers) will thank you.

---

## Filter Lock and Wet Lock — Creative Use

Two modifier toggles change how L1 release works:

### Filter Lock (L1+L3)

When OFF (default): On L1 release, Filter Freq returns to baseline (the
default open position).

When ON: On L1 release, Filter Freq stays where you left it.

**Use case:** You've swept the filter down to a specific point for a
section. You want that filter setting to persist as the new baseline
for the next 16 bars while you do other things. Toggle filter lock ON,
release L1, the filter stays. The filter is now your "set" position
until you sweep it again.

### Wet Lock (L1+R3)

When OFF (default): On L1 release, FX Send drops to 0 (wet effects
silenced).

When ON: On L1 release, FX Send stays where you set it.

**Use case:** You want a constant wet bath throughout a breakdown.
Set FX Send to some moderate level (e.g., 50%). Toggle wet lock ON.
Release L1. The wet send stays at 50% — every sound played gets
processed by the wet chain. No need to hold throws or constantly
manage the send level.

### Combined locks

Both locks ON means both Filter Freq AND FX Send stay where you left
them on L1 release. The only thing that resets is Stutter (always
goes to 0 on release).

This effectively turns FX Machine into a "set and forget" mode where
the L1 button just opens the controls without changing the underlying
sound on release.

### When to NOT use locks

In conventional DJ use, you want predictable behavior: pressing L1,
making adjustments, releasing L1, and KNOWING the sound returns to
your baseline state. Locks override this safety, which can lead to
"why is the sound still filtered?" confusion.

Use locks deliberately for specific sections, then turn them off when
done. Don't leave them on by default.

---

## Common Signal Chain Variations

The standard FX Machine signal chain is one of many possible
configurations. Here are some musically valid variations:

### Variation 1: Echo instead of Long Digi Delay

Replace the Delay device in the Wet chain with Echo (Ableton 11+).
Echo has analog character, saturation, and modulation that creates
a more vintage tape-echo sound. Map Echo's Feedback parameter to the
Delay FB macro.

### Variation 2: Hybrid Reverb instead of Reverb

Replace the Reverb with Hybrid Reverb (Ableton 11+). Hybrid Reverb
uses convolution + algorithmic processing for more realistic spaces.
Map Hybrid Reverb's Size parameter to the Reverb Size macro.

### Variation 3: Add a phaser to the Wet chain

Insert a Phaser device between the Reverb and Delay in the Wet chain.
The phaser will add subtle modulation to the wet tails, creating more
movement and complexity in the atmospheric wash.

You'd need to add another macro to control the Phaser (or just set it
to a fixed depth and leave it).

### Variation 4: Multi-band compressor in the outer chain

Insert a Multiband Dynamics device at the end of the outer chain
(before the Width Utility). This master-buses the combined dry+wet
output. Useful for stage volume control or to tame extreme wet bursts.

### Variation 5: Saturator in the EQ chain

Insert a Saturator between the Utility (TRIM) and EQ Three in the EQ
rack. This adds analog-style harmonic saturation to the signal before
EQ. Gives everything a more "warm" character.

### Variation 6: Drop the Stutter

If you don't use Beat Repeat, remove it from the outer chain. Reassign
the Stutter macro slot to something else (e.g., a flanger or chorus).

The Stutter macro slot (FX_SLOT_STUTTER = 3) is hardcoded in
`src/config.py` to use Beat Repeat-specific logic. If you change the
device, you may need to adjust the momentary effect code as well.

---

## Alternative Devices and Substitutions

If you don't have certain Ableton devices (e.g., you're on Intro
edition), you can substitute:

### Reverb alternatives

| If you don't have... | Use instead |
|---|---|
| Reverb (Suite/Standard) | Convolution Reverb Pro (Suite only) |
| Reverb | Valhalla VintageVerb (free trial, commercial $$$) |
| Reverb | TAL-Reverb-4 (free) |

### Delay alternatives

| If you don't have... | Use instead |
|---|---|
| Delay | Echo (Ableton 11+) |
| Delay | Filter Delay |
| Delay | Valhalla Delay (commercial $$$) |
| Delay | TAL-Dub-3 (free) |

### Beat Repeat alternative

If you're on Ableton Intro (no Beat Repeat), substitute:
- Audio Effect Rack with a tempo-synced gate (LFO Tool, free)
- Or skip stutter entirely

### Auto Filter alternatives

Auto Filter is in all Ableton editions, so substitution rarely needed.
If you want a different filter character:
- TAL-Filter-2 (free)
- Native Instruments Filter Bank
- u-he Bazille filters (if you own Bazille)

### What about hardware?

You can route the audio through hardware processors via Ableton's
External Audio Effect device. However, hardware adds latency
(typically 5-20ms round-trip) which may affect the throw-and-tail
technique. Stick to software for the wet chain.

---

## Building a Minimal Version

If you want to start simple and add complexity later, here's the
minimum viable FX Machine setup:

### Minimal EQ rack

- Audio Effect Rack
- EQ Three (no Utility/TRIM)
- 3 macros: EQ Low, EQ Mid, EQ High

Skip TRIM. Set the rack's Macro 4 to something unused but keep it named
"Trim" if you want FX Machine to find 4/4 macros. The TRIM band will
show in the UI but won't do anything if not mapped.

### Minimal FX rack

- Audio Effect Rack
- Auto Filter only
- Macros: Filter Freq, Filter Mode, Filter Res

Skip the nested wet/dry rack entirely. No reverb, no delay, no stutter,
no width. Five of the FX macros will be unused (but still named) for
discovery purposes.

### What you lose

- No throw-and-tail technique
- No reverb tails
- No delay tails
- No stutter effect
- No stereo width control

### What you keep

- Filter sweeps (Auto Filter)
- Bass cut momentary (still works on the filter)
- Full EQ kill behavior
- All the navigation features
- The diagnostics layer

This minimal setup is good for learning the system or for very
CPU-constrained machines.

---

## Building an Extended Version

Conversely, you can extend the signal chain with additional effects.
The discovery system finds any 8 named macros, so as long as the names
match, FX Machine doesn't care what device is behind each macro.

### Extension ideas

**Phaser/Chorus on outer chain:** Add modulation to the dry signal.

**Compressor before EQ:** Tighten dynamics before frequency shaping.

**Bit Crusher on outer chain:** Lo-fi character for specific sections.

**Vinyl Distortion on outer chain:** Analog character for whole channel.

**Filter Delay alongside main Delay:** Filtered echoes for variety.

**Convolution Reverb alongside main Reverb:** True space simulation.

**Resonator in the Wet chain:** Adds pitched resonance to atmospheres.

### How to integrate

For each new effect:
1. Decide where it fits in the signal flow (outer path? wet chain?)
2. Add the device to the appropriate rack
3. Map its key parameters to existing or new macros
4. Adjust the FX_SWEEP_SECONDS configuration if needed
5. Test it for CPU impact

Just remember the constraint: only 8 macros total. If you want to add
9th and 10th effects, you'd need to modify FX Machine's code to handle
more macros (changes to `state.py`, the FX engine, and the UI builder).

---

## Gain Staging Throughout the Chain

Proper gain staging is critical for clean audio. FX Machine's signal
chain has multiple gain stages:

```
Source → [TRIM] → [EQ Three] → [Filter] → [Stutter] → [Wet/Dry Rack] → [Width] → Output
            ↑          ↑                                   ↑               ↑
       Input gain  Frequency-      Filter has         Wet/dry sum    Width can
       (-∞ to +9)  dependent gain  pass-through       can exceed     attenuate
                                   gain (0 dB)        unity if wet   wider stereo
                                                      is high
```

### General principles

1. **Set TRIM so the input peaks around -6 to -3 dBFS.** This gives
   you 3-6 dB of headroom for EQ boosts.

2. **EQ adjustments cause gain changes.** Boosting any band increases
   overall level. Cutting reduces level. After major EQ moves, check
   that the output level hasn't drifted too high.

3. **Wet effects can cause overall level increase.** Throwing FX Send
   adds wet signal on top of dry. If both are loud, the sum can clip.
   Set Reverb and Delay output levels conservatively.

4. **The Width Utility can affect perceived loudness.** Width at 200%
   exaggerates stereo content, which sometimes sounds louder.

### When you hear clipping

If you hear distortion (especially during throws or high EQ boosts):

1. Check the Master output meter in Ableton — is it red?
2. If yes, reduce the Master volume in Ableton
3. Or: reduce the TRIM macro by a few dB
4. Or: reduce the output level of devices in the wet chain (Reverb, Delay)

FX Machine doesn't auto-manage gain. You're responsible for ensuring
the signal stays within usable range. The CLIP indicator in the meter
is your warning — heed it.

### The CLIP indicator

The 22-segment LED meter shows real-time level with a 2-stage CLIP
indicator at the top:

- **Yellow CLIP (>+6 dB):** Warning. You're getting hot. Consider
  reducing levels.
- **Red CLIP, flickering (>+9 dB):** Critical. Audio is clipping.
  Reduce levels immediately.

Configure these thresholds in `config/active.toml` if your reference
level differs from the defaults.

---

## Latency Considerations

Audio processing introduces latency. FX Machine's signal chain has
several sources:

### Device latency

| Device | Typical latency |
|---|---|
| Utility | 0 samples (instant) |
| EQ Three | 0 samples |
| Auto Filter | 0 samples |
| Beat Repeat | 0 samples (when inactive) |
| Reverb (Dark Hall) | 64-512 samples depending on quality |
| Delay (Long Digi) | 0 samples (the delay itself is intentional, but no extra latency) |

### Total latency

Most of the chain adds 0 latency. The reverb is the main contributor.
At 48 kHz sample rate:
- 64 samples = ~1.3ms
- 256 samples = ~5.3ms
- 512 samples = ~10.6ms

This is well below human perception threshold (~10-20ms for percussive
sounds). You won't notice it.

### Ableton's PDC (Plugin Delay Compensation)

Ableton automatically compensates for plugin latency by delaying other
tracks to match. This means your FX Machine processed track stays in
sync with unprocessed tracks. No manual intervention needed.

### Wireless/Bluetooth audio

If your audio output is wireless (Bluetooth speakers, AirPods, etc.),
expect 100-200ms of additional latency from the wireless transmission.
This is on top of FX Machine's processing. For live performance,
use WIRED audio output to keep latency low.

### Controller latency

The gamepad → FX Machine → Ableton path adds:
- Gamepad polling: 0-8ms (125 Hz)
- Gesture processing: <1ms
- OSC throttle: 0-15ms
- UDP send: <1ms
- AbletonOSC dispatch: 2-5ms
- Ableton processing: 5-10ms

Total controller → audio latency: 15-40ms. Below perception threshold.

---

## Quality vs CPU Trade-Offs

The default signal chain is moderate CPU. You can dial it up or down:

### Lower CPU (less quality)

- **Reverb:** Set Quality to "Eco" (lower-quality algorithm)
- **Delay:** Use simple Delay instead of Long Digi
- **Beat Repeat:** Disable Pitch (no pitch-shifting)
- **Auto Filter:** Use 12 dB/octave instead of 24
- **Disable diagnostics:** Set `[diagnostics] enabled = false`

CPU impact reduction: ~30-50%

### Higher CPU (better quality)

- **Reverb:** Set Quality to "High" (more reflections, better diffusion)
- **Use Hybrid Reverb** instead of Reverb (more realistic spaces)
- **Use Convolution Reverb Pro** for impulse-response based reverbs
- **Increase Reverb Decay Time** (longer tails = more processing)
- **Use Echo instead of Delay** (analog modeling, more CPU)

CPU impact increase: ~50-200%

### Real-world numbers

On a 2017 i5-7300HQ laptop (the development hardware), the default
FX Machine signal chain uses ~5-8% CPU during active processing
(audio playing, throws happening). The diagnostics layer adds 1-2%.

Total system load (Ableton + FX Machine + diagnostics) typically
sits at 35-50% on this hardware with a normal session running.

For modern hardware (2020+ CPUs), expect much lower percentages.

---

## Why This Specific Approach Wins

After all this design discussion, here's the summary of why FX Machine's
signal chain works the way it does:

### 1. It matches the standard

DJ-mixer-style EQ + FX is the standard for live electronic music
performance. Performers expect this exact signal flow. Audiences
expect the sounds it produces. FX Machine doesn't reinvent — it
replicates a well-understood workflow.

### 2. It enables the throw-and-tail technique

The single most important DJ effect technique — throw a wet swell,
let it tail under clean playing — requires the specific nested wet/dry
rack architecture. Without this, FX Machine would be just a parameter
controller. With it, FX Machine is a live performance instrument.

### 3. It maintains musical integrity

EQ before FX, TRIM before EQ, filter on the outer path, width at the
end. Every device placement is justified by what it does to the
audio musically. Nothing is arbitrary.

### 4. It's CPU-efficient

The default chain uses common Ableton devices that ship with all
editions. CPU load is modest. The architecture doesn't require
expensive third-party plugins to work.

### 5. It's extensible

You can swap devices, add new ones, change the wet chain composition.
The framework supports variations without code changes (as long as
you keep the 8 macro names).

### 6. It's safe

Bass safety prevents speaker damage and listener discomfort. CLIP
indicators warn before audio gets too hot. The wet/dry architecture
prevents wet effects from contaminating the dry signal.

### 7. It's hardware-like

The signal chain feels like a real DJ mixer. Knob positions mean
something. Gestures map to musical actions. The behavior matches
performer expectations from physical hardware.

This is the design that makes FX Machine feel like an instrument
instead of a software utility. Understanding it lets you tune and
extend it without breaking what makes it musical.

---

*This document describes the signal chain as designed for FX Machine
v1.0.0. The rack topology is stable and unlikely to change in future
versions. The specific devices and effects can be substituted as long
as the macro naming convention is preserved.*
```
