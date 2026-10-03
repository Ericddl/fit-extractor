import copy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import unittest

from activity_history import build_history_entry, parse_history, render_history, upsert_history


def activity(number=1, **session):
    return build_history_entry({"session": session, "records": []}, f"{number:064x}")


class EntryTests(unittest.TestCase):
    def test_session_fields_units_and_rounding(self):
        data = {"session": {
            "start_time": (datetime(2026, 9, 22, 10, 17, 3), None),
            "sport": ("swimming", None), "sub_sport": ("open_water", None),
            "total_distance": (1723.4, "m"), "total_timer_time": (90061.9, "s"),
            "total_elapsed_time": (100000, "s"), "total_ascent": (12.8, "m"),
            "avg_heart_rate": (138.2, "bpm"), "max_heart_rate": (161, "bpm"),
            "training_stress_score": (43.28, "tss"), "total_training_effect": (2.43, None),
        }, "records": []}
        original = copy.deepcopy(data)
        entry = build_history_entry(data, "a" * 64)
        self.assertEqual(entry.start, datetime(2026, 9, 22, 10, 17, 3, tzinfo=timezone.utc))
        self.assertEqual(entry.sport, "Natation eau libre")
        self.assertEqual((entry.distance, entry.duration, entry.ascent), ("1.72", "25:01:01", "13"))
        self.assertEqual((entry.avg_heart_rate, entry.max_heart_rate, entry.tss, entry.training_effect),
                         ("138", "161", "43.3", "2.4"))
        self.assertEqual(data, original)
        data["session"]["total_distance"] = (1.7234, "km")
        self.assertEqual(build_history_entry(data, "a" * 64), entry)

    def test_missing_metrics_do_not_use_records_or_elapsed_time(self):
        entry = build_history_entry({
            "session": {"total_elapsed_time": (60, "s"), "total_anaerobic_training_effect": (4, None)},
            "records": [{"distance": (2, "km"), "heart_rate": (130, "bpm"), "altitude": (10, "m")}],
        }, "a" * 64)
        self.assertEqual((entry.distance, entry.duration, entry.ascent, entry.avg_heart_rate,
                          entry.max_heart_rate, entry.tss, entry.training_effect), ("-",) * 7)
        self.assertIsNone(entry.start)

    def test_invalid_numbers_and_units_become_missing(self):
        for value in (None, True, "12", [12], (12,), float("nan"), float("inf"), -1, 10 ** 400):
            with self.subTest(value=repr(value)):
                entry = activity(total_distance=(value, "m"), total_timer_time=(value, "s"),
                                 avg_heart_rate=(value, "bpm"), total_training_effect=(value, None))
                self.assertEqual((entry.distance, entry.duration, entry.avg_heart_rate, entry.training_effect), ("-",) * 4)
        entry = activity(total_distance=(20, "yards"), total_timer_time=(10, None),
                         total_ascent=(2, None), training_stress_score=(5, None),
                         total_training_effect=(2, "tss"))
        self.assertEqual((entry.distance, entry.duration, entry.ascent, entry.tss, entry.training_effect), ("-",) * 5)
        self.assertEqual(activity(total_distance=12).distance, "-")

    def test_zero_and_positive_heart_rate(self):
        entry = activity(total_distance=(-0.0, "m"), total_timer_time=(0, "s"), total_ascent=(0, "m"),
                         avg_heart_rate=(0, "bpm"), max_heart_rate=(0.4, "bpm"),
                         training_stress_score=(0, "tss"), total_training_effect=(0, None))
        self.assertEqual((entry.distance, entry.duration, entry.ascent, entry.tss, entry.training_effect),
                         ("0.00", "00:00:00", "0", "0.0", "0.0"))
        self.assertEqual((entry.avg_heart_rate, entry.max_heart_rate), ("-", "-"))
        self.assertEqual(activity(avg_heart_rate=(0.6, "bpm")).avg_heart_rate, "1")

    def test_dates_use_utc_and_first_valid_record_in_file_order(self):
        aware = datetime(2026, 10, 2, 0, 30, 1, 123456, tzinfo=timezone(timedelta(hours=2)))
        expected = datetime(2026, 10, 1, 22, 30, 1, 123456, tzinfo=timezone.utc)
        self.assertEqual(activity(start_time=(aware, None)).start, expected)
        data = {"session": {"start_time": (date(2026, 10, 2), None), "timestamp": (aware, None)},
                "records": [{"local_timestamp": (aware, None)}, {"timestamp": ("invalid", None)},
                            {"timestamp": (aware, None)}, {"timestamp": (datetime(2020, 1, 1), None)}]}
        self.assertEqual(build_history_entry(data, "b" * 64).start, expected)
        data["records"] = []
        self.assertIsNone(build_history_entry(data, "b" * 64).start)

    def test_sport_labels_and_fallbacks(self):
        cases = [
            ("running", "generic", "Course"), ("running", "trail", "Trail"),
            ("cycling", None, "Vélo"), ("cycling", "road", "Vélo route"),
            ("cycling", "mountain", "VTT"), ("swimming", "open_water", "Natation eau libre"),
            ("swimming", "lap_swimming", "Natation en bassin"), ("running", "running", "Course"),
            ("running", "treadmill", "Course (treadmill)"), ("rowing", "indoor", "rowing (indoor)"),
            (None, "open_water", "open_water"), (None, None, "-"), (42, None, "42"),
        ]
        for sport, sub_sport, expected in cases:
            with self.subTest(sport=sport, sub_sport=sub_sport):
                self.assertEqual(activity(sport=(sport, None), sub_sport=(sub_sport, None)).sport, expected)


class FormatTests(unittest.TestCase):
    def test_empty_and_populated_round_trips(self):
        entries = [replace(activity(1, start_time=(datetime(2026, 1, 1, 0, 0, 0, 1), None)),
                           link="../Mes séances/%20 #?|()_é.md"),
                   activity(2, sport=("A&B | <test> `x` [y] *z* \\ q\nr", None))]
        for rows in ([], entries):
            text = render_history(rows)
            self.assertEqual(parse_history(text), rows)
            for _ in range(3):
                self.assertEqual(render_history(parse_history(text)), text)
            self.assertIn(f"rows:{len(rows)}", text)
            self.assertTrue(text.endswith("\n"))

    def test_malformed_history_is_rejected(self):
        text = render_history([activity()])
        row = next(line for line in text.splitlines() if "activity-id:" in line)
        invalid = [
            "", text.replace(":v1", ":v2"), text[:-1], text[:text.index("\n<!-- fit-extractor-history:end")],
            text.replace("rows:1", "rows:2"), text.replace("rows:1", "rows:01"), text + "notes\n",
            text.replace("Distance (km)", "Distance (m)"),
            text.replace("0" * 63 + "1", "G" * 64),
            text.replace(row, row + "\n" + row).replace("rows:1", "rows:2"),
            text.replace(row, row.replace("| - |", "| NaN |", 1)),
            text.replace(row, row.replace(" | - <!--", " | extrait | - <!--")),
        ]
        for corrupted in invalid:
            with self.subTest(corrupted=corrupted[-100:]), self.assertRaises(ValueError):
                parse_history(corrupted)

    def test_invalid_cells_are_not_silently_replaced(self):
        base = replace(activity(), link="file.md")
        for change in (
            {"distance": "inf"}, {"duration": "01:60:00"}, {"duration": "001:00:00"},
            {"avg_heart_rate": "0"}, {"training_effect": "-1.0"}, {"tss": "2"},
            {"link": "/absolute.md"}, {"sport": "\n"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                render_history([replace(base, **change)])
        text = render_history([base])
        for link in ("bad%ZZ.md", "bad%ff.md", "bad%2fpath.md", "bad#fragment.md", ""):
            with self.subTest(link=link), self.assertRaises(ValueError):
                parse_history(text.replace("file.md", link))
        dated = render_history([activity(start_time=(datetime(2026, 2, 1), None))])
        with self.assertRaises(ValueError):
            parse_history(dated.replace("2026-02-01", "2026-02-30"))

    def test_order_upsert_and_displaced_link_identity(self):
        start = datetime(2026, 10, 2, tzinfo=timezone.utc)
        early = activity(1, start_time=(start, None))
        later = activity(3, start_time=(start + timedelta(microseconds=1), None))
        equal = activity(2, start_time=(start, None))
        entries = []
        for entry in (later, activity(5), early, activity(4), equal):
            entries = upsert_history(entries, entry, set())
        self.assertEqual([entry.activity_id for entry in entries], [f"{n:064x}" for n in (3, 1, 2, 4, 5)])
        updated = replace(early, distance="5.00", link="new.md")
        entries = upsert_history(entries, updated, set())
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[1], updated)
        original = list(entries)
        entries = upsert_history(entries, replace(equal, link="new.md"), {early.activity_id})
        self.assertEqual(original[1].link, "new.md")
        reread = parse_history(render_history(entries))
        self.assertIsNone(reread[1].link)
        self.assertEqual(reread[1].activity_id, early.activity_id)
        self.assertEqual(reread[1].distance, "5.00")


if __name__ == "__main__":
    unittest.main()
