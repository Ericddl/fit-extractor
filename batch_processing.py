"""Coordination du batch et de la reprise ; les travailleurs ne publient rien."""

import argparse
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, replace
import multiprocessing
import os
from pathlib import Path
import signal
import sys

from activity_history import HistoryEntry, build_history_entry, render_history, sort_history
import file_manager as files
from gpx_exporter import build_gpx, extract_gps_points, has_gps_points


def parse_jobs(value: str) -> int:
    try:
        available = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        available = os.cpu_count()
    available = available or 1
    if value == "auto":
        return min(4, available)
    if value == "all":
        return available
    try:
        number = int(value)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("--jobs attend auto, all ou un entier strictement positif")


@dataclass
class PreparedActivity:
    activity_id: str | None
    session: dict | None = None
    markdown: str | None = None
    gps_points: list | None = None
    entry: HistoryEntry | None = None
    history_error: str | None = None
    skipped: bool = False


def prepare_activity(path: Path, known_ids: frozenset[str], details: bool,
                     gps: bool, gps_limit: int) -> PreparedActivity:
    # Import local : le parser/renderer reste dans extractor, sans cycle d'import.
    from extractor import parse_fit, format_markdown, detect_device

    data = parse_fit(path, include_history_id=True, skip_history_ids=known_ids)
    identity = data["history"]["activity_id"]
    if data.get("already_exported"):
        return PreparedActivity(identity, skipped=True)
    entry = None
    history_error = data["history"]["error"]
    if history_error is None:
        try:
            entry = build_history_entry(data, identity)
        except Exception as error:
            history_error = str(error)
    return PreparedActivity(
        identity, data["session"],
        format_markdown(data, detect_device(data), path, gps, gps_limit, details),
        extract_gps_points(data["records"]), entry, history_error,
    )


def _worker_setup():
    # Le coordinateur seul traite Ctrl+C et inscrit les exports déjà publiés.
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def _prepared_results(paths, jobs, known_ids, details, gps, gps_limit):
    if jobs == 1:
        for path in paths:
            try:
                result = prepare_activity(path, frozenset(known_ids), details, gps, gps_limit)
            except Exception as error:
                result = error
            yield path, result
        return
    # spawn évite d'hériter du verrou du coordinateur et fonctionne aussi sous Windows.
    pool = ProcessPoolExecutor(max_workers=jobs, mp_context=multiprocessing.get_context("spawn"),
                               initializer=_worker_setup)
    pending = deque()
    remaining = iter(paths)
    def submit(path):
        return path, pool.submit(prepare_activity, path, frozenset(known_ids), details, gps, gps_limit)
    try:
        for _ in range(min(jobs, len(paths))):
            pending.append(submit(next(remaining)))
        while pending:
            path, future = pending.popleft()
            try:
                result = future.result()
            except Exception as error:
                result = error
            yield path, result
            # L'ordre stable rend les noms indépendants de la vitesse des travailleurs.
            del result, future
            path = next(remaining, None)
            if path is not None:
                pending.append(submit(path))
    finally:
        for _, future in pending:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)


@contextmanager
def _finish_publication_on_interrupt():
    interrupted = False
    def remember_interrupt(signum, frame):
        nonlocal interrupted
        interrupted = True
    previous = signal.signal(signal.SIGINT, remember_interrupt)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)
    if interrupted:
        raise KeyboardInterrupt


def run_batch(directory: Path, jobs: int, *, details=False, gps=False, gps_limit=30) -> int:
    paths = files.find_activity_files(directory)
    try:
        entries = files.read_activity_history()
    except Exception as error:
        raise ValueError(f"Historique inutilisable : {error}. Lancez --sync-history.") from error
    history_dir = files.activity_history_path().parent
    known_ids = {entry.activity_id for entry in entries
                 if entry.link is not None and _usable_markdown(history_dir / entry.link)}
    updates = []
    exported = skipped = failed = processed = 0
    history_warnings = 0
    interrupted = False
    infrastructure_error = False
    print(f"Batch : {len(paths)} fichier(s), {min(jobs, len(paths))} processus, détails {'oui' if details else 'non'}.",
          file=sys.stderr)
    results = _prepared_results(paths, min(jobs, max(1, len(paths))), known_ids, details, gps, gps_limit)
    try:
        for path, result in results:
            processed += 1
            try:
                if isinstance(result, Exception):
                    raise result
                if result.skipped or result.activity_id in known_ids:
                    skipped += 1
                    print(f"[{processed}/{len(paths)}] Déjà exporté : {path}", file=sys.stderr)
                    continue
                target, _ = files.plan_output_paths(result.session, path)
                points = result.gps_points
                gpx = build_gpx(points, target.stem) if has_gps_points(points) else None
                # Une interruption pendant la transaction est différée jusqu'à
                # l'enregistrement de son résultat dans la liste à publier.
                with _finish_publication_on_interrupt():
                    files.ensure_workdirs()
                    archive = files.export_activity(path, target, result.markdown, gpx)
                    exported += 1
                    if result.activity_id is not None:
                        known_ids.add(result.activity_id)
                    if result.entry is not None:
                        updates.append((result.entry, target))
                    if result.history_error:
                        history_warnings += 1
                        print(f"Attention : historique non préparé : {result.history_error}. Archive : {archive}",
                              file=sys.stderr)
                    print(f"[{processed}/{len(paths)}] Markdown : {target} ; archive : {archive}", file=sys.stderr)
            except Exception as error:
                failed += 1
                print(f"[{processed}/{len(paths)}] Échec : {path} : {error}", file=sys.stderr)
    except KeyboardInterrupt:
        interrupted = True
        print("Interruption : arrêt des nouvelles tâches, inscription des exports réussis…", file=sys.stderr)
    except Exception as error:
        infrastructure_error = True
        print(f"Échec du batch : {error}", file=sys.stderr)
    finally:
        try:
            if updates:
                files.update_activity_histories(updates)
        except Exception as error:
            history_warnings += 1
            print(f"Attention : historique des activités non mis à jour : {error}. "
                  f"Archives dans {history_dir} ; reprise avec --sync-history.", file=sys.stderr)
        finally:
            results.close()
    status = ("avertissement, reprise avec --sync-history" if history_warnings
              else "mis à jour" if updates else "inchangé")
    print(f"Bilan : {exported} exporté(s), {skipped} ignoré(s), {failed} échoué(s), "
          f"{len(paths) - processed} non traité(s) ; historique : {status}.", file=sys.stderr)
    return 130 if interrupted else (1 if failed or infrastructure_error else 0)


def _usable_markdown(path: Path) -> bool:
    return (path.suffix.lower() == ".md" and not path.is_symlink() and path.is_file()
            and path.resolve() != files.activity_history_path().resolve())


def sync_history() -> None:
    from extractor import parse_fit

    entries, original, broken, warnings = files.load_history_for_sync()
    directory = files.activity_history_path().parent.resolve()
    paths = files.find_activity_files(directory) if directory.exists() else []
    by_id = {entry.activity_id: entry for entry in entries}
    families = {}
    # Toutes les archives sont lues avant toute publication ou sauvegarde.
    for index, path in enumerate(paths, 1):
        try:
            data = parse_fit(path, include_history_id=True, skip_history_ids=frozenset(by_id))
            if data["history"]["error"]:
                raise ValueError(data["history"]["error"])
            identity = data["history"]["activity_id"]
            if identity not in by_id:
                by_id[identity] = build_history_entry(data, identity)
            target, duplicate = files.archive_markdown_candidate(path)
            identities, ambiguous = families.setdefault(target, (set(), False))
            identities.add(identity)
            families[target] = (identities, ambiguous or duplicate)
        except Exception as error:
            raise ValueError(f"Archive illisible : {path} : {error}. Registre conservé.") from error
        if index % 50 == 0:
            print(f"Synchronisation : {index}/{len(paths)} archives vérifiées.", file=sys.stderr)

    candidates = {}
    for target, (identities, ambiguous) in families.items():
        if ambiguous or len(identities) != 1:
            warnings.append(f"Association ambiguë : {target} (_dupN ou plusieurs FIT)")
        elif _usable_markdown(target):
            identity = next(iter(identities))
            candidates.setdefault(identity, []).append(target)
        else:
            warnings.append(f"Markdown manquant : {target}")

    owners = {}
    for entry in by_id.values():
        if entry.link is not None and _usable_markdown(directory / entry.link):
            owners.setdefault((directory / entry.link).resolve(), set()).add(entry.activity_id)
    preserved = set()
    reserved = {}
    for identity, entry in list(by_id.items()):
        target = directory / entry.link if entry.link is not None else None
        valid = target is not None and _usable_markdown(target)
        if valid:
            # Un lien existant peut trancher une famille _dupN, mais pas contredire
            # l'identité de toutes ses archives ni être partagé entre activités.
            family = families.get(target.resolve())
            valid = (len(owners[target.resolve()]) == 1
                     and (family is None or identity in family[0]))
        if valid:
            preserved.add(identity)
            reserved[target.resolve()] = identity
    for identity, entry in list(by_id.items()):
        if identity not in preserved:
            if entry.link is not None:
                warnings.append(f"Lien indisponible ou incohérent : {entry.link}")
            choices = [path for path in candidates.get(identity, [])
                       if reserved.get(path.resolve(), identity) == identity]
            target = choices[0] if len(choices) == 1 else None
            if len(choices) > 1:
                warnings.append(f"Plusieurs Markdown pour l’activité {identity} : aucun lien choisi")
            link = Path(os.path.relpath(target, directory)).as_posix() if target is not None else None
            by_id[identity] = replace(entry, link=link)

    for path in files.find_activity_files(directory, (".md",)) if directory.exists() else []:
        if path == files.activity_history_path():
            continue
        if path not in families:
            warnings.append(f"Markdown sans archive FIT correspondante : {path}")
    result = sort_history(list(by_id.values()))
    render_history(result)
    if broken and not result:
        raise ValueError("Aucune donnée récupérable : registre cassé conservé")
    if broken:
        backup = files.backup_activity_history(original)
        print(f"Sauvegarde de l’historique : {backup}", file=sys.stderr)
    files.write_activity_history(result)
    for warning in warnings:
        print(f"Attention : {warning}", file=sys.stderr)
    print(f"Historique {'réparé' if broken else 'synchronisé'} : {len(result)} activité(s), "
          f"{len(paths)} archive(s) vérifiée(s), {len(result) - len(entries)} ajout(s).", file=sys.stderr)
