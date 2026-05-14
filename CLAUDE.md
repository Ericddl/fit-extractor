# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`fit-extractor` is a Python CLI that converts `.fit` files (Suunto Spartan Ultra, Garmin Edge) into dense Markdown optimized for copy-pasting into AI coaching tools (ChatGPT, Claude). Output targets a French-speaking athlete archiving workouts in Obsidian.

## CLI Usage

```bash
python extractor.py <input.fit> [--output path/output.md] [--gps] [--gps-limit N] [--stdout] [--force]
```

A bare filename is resolved from `import/`. By default the `.md` lands in `export/` under `YYYY-MM-DD_<sport>_<index>.md`, a `.gpx` (GPX 1.1 — trace complète) is generated next to it if the FIT contains GPS points, and the source `.fit`/`.fit.gz` is moved into `export/` with the same basename after success.

Dependencies: `fitparse` only (`pip install fitparse`). Python 3.10+.

## Architecture

Three modules: `extractor.py` (parsing + Markdown formatting + CLI orchestration), `file_manager.py` (paths, naming, archival), and `gpx_exporter.py` (GPS extraction + GPX 1.1 generation).

Data flow:

```
import/file.fit(.gz) → resolve_input_path → decompress in memory →
fitparse + StandardUnitsDataProcessor → extract all message types →
detect hardware (Suunto vs Garmin) → plan_output_paths (build basename, find next index) →
render conditional Markdown → write export/<basename>.md →
extract_gps_points → if any: build_gpx + write export/<basename>.gpx →
move source .fit to export/<basename>.fit(.gz)
```

Core functions in `extractor.py`:
- `parse_fit()` — generic extraction iterating all fields (never hardcode field lists)
- `detect_device()` — reads `device_info.manufacturer` to activate device-specific sections
- `compute_hrv()` — calculates RMSSD and SDNN from raw RR intervals
- `format_markdown()` — assembles output with conditional sections
- `main()` — argparse CLI orchestration

Core functions in `file_manager.py`:
- `ensure_workdirs()` — creates `import/` and `export/`
- `resolve_input_path()` — resolves bare filenames against `import/`
- `plan_output_paths()` — builds `export/<YYYY-MM-DD>_<activity>_<index>.md` with auto-increment (scans `.md`, `.fit`, `.fit.gz`, `.gpx`)
- `move_processed_fit()` — moves source `.fit`/`.fit.gz` next to the `.md`, preserves `.fit.gz` compound suffix

Core functions in `gpx_exporter.py`:
- `extract_gps_points()` — filters records to valid lat/lon entries, normalises to a list of `{timestamp, lat, lon, ele, heart_rate, speed}` dicts
- `has_gps_points()` — boolean check on the filtered list
- `format_gpx_time()` — datetime → ISO 8601 UTC with `Z` suffix
- `build_gpx()` — GPX 1.1 XML via `xml.etree.ElementTree`, `<trk>`/`<trkseg>`/`<trkpt>` with `<ele>` and `<time>` when available
- `write_gpx_file()` — refuses overwrite without `force=True`, no-op on empty content

## Invariants (never break these)

- **Always pass `StandardUnitsDataProcessor()`** to fitparse — converts speeds to km/h, distances to meters, altitudes to meters
- **Extract generically** — iterate all fields per message, don't hardcode field names (forward-compatibility)
- **Skip `unknown_XXX` fields** — proprietary undocumented fields, noise for AI coaching
- **HRV: output RMSSD and SDNN only** — raw RR intervals can exceed 10k points, overflowing AI context
- **`None` → `"-"`** — missing data is extremely common across hardware; always fallback gracefully
- **Never write a decompressed `.fit` to disk** — `.fit.gz` is decompressed in memory only (the archive move preserves `.fit.gz`)
- **Refuse to overwrite `.md` via `--output`** without `--force` flag. In auto mode, the index auto-increments so no `--force` needed.
- **All labels in French** — section titles and metric names
- **All file-path / naming / archival logic lives in `file_manager.py`** — keep `extractor.py` focused on parsing + formatting + orchestration
- **All GPS-extraction / GPX-building logic lives in `gpx_exporter.py`** — keep `extractor.py` thin
- **Default I/O is `import/` → `export/`** — never write `.md` next to the source `.fit` by default
- **`.fit.gz` detection** uses `name.lower().endswith(".fit.gz")`, not `Path.suffix` (which only sees `.gz`)
- **Source `.fit` move only after successful `.md` write** — never leave the source half-processed
- **GPX uses stdlib `xml.etree.ElementTree`** — never add `gpxpy` or any other GPX dependency
- **GPX V1 contains only lat/lon/ele/time** — no FC, cadence, speed, power; those stay in Markdown
- **Never generate an empty `.gpx`** — if no exploitable GPS points, print explicit stderr message and skip the file
- **`--gps-limit` only affects the Markdown GPS section** — the `.gpx` always carries the full track
- **GPX shares the basename of `.md` and `.fit`** — derived via `md_path.with_suffix(".gpx")`

## Hardware-Specific Sections

Sections only appear when the relevant data exists:

| Section | Suunto Spartan Ultra | Garmin Edge |
|---|---|---|
| HRV (RMSSD/SDNN) | ✓ | ✗ |
| Developer fields (`feeling`, `recovery_time`, `peak_epoc`, `ddfa`, zone times) | ✓ | ✗ |
| User profile (age, weight, resting/max HR) | ✗ | ✓ |
| Target zones (FTP, HR threshold) | ✗ | ✓ |
| Running cadence / strides | ✓ | ✗ |
| VAM | ✗ | ✓ |

## Spec

Full technical specification (decision rationale, output schema, known limitations): `docs/SPEC.md`.
