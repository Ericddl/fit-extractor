import copy
from datetime import datetime, timedelta
from pathlib import Path
import unittest

from activity_analysis import Sample, _analyze_climbs, analyze_records
from extractor import format_markdown


START = datetime(2026, 10, 2, 10, 0)


def record(seconds, distance, altitude):
    fields = {
        "timestamp": (START + timedelta(seconds=seconds), None),
        "distance": (distance / 1000, "km"),
    }
    if altitude is not None:
        fields["altitude"] = (altitude, "m")
    return fields


def records_from_altitudes(altitudes):
    return [record(index * 60, index * 100, altitude)
            for index, altitude in enumerate(altitudes)]


def sample_run(altitudes, distances=None):
    if distances is None:
        distances = [index * 100 for index in range(len(altitudes))]
    return [Sample(index * 60, distance, altitude, None, False, altitude)
            for index, (distance, altitude) in enumerate(zip(distances, altitudes))]


def markdown(records, *, sport="running", sub_sport="trail", details=False):
    session = {"sport": (sport, None), "start_time": (START, None)}
    if sub_sport is not None:
        session["sub_sport"] = (sub_sport, None)
    data = {
        "session": session, "records": records, "laps": [], "hrv_intervals": [],
        "device_info": [], "user_profile": {}, "zones_target": {},
    }
    return format_markdown(data, "unknown", Path("synthetic.fit"), False, 30, details=details)


def table(text, title):
    heading = f"## {title}"
    if heading not in text:
        return []
    section = text.split(heading, 1)[1].split("\n---", 1)[0]
    return [[cell.strip() for cell in line.strip("|").split("|")]
            for line in section.splitlines() if line.startswith("|")]


class ElevationAnalysisTests(unittest.TestCase):
    def test_delayed_distance_updates_preserve_ascent_and_descent(self):
        distances = [0, 100, 100, 100, 300, 700, 1000]
        for altitudes, ascent, descent in (
            ([0, 0, 0, 50, 100, 100, 100], 100, 0),
            ([100, 100, 100, 50, 0, 0, 0], 0, 100),
        ):
            with self.subTest(altitudes=altitudes):
                records = [record(index * 100, distance, altitude)
                           for index, (distance, altitude) in enumerate(zip(distances, altitudes))]
                before = copy.deepcopy(records)
                row, = analyze_records(records, "running")["kilometers"]
                self.assertTrue(row["complete"])
                self.assertTrue(row["altitude_complete"])
                self.assertEqual(row["ascent"], ascent)
                self.assertEqual(row["descent"], descent)
                self.assertEqual(row["seconds"], 600)
                self.assertEqual(records, before)

    def test_repeated_boundary_elevation_belongs_to_next_kilometer(self):
        records = [record(index * 100, distance, altitude)
                   for index, (distance, altitude) in enumerate(zip(
                       [0, 500, 1000, 1000, 1000, 1000, 1500, 2000, 2000],
                       [0, 0, 0, 0, 50, 100, 100, 100, 100],
                   ))]
        first, last = analyze_records(records, "running")["kilometers"]
        self.assertEqual(first["ascent"], 0)
        self.assertEqual(first["seconds"], 200)
        self.assertEqual(last["ascent"], 100)
        self.assertEqual(last["seconds"], 600)

    def test_elevation_and_climbs_do_not_bridge_missing_data_or_gaps(self):
        for missing in ("timestamp", "altitude", "distance"):
            with self.subTest(missing=missing):
                records = records_from_altitudes([0] * 5 + [200] * 6)
                if missing == "timestamp":
                    for fields in records[5:]:
                        timestamp, unit = fields["timestamp"]
                        fields["timestamp"] = (timestamp + timedelta(seconds=600), unit)
                else:
                    records[5].pop(missing)
                analysis = analyze_records(records, "running")
                self.assertEqual(analysis["kilometers"][0]["ascent"], 0)
                self.assertEqual(analysis["climbs"], [])

    def test_terrain_includes_elevation_during_delayed_distance_updates(self):
        records = [record(index * 100, distance, altitude)
                   for index, (distance, altitude) in enumerate(zip(
                       [0, 0, 0, 0, 0, 50, 100], [0, 0, 0, 10, 20, 20, 20],
                   ))]
        analysis = analyze_records(records, "running")
        self.assertEqual(analysis["terrain"]["Montée"]["distance"], 50)
        self.assertEqual(analysis["terrain"]["Plat"]["distance"], 50)
        self.assertEqual(analysis["terrain_distance"], 100)


class ClimbDetectionTests(unittest.TestCase):
    def test_whole_climb_includes_small_descents_and_plateaus(self):
        run = sample_run([50, 0, 0, 100, 80, 80, 150, 150, 100])
        row, = _analyze_climbs([run])
        self.assertEqual((row["start"], row["end"]), (200, 600))
        self.assertEqual(row["ascent"], 170)
        self.assertEqual(row["descent"], 20)
        self.assertEqual(row["seconds"], 240)
        self.assertEqual(row["vam"], 2550)
        self.assertTrue(row["complete"])

    def test_gain_and_descent_thresholds_are_inclusive(self):
        row, = _analyze_climbs([sample_run([50, 0, 100, 50])])
        self.assertTrue(row["complete"])
        self.assertEqual(row["ascent"], 100)
        self.assertEqual(_analyze_climbs([sample_run([0, 99, 0])]), [])

    def test_descent_of_50_m_separates_two_climbs(self):
        first, last = _analyze_climbs([sample_run([50, 0, 100, 50, 150, 100])])
        self.assertEqual((first["start"], first["end"]), (100, 200))
        self.assertEqual((last["start"], last["end"]), (300, 400))
        self.assertEqual(first["ascent"], 100)
        self.assertEqual(last["ascent"], 100)

    def test_edges_are_marked_partial(self):
        for altitudes in ([0, 100, 50], [50, 0, 100, 90]):
            with self.subTest(altitudes=altitudes):
                row, = _analyze_climbs([sample_run(altitudes)])
                self.assertFalse(row["complete"])
                self.assertEqual(row["vam"], 6000)

    def test_separate_continuous_runs_are_not_merged(self):
        self.assertEqual(_analyze_climbs([
            sample_run([0, 90]), sample_run([90, 180]),
        ]), [])

    def test_no_climb_without_distance_extent(self):
        self.assertEqual(_analyze_climbs([sample_run([0, 100, 50], [0, 0, 0])]), [])

    def test_delayed_distance_updates_and_stationary_time_are_preserved(self):
        row, = _analyze_climbs([sample_run([50, 0, 100, 100, 200, 150], [0, 100, 100, 100, 200, 300])])
        self.assertEqual(row["ascent"], 200)
        self.assertEqual(row["seconds"], 180)
        self.assertEqual(row["vam"], 4000)

    def test_analysis_uses_filtered_altitudes_and_leaves_records_unchanged(self):
        records = records_from_altitudes([50, 50, 50, 0, 0, 0, 100, 100, 100, 50, 50, 50])
        before = copy.deepcopy(records)
        row, = analyze_records(records, "running")["climbs"]
        self.assertEqual(row["start"], 500)
        self.assertEqual(row["end"], 600)
        self.assertEqual(row["vam"], 6000)
        self.assertTrue(row["complete"])
        self.assertEqual(records, before)

    def test_regressions_disable_climbs(self):
        for key, value in (("timestamp", (START - timedelta(seconds=1), None)),
                           ("distance", (0.1, "km"))):
            with self.subTest(key=key):
                records = records_from_altitudes([0, 0, 0, 100, 100, 100, 50, 50, 50])
                records[4][key] = value
                analysis = analyze_records(records, "running")
                self.assertEqual(analysis["climbs"], [])
                self.assertIn("non monotone", analysis["climb_reason"])


class ClimbMarkdownTests(unittest.TestCase):
    def setUp(self):
        self.records = records_from_altitudes([50, 50, 50, 0, 0, 0, 100, 100, 100, 50, 50, 50])

    def test_separate_trail_table_with_and_without_details_and_without_gps(self):
        for details in (False, True):
            with self.subTest(details=details):
                text = markdown(self.records, details=details)
                header, separator, row = table(text, "Montées")
                self.assertEqual(header[-1], "VAM estimée")
                self.assertEqual(len(row), len(header))
                self.assertEqual(len(separator), len(header))
                self.assertEqual(row[1:3], ["0.500 km", "0.600 km"])
                self.assertEqual(row[-1], "6000 m/h")
                self.assertNotIn("VAM estimée", table(text, "Découpage kilométrique")[0])
                self.assertIn("arrêts compris", text)

    def test_table_is_exclusive_to_running_trail(self):
        for sport, sub_sport in (("running", "generic"), ("running", None),
                                 ("running", "track"), ("cycling", "trail"), ("hiking", "trail")):
            with self.subTest(sport=sport, sub_sport=sub_sport):
                text = markdown(self.records, sport=sport, sub_sport=sub_sport)
                self.assertEqual(table(text, "Montées"), [])
                self.assertNotIn("VAM estimée", text)

    def test_absence_of_climbs_is_explained(self):
        for altitudes in ([0] * 10, [None] * 10, []):
            with self.subTest(altitudes=altitudes):
                text = markdown(records_from_altitudes(altitudes))
                self.assertEqual(table(text, "Montées"), [])
                self.assertIn("Montées indisponibles", text)

    def test_partial_climb_is_labeled(self):
        row = table(markdown(records_from_altitudes([0, 0, 0, 100, 100, 100])), "Montées")[-1]
        self.assertEqual(row[4], "Partielle")

    def test_vam_is_calculated_before_ascent_display_rounding(self):
        records = copy.deepcopy(self.records)
        for fields in records:
            altitude, unit = fields["altitude"]
            fields["altitude"] = (altitude * 1.004, unit)
        row = table(markdown(records), "Montées")[-1]
        self.assertEqual(row[5], "100 m")
        self.assertEqual(row[-1], "6024 m/h")


if __name__ == "__main__":
    unittest.main()
