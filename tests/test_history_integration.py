import copy
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import replace
from datetime import datetime
import gzip
import hashlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import extractor
import file_manager
from activity_history import build_history_entry, parse_history, render_history


def sample_data():
    return {
        "session": {"start_time": (datetime(2026, 10, 2, 10, 0), None),
                    "sport": ("running", None), "total_distance": (1234, "m"),
                    "total_timer_time": (600, "s")},
        "records": [], "laps": [], "hrv_intervals": [], "device_info": [],
        "user_profile": {}, "zones_target": {},
    }


class FingerprintTests(unittest.TestCase):
    def test_hash_uses_decompressed_bytes_with_one_read_and_parser(self):
        raw = b"synthetic FIT bytes"
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            variants = [raw, raw, gzip.compress(raw, mtime=1), gzip.compress(raw, mtime=2)]
            names = ["first.fit", "renamed.fit", "first.fit.gz", "second.FIT.GZ"]
            for name, content in zip(names, variants):
                path = directory / name
                path.write_bytes(content)
                original_read = Path.read_bytes
                with patch.object(Path, "read_bytes", autospec=True, side_effect=original_read) as read, \
                        patch.object(extractor, "FitFile") as parser:
                    parser.return_value.get_messages.return_value = []
                    data = extractor.parse_fit(path, include_history_id=True)
                    read.assert_called_once_with(path)
                    parser.assert_called_once()
                    self.assertEqual(parser.call_args.args[0].getvalue(), raw)
                    self.assertIsInstance(parser.call_args.kwargs["data_processor"], extractor.StandardUnitsDataProcessor)
                    self.assertEqual(data["history"], {"activity_id": hashlib.sha256(raw).hexdigest(), "error": None})

    def test_default_skips_hash_and_hash_error_does_not_fail_parsing(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source.fit"
            source.write_bytes(b"FIT")
            with patch.object(extractor, "FitFile") as parser, \
                    patch.object(extractor.hashlib, "sha256", side_effect=RuntimeError("hachage indisponible")) as digest:
                parser.return_value.get_messages.return_value = []
                self.assertNotIn("history", extractor.parse_fit(source))
                digest.assert_not_called()
                result = extractor.parse_fit(source, include_history_id=True)
                self.assertEqual(result["history"], {"activity_id": None, "error": "hachage indisponible"})


class HistoryIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.export_dir = self.root / "export"
        self.import_dir = self.root / "import"
        self.source = self.root / "source.fit"
        self.source.write_bytes(b"activity A")
        self.data = sample_data()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(file_manager, "EXPORT_DIR", self.export_dir))
        self.stack.enter_context(patch.object(file_manager, "IMPORT_DIR", self.import_dir))
        self.stack.enter_context(patch.object(extractor, "IMPORT_DIR", self.import_dir))
        self.history = file_manager.activity_history_path()

    def fake_parse(self, path, *, include_history_id=False):
        result = copy.deepcopy(self.data)
        if include_history_id:
            result["history"] = {"activity_id": hashlib.sha256(path.read_bytes()).hexdigest(), "error": None}
        return result

    def run_cli(self, *args, parse_error=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(extractor, "parse_fit", side_effect=parse_error or self.fake_parse) as parser, \
                patch("sys.argv", ["extractor.py", str(self.source), *map(str, args)]), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                extractor.main()
                code = 0
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue(), parser

    def seed_history(self):
        self.export_dir.mkdir(exist_ok=True)
        entry = replace(build_history_entry(self.data, "a" * 64), link="old.md")
        text = render_history([entry])
        self.history.write_text(text, encoding="utf-8")
        return text.encode("utf-8")

    def assert_no_temporaries(self):
        self.assertEqual(list(self.export_dir.glob(".fit-history-*")), [])

    def test_first_export_without_gps_and_same_fit_reprocessed(self):
        code, stdout, stderr, parser = self.run_cli()
        self.assertEqual((code, stdout), (0, ""))
        self.assertIn("GPX non généré", stderr)
        parser.assert_called_once_with(self.source, include_history_id=True)
        self.assertFalse(self.source.exists())
        entries = parse_history(self.history.read_text())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].link, "2026-10-02_running_001.md")
        archive = self.export_dir / "2026-10-02_running_001.fit"
        self.assertEqual(archive.read_bytes(), b"activity A")
        self.source.write_bytes(archive.read_bytes())
        self.assertEqual(self.run_cli()[0], 0)
        entries = parse_history(self.history.read_text())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].link, "2026-10-02_running_002.md")
        self.assertTrue(archive.exists())
        self.assert_no_temporaries()

    def test_import_order_is_not_date_order(self):
        for day in (20, 3, 12):
            self.source.write_bytes(str(day).encode())
            self.data["session"]["start_time"] = (datetime(2026, 9, day), None)
            self.assertEqual(self.run_cli()[0], 0)
        self.assertEqual([entry.start.day for entry in parse_history(self.history.read_text())], [20, 12, 3])

    def test_stdout_ignores_reserved_output_and_all_history_operations(self):
        with patch.object(extractor, "build_history_entry") as build, \
                patch.object(extractor, "update_activity_history") as update, \
                patch.object(extractor, "export_activity") as export:
            code, stdout, _, parser = self.run_cli("--stdout", "--details", "--output", self.history, "--force")
        self.assertEqual(code, 0)
        self.assertIn("# Activité", stdout)
        parser.assert_called_once_with(self.source, include_history_id=False)
        build.assert_not_called()
        update.assert_not_called()
        export.assert_not_called()
        self.assertTrue(self.source.exists())
        self.assertFalse(self.export_dir.exists())
        self.assertFalse(self.import_dir.exists())

    def test_options_do_not_change_history_metrics(self):
        self.assertEqual(self.run_cli()[0], 0)
        expected = parse_history(self.history.read_text())[0]
        self.source.write_bytes(b"activity A")
        self.assertEqual(self.run_cli("--details", "--gps", "--gps-limit", "1")[0], 0)
        actual = parse_history(self.history.read_text())[0]
        self.assertEqual(replace(actual, link=expected.link), expected)

    def test_invalid_arguments_and_parsing_failure_leave_history_untouched(self):
        before = self.seed_history()
        with patch.object(extractor, "update_activity_history") as update:
            result = self.run_cli("--gps-limit", "0")
            self.assertEqual(result[0], 2)
            result[3].assert_not_called()
            self.assertEqual(self.run_cli(parse_error=ValueError("FIT invalide"))[0], 1)
            update.assert_not_called()
        self.assertEqual(self.history.read_bytes(), before)
        self.assertEqual(self.source.read_bytes(), b"activity A")

    def test_export_failure_rolls_back_and_does_not_read_history(self):
        before = self.seed_history()
        target = self.export_dir / "session.md"
        target.write_bytes(b"old Markdown")
        gpx = target.with_suffix(".gpx")
        gpx.write_bytes(b"old GPX")
        original_unlink = Path.unlink

        def fail_source(path, *args, **kwargs):
            if path == self.source:
                raise OSError("suppression source refusée")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True, side_effect=fail_source), \
                patch.object(Path, "read_text", side_effect=AssertionError("lecture historique interdite")), \
                patch.object(extractor, "update_activity_history") as update:
            result = self.run_cli("--output", target, "--force")
        self.assertEqual(result[0], 1)
        update.assert_not_called()
        self.assertEqual(target.read_bytes(), b"old Markdown")
        self.assertEqual(gpx.read_bytes(), b"old GPX")
        self.assertEqual(self.source.read_bytes(), b"activity A")
        self.assertFalse(target.with_suffix(".fit").exists())
        self.assertEqual(self.history.read_bytes(), before)

    def test_history_preparation_errors_are_nonblocking(self):
        before = self.seed_history()
        with patch.object(extractor, "build_history_entry", side_effect=ValueError("préparation refusée")), \
                patch.object(extractor, "update_activity_history") as update:
            result = self.run_cli()
        self.assertEqual(result[0], 0)
        self.assertIn("préparation refusée", result[2])
        self.assertIn("Archive disponible pour reprise", result[2])
        self.assertFalse(self.source.exists())
        self.assertEqual(self.history.read_bytes(), before)
        update.assert_not_called()

    def test_history_hash_error_is_nonblocking_in_cli(self):
        self.data["history"] = {"activity_id": None, "error": "hachage refusé"}
        with patch.object(self, "fake_parse", return_value=self.data), \
                patch.object(extractor, "update_activity_history") as update:
            result = self.run_cli()
        self.assertEqual(result[0], 0)
        self.assertIn("hachage refusé", result[2])
        self.assertFalse(self.history.exists())
        self.assertFalse(self.source.exists())
        update.assert_not_called()

    def test_history_io_errors_preserve_old_bytes_and_keep_exports(self):
        for stage in ("read", "create", "write", "replace"):
            with self.subTest(stage=stage):
                self.source.write_bytes(b"activity A")
                before = self.seed_history()
                with ExitStack() as stack:
                    if stage == "read":
                        stack.enter_context(patch.object(Path, "read_text", side_effect=OSError("lecture refusée")))
                    elif stage == "create":
                        stack.enter_context(patch.object(file_manager.tempfile, "NamedTemporaryFile", side_effect=OSError("création refusée")))
                    elif stage == "write":
                        original_temporary = file_manager.tempfile.NamedTemporaryFile

                        def fail_write(**kwargs):
                            handle = original_temporary(**kwargs)
                            handle.write = Mock(side_effect=OSError("écriture refusée"))
                            return handle

                        stack.enter_context(patch.object(file_manager.tempfile, "NamedTemporaryFile", side_effect=fail_write))
                    else:
                        stack.enter_context(patch.object(file_manager.os, "replace", side_effect=OSError("remplacement refusé")))
                    result = self.run_cli()
                self.assertEqual(result[0], 0)
                self.assertIn("historique des activités non mis à jour", result[2])
                self.assertIn("Markdown généré", result[2])
                self.assertEqual(self.history.read_bytes(), before)
                self.assertFalse(self.source.exists())
                self.assertTrue(list(self.export_dir.glob("2026-*.fit")))
                self.assert_no_temporaries()

    def test_cleanup_failure_reports_path_and_primary_error(self):
        before = self.seed_history()
        original_unlink = Path.unlink

        def fail_cleanup(path, *args, **kwargs):
            if path.name.startswith(".fit-history-"):
                raise OSError("nettoyage refusé")
            return original_unlink(path, *args, **kwargs)

        with patch.object(file_manager.os, "replace", side_effect=OSError("remplacement refusé")), \
                patch.object(Path, "unlink", autospec=True, side_effect=fail_cleanup):
            result = self.run_cli()
        self.assertEqual(result[0], 0)
        self.assertIn("remplacement refusé", result[2])
        self.assertIn("nettoyage refusé", result[2])
        self.assertEqual(self.history.read_bytes(), before)
        leftover, = self.export_dir.glob(".fit-history-*")
        self.assertIn(str(leftover), result[2])

    def test_invalid_history_is_preserved(self):
        valid = self.seed_history()
        for content in (b"", b"manual notes", b"\xff", valid.replace(b":v1", b":v2"), valid[:-35]):
            with self.subTest(content=content[:20]):
                self.history.write_bytes(content)
                self.source.write_bytes(b"activity A")
                result = self.run_cli()
                self.assertEqual(result[0], 0)
                self.assertIn("historique des activités non mis à jour", result[2])
                self.assertEqual(self.history.read_bytes(), content)
                self.assert_no_temporaries()

    def test_symbolic_history_is_refused_including_dangling_link(self):
        self.export_dir.mkdir()
        destination = self.root / "real-history.md"
        self.history.symlink_to(destination)
        for existing in (False, True):
            with self.subTest(existing=existing):
                if existing:
                    destination.write_bytes(b"private content")
                self.source.write_bytes(b"activity A")
                result = self.run_cli()
                self.assertEqual(result[0], 0)
                self.assertIn("Historique symbolique refusé", result[2])
                self.assertTrue(self.history.is_symlink())
                if existing:
                    self.assertEqual(destination.read_bytes(), b"private content")
                else:
                    self.assertFalse(destination.exists())

    def test_reserved_path_and_aliases_are_rejected_before_publication(self):
        targets = [self.history, self.export_dir / ".." / "export" / self.history.name]
        alias_dir = self.root / "alias"
        alias_dir.symlink_to(self.export_dir, target_is_directory=True)
        targets.append(alias_dir / self.history.name)
        for target in targets:
            result = self.run_cli("--output", target, "--force")
            self.assertEqual(result[0], 1)
            self.assertIn("Chemin réservé", result[2])
            self.assertTrue(self.source.exists())
            self.assertFalse(self.history.exists())
        before = self.seed_history()
        alias = self.root / "hardlink.md"
        os.link(self.history, alias)
        self.assertEqual(self.run_cli("--output", alias, "--force")[0], 1)
        self.assertEqual(self.history.read_bytes(), before)
        self.assertEqual(alias.read_bytes(), before)
        self.assertEqual(self.source.read_bytes(), b"activity A")

    def test_symbolic_history_loop_does_not_block_other_exports(self):
        self.export_dir.mkdir()
        self.history.symlink_to(self.history.name)
        result = self.run_cli()
        self.assertEqual(result[0], 0)
        self.assertIn("Historique symbolique refusé", result[2])
        self.assertFalse(self.source.exists())
        self.assertTrue(self.history.is_symlink())
        self.source.write_bytes(b"activity B")
        self.assertEqual(self.run_cli("--output", self.history, "--force")[0], 1)
        self.assertTrue(self.source.exists())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO indisponibles")
    def test_non_regular_history_is_not_opened(self):
        self.export_dir.mkdir()
        os.mkfifo(self.history)
        with patch.object(Path, "read_text", side_effect=AssertionError("lecture bloquante interdite")):
            result = self.run_cli()
        self.assertEqual(result[0], 0)
        self.assertIn("L’historique n’est pas un fichier", result[2])
        self.assertFalse(self.source.exists())

    def test_custom_output_force_archive_collision_and_stale_gpx(self):
        target = self.root / "Mes séances" / "course %20 #?|()é.md"
        self.data["records"] = [{"position_lat": (45, "deg"), "position_long": (3, "deg")}]
        self.assertEqual(self.run_cli("--output", target)[0], 0)
        before = parse_history(self.history.read_text())[0]
        self.assertEqual((self.export_dir / before.link).resolve(), target.resolve())
        self.assertTrue(target.with_suffix(".gpx").exists())
        self.source.write_bytes(b"activity B")
        self.data["records"] = []
        self.assertEqual(self.run_cli("--output", target, "--force")[0], 0)
        entries = {entry.activity_id: entry for entry in parse_history(self.history.read_text())}
        self.assertEqual(len(entries), 2)
        self.assertIsNone(entries[before.activity_id].link)
        self.assertFalse(target.with_suffix(".gpx").exists())
        self.assertEqual(target.with_suffix(".fit").read_bytes(), b"activity A")
        self.assertEqual((target.parent / (target.stem + "_dup1.fit")).read_bytes(), b"activity B")

    def test_warning_names_actual_archive_after_forced_export(self):
        target = self.export_dir / "session.md"
        self.assertEqual(self.run_cli("--output", target)[0], 0)
        before = self.history.read_bytes()
        self.source.write_bytes(b"activity B")
        with patch.object(extractor, "update_activity_history", side_effect=OSError("registre indisponible")):
            result = self.run_cli("--output", target, "--force")
        self.assertEqual(result[0], 0)
        self.assertIn(f"Archive disponible pour reprise : {target.parent / 'session_dup1.fit'}", result[2])
        self.assertEqual(self.history.read_bytes(), before)
        self.assertEqual(parse_history(self.history.read_text())[0].link, "session.md")
        self.assertEqual((target.parent / "session_dup1.fit").read_bytes(), b"activity B")

    def test_reused_automatic_filename_invalidates_old_link(self):
        self.assertEqual(self.run_cli()[0], 0)
        old_id = parse_history(self.history.read_text())[0].activity_id
        for path in self.export_dir.glob("2026-*"):
            path.unlink()
        self.source.write_bytes(b"activity B")
        self.assertEqual(self.run_cli()[0], 0)
        entries = {entry.activity_id: entry for entry in parse_history(self.history.read_text())}
        self.assertEqual(len(entries), 2)
        self.assertIsNone(entries[old_id].link)

    def test_gzip_archive_keeps_exact_compressed_bytes(self):
        self.source = self.root / "source.FIT.GZ"
        content = gzip.compress(b"synthetic FIT", mtime=1)
        self.source.write_bytes(content)
        self.assertEqual(self.run_cli()[0], 0)
        archive, = self.export_dir.glob("*.fit.gz")
        self.assertEqual(archive.read_bytes(), content)
        self.assertFalse(self.source.exists())
        self.assertEqual(list(self.export_dir.glob("*.fit")), [])

    def test_global_history_ignores_current_working_directory(self):
        current = Path.cwd()
        self.addCleanup(os.chdir, current)
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        os.chdir(elsewhere)
        self.assertEqual(self.run_cli("--output", "session.md")[0], 0)
        self.assertTrue(self.history.exists())
        self.assertEqual(parse_history(self.history.read_text())[0].link, "../elsewhere/session.md")
        self.assertFalse((elsewhere / "export").exists())


if __name__ == "__main__":
    unittest.main()
