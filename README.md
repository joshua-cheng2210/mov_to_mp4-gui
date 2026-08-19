# MOV to MP4 Converter

A desktop tool for batch-converting `.MOV` files to `.MP4`, built for processing phone/camera footage before posting. Drop in files, convert several at once, watch per-file progress in a GUI — no command line needed for day-to-day use.

## Features

- **GUI file picker** (Tkinter) — add one or many `.MOV` files, see queued/converting/finished/failed status per file with a live progress bar
- **Parallel conversion** — a bounded worker pool runs multiple `ffmpeg` processes at once (configurable, default 5), with per-file thread counts balanced against your CPU core count to avoid oversubscription
- **Automatic retry-friendly UI** — failed conversions show the ffmpeg error inline and stay queued for a one-click retry without re-adding files
- **Self-installing launcher** — `Convert_MOV_to_MP4.bat` checks for and installs the required `imageio-ffmpeg` package on first run, then launches the GUI
- **Live dual logging** — every run's output streams to the console *and* `mov_to_mp4.log` simultaneously, with automatic log rotation (trims to the last 2000 lines once the file passes 1MB, so it never grows unbounded)

## Requirements

- Python 3 with `tkinter` (included in standard Windows Python installs)
- `ffmpeg` — either already on your `PATH`, or the `imageio-ffmpeg` package (auto-installed by the launcher, which bundles its own `ffmpeg` binary)

## Usage

**Easiest:** double-click `Convert_MOV_to_MP4.bat`. It installs dependencies if needed and opens the GUI.

**Manual:**
```
python mov_to_mp4.py
```

Each converted file is saved as `.mp4` in the same folder as the original (auto-numbered if a file with that name already exists), using H.264 video + AAC audio with `faststart` enabled for fast web/mobile playback.

## Project structure

| File | Purpose |
|---|---|
| `mov_to_mp4.py` | The converter — GUI, worker pool, ffmpeg orchestration, progress parsing |
| `Convert_MOV_to_MP4.bat` | Double-click launcher — dependency check, live console + file logging with rotation |
| `mov_to_mp4.log` | Generated at runtime — rolling log of each run (auto-trimmed, not committed) |

## Logging design

The launcher relaunches itself as a subprocess so its combined stdout/stderr can be piped through PowerShell's `Tee-Object`, which writes to `mov_to_mp4.log` *and* passes output through to the console at the same time. Before each run, the log is checked and trimmed to its last 2000 lines if it's grown past 1MB, keeping recent history without unbounded growth.

---

## MOV to MP4 Converter

- Built a MOV→MP4 batch conversion tool with a Tkinter GUI and multithreaded ffmpeg pipeline (worker pool + per-file progress tracking), wrapped in a self-installing Windows launcher with live console/file logging and automatic log rotation.
- Diagnosed and fixed a process-isolation bug in the Windows batch launcher where piping into a subroutine call silently failed across process boundaries; redesigned it as a self-relaunching script with dual console/file logging (PowerShell `Tee-Object`) and size-based log rotation.
- Designed a cross-process logging system (batch + PowerShell) enabling live console output and persistent log capture with automatic rotation to prevent unbounded file growth.
