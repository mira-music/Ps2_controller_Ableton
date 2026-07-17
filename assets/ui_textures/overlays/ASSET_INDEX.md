# Overlay asset index

Every file outside `contact_sheets/` contains **one complete centred element only**. The contact sheets are retained as source/reference material and are not intended for direct placement.

## Paper labels — `paper_labels/`

Six complete, pre-aged blank paper elements:

- `label_large.png`
- `label_round.png`
- `label_strip_long.png`
- `label_strip_thin.png`
- `label_wide.png`
- `label_folded.png`

Each includes light fibre, crease, and wear detail while keeping an empty area for a custom Photoshop label.

## Music stickers — `music_stickers/`

Eight complete, pre-aged stickers:

- cassette
- equalizer
- fader bank
- patch grid
- speaker stack
- turntable
- vinyl record
- waveform

They use distressed ink, faded colour, scuffed edges, and worn paper outlines. They are original generic music graphics, with no third-party logos or artist artwork.

## Tape — `tape/`

### Blank — `tape/blank/`

- `masking_tape_wide.png`
- `gaffer_tape_strip.png`
- `foil_repair_patch.png`

### Marked — `tape/marked/`

- `fx_machine_marker_tape.png`
- `modulated_marker_tape.png`

The marked tape labels have the requested handwritten text. All tape assets include realistic creases, torn edges, and light age/wear.

## Damage — `damage/`

`hardware_wear_overlay.png` is a sparse, full-panel wear overlay. It is intentionally not split because its scratches, prints, and scuffs are designed to be composited together at low opacity.

## Photoshop masking

The generated working assets use a black background rather than an alpha channel. Use **Select → Color Range** on black to create a layer mask. For the dark gaffer tape, select its outer edge or use a suitable blend mode instead of removing all black pixels.
