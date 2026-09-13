"""Calculs sportifs purs à partir des champs FIT normalisés, sans accès disque."""

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import median


def finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def field_value(fields: dict, key: str):
    entry = fields.get(key)
    return entry[0] if entry is not None else None


def numeric_field(fields: dict, key: str, unit: str | None = None):
    entry = fields.get(key)
    if entry is None or not finite_number(entry[0]):
        return None
    value, source_unit = entry
    if unit is None or source_unit == unit:
        return float(value)
    factors = {
        ("km", "m"): 1000, ("m", "km"): 0.001,
        ("m/s", "km/h"): 3.6, ("m/s", "m/h"): 3600,
        ("km/h", "m/h"): 1000,
    }
    factor = factors.get((source_unit, unit))
    return value * factor if factor is not None else None


def preferred_number(fields: dict, key: str, unit: str):
    enhanced = numeric_field(fields, f"enhanced_{key}", unit)
    return enhanced if enhanced is not None else numeric_field(fields, key, unit)


def activity_speed(fields: dict):
    distance = numeric_field(fields, "total_distance", "m")
    duration = numeric_field(fields, "total_timer_time", "s")
    if distance is not None and distance > 0 and duration is not None and duration > 0:
        return distance / duration * 3.6
    for key in ("enhanced_avg_speed", "avg_speed"):
        speed = numeric_field(fields, key, "km/h")
        if speed is not None and speed >= 0:
            return speed
    return None


@dataclass
class Sample:
    timestamp: float | None
    distance: float | None
    altitude: float | None
    heart_rate: float | None
    gps: bool
    smoothed_altitude: float | None = None


def _sample(record: dict) -> Sample:
    timestamp = field_value(record, "timestamp")
    if isinstance(timestamp, datetime):
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.timestamp()
    else:
        timestamp = None
    distance = numeric_field(record, "distance", "m")
    if distance is not None and distance < 0:
        distance = None
    heart_rate = numeric_field(record, "heart_rate", "bpm")
    if heart_rate is not None and heart_rate <= 0:
        heart_rate = None
    latitude = numeric_field(record, "position_lat", "deg")
    longitude = numeric_field(record, "position_long", "deg")
    gps = (latitude is not None and longitude is not None
           and -90 <= latitude <= 90 and -180 <= longitude <= 180)
    return Sample(timestamp, distance, preferred_number(record, "altitude", "m"), heart_rate, gps)


def _valid_interval(first: Sample, second: Sample, gap_limit: float) -> bool:
    return (
        first.timestamp is not None and second.timestamp is not None
        and 0 < second.timestamp - first.timestamp <= gap_limit
        and first.distance is not None and second.distance is not None
        and second.distance >= first.distance
    )


def _altitude_runs(samples: list[Sample], gap_limit: float) -> list[list[Sample]]:
    runs = []
    current = []
    for sample in samples:
        if sample.altitude is None or sample.distance is None or sample.timestamp is None:
            if current:
                runs.append(current)
            current = []
            continue
        if current and not _valid_interval(current[-1], sample, gap_limit):
            runs.append(current)
            current = []
        current.append(sample)
    if current:
        runs.append(current)
    for run in runs:
        for index, sample in enumerate(run):
            window = run[max(0, index - 2):index + 3]
            sample.smoothed_altitude = median(point.altitude for point in window)
    return runs


def _empty_bin(start: float, end: float) -> dict:
    return {
        "start": start, "end": end, "distance": end - start,
        "covered": 0.0, "seconds": 0.0, "hr_seconds": 0.0, "hr_integral": 0.0,
        "ascent": 0.0, "descent": 0.0, "altitude_covered": 0.0, "broken": False,
    }


def _accumulate(row: dict, first: Sample, second: Sample, lower: float, upper: float) -> None:
    duration = (second.timestamp - first.timestamp) * (upper - lower)
    distance = (second.distance - first.distance) * (upper - lower)
    row["seconds"] += duration
    row["covered"] += distance
    if first.heart_rate is not None and second.heart_rate is not None:
        change = second.heart_rate - first.heart_rate
        mean_hr = first.heart_rate + change * (lower + upper) / 2
        row["hr_integral"] += mean_hr * duration
        row["hr_seconds"] += duration
    if first.smoothed_altitude is not None and second.smoothed_altitude is not None:
        elevation = (second.smoothed_altitude - first.smoothed_altitude) * (upper - lower)
        if distance > 0:
            row["ascent"] += max(0, elevation)
            row["descent"] += max(0, -elevation)
            row["altitude_covered"] += distance


def _distance_bins(samples: list[Sample], gap_limit: float, width: float, origin: float, end: float) -> list:
    count = max(0, math.ceil((end - origin) / width - 1e-10))
    rows = [_empty_bin(origin + index * width, min(end, origin + (index + 1) * width))
            for index in range(count)]
    for first, second in zip(samples, samples[1:]):
        if not _valid_interval(first, second, gap_limit):
            uncertain_time = (first.distance is None or second.distance is None
                              or first.distance == second.distance)
            for sample in (first, second) if uncertain_time else ():
                if sample.distance is not None and rows:
                    index = min(count - 1, max(0, math.floor((sample.distance - origin) / width)))
                    rows[index]["broken"] = True
            continue
        traveled = second.distance - first.distance
        if traveled == 0:
            if rows:
                index = min(count - 1, max(0, math.floor((first.distance - origin) / width)))
                _accumulate(rows[index], first, second, 0, 1)
            continue
        start_index = max(0, math.floor((first.distance - origin) / width))
        stop_index = min(count, math.ceil((second.distance - origin) / width))
        for index in range(start_index, stop_index):
            row = rows[index]
            lower = max(first.distance, row["start"])
            upper = min(second.distance, row["end"])
            if upper > lower:
                _accumulate(row, first, second,
                            (lower - first.distance) / traveled, (upper - first.distance) / traveled)
    for row in rows:
        row["complete"] = not row["broken"] and math.isclose(row["covered"], row["distance"], abs_tol=1e-5)
        row["altitude_complete"] = math.isclose(row["altitude_covered"], row["distance"], abs_tol=1e-5)
        row["heart_rate"] = row["hr_integral"] / row["hr_seconds"] if row["hr_seconds"] else None
    return rows


def analyze_records(records: list[dict], sport: str) -> dict:
    """Analyse la couverture et les portions continues, sans interpoler les interruptions."""
    samples = [_sample(record) for record in records]
    positive_intervals = [second.timestamp - first.timestamp
                          for first, second in zip(samples, samples[1:])
                          if first.timestamp is not None and second.timestamp is not None
                          and second.timestamp > first.timestamp]
    gap_limit = max(10, 5 * median(positive_intervals)) if positive_intervals else 10
    gaps = [interval for interval in positive_intervals if interval > gap_limit]
    times = [sample.timestamp for sample in samples if sample.timestamp is not None]
    distances = [sample.distance for sample in samples if sample.distance is not None]
    backwards = sum(second < first for first, second in zip(times, times[1:]))
    regressions = sum(second < first for first, second in zip(distances, distances[1:]))
    quality = {
        "records": len(samples), "heart_rate": sum(sample.heart_rate is not None for sample in samples),
        "gps": sum(sample.gps for sample in samples), "altitude": sum(sample.altitude is not None for sample in samples),
        "missing_time": len(samples) - len(times), "missing_distance": len(samples) - len(distances),
        "non_increasing_time": sum(second <= first for first, second in zip(times, times[1:])),
        "backwards_time": backwards, "distance_regressions": regressions,
        "gap_limit": gap_limit, "gaps": len(gaps), "largest_gap": max(gaps, default=0),
    }
    runs = _altitude_runs(samples, gap_limit)
    result = {"quality": quality, "kilometers": [], "kilometer_reason": None,
              "terrain": {}, "terrain_distance": 0.0,
              "altitudes": [sample.altitude for sample in samples if sample.altitude is not None]}
    if sport == "running":
        if backwards or regressions:
            result["kilometer_reason"] = "chronologie ou distance cumulée non monotone"
        elif len(distances) < 2 or distances[-1] <= distances[0]:
            result["kilometer_reason"] = "distance cumulée insuffisante"
        elif len(times) < 2:
            result["kilometer_reason"] = "horodatages insuffisants"
        else:
            origin = math.floor(distances[0] / 1000) * 1000
            if (distances[-1] - origin) / 1000 > 10000:
                result["kilometer_reason"] = "distance cumulée excessive (plus de 10 000 kilomètres)"
            else:
                result["kilometers"] = _distance_bins(samples, gap_limit, 1000, origin, distances[-1])
    if sport in {"running", "cycling"}:
        terrain = {name: _empty_bin(0, 0) for name in ("Montée", "Plat", "Descente")}
        for run in runs:
            if len(run) < 2 or run[-1].distance - run[0].distance < 50:
                continue
            if run[-1].distance - run[0].distance > 10000000:
                continue
            for row in _distance_bins(run, gap_limit, 50, run[0].distance, run[-1].distance):
                if (not row["complete"] or not row["altitude_complete"]
                        or not math.isclose(row["distance"], 50, abs_tol=1e-6) or row["seconds"] <= 0):
                    continue
                slope = (row["ascent"] - row["descent"]) / row["distance"]
                name = "Montée" if slope > 0.03 + 1e-9 else "Descente" if slope < -0.03 - 1e-9 else "Plat"
                target = terrain[name]
                target["distance"] += row["distance"]
                for key in ("seconds", "hr_seconds", "hr_integral"):
                    target[key] += row[key]
        for name, row in terrain.items():
            if row["distance"]:
                row["heart_rate"] = row["hr_integral"] / row["hr_seconds"] if row["hr_seconds"] else None
                result["terrain"][name] = row
                result["terrain_distance"] += row["distance"]
    return result
