# FX Machine Config Folder

This folder holds all configuration files for FX Machine.

## What's in here

| File | What it does |
|---|---|
| `default.toml` | **Factory template.** Do not edit. This is the safety net. |
| `active.toml` | **Your current settings.** This is the file the app actually reads. Edit this one. |
| `presets/` | **Your saved profiles.** Copy any `.toml` here to keep a snapshot. |
| `EXAMPLES.toml` | Ready-to-copy snippets for common performance styles. |

## How to use this

### First time
On first run, the app creates `active.toml` automatically by copying `default.toml`. You'll find this file appear after launching FX Machine for the first time.

### Adjusting how the system feels
1. Open `active.toml` in any text editor (Notepad, Notepad++, VS Code, etc.)
2. Read the comments — every value is explained in plain English
3. Change a number and save the file
4. In the FX Machine app, press `SELECT + START` on your controller (or click the `⟳ REFRESH` button in the UI)
5. The app reloads your config without restarting

If you break the file (typo, wrong format), the app warns you on reload and **keeps using the previous working values**. Your show is safe.

### Saving a preset
When `active.toml` feels great, save a snapshot:
1. Copy `active.toml` to `presets/` and rename it (e.g., `presets/my_club_set.toml`)
2. Later, copy any preset back to `active.toml` to load it
3. Press `SELECT + START` to apply

### Resetting to factory defaults
1. Delete `active.toml` (or rename it to `active.toml.backup`)
2. Restart the app
3. A fresh `active.toml` will be created from `default.toml`

### Sharing your tuning
Just send someone your `.toml` file. They drop it in their `config/` folder and rename to `active.toml`. They get your exact feel.

## Values that need a restart

Most settings reload instantly (they're marked with `[LIVE]` in the comments). A few system-level settings need a full app restart to take effect (marked with `[RESTART]` in the comments). When you reload and a `[RESTART]` value has changed, the app will tell you in the notification slot.

## Help! I broke something

If the app refuses to start because of a corrupted `active.toml`:
1. Delete or rename `active.toml`
2. Launch the app — it will recreate a fresh one from `default.toml`
3. If `default.toml` is also broken (somehow), the app falls back to hardcoded safety values in the code itself

You can't permanently break the app from a config file. The worst case is a restart.

---

*Made by MIRA / Modulated_OFC for live performance.*