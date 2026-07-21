# FX Machine UI conception — module-first rebuild

The previous assembled preview remains available as a reference only. New UI work happens here as independent module previews so geometry is approved before modules are combined.

## Rules

1. Each preview is standalone: no Ableton, OSC, pygame, controller, or app-state dependency.
2. Each module has one fixed logical design size and a documented coordinate map.
3. No texture is stretched. A future texture must be created for the approved module dimensions.
4. A module is not added to the assembled faceplate until its spacing, text hierarchy, sockets, and active states are approved.

## Module order

1. **EQ channel strip** — current work
2. Session Navigator LCD
3. FX control matrix
4. Header / transport + status strip
5. Final faceplate assembly

Run the first concept preview:

```bat
python ui_concept\preview_eq_module.py
```

Keyboard controls:

- `E`: cycle selected EQ band
- `C`: toggle CLIP warning
- `Space`: toggle simulated signal activity
- `Esc`: close

## Retro monitor model

A separate all-pixel, single-monitor model is now available. It does not reuse
any panel textures or hardware-module layout:

```bat
python ui_concept\preview_retro_monitor.py
```

It renders every interface element inside a 160 × 120 virtual CRT grid at an
integer 4× scale. `E`, `F`, `C`, and `Space` cycle EQ focus, FX focus, CLIP,
and transport state respectively.
