from contextlib import ExitStack, redirect_stderr
from dataclasses import replace
import gzip
import hashlib
import io
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import batch_processing as batch
import extractor
import file_manager as files
from activity_history import build_history_entry, parse_history, render_history


def synthetic_fit(seed=0, gps=True):
    """Petit FIT valide construit en mémoire ; aucune donnée personnelle."""
    start = 1100000000 + seed * 3600
    def definition(local, global_number, fields):
        return (bytes([0x40 | local, 0, 0]) + struct.pack("<H", global_number)
                + bytes([len(fields)]) + b"".join(bytes(field) for field in fields))
    payload = definition(0, 18, [(2, 4, 0x86), (5, 1, 0), (7, 4, 0x86),
                                  (8, 4, 0x86), (9, 4, 0x86)])
    payload += b"\0" + struct.pack("<IBIII", start, 1, 10000, 10000, 3000)
    fields = [(253, 4, 0x86), (5, 4, 0x86), (6, 2, 0x84), (3, 1, 2), (2, 2, 0x84)]
    if gps:
        fields += [(0, 4, 0x85), (1, 4, 0x85)]
    payload += definition(1, 20, fields)
    for index in range(11):
        payload += b"\1" + struct.pack("<IIHBH", start + index, index * 300, 3000, 120 + index, 3000 + index)
        if gps:
            payload += struct.pack("<ii", 500000000 + index * 100, 10000000 + index * 100)
    header = struct.pack("<BBHI4s", 12, 16, 100, len(payload), b".FIT")
    raw = header + payload
    crc = 0
    for byte in raw:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return raw + struct.pack("<H", crc)


class BatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "input"
        self.source.mkdir()
        self.export = self.root / "export"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(files, "EXPORT_DIR", self.export))
        self.stack.enter_context(patch.object(files, "IMPORT_DIR", self.root / "import"))
        self.output = io.StringIO()
        self.stack.enter_context(redirect_stderr(self.output))

    def source_fit(self, name="a.fit", seed=0, gps=True):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = synthetic_fit(seed, gps)
        path.write_bytes(gzip.compress(raw) if name.lower().endswith(".gz") else raw)
        return path

    def entries(self):
        return parse_history(files.activity_history_path().read_text())

    def test_batch_deduplicates_gzip_and_retries_missing_markdown(self):
        first = self.source_fit()
        duplicate = self.source_fit("nested/b.FIT.GZ")
        other = self.source_fit("c.fit", seed=1, gps=False)
        with patch.object(files, "write_activity_history", wraps=files.write_activity_history) as write:
            self.assertEqual(batch.run_batch(self.source, 1), 0)
        write.assert_called_once()
        self.assertFalse(first.exists())
        self.assertFalse(other.exists())
        self.assertTrue(duplicate.exists())
        self.assertEqual(len(self.entries()), 2)
        self.assertEqual(len(list(self.export.glob("*.gpx"))), 1)
        with patch.object(extractor, "FitFile", side_effect=AssertionError("pas de parsing")):
            self.assertEqual(batch.run_batch(self.source, 1), 0)
        identity = hashlib.sha256(synthetic_fit()).hexdigest()
        entry = next(entry for entry in self.entries() if entry.activity_id == identity)
        (self.export / entry.link).unlink()
        self.assertEqual(batch.run_batch(self.source, 1), 0)
        self.assertFalse(duplicate.exists())
        self.assertEqual(len(self.entries()), 2)

    def test_partial_failure_and_publication_rollback(self):
        good = self.source_fit()
        bad = self.source / "b.fit"
        bad.write_bytes(b"bad FIT")
        failing = self.source_fit("c.fit", seed=2)
        before = failing.read_bytes()
        original = Path.unlink
        def fail_source(path, *args, **kwargs):
            if path == failing:
                raise OSError("archive non supprimable")
            return original(path, *args, **kwargs)
        with patch.object(Path, "unlink", autospec=True, side_effect=fail_source):
            self.assertEqual(batch.run_batch(self.source, 1), 1)
        self.assertFalse(good.exists())
        self.assertEqual(failing.read_bytes(), before)
        self.assertEqual(bad.read_bytes(), b"bad FIT")
        self.assertEqual(len(self.entries()), 1)
        self.assertEqual(len(list(self.export.glob("*.fit"))), 1)
        self.assertIn("2 échoué(s)", self.output.getvalue())

    def test_invalid_history_blocks_batch_before_parsing(self):
        source = self.source_fit()
        self.export.mkdir()
        files.activity_history_path().write_bytes(b"broken")
        with patch.object(extractor, "FitFile") as parser:
            with self.assertRaisesRegex(ValueError, "--sync-history"):
                batch.run_batch(self.source, 1)
        parser.assert_not_called()
        self.assertTrue(source.exists())
        self.assertEqual(files.activity_history_path().read_bytes(), b"broken")

    def test_history_failure_keeps_successful_export(self):
        source = self.source_fit()
        with patch.object(files.os, "replace", side_effect=OSError("historique indisponible")):
            self.assertEqual(batch.run_batch(self.source, 1), 0)
        self.assertFalse(source.exists())
        self.assertEqual(len(list(self.export.glob("*.fit"))), 1)
        self.assertIn("--sync-history", self.output.getvalue())

    def test_interrupt_registers_only_published_activities(self):
        self.source_fit()
        second = self.source_fit("b.fit", 1)
        prepare = batch.prepare_activity
        def interrupt(path, *args):
            if path == second:
                raise KeyboardInterrupt
            return prepare(path, *args)
        with patch.object(batch, "prepare_activity", side_effect=interrupt):
            self.assertEqual(batch.run_batch(self.source, 1), 130)
        self.assertEqual(len(self.entries()), 1)
        self.assertTrue(second.exists())

    @unittest.skipIf(os.name == "nt", "Signal POSIX")
    def test_interrupt_during_publication_is_deferred(self):
        self.source_fit()
        original_export = files.export_activity
        def interrupt(*args, **kwargs):
            os.kill(os.getpid(), signal.SIGINT)
            return original_export(*args, **kwargs)
        with patch.object(files, "export_activity", side_effect=interrupt):
            self.assertEqual(batch.run_batch(self.source, 1), 130)
        self.assertEqual(len(self.entries()), 1)

    def test_inventory_skips_symlinks_and_staging(self):
        source = self.source_fit()
        self.source_fit("nested/b.fit.gz", 1)
        self.source_fit(".fit-export-interrupted/c.fit", 2)
        (self.source / "link.fit").symlink_to(source)
        (self.source / "cycle").symlink_to(self.source, target_is_directory=True)
        (self.source / "other.tcx").write_text("ignored")
        self.assertEqual(len(files.find_activity_files(self.source)), 2)

    def test_empty_batch_does_not_create_export(self):
        self.assertEqual(batch.run_batch(self.source, 1), 0)
        self.assertFalse(self.export.exists())

    def test_sync_restores_deleted_row_and_backs_up_exact_bytes(self):
        self.source_fit()
        self.source_fit("b.fit.gz", 1)
        batch.run_batch(self.source, 1)
        history = files.activity_history_path()
        original_entries = self.entries()
        lines = history.read_text().splitlines(keepends=True)
        damaged = "".join(line for line in lines if original_entries[0].activity_id not in line).encode()
        history.write_bytes(damaged)
        batch.sync_history()
        self.assertEqual(self.entries(), original_entries)
        backups = list(self.export.glob("historique_activites.md.bak-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), damaged)
        history.write_text(render_history(original_entries[1:]))
        batch.sync_history()
        self.assertEqual(self.entries(), original_entries)
        self.assertEqual(len(list(self.export.glob("historique_activites.md.bak-*"))), 1)

    def test_sync_recreates_absent_history_without_modifying_exports(self):
        self.source_fit()
        batch.run_batch(self.source, 1)
        history = files.activity_history_path()
        expected = history.read_bytes()
        history.unlink()
        before = {path.name: path.read_bytes() for path in self.export.iterdir()}
        batch.sync_history()
        self.assertEqual(history.read_bytes(), expected)
        self.assertEqual({path.name: path.read_bytes() for path in self.export.iterdir() if path != history}, before)

    def test_sync_preserves_valid_external_rows_and_recovers_malformed_row(self):
        source = self.source_fit()
        outside_data = extractor.parse_fit(source, include_history_id=True)
        outside = replace(build_history_entry(outside_data, "a" * 64), link="../outside.md")
        (self.root / "outside.md").write_text("external")
        batch.run_batch(self.source, 1)
        history = files.activity_history_path()
        text = render_history([outside, *self.entries()])
        text = text.replace("| 0.03 |", "| invalid |", 1)
        # La ligne corrompue externe n'est pas récupérable, celle de l'archive l'est.
        history.write_text(text)
        batch.sync_history()
        self.assertEqual(len(self.entries()), 1)
        self.assertIn("irrécupérable", self.output.getvalue())
        # Une simple troncature du compteur préserve aussi les lignes externes.
        history.write_text(render_history([outside, *self.entries()]).split("<!-- fit-extractor-history:end")[0])
        batch.sync_history()
        self.assertEqual(len(self.entries()), 2)
        self.assertEqual(next(e for e in self.entries() if e.activity_id == "a" * 64), outside)

    def test_sync_failure_preserves_history_and_source_bytes(self):
        self.source_fit()
        batch.run_batch(self.source, 1)
        history = files.activity_history_path()
        damaged = history.read_bytes().replace(b"rows:1", b"rows:9")
        for stage in ("archive", "backup", "write", "replace"):
            with self.subTest(stage=stage), ExitStack() as stack:
                history.write_bytes(damaged)
                if stage == "archive":
                    stack.enter_context(patch.object(extractor, "parse_fit", side_effect=OSError("read")))
                elif stage == "backup":
                    stack.enter_context(patch.object(files, "backup_activity_history", side_effect=OSError("backup")))
                elif stage == "write":
                    stack.enter_context(patch.object(files, "write_activity_history", side_effect=OSError("write")))
                else:
                    stack.enter_context(patch.object(files.os, "replace", side_effect=OSError("replace")))
                with self.assertRaises((ValueError, OSError)):
                    batch.sync_history()
                self.assertEqual(history.read_bytes(), damaged)

    def test_failed_backup_removes_partial_file_and_preserves_history(self):
        self.source_fit()
        batch.run_batch(self.source, 1)
        history = files.activity_history_path()
        damaged = history.read_bytes().replace(b"rows:1", b"rows:8")
        history.write_bytes(damaged)
        with patch.object(files.os, "fsync", side_effect=OSError("disque plein")):
            with self.assertRaises(OSError):
                batch.sync_history()
        self.assertEqual(history.read_bytes(), damaged)
        self.assertEqual(list(self.export.glob("*.bak-*")), [])

    def test_invalid_utf8_row_is_recovered_from_archive(self):
        self.source_fit()
        batch.run_batch(self.source, 1)
        history = files.activity_history_path()
        original = history.read_bytes()
        damaged = original.replace(b"Course", b"Cou\xffrse")
        history.write_bytes(damaged)
        batch.sync_history()
        self.assertEqual(history.read_bytes(), original)
        self.assertEqual(next(self.export.glob("*.bak-*")).read_bytes(), damaged)

    def test_sync_preserves_known_link_in_ambiguous_family(self):
        self.source_fit()
        batch.run_batch(self.source, 1)
        entry = self.entries()[0]
        target = self.export / entry.link
        (target.with_name(target.stem + "_dup1.fit")).write_bytes(synthetic_fit(1))
        batch.sync_history()
        actual = {row.activity_id: row for row in self.entries()}
        self.assertEqual(actual[entry.activity_id], entry)
        self.assertIsNone(actual[hashlib.sha256(synthetic_fit(1)).hexdigest()].link)

    def test_sync_clears_conflicting_and_missing_links(self):
        self.source_fit()
        self.source_fit("b.fit", 1)
        batch.run_batch(self.source, 1)
        first, second = self.entries()
        history = files.activity_history_path()
        history.write_text(render_history([first, replace(second, link=first.link)]))
        batch.sync_history()
        self.assertEqual(next(row for row in self.entries() if row.activity_id == second.activity_id), second)
        # Un lien sans archive et sans fichier est retiré mais l'identité reste.
        external = replace(first, activity_id="f" * 64, link="missing.md")
        history.write_text(render_history([*self.entries(), external]))
        batch.sync_history()
        self.assertIsNone(next(row for row in self.entries() if row.activity_id == "f" * 64).link)

    def test_sync_refuses_future_version_symlink_and_empty_recovery(self):
        self.export.mkdir()
        history = files.activity_history_path()
        for raw in (b"broken", render_history([]).replace(":v1", ":v99").encode()):
            history.write_bytes(raw)
            with self.assertRaises(ValueError):
                batch.sync_history()
            self.assertEqual(history.read_bytes(), raw)
        history.unlink()
        history.symlink_to(self.root / "missing")
        with self.assertRaises(ValueError):
            batch.sync_history()
        self.assertTrue(history.is_symlink())

    def test_sync_ambiguous_archive_families_do_not_invent_links(self):
        self.export.mkdir()
        (self.export / "session.fit").write_bytes(synthetic_fit())
        (self.export / "session_dup1.fit.gz").write_bytes(gzip.compress(synthetic_fit(1)))
        (self.export / "session.md").write_text("ambiguous")
        (self.export / "orphan.md").write_text("orphan")
        batch.sync_history()
        self.assertEqual(len(self.entries()), 2)
        self.assertTrue(all(entry.link is None for entry in self.entries()))
        self.assertIn("Association ambiguë", self.output.getvalue())
        self.assertIn("sans archive FIT", self.output.getvalue())

    def test_bulk_history_resolves_reassigned_links(self):
        self.export.mkdir()
        data = {"session": {}, "records": []}
        first = build_history_entry(data, "a" * 64)
        second = build_history_entry(data, "b" * 64)
        target = self.export / "same.md"
        files.update_activity_histories([(first, target), (second, target)])
        self.assertIsNone(self.entries()[0].link)
        self.assertEqual(self.entries()[1].link, "same.md")

    def test_jobs_and_cli_invalid_options(self):
        with patch.object(batch.os, "cpu_count", return_value=22), \
                patch.object(batch.os, "sched_getaffinity", return_value=set(range(22)), create=True):
            self.assertEqual(batch.parse_jobs("auto"), 4)
            self.assertEqual(batch.parse_jobs("all"), 22)
            self.assertEqual(batch.parse_jobs("8"), 8)
        for args in (["--jobs", "0", "--batch", str(self.source)],
                     ["--batch", str(self.source), "--stdout"],
                     ["--sync-history", "--jobs", "2"],
                     ["--sync-history", "--batch", str(self.source)]):
            with self.subTest(args=args), patch("sys.argv", ["extractor.py", *args]), \
                    patch.object(extractor, "activity_write_lock") as lock:
                with self.assertRaises(SystemExit) as error:
                    extractor.main()
                self.assertEqual(error.exception.code, 2)
                lock.assert_not_called()


class ProcessTests(unittest.TestCase):
    def test_real_process_batch_matches_sequential_and_lock_blocks_all_writers(self):
        repo = Path(extractor.__file__).parent
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outputs = []
            for jobs in (1, 2):
                project = root / str(jobs)
                project.mkdir()
                for source in repo.glob("*.py"):
                    shutil.copy2(source, project / source.name)
                incoming = project / "input"
                incoming.mkdir()
                for number in range(4):
                    (incoming / f"{number}.fit").write_bytes(synthetic_fit(number, number % 2 == 0))
                (incoming / "duplicate.fit.gz").write_bytes(gzip.compress(synthetic_fit()))
                command = [sys.executable, "-B", str(project / "extractor.py")]
                result = subprocess.run([*command, "--batch", str(incoming), "--jobs", str(jobs)],
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("4 exporté(s), 1 ignoré(s)", result.stderr)
                outputs.append({p.name: p.read_bytes() for p in (project / "export").iterdir()})
                with patch.object(files, "EXPORT_DIR", project / "export"):
                    with files.activity_write_lock():
                        for args in (["--batch", str(incoming)], ["--sync-history"],
                                     [str(incoming / "duplicate.fit.gz")]):
                            result = subprocess.run([*command, *args], capture_output=True, text=True, timeout=10)
                            self.assertEqual(result.returncode, 1, result.stderr)
                            self.assertIn("autre commande", result.stderr)
                        # stdout fonctionne même pendant un autre export.
                        result = subprocess.run([*command, str(incoming / "duplicate.fit.gz"), "--stdout"],
                                                capture_output=True, text=True, timeout=10)
                        self.assertEqual(result.returncode, 0, result.stderr)
                    with files.activity_write_lock():
                        pass
            self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main()
