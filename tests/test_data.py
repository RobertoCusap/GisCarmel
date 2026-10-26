"""Source-preservation checks for plant observations and representative photos."""

from pathlib import Path
import os
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from plant_data import DataError, load_dataset, parse_coordinate


class CoordinateTests(unittest.TestCase):
    def test_decimal_and_dms(self):
        self.assertAlmostEqual(parse_coordinate("8° 46' 56.064\" N", "latitude"), 8.78224)
        self.assertAlmostEqual(parse_coordinate("125.82599 E", "longitude"), 125.82599)
        self.assertEqual(parse_coordinate("S 8 30 0", "latitude"), -8.5)
        self.assertEqual(parse_coordinate("-125.8", "longitude"), -125.8)

    def test_invalid_coordinates_are_rejected(self):
        for value, axis in [(None, "latitude"), (True, "latitude"), ("NaN", "latitude"), (float("inf"), "longitude"), (91, "latitude"), (181, "longitude"), ("8 60 0 N", "latitude"), ("8 30 0 E", "latitude"), ("-8 N", "latitude"), ("8,7822", "latitude")]:
            with self.subTest(value=value, axis=axis), self.assertRaises(ValueError):
                parse_coordinate(value, axis)


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        self.workbook = self.root / "survey.xlsx"

    def tearDown(self):
        self.temp.cleanup()

    def write_rows(self, rows, header=None):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Field survey"
        sheet.append(header or ["LOCAL NAME", "SCIENTIFIC NAME", "LONGITUDE", "LATITUDE"])
        for row in rows:
            sheet.append(row)
        workbook.save(self.workbook)
        workbook.close()

    def add_photos(self, folder, names):
        path = self.assets / folder
        path.mkdir()
        for name in names:
            (path / name).write_bytes(b"test image")

    def test_duplicate_rows_and_shared_locations_are_preserved(self):
        self.write_rows([["Makahiya", "Mimosa pudica", 125.8, 8.7], ["Makahiya", "Mimosa pudica", 125.8, 8.7], ["Kalabo", "Coleus amboinicus", 125.8, 8.7]])
        data = load_dataset(self.workbook, self.assets)
        self.assertEqual(len(data["observations"]), 3)
        self.assertEqual(data["stats"]["locations"], 1)
        self.assertEqual(data["stats"]["duplicate_species_coordinates"], 1)
        self.assertEqual(data["stats"]["overlapping_observations"], 2)
        self.assertEqual(len({o["id"] for o in data["observations"]}), 3)
        self.assertTrue(all(o["location_count"] == 3 for o in data["observations"]))

    def test_photos_stay_with_species_rotate_and_absence_is_null(self):
        self.write_rows([["Guava / Bayabas", "Psidium guajava", 125.8, 8.7], ["Guava / Bayabas", "Psidium guajava", 125.81, 8.71], ["Guava / Bayabas", "Psidium guajava", 125.82, 8.72], ["Missing photo", "Source name", 125.83, 8.73]])
        self.add_photos("GUAVA", ["b photo.jpeg", "a.jpeg"])
        self.add_photos("UNRELATED", ["wrong.jpeg"])
        data = load_dataset(self.workbook, self.assets)
        images = [o["image"] for o in data["observations"]]
        self.assertEqual(images, ["/media/GUAVA/a.jpeg", "/media/GUAVA/b%20photo.jpeg", "/media/GUAVA/a.jpeg", None])
        self.assertEqual(data["stats"]["photos"], 2)
        self.assertEqual(data["stats"]["species_with_photos"], 1)
        self.assertEqual(load_dataset(self.workbook, self.assets), data)

    def test_invalid_rows_are_reported_and_valid_outlier_retained(self):
        self.write_rows([["Plant", "Scientific name", 125.8, 8.7], ["Plant", "Scientific name", 125.8, 8.7], ["Plant", "Scientific name", 125.8, 8.8], ["Plant", "Scientific name", 125.8, "bad"], [None, "Scientific name", 125.8, 8.7]])
        data = load_dataset(self.workbook, self.assets)
        self.assertEqual(data["stats"]["observations"], 3)
        self.assertEqual(data["stats"]["skipped_rows"], 2)
        self.assertEqual(data["observations"][2]["latitude"], 8.8)
        self.assertEqual(len([i for i in data["issues"] if i["code"] == "invalid_row"]), 2)
        self.assertTrue(any(i["code"] == "coordinate_outlier" for i in data["issues"]))

    def test_source_categories_with_same_scientific_name_stay_separate(self):
        self.write_rows([["Elepante", "Stachytarpheta jamaicensis", 125.8, 8.7], ["Kandi-kandi", "Stachytarpheta jamaicensis", 125.8, 8.7]])
        data = load_dataset(self.workbook, self.assets)
        self.assertEqual(data["stats"]["species"], 2)
        self.assertEqual(len({s["color"] for s in data["species"]}), 2)

    def test_missing_file_or_schema_has_actionable_error(self):
        with self.assertRaisesRegex(DataError, "Workbook not found"):
            load_dataset(self.root / "absent.xlsx", self.assets)
        self.write_rows([["Plant", "Name", 125.8, 8.7]], header=["Plant", "Name", "X", "Y"])
        with self.assertRaisesRegex(DataError, "Required headers"):
            load_dataset(self.workbook, self.assets)

    def test_corrupted_workbook_has_readable_error(self):
        self.workbook.write_bytes(b"This is not an Excel workbook")
        with self.assertRaisesRegex(DataError, "Cannot read survey.xlsx"):
            load_dataset(self.workbook, self.assets)

    def test_provided_workbook_contract(self):
        project = Path(__file__).resolve().parents[1]
        # Allows validating an identical source copy when OneDrive/Excel locks
        # the working file, without changing the workbook or source assertions.
        source = Path(os.environ.get("TEST_DATA_FILE", project / "DATA_FOR_MAPPING-1.xlsx"))
        if not source.exists():
            self.skipTest("Original source workbook not present")
        data = load_dataset(source, project / "assets")
        self.assertEqual(data["stats"]["observations"], 459)
        self.assertEqual(data["stats"]["species"], 43)
        self.assertEqual(data["stats"]["locations"], 319)
        self.assertEqual(data["stats"]["skipped_rows"], 0)
        self.assertEqual(data["stats"]["duplicate_species_coordinates"], 92)
        self.assertEqual(data["stats"]["photos"], 158)
        self.assertEqual(data["stats"]["species_with_photos"], 18)
        self.assertEqual(len({s["color"] for s in data["species"]}), 43)
        gabon = next(o for o in data["observations"] if o["source_row"] == 340)
        self.assertEqual(gabon["latitude"], 8.87968)
        self.assertTrue(any(i["code"] == "coordinate_outlier" and i["source_row"] == 340 for i in data["issues"]))


if __name__ == "__main__":
    unittest.main()
