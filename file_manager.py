"""Gestion des dossiers import/ et export/ et du nommage normalisé des activités.

Workflow :
- les .fit/.fit.gz à traiter sont lus depuis `import/`
- les .md générés et les .fit traités sont archivés dans `export/`
- le basename suit le format `YYYY-MM-DD_<activite>_<indice>` partagé par .md et .fit
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from datetime import date, datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
IMPORT_DIR = PROJECT_ROOT / "import"
EXPORT_DIR = PROJECT_ROOT / "export"

_INDEX_DIGITS = 3
_BASENAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})_(?P<activity>.+)_(?P<index>\d{3})\.(?:md|fit|fit\.gz|gpx)$",
    re.IGNORECASE,
)


def ensure_workdirs() -> None:
    IMPORT_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename_part(text: str | None, fallback: str = "activite") -> str:
    if not text:
        return fallback
    normalized = unicodedata.normalize("NFD", str(text))
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    lower = ascii_only.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lower)
    cleaned = cleaned.strip("_")
    return cleaned or fallback


def resolve_input_path(user_arg: Path) -> Path:
    """Si l'argument est un nom nu introuvable tel quel mais présent dans import/, retourne ce chemin."""
    if user_arg.exists():
        return user_arg
    if user_arg.is_absolute() or len(user_arg.parts) > 1:
        return user_arg
    candidate = IMPORT_DIR / user_arg.name
    if candidate.exists():
        return candidate
    return user_arg


def _session_value(session: dict, key: str):
    entry = session.get(key)
    if entry is None:
        return None
    value = entry[0] if isinstance(entry, tuple) else entry
    return value


def resolve_activity_date(session: dict) -> date:
    for key in ("start_time", "timestamp", "date"):
        value = _session_value(session, key)
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
    return date.today()


def resolve_activity_name(session: dict) -> str:
    sport = _session_value(session, "sport")
    sub_sport = _session_value(session, "sub_sport")

    sport_part = sanitize_filename_part(sport, fallback="")
    sub_part = sanitize_filename_part(sub_sport, fallback="")

    if sub_part in {"", "generic", sport_part}:
        sub_part = ""

    combined = "_".join(p for p in (sport_part, sub_part) if p)
    return combined or "activite"


def next_available_index(directory: Path, date_str: str, activity: str) -> int:
    if not directory.exists():
        return 1
    prefix = f"{date_str}_{activity}_"
    max_index = 0
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        name = entry.name
        if not name.lower().startswith(prefix.lower()):
            continue
        match = _BASENAME_RE.match(name)
        if not match:
            continue
        if match.group("date") != date_str or match.group("activity").lower() != activity.lower():
            continue
        try:
            idx = int(match.group("index"))
        except ValueError:
            continue
        if idx > max_index:
            max_index = idx
    return max_index + 1


def build_activity_basename(activity_date: date, activity: str, index: int) -> str:
    return f"{activity_date:%Y-%m-%d}_{activity}_{index:0{_INDEX_DIGITS}d}"


def plan_output_paths(session: dict, fallback_source: Path) -> tuple[Path, str]:
    """Calcule (md_path, basename) en évitant toute collision avec export/."""
    activity_date = resolve_activity_date(session)
    activity = resolve_activity_name(session)
    if activity == "activite":
        fallback = sanitize_filename_part(fallback_source.stem.replace(".fit", ""), fallback="activite")
        if fallback and fallback != "activite":
            activity = fallback

    date_str = f"{activity_date:%Y-%m-%d}"
    index = next_available_index(EXPORT_DIR, date_str, activity)
    basename = build_activity_basename(activity_date, activity, index)
    md_path = EXPORT_DIR / f"{basename}.md"
    return md_path, basename


def _source_fit_extension(source: Path) -> str:
    if source.name.lower().endswith(".fit.gz"):
        return ".fit.gz"
    return ".fit"


def move_processed_fit(source: Path, md_target: Path) -> Path:
    """Déplace `source` à côté du .md cible avec le même basename, en préservant .fit / .fit.gz.

    Garde-fou anti-race : si la destination existe déjà, suffixe `_dupN` avant l'extension.
    """
    extension = _source_fit_extension(source)
    target_dir = md_target.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    base = md_target.stem
    destination = target_dir / f"{base}{extension}"

    if destination.exists():
        n = 1
        while True:
            candidate = target_dir / f"{base}_dup{n}{extension}"
            if not candidate.exists():
                destination = candidate
                break
            n += 1

    shutil.move(str(source), str(destination))
    return destination
