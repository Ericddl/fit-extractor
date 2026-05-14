"""Génération d'un fichier GPX 1.1 à partir des records GPS extraits du FIT.

Stdlib uniquement (`xml.etree.ElementTree`). Pas d'extensions FC/vitesse/cadence
en V1 — la trace seule suffit pour la visualisation cartographique.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
DEFAULT_CREATOR = "fit-extractor"


def _record_value(record: dict, key: str):
    entry = record.get(key)
    if entry is None:
        return None
    value = entry[0] if isinstance(entry, tuple) else entry
    return value


def extract_gps_points(records: list[dict]) -> list[dict]:
    """Filtre les records FIT pour ne garder que les points GPS exploitables.

    Un point est conservé si latitude et longitude sont non-nulles, numériques,
    et dans les plages valides (-90..90, -180..180). Les autres champs (altitude,
    timestamp, heart_rate, speed) sont remontés tels quels quand présents.
    """
    points: list[dict] = []
    for record in records:
        lat_raw = _record_value(record, "position_lat")
        lon_raw = _record_value(record, "position_long")
        if lat_raw is None or lon_raw is None:
            continue
        try:
            lat = float(lat_raw)
            lon = float(lon_raw)
        except (TypeError, ValueError):
            continue
        if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
            continue

        altitude = _record_value(record, "altitude")
        ele = None
        if altitude is not None:
            try:
                ele = float(altitude)
            except (TypeError, ValueError):
                ele = None

        points.append({
            "timestamp": _record_value(record, "timestamp"),
            "lat": lat,
            "lon": lon,
            "ele": ele,
            "heart_rate": _record_value(record, "heart_rate"),
            "speed": _record_value(record, "speed"),
        })
    return points


def has_gps_points(gps_points: list[dict]) -> bool:
    return bool(gps_points)


def format_gpx_time(dt: datetime) -> str:
    """Formate un datetime en ISO 8601 UTC `YYYY-MM-DDTHH:MM:SSZ`.

    Un datetime naive est interprété comme UTC (les timestamps FIT le sont).
    Un datetime tz-aware est converti en UTC.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_gpx(
    gps_points: list[dict],
    track_name: str,
    creator: str = DEFAULT_CREATOR,
) -> str:
    """Construit le XML GPX 1.1 complet à partir des points GPS."""
    gpx = ET.Element(
        "gpx",
        {
            "version": "1.1",
            "creator": creator,
            "xmlns": GPX_NAMESPACE,
        },
    )
    trk = ET.SubElement(gpx, "trk")
    ET.SubElement(trk, "name").text = track_name
    trkseg = ET.SubElement(trk, "trkseg")

    for point in gps_points:
        trkpt = ET.SubElement(
            trkseg,
            "trkpt",
            {"lat": f"{point['lat']:.6f}", "lon": f"{point['lon']:.6f}"},
        )
        ele = point.get("ele")
        if ele is not None:
            ET.SubElement(trkpt, "ele").text = f"{ele:.1f}"
        ts = point.get("timestamp")
        if isinstance(ts, datetime):
            ET.SubElement(trkpt, "time").text = format_gpx_time(ts)

    ET.indent(gpx, space="  ")
    body = ET.tostring(gpx, encoding="unicode")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{body}\n'


def write_gpx_file(gpx_content: str, output_path: Path, force: bool = False) -> None:
    if not gpx_content:
        return
    if output_path.exists() and not force:
        raise FileExistsError(str(output_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(gpx_content, encoding="utf-8")
