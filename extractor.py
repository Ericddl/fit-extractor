#!/usr/bin/env python3
"""fit-extractor — Convert .fit files to AI-coaching Markdown."""

import argparse
import gzip
import io
import math
import sys
from datetime import date, datetime, time
from pathlib import Path

from fitparse import FitFile, StandardUnitsDataProcessor

from activity_analysis import activity_speed, analyze_records, numeric_field, preferred_number
from file_manager import (
    ensure_workdirs,
    export_activity,
    plan_output_paths,
    resolve_input_path,
    IMPORT_DIR,
)
from gpx_exporter import (
    build_gpx,
    extract_gps_points,
    has_gps_points,
)


def parse_fit(path: Path) -> dict:
    raw = path.read_bytes()
    if path.name.lower().endswith(".fit.gz"):
        raw = gzip.decompress(raw)

    fitfile = FitFile(io.BytesIO(raw), data_processor=StandardUnitsDataProcessor())

    def extract_fields(msg):
        result = {}
        for field in msg:
            if field.value is not None and not field.name.startswith("unknown_"):
                result[field.name] = (field.value, field.units)
        return result

    data = {
        "session": {},
        "laps": [],
        "records": [],
        "hrv_intervals": [],
        "device_info": [],
        "user_profile": {},
        "zones_target": {},
    }

    for msg in fitfile.get_messages("session"):
        data["session"].update(extract_fields(msg))

    for msg in fitfile.get_messages("lap"):
        data["laps"].append(extract_fields(msg))

    for msg in fitfile.get_messages("record"):
        data["records"].append(extract_fields(msg))

    for msg in fitfile.get_messages("hrv"):
        for field in msg:
            if field.name == "time" and field.value is not None:
                vals = field.value if isinstance(field.value, (list, tuple)) else [field.value]
                data["hrv_intervals"].extend(v for v in vals if v is not None)

    for msg in fitfile.get_messages("device_info"):
        data["device_info"].append(extract_fields(msg))

    for msg in fitfile.get_messages("user_profile"):
        data["user_profile"].update(extract_fields(msg))

    for msg in fitfile.get_messages("zones_target"):
        data["zones_target"].update(extract_fields(msg))

    return data


def detect_device(data: dict) -> str:
    for info in data["device_info"]:
        if "manufacturer" in info:
            mfr = str(info["manufacturer"][0]).lower()
            if "suunto" in mfr:
                return "suunto"
            if "garmin" in mfr:
                return "garmin"
    return "other"


def compute_hrv(rr_intervals: list) -> tuple:
    rr = [t for t in rr_intervals if 0.3 <= t <= 2.0]
    if len(rr) < 2:
        return None, None
    diffs = [rr[i + 1] - rr[i] for i in range(len(rr) - 1)]
    rmssd = math.sqrt(sum(d ** 2 for d in diffs) / len(diffs)) * 1000
    mean_rr = sum(rr) / len(rr)
    sdnn = math.sqrt(sum((r - mean_rr) ** 2 for r in rr) / len(rr)) * 1000
    return round(rmssd, 1), round(sdnn, 1)


def _fmt_duration(seconds) -> str:
    if not _finite_number(seconds) or seconds < 0:
        return "-"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_pace(speed_kmh, distance_km: float = 1) -> str:
    if not _finite_number(speed_kmh) or speed_kmh <= 0:
        return "-"
    minutes, seconds = divmod(round(3600 * distance_km / speed_kmh), 60)
    unit = "100 m" if distance_km == 0.1 else "km"
    return f"{minutes}:{seconds:02d} /{unit}"


def _fmt_effort(speed, sport: str) -> str:
    if not _finite_number(speed) or speed < 0:
        return "-"
    if sport in {"running", "swimming"}:
        return _fmt_pace(speed, 0.1 if sport == "swimming" else 1)
    return f"{speed:.1f} km/h"


def _swim_stroke(value) -> str:
    if value is None:
        return "-"
    labels = {"freestyle": "Crawl", "backstroke": "Dos", "breaststroke": "Brasse",
              "butterfly": "Papillon", "drill": "Éducatifs", "mixed": "Mixte",
              "im": "Quatre nages"}
    return labels.get(str(value), f"Autre ({value})")


def _fmt_recovery(seconds) -> str:
    if seconds is None:
        return "-"
    h, rem = divmod(int(seconds), 3600)
    return f"{h}h {rem // 60:02d}min"


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("un entier strictement positif est requis") from None
    if number < 1:
        raise argparse.ArgumentTypeError("un entier strictement positif est requis")
    return number


def _markdown_cell(value) -> str:
    text = str(value) if value is not None else "-"
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(
        ">", "&gt;"
    ).replace("\\", "&#92;").replace("|", "&#124;").replace(
        "`", "&#96;"
    ).replace("\r", " ").replace("\n", " ")


def _finite_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _numeric_summary(values: list) -> tuple:
    numeric = [value for value in values if _finite_number(value)]
    if not numeric:
        return 0, "-", "-", "-"
    mean = math.fsum(value / len(numeric) for value in numeric)
    return len(numeric), f"{min(numeric):.6g}", f"{max(numeric):.6g}", f"{mean:.6g}"


def _detail_value(value) -> str:
    if value is None or isinstance(value, float) and not math.isfinite(value):
        return "-"
    if isinstance(value, (bytes, bytearray)):
        return f"Données binaires ({len(value)} octets)"
    if isinstance(value, dict):
        return f"Données structurées ({len(value)} champs)"
    if isinstance(value, (tuple, list)):
        if len(value) <= 16:
            return ", ".join(_detail_value(item) for item in value)
        count, minimum, maximum, mean = _numeric_summary(value)
        return (
            f"{len(value)} éléments ; {count} valeurs numériques valides ; "
            f"min {minimum} ; max {maximum} ; moyenne d’échantillons {mean}"
        )
    return str(value)


def _canonical_field(key: str) -> str:
    return key.removeprefix("enhanced_")


def _detail_fields(fields: dict, consumed: set):
    represented = {_canonical_field(key) for key in consumed}
    for key in sorted(fields):
        if key.startswith("unknown_") or key in {"hrv", "hrv_intervals", "rr_intervals"}:
            continue
        canonical = _canonical_field(key)
        if canonical in represented:
            continue
        value, units = fields[key]
        if value is not None:
            represented.add(canonical)
            yield key, value, units


def _append_detail_table(lines: list, title: str, groups: list) -> None:
    rows = []
    for label, fields, consumed in groups:
        for key, value, units in _detail_fields(fields, consumed):
            cells = (label, key, _detail_value(value), units)
            rows.append("| " + " | ".join(_markdown_cell(cell) for cell in cells) + " |")
    if rows:
        lines.extend([
            f"## {title}", "| Élément | Champ FIT | Valeur | Unité |",
            "|---|---|---|---|", *rows, "", "---", "",
        ])


def _append_record_summary(lines: list, records: list) -> None:
    series = {}
    for record in records:
        for key, value, units in _detail_fields(record, set()):
            if key in {"timestamp", "local_timestamp"} or key.startswith("position_"):
                continue
            if isinstance(value, (bool, date, datetime, time)) or units == "semicircles":
                continue
            if isinstance(value, (int, float)) and not _finite_number(value):
                continue
            series.setdefault((_canonical_field(key), units), []).append(value)
    rows = []
    for (key, units), values in sorted(series.items(), key=lambda item: (item[0][0], str(item[0][1]))):
        count, minimum, maximum, mean = _numeric_summary(values)
        cells = (key, units, len(values), count, minimum, maximum, mean)
        rows.append("| " + " | ".join(_markdown_cell(cell) for cell in cells) + " |")
    if rows:
        lines.extend([
            "## Synthèse des mesures enregistrées",
            "Moyennes arithmétiques des échantillons valides, non pondérées par le temps. "
            "Les valeurs textuelles ou structurées sont comptées sans être moyennées.",
            "", "| Champ FIT | Unité | Présences | Numériques valides | Min | Max | Moyenne |",
            "|---|---|---|---|---|---|---|", *rows, "", "---", "",
        ])


def _sparkline(values: list, pace: bool = False) -> tuple[str, float | None, float | None]:
    visible = [value for value in values if value is not None and (not pace or value > 0)]
    minimum = min(visible) if visible else None
    maximum = max(visible) if visible else None
    glyphs = "▁▂▃▄▅▆▇█"
    characters = []
    for value in values:
        if value is None:
            characters.append(" ")
        elif pace and value == 0:
            characters.append("·")
        elif maximum == minimum:
            characters.append("▄")
        else:
            level = round(7 * (value - minimum) / (maximum - minimum))
            characters.append(glyphs[max(0, min(7, level))])
    return "".join(characters), minimum, maximum


def _graph_axis_labels(labels: list[str]) -> str:
    characters = [" "] * 60
    for offset, label in zip((0, 30 - len(labels[1]) // 2, 60 - len(labels[2])), labels):
        characters[offset:offset + len(label)] = label
    return "".join(characters)


def _append_activity_graphs(lines: list, graphs: dict, sport: str) -> None:
    lines.extend([
        "## Graphiques de la séance", "",
        "Échelles indépendantes, bornes des valeurs tracées. Espaces : données non tracées. "
        "Plus haut = altitude ou cardio plus élevé ; pour vitesse/allure, plus haut = plus rapide. "
        "En allure, · indique une vitesse nulle.", "",
    ])
    for key, title in (("altitude", "Altitude — distance FIT"),
                       ("heart_rate", "Cardio — temps enregistré"),
                       ("speed", "Allure — temps enregistré" if sport in {"running", "swimming"}
                        else "Vitesse — temps enregistré")):
        graph = graphs[key]
        lines.extend([f"### {title}", ""])
        if graph["reason"]:
            lines.extend([f"Graphique indisponible : {graph['reason']}.", ""])
            continue
        pace = key == "speed" and sport in {"running", "swimming"}
        drawing, minimum, maximum = _sparkline(graph["values"], pace)
        if minimum is None:
            scale = "Vitesse nulle sur les positions tracées."
        else:
            if key == "speed":
                low_label, high_label = _fmt_effort(minimum, sport), _fmt_effort(maximum, sport)
            else:
                unit = "m" if key == "altitude" else "bpm"
                low_label, high_label = f"{minimum:.1f} {unit}", f"{maximum:.1f} {unit}"
            scale = f"Bas : {low_label} ; haut : {high_label}."
            if minimum == maximum:
                if pace and 0 in graph["values"]:
                    scale += " Allure constante hors arrêts."
                else:
                    scale += " Valeur constante."
        start, end = graph["start"], graph["end"]
        if key == "altitude":
            labels = [f"{position / 1000:.2f} km" for position in (start, (start + end) / 2, end)]
        else:
            labels = [_fmt_duration(round(position)) for position in (0, (end - start) / 2, end - start)]
        ticks = "┬" + "─" * 29 + "┬" + "─" * 28 + "┬"
        lines.extend([scale, "", "```text", drawing, ticks, _graph_axis_labels(labels), "```", ""])
    lines.extend(["---", ""])


def _append_analysis_table(lines: list, title: str, headers: list, rows: list, note: str = "") -> None:
    if not rows:
        return
    lines.extend([f"## {title}", ""])
    if note:
        lines.extend([note, ""])
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for header in headers) + " |")
    lines.extend("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |" for row in rows)
    lines.extend(["", "---", ""])


def _append_activity_analysis(lines: list, analysis: dict, sport: str, elapsed, timer) -> None:
    rows = []
    for row in analysis["kilometers"]:
        complete = row["complete"] and row["seconds"] > 0
        speed = row["distance"] / row["seconds"] * 3.6 if complete else None
        status = "Complet" if complete else "Incomplet"
        if complete and row["distance"] < 1000:
            status = "Dernier segment"
        rows.append([
            int(row["start"] // 1000) + 1, f"{row['distance'] / 1000:.3f} km", status,
            _fmt_duration(row["seconds"]) if complete else "-", _fmt_effort(speed, sport),
            f"{row['heart_rate']:.0f} bpm" if complete and row["heart_rate"] is not None else "-",
            f"{row['ascent']:.0f} m" if complete and row["altitude_complete"] else "-",
            f"{row['descent']:.0f} m" if complete and row["altitude_complete"] else "-",
        ])
    _append_analysis_table(
        lines, "Découpage kilométrique", ["Km", "Distance", "État", "Durée enregistrée", "Allure", "FC moy.", "D+ estimé", "D− estimé"], rows,
        "Limites interpolées sur la distance cumulée FIT. La durée enregistrée peut inclure des arrêts. "
        "Aucune interpolation à travers une interruption ; dénivelé estimé après médiane glissante de cinq points. "
        "FC pondérée par les durées des intervalles avec deux mesures FC valides.",
    )
    terrain_rows = []
    for name, row in analysis["terrain"].items():
        speed = row["distance"] / row["seconds"] * 3.6
        terrain_rows.append([
            name, f"{row['distance'] / 1000:.2f} km", _fmt_duration(row["seconds"]),
            _fmt_effort(speed, sport),
            f"{row['heart_rate']:.0f} bpm" if row["heart_rate"] is not None else "-",
        ])
    _append_analysis_table(
        lines, "Répartition du terrain", ["Terrain", "Distance", "Durée enregistrée", "Allure" if sport == "running" else "Vitesse", "FC moy."], terrain_rows,
        f"Estimation à partir de l’altitude enregistrée : {analysis['terrain_distance'] / 1000:.2f} km analysés. "
        "Médiane glissante de cinq points ; tronçons de 50 m ; montée au-dessus de +3 %, "
        "descente sous −3 %, plat entre ces seuils. Portions trop courtes ou interrompues exclues. "
        "Les FC moyennes des analyses sont pondérées par les durées où la FC est disponible aux deux extrémités.",
    )
    quality = analysis["quality"]
    total = quality["records"]
    quality_rows = [["Records", total]]
    for key, label in (("heart_rate", "FC exploitable"), ("gps", "Coordonnées GPS valides"), ("altitude", "Altitude disponible")):
        coverage = f"{100 * quality[key] / total:.1f} % ({quality[key]}/{total})" if total else "-"
        quality_rows.append([label, coverage])
    for key, label in (("missing_time", "Horodatages absents ou invalides"),
                       ("missing_distance", "Distances absentes ou invalides"),
                       ("non_increasing_time", "Horodatages non croissants"),
                       ("distance_regressions", "Régressions de distance")):
        if quality[key]:
            quality_rows.append([label, quality[key]])
    quality_rows.append(["Interruptions temporelles", quality["gaps"]])
    if quality["gaps"]:
        quality_rows.append(["Plus grande interruption", f"{quality['largest_gap']:.1f} s"])
    if analysis["kilometer_reason"]:
        quality_rows.append(["Découpage kilométrique indisponible", analysis["kilometer_reason"]])
    if sport in {"running", "cycling"} and not analysis["terrain"]:
        quality_rows.append(["Terrain indisponible", "aucun tronçon continu de 50 m avec distance, temps et altitude exploitables"])
    if _finite_number(elapsed) and _finite_number(timer) and (timer < 0 or elapsed < timer):
        quality_rows.append(["Durées incohérentes", "temps hors chronomètre non calculé"])
    _append_analysis_table(
        lines, "Qualité de l’enregistrement", ["Indicateur", "Valeur"], quality_rows,
        f"Interruption : écart supérieur à {quality['gap_limit']:.1f} s "
        "(max de 10 s et de cinq fois l’intervalle médian positif). "
        "Ce critère n’identifie pas automatiquement une pause ou une perte GPS. "
        "La couverture décrit les records, pas une proportion de la durée.",
    )


def format_markdown(
    data: dict,
    device: str,
    source_path: Path,
    include_gps: bool,
    gps_limit: int,
    details: bool = False,
) -> str:
    if isinstance(gps_limit, bool) or not isinstance(gps_limit, int) or gps_limit < 1:
        raise ValueError("gps_limit doit être un entier strictement positif")
    session = data["session"]
    lines = []
    session_consumed = set()
    lap_groups = []
    device_consumed = [set() for info in data["device_info"]]

    def sv(key):
        entry = session.get(key)
        if entry and entry[0] is not None:
            session_consumed.add(key)
        return entry[0] if entry and entry[0] is not None else None

    def session_number(key, unit=None):
        value = numeric_field(session, key, unit)
        if value is not None:
            session_consumed.add(key)
        return value

    # --- Header ---
    sport = str(sv("sport") or "")
    sport_kind = sport.lower()
    analysis = analyze_records(data["records"], sport_kind)
    sub_sport = str(sv("sub_sport") or "")
    start_time = sv("start_time")

    if sub_sport and sub_sport.lower() not in {"generic", sport.lower()}:
        sport_str = f"{sport} ({sub_sport})"
    else:
        sport_str = sport or "-"

    date_str = start_time.strftime("%Y-%m-%d %H:%M") if start_time else "-"
    lines.append(f"# Activité — {sport_str} — {date_str}")

    product_name = "-"
    manufacturer_name = "-"
    for device_index, info in enumerate(data["device_info"]):
        if manufacturer_name == "-" and "manufacturer" in info:
            manufacturer_name = str(info["manufacturer"][0])
            device_consumed[device_index].add("manufacturer")
        if product_name == "-":
            if "product_name" in info:
                product_name = str(info["product_name"][0])
                device_consumed[device_index].add("product_name")
            elif "garmin_product" in info:
                product_name = f"Garmin #{info['garmin_product'][0]}"
                device_consumed[device_index].add("garmin_product")
        if product_name != "-" and manufacturer_name != "-":
            break

    lines.append(f"**Matériel** : {product_name} ({manufacturer_name})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Résumé général ---
    lines.append("## Résumé général")
    lines.append("| Métrique | Valeur |")
    lines.append("|----------|--------|")

    dist = session_number("total_distance", "m")
    if dist is not None:
        lines.append(f"| Distance | {dist / 1000:.2f} km |")

    elapsed = session_number("total_elapsed_time", "s")
    if elapsed is not None:
        lines.append(f"| Durée totale | {_fmt_duration(elapsed)} |")

    timer = session_number("total_timer_time", "s")
    if timer is not None:
        lines.append(f"| Durée chronométrée | {_fmt_duration(timer)} |")
    if elapsed is not None and timer is not None and 0 <= timer <= elapsed:
        lines.append(f"| Temps hors chronomètre | {_fmt_duration(elapsed - timer)} |")

    ascent = sv("total_ascent")
    if ascent is not None:
        lines.append(f"| Dénivelé + | {ascent} m |")

    descent = sv("total_descent")
    if descent is not None:
        lines.append(f"| Dénivelé - | {descent} m |")

    speed = activity_speed(session)
    if speed is not None:
        session_consumed.update({"avg_speed", "enhanced_avg_speed"})
        label = "Allure moyenne" if sport_kind in {"running", "swimming"} else "Vitesse moyenne"
        lines.append(f"| {label} | {_fmt_effort(speed, sport_kind)} |")

    for key, label, operation in (("min_altitude", "Altitude minimale", min), ("max_altitude", "Altitude maximale", max)):
        altitude = preferred_number(session, key, "m")
        source_label = ""
        if altitude is not None:
            session_consumed.update({key, f"enhanced_{key}"})
        elif analysis["altitudes"]:
            altitude = operation(analysis["altitudes"])
            source_label = " (records)"
        if altitude is not None:
            lines.append(f"| {label}{source_label} | {altitude:.0f} m |")

    avg_hr = sv("avg_heart_rate")
    if avg_hr is not None:
        lines.append(f"| FC moyenne | {avg_hr} bpm |")

    max_hr = sv("max_heart_rate")
    if max_hr is not None:
        lines.append(f"| FC max | {max_hr} bpm |")

    min_hr = sv("min_heart_rate")
    if min_hr is not None:
        lines.append(f"| FC min | {min_hr} bpm |")

    calories = sv("total_calories")
    if calories is not None:
        lines.append(f"| Calories | {calories} kcal |")

    temp = sv("avg_temperature")
    if temp is not None:
        lines.append(f"| Température moy. | {temp} °C |")

    cadence = sv("avg_running_cadence")
    if cadence is not None:
        lines.append(f"| Cadence moy. | {cadence} foulées/min |")

    if sport_kind == "swimming":
        cycles = session_number("total_cycles")
        if cycles is not None and cycles >= 0:
            lines.append(f"| Cycles de nage | {cycles:g} |")
        swim_cadence = session_number("avg_cadence", "rpm")
        if swim_cadence is not None and swim_cadence >= 0:
            lines.append(f"| Cadence de nage | {swim_cadence:g} cycles/min |")
        strokes = {str(lap["swim_stroke"][0]) for lap in data["laps"]
                   if lap.get("swim_stroke") and lap["swim_stroke"][0] is not None}
        if sv("swim_stroke") is not None:
            strokes.add(str(sv("swim_stroke")))
        if strokes:
            labels = ", ".join(_swim_stroke(stroke) for stroke in sorted(strokes))
            lines.append(f"| Types de nage | {_markdown_cell(labels)} |")

    vam = session_number("avg_vam", "m/h")
    if vam is not None:
        lines.append(f"| VAM | {vam:.0f} m/h |")

    tss = sv("training_stress_score")
    if tss is not None:
        lines.append(f"| Training Stress Score | {tss:.1f} TSS |")

    te = sv("total_training_effect")
    if te is not None:
        lines.append(f"| Training Effect | {te} |")
    anaerobic_te = session_number("total_anaerobic_training_effect")
    if anaerobic_te is not None:
        lines.append(f"| Training Effect anaérobie | {anaerobic_te:g} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    _append_activity_graphs(lines, analysis["graphs"], sport_kind)

    # --- Zones d'entraînement ---
    hr_zones = sv("time_in_hr_zone")
    aerobic_zone_time = sv("time_in_aerobic_zone")
    anaerobic_zone_time = sv("time_in_anaerobic_zone")

    if hr_zones is not None:
        zone_list = hr_zones if isinstance(hr_zones, (list, tuple)) else [hr_zones]
        zone_total = sum(value for value in zone_list if _finite_number(value) and value >= 0)
        lines.append("## Zones d'entraînement")
        lines.append("Pourcentages calculés sur la somme des durées de zones FC valides, pas sur la durée totale.")
        lines.append("")
        lines.append("| Zone | Durée | Part du temps en zones FC |")
        lines.append("|------|-------|-------|")
        for i, zt in enumerate(zone_list, 1):
            if _finite_number(zt) and zt >= 0:
                percentage = f"{100 * zt / zone_total:.1f} %" if zone_total > 0 else "-"
                lines.append(f"| Zone {i} | {_fmt_duration(zt)} | {percentage} |")
        if aerobic_zone_time is not None:
            lines.append(f"| Aérobie | {_fmt_duration(aerobic_zone_time)} | - |")
        if anaerobic_zone_time is not None:
            lines.append(f"| Anaérobie | {_fmt_duration(anaerobic_zone_time)} | - |")
        lines.append("")
        lines.append("---")
        lines.append("")

    # --- Métriques avancées (Suunto) ---
    suunto_keys = [
        "recovery_time", "peak_epoc", "cumulative_baseline",
        "aerobic_threshold", "aerobic_baseline", "feeling",
        "time_in_aerobic_zone", "time_in_anaerobic_zone", "time_in_vo2max_zone",
    ]
    if any(sv(k) is not None for k in suunto_keys):
        lines.append("## Métriques avancées (Suunto)")
        lines.append("| Métrique | Valeur |")
        lines.append("|----------|--------|")

        rec = sv("recovery_time")
        if rec is not None:
            lines.append(f"| Temps de récupération | {_fmt_recovery(rec)} |")

        epoc = sv("peak_epoc")
        if epoc is not None:
            lines.append(f"| EPOC peak | {epoc:.1f} l/kg |")

        baseline = sv("cumulative_baseline")
        if baseline is not None:
            lines.append(f"| Baseline cumulative | {baseline:.3f} |")

        aero_thr = sv("aerobic_threshold")
        if aero_thr is not None:
            lines.append(f"| Seuil aérobie | {aero_thr:.1f} bpm |")

        aero_base = sv("aerobic_baseline")
        if aero_base is not None:
            lines.append(f"| Baseline aérobie | {aero_base:.3f} |")

        feeling = sv("feeling")
        if feeling is not None:
            lines.append(f"| Ressenti | {feeling}/5 |")

        if aerobic_zone_time is not None:
            lines.append(f"| Temps zone aérobie | {_fmt_duration(aerobic_zone_time)} |")

        if anaerobic_zone_time is not None:
            lines.append(f"| Temps zone anaérobie | {_fmt_duration(anaerobic_zone_time)} |")

        vo2max_time = sv("time_in_vo2max_zone")
        if vo2max_time is not None:
            lines.append(f"| Temps zone VO2max | {_fmt_duration(vo2max_time)} |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # --- HRV ---
    if data["hrv_intervals"]:
        rmssd, sdnn = compute_hrv(data["hrv_intervals"])
        if rmssd is not None and sdnn is not None:
            lines.append("## HRV")
            lines.append("| Métrique | Valeur |")
            lines.append("|----------|--------|")
            lines.append(f"| RMSSD | {rmssd} ms |")
            lines.append(f"| SDNN | {sdnn} ms |")
            lines.append(f"| Nb intervalles RR | {len(data['hrv_intervals'])} |")
            lines.append("")
            lines.append("---")
            lines.append("")

    # --- Profil utilisateur (Garmin) ---
    if data["user_profile"]:
        profile = data["user_profile"]
        lines.append("## Profil utilisateur")
        lines.append("| Champ | Valeur |")
        lines.append("|-------|--------|")

        explicit_profile = {
            "age": ("Âge", "ans"),
            "weight": ("Poids", "kg"),
            "resting_heart_rate": ("FC repos", "bpm"),
            "max_heart_rate": ("FC max configurée", "bpm"),
        }
        shown = set(explicit_profile)
        for key, (label, unit_override) in explicit_profile.items():
            raw = profile.get(key)
            if raw and raw[0] is not None and raw[0] != 0:
                lines.append(f"| {label} | {raw[0]} {unit_override} |")
        for key, (pv, pu) in profile.items():
            if key not in shown:
                lines.append(f"| {key} | {pv} {pu or ''}".rstrip() + " |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # --- Zones cibles (Garmin) ---
    if data["zones_target"]:
        zt = data["zones_target"]
        lines.append("## Zones cibles")
        lines.append("| Champ | Valeur |")
        lines.append("|-------|--------|")

        explicit_zt = {
            "functional_threshold_power": ("FTP", "W"),
            "threshold_heart_rate": ("Seuil FC", "bpm"),
        }
        shown_zt = set(explicit_zt)
        for key, (label, unit_override) in explicit_zt.items():
            raw = zt.get(key)
            if raw and raw[0] is not None and raw[0] != 0:
                lines.append(f"| {label} | {raw[0]} {unit_override} |")
        for key, (zv, zu) in zt.items():
            if key not in shown_zt:
                lines.append(f"| {key} | {zv} {zu or ''}".rstrip() + " |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # --- Tours / Laps ---
    if data["laps"]:
        lines.append("## Tours / Laps")
        effort_label = "Allure" if sport_kind in {"running", "swimming"} else "Vitesse"
        headers = ["#", "Distance", "Durée", "FC moy", "FC max", effort_label, "Dénivelé+", "Temp."]
        if sport_kind == "swimming":
            headers.extend(["Nage", "Cycles", "Cadence (cycles/min)"])
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for header in headers) + " |")

        for i, lap in enumerate(data["laps"], 1):
            lap_consumed = set()
            lap_groups.append((f"Tour {i}", lap, lap_consumed))
            def lv(key, _lap=lap):
                entry = _lap.get(key)
                if entry and entry[0] is not None:
                    lap_consumed.add(key)
                return entry[0] if entry and entry[0] is not None else None

            dist_l = numeric_field(lap, "total_distance", "m")
            if dist_l is not None:
                lap_consumed.add("total_distance")
            dist_s = f"{dist_l / 1000:.2f} km" if dist_l is not None else "-"

            dur_l = lv("total_timer_time")
            if dur_l is None:
                dur_l = lv("total_elapsed_time")
            dur_s = _fmt_duration(dur_l)

            avg_hr_l = lv("avg_heart_rate")
            avg_hr_s = f"{avg_hr_l} bpm" if avg_hr_l is not None else "-"

            max_hr_l = lv("max_heart_rate")
            max_hr_s = f"{max_hr_l} bpm" if max_hr_l is not None else "-"

            speed_l = activity_speed(lap)
            if speed_l is not None:
                lap_consumed.update({"avg_speed", "enhanced_avg_speed", "total_timer_time"})
            speed_s = _fmt_effort(speed_l, sport_kind)

            ascent_l = lv("total_ascent")
            ascent_s = f"{ascent_l} m" if ascent_l is not None else "-"

            temp_l = lv("avg_temperature")
            temp_s = f"{temp_l} °C" if temp_l is not None else "-"

            cells = [i, dist_s, dur_s, avg_hr_s, max_hr_s, speed_s, ascent_s, temp_s]
            if sport_kind == "swimming":
                swim_cycles = numeric_field(lap, "total_cycles")
                swim_cadence = numeric_field(lap, "avg_cadence", "rpm")
                cells.extend([
                    _swim_stroke(lv("swim_stroke")),
                    f"{swim_cycles:g}" if swim_cycles is not None and swim_cycles >= 0 else "-",
                    f"{swim_cadence:g}" if swim_cadence is not None and swim_cadence >= 0 else "-",
                ])
                if swim_cycles is not None:
                    lap_consumed.add("total_cycles")
                if swim_cadence is not None:
                    lap_consumed.add("avg_cadence")
            lines.append("| " + " | ".join(_markdown_cell(cell) for cell in cells) + " |")

        lines.append("")
        lines.append("---")
        lines.append("")

    # --- Points GPS ---
    if include_gps and data["records"]:
        gps_records = [
            r for r in data["records"]
            if "position_lat" in r and r["position_lat"][0] is not None
            and "position_long" in r and r["position_long"][0] is not None
        ]
        if gps_records:
            step = max(1, len(gps_records) // gps_limit)
            sampled = gps_records[::step][:gps_limit]

            lines.append("## Points GPS")
            lines.append("| Temps | Lat | Long | Alt (m) | FC | Vitesse |")
            lines.append("|-------|-----|------|---------|----|----|")

            for rec in sampled:
                def rv(key, _rec=rec):
                    entry = _rec.get(key)
                    return entry[0] if entry and entry[0] is not None else None

                ts = rv("timestamp")
                ts_s = ts.strftime("%H:%M:%S") if ts else "-"
                lat = rv("position_lat")
                lat_s = f"{lat:.5f}" if lat is not None else "-"
                lon = rv("position_long")
                lon_s = f"{lon:.5f}" if lon is not None else "-"
                alt = rv("altitude")
                alt_s = f"{alt:.0f}" if alt is not None else "-"
                hr = rv("heart_rate")
                hr_s = f"{hr} bpm" if hr is not None else "-"
                spd = rv("speed")
                spd_s = f"{spd:.1f} km/h" if spd is not None else "-"

                lines.append(f"| {ts_s} | {lat_s} | {lon_s} | {alt_s} | {hr_s} | {spd_s} |")

            lines.append("")
            lines.append("---")
            lines.append("")

    _append_activity_analysis(lines, analysis, sport_kind, elapsed, timer)

    if details:
        _append_detail_table(lines, "Champs complémentaires de séance", [
            ("Séance", session, session_consumed),
        ])
        _append_detail_table(lines, "Champs complémentaires par tour", lap_groups)
        _append_detail_table(lines, "Informations complémentaires du matériel", [
            (f"Appareil {device_index + 1}", info, device_consumed[device_index])
            for device_index, info in enumerate(data["device_info"])
        ])
        _append_record_summary(lines, data["records"])

    # --- Footer ---
    lines.append(
        f"*Généré depuis `{source_path.name}` — {len(data['records'])} enregistrements — {product_name}*"
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Convertir un fichier .fit en Markdown pour le coaching IA."
    )
    parser.add_argument(
        "input", type=Path,
        help="Fichier .fit ou .fit.gz (nom seul = recherché dans import/)"
    )
    parser.add_argument(
        "--output", type=Path,
        help="Chemin du .md de sortie (sinon export/YYYY-MM-DD_<activité>_<indice>.md)"
    )
    parser.add_argument("--stdout", action="store_true", help="Afficher dans le terminal")
    parser.add_argument(
        "--details", action="store_true",
        help="Ajouter les champs complémentaires et les synthèses des mesures"
    )
    parser.add_argument("--gps", action="store_true", help="Inclure les points GPS échantillonnés")
    parser.add_argument(
        "--gps-limit", type=_positive_int, default=30, metavar="N",
        help="Nombre max de points GPS (défaut : 30)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Avec --output, autorise le remplacement du .md et du .gpx associés"
    )
    args = parser.parse_args()

    input_path = resolve_input_path(args.input)
    if not input_path.exists():
        print(
            f"Erreur : fichier introuvable : {args.input} "
            f"(cherché également dans {IMPORT_DIR}/)",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        data = parse_fit(input_path)
    except Exception as e:
        print(f"Erreur lors du parsing FIT : {e}", file=sys.stderr)
        sys.exit(1)

    try:
        device = detect_device(data)
        markdown = format_markdown(
            data, device, input_path, args.gps, args.gps_limit, args.details
        )
        if args.stdout:
            print(markdown)
            return
        if args.output:
            md_path = args.output
        else:
            md_path, _basename = plan_output_paths(data["session"], input_path)
        gps_points = extract_gps_points(data["records"])
        gpx_content = build_gpx(gps_points, md_path.stem) if has_gps_points(gps_points) else None
        ensure_workdirs()
        final_fit = export_activity(input_path, md_path, markdown, gpx_content, args.force)
    except Exception as error:
        print(f"Erreur lors de l’export : {error}", file=sys.stderr)
        sys.exit(1)

    print(f"Markdown généré : {md_path}", file=sys.stderr)
    if gpx_content is not None:
        print(f"GPX généré : {md_path.with_suffix('.gpx')} ({len(gps_points)} points)", file=sys.stderr)
    else:
        print("Aucun point GPS exploitable trouvé : GPX non généré.", file=sys.stderr)
    print(f"Archive FIT : {final_fit}", file=sys.stderr)


if __name__ == "__main__":
    main()
