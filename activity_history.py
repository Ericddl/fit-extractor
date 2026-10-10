"""Entrées et format Markdown de l'historique ; aucun accès disque."""

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import html
import math
import re
from urllib.parse import quote, unquote

from activity_analysis import numeric_field


_HEADER = [
    "# Historique des activités",
    "<!-- fit-extractor-history:v1 -->",
    "",
    "Périmètre : activités traitées avec succès et enregistrées par cet outil.",
    "Débuts en UTC (début FIT, sinon premier record horodaté) ; « - » signifie donnée absente.",
    "D+, FC, TSS et TE fournis par le FIT, sans recalcul.",
    "",
    "| Début (UTC) | Sport | Distance (km) | Durée chrono | D+ (m) | FC moy. (bpm) | FC max (bpm) | TSS | TE aérobie | Fichier |",
    "|---|---|---:|---|---:|---:|---:|---:|---:|---|",
]
_ID_RE = re.compile(r"[0-9a-f]{64}")
_FILE_RE = re.compile(
    r"(?:-|\[Séance\]\((?P<link>[^)\s]+)\)) "
    r"<!-- activity-id:sha256:(?P<activity_id>[0-9a-f]{64}) -->"
)
_INTEGER = r"(?:0|[1-9][0-9]*)"
_SPORTS = {"running": "Course", "cycling": "Vélo", "swimming": "Natation"}
_SUB_SPORTS = {
    ("running", "trail"): "Trail",
    ("cycling", "road"): "Vélo route",
    ("cycling", "mountain"): "VTT",
    ("swimming", "open_water"): "Natation eau libre",
    ("swimming", "lap_swimming"): "Natation en bassin",
}


@dataclass(frozen=True)
class HistoryEntry:
    activity_id: str
    start: datetime | None
    sport: str
    distance: str
    duration: str
    ascent: str
    avg_heart_rate: str
    max_heart_rate: str
    tss: str
    training_effect: str
    link: str | None = None  # Chemin relatif POSIX, non encodé.


def _value(fields: dict, key: str):
    entry = fields.get(key)
    return entry[0] if isinstance(entry, tuple) and len(entry) == 2 else None


def _utc(value) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    try:
        if value.utcoffset() is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _number(fields: dict, key: str, unit: str | None) -> float | None:
    entry = fields.get(key)
    if not isinstance(entry, tuple) or len(entry) != 2:
        return None
    if unit is None and entry[1] is not None:
        return None
    try:
        value = numeric_field(fields, key, unit)
        if value is not None and math.isfinite(value) and value >= 0:
            return value if value else 0.0
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def _decimal(value: float | None, digits: int, positive: bool = False) -> str:
    if value is None:
        return "-"
    result = f"{value:.{digits}f}"
    return "-" if positive and float(result) <= 0 else result


def _duration(value: float | None) -> str:
    if value is None:
        return "-"
    hours, remainder = divmod(int(value), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _sport(fields: dict) -> str:
    def text(key):
        value = _value(fields, key)
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            return ""
        return " ".join(str(value).splitlines()).strip()

    sport, sub_sport = text("sport"), text("sub_sport")
    if sub_sport.lower() in {"generic", sport.lower()}:
        sub_sport = ""
    known = _SUB_SPORTS.get((sport.lower(), sub_sport.lower()))
    if known:
        return known
    label = _SPORTS.get(sport.lower(), sport)
    return f"{label} ({sub_sport})" if label and sub_sport else label or sub_sport or "-"


def build_history_entry(data: dict, activity_id: str) -> HistoryEntry:
    """Sélectionne les métriques de séance sans modifier les données extraites."""
    if not _ID_RE.fullmatch(activity_id):
        raise ValueError("Identifiant d’activité invalide")
    session = data["session"]
    start = _utc(_value(session, "start_time"))
    if start is None:
        start = next((timestamp for record in data["records"]
                      if (timestamp := _utc(_value(record, "timestamp"))) is not None), None)
    return HistoryEntry(
        activity_id=activity_id,
        start=start,
        sport=_sport(session),
        distance=_decimal(_number(session, "total_distance", "km"), 2),
        duration=_duration(_number(session, "total_timer_time", "s")),
        ascent=_decimal(_number(session, "total_ascent", "m"), 0),
        avg_heart_rate=_decimal(_number(session, "avg_heart_rate", "bpm"), 0, positive=True),
        max_heart_rate=_decimal(_number(session, "max_heart_rate", "bpm"), 0, positive=True),
        tss=_decimal(_number(session, "training_stress_score", "tss"), 1),
        training_effect=_decimal(_number(session, "total_training_effect", None), 1),
    )


def _escape_text(value: str) -> str:
    return value.translate(str.maketrans({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", "\\": "&#92;",
        "|": "&#124;", "`": "&#96;", "[": "&#91;", "]": "&#93;",
        "*": "&#42;", "_": "&#95;", "~": "&#126;",
    }))


def _format_start(value: datetime | None) -> str:
    return value.isoformat().replace("+00:00", "Z") if value is not None else "-"


def _render_row(entry: HistoryEntry) -> str:
    link = f"[Séance]({quote(entry.link, safe='/')})" if entry.link is not None else "-"
    cells = [
        _format_start(entry.start), _escape_text(entry.sport), entry.distance,
        entry.duration, entry.ascent, entry.avg_heart_rate, entry.max_heart_rate,
        entry.tss, entry.training_effect,
        f"{link} <!-- activity-id:sha256:{entry.activity_id} -->",
    ]
    return "| " + " | ".join(cells) + " |"


def _parse_row(line: str) -> HistoryEntry:
    if not line.startswith("| ") or not line.endswith(" |"):
        raise ValueError("Ligne de tableau invalide")
    cells = line[2:-2].split(" | ")
    if len(cells) != 10:
        raise ValueError("Dix colonnes sont requises")
    start = None
    if cells[0] != "-":
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{6})?Z", cells[0]):
            raise ValueError("Début UTC invalide")
        start = datetime.fromisoformat(cells[0][:-1] + "+00:00")
        if _format_start(start) != cells[0]:
            raise ValueError("Début UTC non canonique")
    sport = html.unescape(cells[1])
    if not sport or sport != sport.strip() or len(sport.splitlines()) != 1 or _escape_text(sport) != cells[1]:
        raise ValueError("Libellé de sport invalide")
    for index, pattern in (
        (2, _INTEGER + r"\.[0-9]{2}"), (3, r"[0-9]{2,}:[0-5][0-9]:[0-5][0-9]"),
        (4, _INTEGER), (5, r"[1-9][0-9]*"), (6, r"[1-9][0-9]*"),
        (7, _INTEGER + r"\.[0-9]"), (8, _INTEGER + r"\.[0-9]"),
    ):
        if cells[index] != "-" and not re.fullmatch(pattern, cells[index]):
            raise ValueError(f"Valeur invalide dans la colonne {index + 1}")
    if cells[3] != "-" and len(cells[3].split(":")[0]) > 2 and cells[3].startswith("0"):
        raise ValueError("Durée non canonique")
    match = _FILE_RE.fullmatch(cells[9])
    if match is None:
        raise ValueError("Lien ou identifiant d’activité invalide")
    link = match["link"]
    if link is not None:
        decoded = unquote(link, errors="strict")
        if not decoded or decoded.startswith("/") or "\x00" in decoded or quote(decoded, safe="/") != link:
            raise ValueError("Lien relatif invalide")
        link = decoded
    return HistoryEntry(match["activity_id"], start, sport, *cells[2:9], link=link)


def parse_history(text: str) -> list[HistoryEntry]:
    """Refuse tout contenu extérieur au format généré, sans réparer des lignes."""
    lines = text.split("\n")
    if len(lines) < len(_HEADER) + 3 or lines[:len(_HEADER)] != _HEADER:
        raise ValueError("En-tête ou version d’historique invalide")
    if lines[-1] != "" or lines[-3] != "":
        raise ValueError("Historique incomplet")
    footer = re.fullmatch(r"<!-- fit-extractor-history:end rows:(0|[1-9][0-9]*) -->", lines[-2])
    rows = lines[len(_HEADER):-3]
    if footer is None or int(footer[1]) != len(rows):
        raise ValueError("Marqueur final ou nombre de lignes invalide")
    entries = []
    seen = set()
    for number, row in enumerate(rows, 1):
        try:
            entry = _parse_row(row)
        except ValueError as error:
            raise ValueError(f"Activité {number} : {error}") from error
        if entry.activity_id in seen:
            raise ValueError(f"Identifiant d’activité en double : {entry.activity_id}")
        seen.add(entry.activity_id)
        entries.append(entry)
    return entries


def render_history(entries: list[HistoryEntry]) -> str:
    text = "\n".join([
        *_HEADER, *(_render_row(entry) for entry in entries), "",
        f"<!-- fit-extractor-history:end rows:{len(entries)} -->", "",
    ])
    parse_history(text)  # Ne jamais publier une entrée impossible à relire.
    return text


def upsert_history(
    entries: list[HistoryEntry], entry: HistoryEntry, displaced_ids: set[str],
) -> list[HistoryEntry]:
    """Remplace l'entrée et retire les liens réaffectés, sans accès aux chemins."""
    result = [
        replace(old, link=None) if old.activity_id in displaced_ids else old
        for old in entries if old.activity_id != entry.activity_id
    ]
    result.append(entry)
    return sort_history(result)


def sort_history(entries: list[HistoryEntry]) -> list[HistoryEntry]:
    """Classe les entrées sans modifier la liste fournie."""
    result = list(entries)
    result.sort(key=lambda item: item.activity_id)
    result.sort(key=lambda item: item.start or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    # Une vraie date minimale reste avant les dates absentes.
    result.sort(key=lambda item: item.start is None)
    return result


def recover_history(text: str) -> tuple[list[HistoryEntry], list[str]]:
    """Récupère les lignes v1 valides ; réservé à la synchronisation explicite."""
    versions = re.findall(r"<!--\s*fit-extractor-history:(v[^\s>\-]+)", text)
    if any(version != "v1" for version in versions):
        raise ValueError("Version d’historique inconnue : réparation refusée")
    entries = {}
    warnings = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line or line in _HEADER or line.startswith("<!-- fit-extractor-history:end"):
            continue
        try:
            if "\ufffd" in line:
                raise ValueError("Ligne contenant des octets irrécupérables")
            entry = _parse_row(line)
        except ValueError:
            warnings.append(f"Ligne {number} irrécupérable (conservée dans la sauvegarde)")
            continue
        if entry.activity_id in entries:
            # Deux lignes contradictoires ne permettent pas de choisir un lien.
            previous = entries[entry.activity_id]
            entries[entry.activity_id] = replace(previous, link=None)
            warnings.append(f"Ligne {number} : identifiant répété, lien retiré")
        else:
            entries[entry.activity_id] = entry
    return sort_history(list(entries.values())), warnings
