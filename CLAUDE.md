# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`fit-extractor` is a Python CLI that converts `.fit` files (Suunto Spartan Ultra, Garmin Edge) into dense Markdown optimized for copy-pasting into AI coaching tools (ChatGPT, Claude). Output targets a French-speaking athlete archiving workouts and pushing this workouts to a AI (chatGPT or Claude) in order to prepare sports events.

## CLI Usage

```bash
python extractor.py <input.fit> [--output path/output.md] [--gps] [--gps-limit N] [--stdout] [--details] [--force]
```

A bare filename is resolved from `import/`. By default the `.md` lands in `export/` under `YYYY-MM-DD_<sport>_<index>.md`, a `.gpx` (GPX 1.1 — trace complète) is generated next to it if the FIT contains GPS points, and the source `.fit`/`.fit.gz` is moved into `export/` with the same basename after success.

Dependencies: `fitparse` only (`pip install fitparse`). Python 3.10+.

`--gps-limit` must be positive (default 30), even without `--gps`; invalid arguments
exit with code 2 before parsing. Processing failures exit with code 1. `--stdout`
creates no directories or exports and never archives the source. Use `python -B`
to also prevent Python bytecode caches.

`--details` adds unrendered session/lap/device fields and record summaries while
keeping the default Markdown unchanged. Numeric series use finite scalar samples:
count/min/max/arithmetic mean, explicitly not time-weighted. Non-numeric series
are counted only; booleans, timestamps, coordinates and raw RR are excluded.
Long field arrays (>16 items) are summarized. Preserve units, escape Markdown cells,
and avoid repeated fields or redundant standard/enhanced variants.

## Architecture

Three modules: `extractor.py` (parsing + Markdown formatting + CLI orchestration), `file_manager.py` (paths, naming, archival), and `gpx_exporter.py` (GPS extraction + GPX 1.1 generation).

Data flow:

```
import/file.fit(.gz) → resolve_input_path → decompress in memory →
fitparse + StandardUnitsDataProcessor → extract fields from selected message types →
detect hardware (Suunto vs Garmin) → plan_output_paths (build basename, find next index) →
render conditional Markdown → extract_gps_points → if any: build_gpx in memory →
export_activity: stage outputs and exact source copy → back up existing outputs →
publish Markdown/GPX/archive → remove source last; restore outputs on handled error
```

Core functions in `extractor.py`:
- `parse_fit()` — generic extraction iterating all fields (never hardcode field lists)
- `detect_device()` — reads `device_info.manufacturer`; sections mostly depend on available data
- `compute_hrv()` — calculates RMSSD and SDNN from raw RR intervals
- `format_markdown()` — assembles output with conditional sections
- `main()` — argparse CLI orchestration

Core functions in `file_manager.py`:
- `ensure_workdirs()` — creates `import/` and `export/`
- `resolve_input_path()` — resolves bare filenames against `import/`
- `plan_output_paths()` — builds `export/<YYYY-MM-DD>_<activity>_<index>.md` with auto-increment (scans `.md`, `.fit`, `.fit.gz`, `.gpx`)
- `plan_archive_path()` — preserves `.fit.gz`, adds `_dupN` on archive collision, detects source already archived
- `export_activity()` — coordinates publication and archival with rollback; used by the CLI
- `move_processed_fit()` — standalone archive helper, not the CLI transaction

Core functions in `gpx_exporter.py`:
- `extract_gps_points()` — filters records to valid lat/lon entries, normalises to a list of `{timestamp, lat, lon, ele, heart_rate, speed}` dicts
- `has_gps_points()` — boolean check on the filtered list
- `format_gpx_time()` — datetime → ISO 8601 UTC with `Z` suffix
- `build_gpx()` — GPX 1.1 XML via `xml.etree.ElementTree`, `<trk>`/`<trkseg>`/`<trkpt>` with `<ele>` and `<time>` when available
- `write_gpx_file()` — standalone GPX writer; the CLI publishes through `export_activity()`

## Invariants (never break these)

- **Always pass `StandardUnitsDataProcessor()`** to fitparse — speeds in km/h, coordinates in degrees; respect field units (`distance` in km, `total_distance` in m)
- **Extract generically within supported message types** — session/lap/record/hrv/device_info/user_profile/zones_target; default rendering is selective, not a full FIT dump
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
- **Remove the source last** — on handled failure restore old outputs and remove new ones, including failures to archive; keep recovery files and report paths if rollback fails
- **No crash/concurrency guarantee** — rollback covers one isolated execution, not power loss or forced termination
- **`--force` never overwrites an archive** — use `_dupN`; remove stale associated GPX when forcing an export without GPS
- **GPX uses stdlib `xml.etree.ElementTree`** — never add `gpxpy` or any other GPX dependency
- **GPX V1 contains only lat/lon/ele/time** — no FC, cadence, speed, power; those stay in Markdown
- **Never generate an empty `.gpx`** — if no exploitable GPS points, print explicit stderr message and skip the file
- **`--gps-limit` only affects the Markdown GPS section** — the `.gpx` always carries the full track
- **GPX shares the Markdown basename** — archive may have `_dupN` on collision

## Validation

No automated test suite or CI is checked in, and there is no `examples/` directory.
Check `python -B extractor.py --help` and `--stdout` with/without `--details` on
appropriate FIT files when available. Exercise writes and injected failures only
with synthetic data or copies in temporary directories (`unittest.mock`, `tempfile`).
Verify byte-for-byte rollback, gzip preservation, collisions and unchanged default
rendering. Report actual checks and limitations; help alone is not a conversion test.

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
