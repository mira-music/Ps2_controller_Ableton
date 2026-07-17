# FX Machine PySide6 UI study

This folder is the **first, non-destructive phase** of the modular retro-hardware UI migration. The production application continues to use `src/ui/` (Tkinter). No controller, OSC, config, or Ableton behavior is changed by this prototype.

## Run the prototype

```bash
python -m pip install PySide6
python -m src.ui_qt.prototype
```

The screen uses simulated meter and macro values only, so it is safe to run without Ableton or a gamepad.

## Design decisions established here

- Matte graphite panels, engraved module labels, calibrated rotary scales.
- Amber means selected/active; green means online; red means unsafe; blue marks wet/connection information.
- Controls are grouped by signal flow rather than a generic dashboard grid.
- Reusable widgets are custom painted with Qt (`AnalogKnob`, `LedMeter`, `MomentaryButton`, `HardwarePanel`, `StatusLed`).

## Next phase

Create a Qt state bridge which snapshots `src.state.state` and `src.state.ableton` under the existing `st._lock` at the UI refresh rate. The bridge must only render snapshots; it must never send OSC while holding the lock.
