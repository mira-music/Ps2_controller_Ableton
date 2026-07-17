# Overlay asset index

The original contact sheets are retained under `contact_sheets/`. Their elements are also exported as separate files so they can be placed directly in Photoshop.

## Paper labels

`paper_labels/` contains blank torn-label pieces: large, round, wide, long-strip, thin-strip, folded, and several fragments.

## Music stickers

`music_stickers/` contains one PNG each for: waveform, cassette, turntable, patch grid, audio jack, equalizer, transport arrows, vinyl record, speaker stack, fader bank, red waveform, and LED matrix.

## Tape

- `tape/blank/` contains individual masking, gaffer, translucent, and foil repair pieces.
- `tape/marked/` contains the first exact-name hand-marker labels: `FX MACHINE` and `MODULATED`.

## Damage

`damage/hardware_wear_overlay.png` is intentionally a full sparse overlay. It is best used at low opacity over a panel rather than cut into isolated stickers.

### Transparency note

The generated images use a black working background rather than an alpha channel. In Photoshop, use **Select → Color Range** on the black background and create a layer mask before placing an element. For dark gaffer tape, use the outline/edge selection or a blend mode rather than selecting all black pixels.
