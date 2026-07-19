# EQ meter LED sprites

Each sprite is 80×44 px and displays at 40×22 logical pixels in the standalone EQ module.

For each zone there are two RGBA textures:

- `*_off.png` — recessed, colour-tinted unlit lens
- `*_on.png` — physical lens plus a blurred alpha glow, top highlight, and lower shadow

The meter does **not** need a unique texture for each of its 22 positions. It instances one of these six state sprites into every physical meter slot:

- green: safe signal
- yellow: high signal
- red: overload / CLIP zone

This keeps the meter authentic, efficient, and configurable.
