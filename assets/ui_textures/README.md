# FX Machine texture kit — source masters

These are the first visual-source assets for the hardware UI redesign. They are **not integrated into the running application yet**. They establish the editable physical materials and module proportions before any texture is wired into Tkinter or the future Qt UI.

## Source files

| File | Native size | Intended use |
|---|---:|---|
| `ui_pngs/panel_masters/faceplate_master.png (1520 × 1800 assembled holder)` | 1122 × 1402 | Overall hardware-front-panel composition and material reference. |
| `ui_pngs/placeable_panels/ (see README.md)` | 793 × 1983 | EQ channel: left meter bay, top clip lens, and one vertical TRIM/HIGH/MID/LOW knob column. |
| `ui_pngs/placeable_panels/ (see README.md)` | 1774 × 887 | Recessed Session Navigator LCD bezel and screen texture. |
| `ui_pngs/placeable_panels/ (see README.md)` | 1536 × 1024 | Eight-control FX module, arranged as a 4 × 2 knob matrix. |

## Editing contract

Please edit a **copy** of a master and preserve its exact pixel dimensions and its PNG format. Send the edited file back using the same filename where possible.

Keep these areas clear because FX Machine will draw live information over them:

- **EQ channel:** the four circular wells receive animated knob graphics; the left slot receives the live LED meter; the red top lens receives the live CLIP state.
- **LCD bezel:** the dark inner screen receives track, scene, clip, bookmark, group, volume, and mode text.
- **FX module:** the eight circular wells receive live macro knob graphics; the header and footer strips receive labels/value readouts.
- **Faceplate master:** this is a visual/layout reference. It is not intended to be a single fixed-size application background because the window can resize.

## Recommended edits

Good edits include: material colour, brushed-metal direction/intensity, corner screws, bevel depth, engraved tick marks, panel seams, and restrained wear.

Avoid baking in labels, numeric values, LEDs, knob caps, or controller states. Those must remain live and be rendered by the app.

## Integration approach

When the edited masters return, the implementation will use individual assets—not one large screenshot-like background—so the UI remains readable and can resize:

1. faceplate material/texture as the base surface;
2. EQ strip, LCD bezel, and FX module as independent panel assets;
3. code-rendered dynamic widgets layered above their designated recesses.

This keeps the real-time meter, all values, selected-band indication, momentary FX states, and navigation data functional.
