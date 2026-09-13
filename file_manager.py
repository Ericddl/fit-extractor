"""Gestion des dossiers import/ et export/ et du nommage normalisé des activités.

Workflow :
- les .fit/.fit.gz à traiter sont lus depuis `import/`
- les .md générés et les .fit traités sont archivés dans `export/`
- le basename suit le format `YYYY-MM-DD_<activite>_<indice>` partagé par .md et .fit
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import tempfile
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


def _same_file(first: Path, second: Path) -> bool:
    return first.resolve() == second.resolve() or (
        first.exists() and second.exists() and first.samefile(second)
    )


def plan_archive_path(source: Path, md_target: Path) -> Path:
    extension = _source_fit_extension(source)
    target_dir = md_target.parent
    base = md_target.stem
    destination = target_dir / f"{base}{extension}"

    if _same_file(source, destination):
        return destination
    if destination.exists() or destination.is_symlink():
        duplicate_index = 1
        while True:
            candidate = target_dir / f"{base}_dup{duplicate_index}{extension}"
            if not candidate.exists() and not candidate.is_symlink():
                destination = candidate
                break
            duplicate_index += 1
    return destination


def move_processed_fit(source: Path, md_target: Path) -> Path:
    """Archive une source seule ; la CLI utilise export_activity pour le lot complet."""
    destination = plan_archive_path(source, md_target)
    if _same_file(source, destination):
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return destination


def export_activity(
    source: Path,
    md_target: Path,
    markdown: str,
    gpx_content: str | None,
    force: bool = False,
) -> Path:
    """Publie les exports et archive la source, avec restauration sur erreur gérée.

    Une seule exécution par destination ; aucune garantie après un arrêt brutal.
    Les sauvegardes sont conservées si la restauration échoue elle-même.
    """
    gpx_content = gpx_content or None
    gpx_target = md_target.with_suffix(".gpx")
    archive_target = plan_archive_path(source, md_target)
    targets = [md_target, gpx_target, archive_target]
    for target_index, target in enumerate(targets):
        if target.is_symlink():
            raise ValueError(f"Destination symbolique refusée : {target}")
        if target.exists() and not target.is_file():
            raise ValueError(f"La destination n’est pas un fichier : {target}")
        if any(_same_file(target, other) for other in targets[:target_index]):
            raise ValueError(f"Destinations confondues : {target}")
    for target in (md_target, gpx_target):
        if _same_file(source, target):
            raise ValueError(f"La sortie désigne la source : {target}")
        if target.exists() and not force:
            raise FileExistsError(f"La sortie existe déjà : {target} ; utilisez --force.")

    archive_in_place = _same_file(source, archive_target)
    md_target.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".fit-export-", dir=md_target.parent))
    backups = {}
    prepared = {}
    changed = []
    keep_backups = False
    try:
        for target, content in ((md_target, markdown), (gpx_target, gpx_content)):
            if content is not None:
                staged = staging_dir / f"new-{len(prepared)}"
                staged.write_text(content, encoding="utf-8")
                prepared[target] = staged
            if target.exists():
                backup = staging_dir / f"backup-{target.name}"
                shutil.copy2(target, backup)
                backups[target] = backup
        if not archive_in_place:
            staged_archive = staging_dir / "source-archive"
            shutil.copy2(source, staged_archive)
            prepared[archive_target] = staged_archive

        for target, staged in prepared.items():
            if force and target != archive_target:
                os.replace(staged, target)
            else:
                os.link(staged, target)
            changed.append(target)
        if gpx_content is None and gpx_target in backups:
            gpx_target.unlink()
            changed.append(gpx_target)
        if not archive_in_place:
            source.unlink()
    except Exception as error:
        restoration_errors = []
        for target in reversed(changed):
            try:
                if target in backups:
                    os.replace(backups[target], target)
                else:
                    target.unlink()
            except OSError as restoration_error:
                restoration_errors.append(f"{target} : {restoration_error}")
        if restoration_errors:
            keep_backups = True
            raise OSError(
                f"Échec de l’export ({error}). Restauration incomplète : "
                + "; ".join(restoration_errors)
                + f". Fichiers de récupération conservés dans {staging_dir.resolve()}"
            ) from error
        raise
    finally:
        if not keep_backups:
            try:
                shutil.rmtree(staging_dir)
            except OSError as cleanup_error:
                print(
                    f"Attention : nettoyage impossible dans {staging_dir.resolve()} : "
                    f"{cleanup_error}", file=sys.stderr,
                )
    return archive_target
