# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

`fit-extractor` is a Python CLI that converts `.fit` files (Suunto Spartan Ultra, Garmin Edge) into dense Markdown optimized for copy-pasting into AI coaching tools (ChatGPT, Claude). Output targets a French-speaking athlete archiving workouts in Obsidian.

## CLI Usage (planned)

```bash
python extractor.py <input.fit> [--output path/output.md] [--gps] [--gps-limit N] [--stdout] [--force]
```

Dependencies: `fitparse` only (`pip install fitparse`). Python 3.10+.

## Architecture

Single-file implementation (`extractor.py`) with this data flow:

```
.fit / .fit.gz → decompress in memory → fitparse + StandardUnitsDataProcessor
→ extract all message types (session, lap, record, hrv, device_info, user_profile, zones_target)
→ detect hardware (Suunto vs Garmin via manufacturer field)
→ render conditional Markdown sections → write file or stdout
```

Core functions:
- `parse_fit()` — generic extraction iterating all fields (never hardcode field lists)
- `detect_device()` — reads `device_info.manufacturer` to activate device-specific sections
- `compute_hrv()` — calculates RMSSD and SDNN from raw RR intervals
- `format_markdown()` — assembles output with conditional sections
- `main()` — argparse CLI orchestration

## Invariants (never break these)

- **Always pass `StandardUnitsDataProcessor()`** to fitparse — converts speeds to km/h, distances to meters, altitudes to meters
- **Extract generically** — iterate all fields per message, don't hardcode field names (forward-compatibility)
- **Skip `unknown_XXX` fields** — proprietary undocumented fields, noise for AI coaching
- **HRV: output RMSSD and SDNN only** — raw RR intervals can exceed 10k points, overflowing AI context
- **`None` → `"-"`** — missing data is extremely common across hardware; always fallback gracefully
- **Never write `.fit` to disk** — decompress `.fit.gz` in memory only
- **Refuse to overwrite** without `--force` flag
- **All labels in French** — section titles and metric names

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
