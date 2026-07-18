# Fixed HD default skin

The only runtime physical holder is:

- `../panel_masters/faceplate_master.png` — **1520 × 1800**, the full 2× faceplate master.
- `faceplate_master_1140x1350.png` — a 75% compact preview derivative for screens below 900 px tall.

The preview downsamples the full holder by exactly 2:1 at the normal 760 × 900 logical canvas. The compact file downsamples to a 570 × 675 laptop-friendly preview.

## Editable physical modules

The holder is assembled from exact-size panel modules in `../placeable_panels/`:

- EQ module: 360 × 1320 at x=40, y=200
- LCD screen module: 1000 × 500 at x=470, y=180
- FX module: 1000 × 650 at x=470, y=760
- Status module: 1440 × 160 at x=40, y=1570

Knob animation uses the pre-rendered 12-position sprite sets in `knob_frames/`. The original generic panels and unused single-cap source images were intentionally removed to keep the skin unambiguous.
