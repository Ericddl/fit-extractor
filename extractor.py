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
    if seconds is None:
        return "-"
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_pace(speed_kmh) -> str:
    if not speed_kmh or speed_kmh <= 0:
        return "-"
    pace = 60 / speed_kmh
    minutes, frac = divmod(pace, 1)
    return f"{int(minutes)}:{round(frac * 60):02d} /km"


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

    def sv_speed():
        return sv("avg_speed") or sv("enhanced_avg_speed")

    # --- Header ---
    sport = str(sv("sport") or "")
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

    dist = sv("total_distance")
    if dist is not None:
        lines.append(f"| Distance | {dist / 1000:.2f} km |")

    elapsed = sv("total_elapsed_time")
    if elapsed is not None:
        lines.append(f"| Durée totale | {_fmt_duration(elapsed)} |")

    timer = sv("total_timer_time")
    if timer is not None:
        lines.append(f"| Durée en mouvement | {_fmt_duration(timer)} |")

    ascent = sv("total_ascent")
    if ascent is not None:
        lines.append(f"| Dénivelé + | {ascent} m |")

    descent = sv("total_descent")
    if descent is not None:
        lines.append(f"| Dénivelé - | {descent} m |")

    speed = sv_speed()
    if speed is not None:
        lines.append(f"| Vitesse moyenne | {speed:.1f} km/h |")
        is_running = "run" in sport.lower() or device == "suunto"
        if is_running and speed > 0:
            lines.append(f"| Allure moyenne | {_fmt_pace(speed)} |")

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

    vam = sv("avg_vam")
    if vam is not None:
        lines.append(f"| VAM | {vam:.1f} m/s |")

    tss = sv("training_stress_score")
    if tss is not None:
        lines.append(f"| Training Stress Score | {tss:.1f} TSS |")

    te = sv("total_training_effect")
    if te is not None:
        lines.append(f"| Training Effect | {te} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Zones d'entraînement ---
    hr_zones = sv("time_in_hr_zone")
    aerobic_zone_time = sv("time_in_aerobic_zone")
    anaerobic_zone_time = sv("time_in_anaerobic_zone")

    if hr_zones is not None:
        zone_list = hr_zones if isinstance(hr_zones, (list, tuple)) else [hr_zones]
        lines.append("## Zones d'entraînement")
        lines.append("| Zone | Durée |")
        lines.append("|------|-------|")
        for i, zt in enumerate(zone_list, 1):
            if zt is not None:
                lines.append(f"| Zone {i} | {_fmt_duration(zt)} |")
        if aerobic_zone_time is not None:
            lines.append(f"| Aérobie | {_fmt_duration(aerobic_zone_time)} |")
        if anaerobic_zone_time is not None:
            lines.append(f"| Anaérobie | {_fmt_duration(anaerobic_zone_time)} |")
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
        lines.append("| # | Distance | Durée | FC moy | FC max | Vitesse | Dénivelé+ | Temp. |")
        lines.append("|---|----------|-------|--------|--------|---------|-----------|-------|")

        for i, lap in enumerate(data["laps"], 1):
            lap_consumed = set()
            lap_groups.append((f"Tour {i}", lap, lap_consumed))
            def lv(key, _lap=lap):
                entry = _lap.get(key)
                if entry and entry[0] is not None:
                    lap_consumed.add(key)
                return entry[0] if entry and entry[0] is not None else None

            dist_l = lv("total_distance")
            dist_s = f"{dist_l / 1000:.2f} km" if dist_l is not None else "-"

            dur_l = lv("total_timer_time")
            if dur_l is None:
                dur_l = lv("total_elapsed_time")
            dur_s = _fmt_duration(dur_l)

            avg_hr_l = lv("avg_heart_rate")
            avg_hr_s = f"{avg_hr_l} bpm" if avg_hr_l is not None else "-"

            max_hr_l = lv("max_heart_rate")
            max_hr_s = f"{max_hr_l} bpm" if max_hr_l is not None else "-"

            speed_l = lv("avg_speed") or lv("enhanced_avg_speed")
            speed_s = f"{speed_l:.1f} km/h" if speed_l is not None else "-"

            ascent_l = lv("total_ascent")
            ascent_s = f"{ascent_l} m" if ascent_l is not None else "-"

            temp_l = lv("avg_temperature")
            temp_s = f"{temp_l} °C" if temp_l is not None else "-"

            lines.append(
                f"| {i} | {dist_s} | {dur_s} | {avg_hr_s} | {max_hr_s}"
                f" | {speed_s} | {ascent_s} | {temp_s} |"
            )

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
        f"*Généré depuis `{source_path.name}` — {len(data['records'])} points GPS — {product_name}*"
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
