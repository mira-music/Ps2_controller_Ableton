# HD default skin assets

These are the first runnable **2× skin assets** for the fixed 760 × 900 logical UI canvas. They must remain pixel-exact:

| Asset | HD source pixels | Logical display size |
|---|---:|---:|
| `faceplate_1520x1800.png` | 1520 × 1800 | 760 × 900 |
| `eq_channel_400x1000.png` | 400 × 1000 | 200 × 500 |
| `session_lcd_bezel_1000x500.png` | 1000 × 500 | 500 × 250 |
| `fx_module_1440x480.png` | 1440 × 480 | 720 × 240 |
| `eq_knob_164x164.png` | 164 × 164 | 82 × 82 |
| `fx_knob_112x112.png` | 112 × 112 | 56 × 56 |

The application will downsample these by exactly 2:1 with Tkinter. That preserves sharp edges without arbitrary runtime image scaling.

The outer faceplate, panel recesses, bezel, and knob cap are visual materials only. Dynamic values, knob indicators, meter segments, LCD text, and safety/connection states remain code-rendered above them.
