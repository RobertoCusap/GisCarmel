"""Integration checks for the local atlas, source exports and photo delivery."""

import csv
from html.parser import HTMLParser
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PIL import Image, ImageOps

from app import create_app


class AssetReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.urls.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.urls.append(attrs["href"])


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app({"TESTING": True})
        cls.data = cls.app.extensions["plant_dataset"]
        if cls.data is None:
            raise AssertionError("The supplied field workbook must load for integration checks")
        cls.photos = next(s for s in cls.data["species"] if s["thumbnail"])

    def setUp(self):
        self.client = self.app.test_client()

    def test_pages_use_local_scripts_and_styles(self):
        for route in ("/", "/map"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "text/html")
                parser = AssetReferences()
                parser.feed(response.get_data(as_text=True))
                self.assertTrue(parser.urls, f"No stylesheet/script assets found at {route}")
                for url in parser.urls:
                    self.assertTrue(url.startswith("/static/"), f"A required app asset uses an external origin: {url}")
                    with self.client.get(url) as asset_response:
                        self.assertEqual(asset_response.status_code, 200, url)
        map_html = self.client.get("/map").get_data(as_text=True)
        self.assertIn("/static/vendor/leaflet/leaflet.js", map_html)
        self.assertIn("/static/vendor/leaflet/leaflet.css", map_html)
        self.assertIn("/static/map.js", map_html)
        with self.client.get("/static/map.js") as response:
            self.assertEqual(response.status_code, 200)

    def test_dataset_and_status_expose_source_counts_and_outlier(self):
        response = self.client.get("/api/data")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["stats"]["observations"], 459)
        self.assertEqual(data["stats"]["species"], 43)
        self.assertEqual(len(data["observations"]), 459)
        self.assertEqual(len({o["id"] for o in data["observations"]}), 459)
        outlier = next(o for o in data["observations"] if o["source_row"] == 340)
        self.assertEqual((outlier["latitude"], outlier["longitude"]), (8.87968, 125.83501))
        status = self.client.get("/api/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["status"], "ok")
        self.assertEqual(status.get_json()["stats"], data["stats"])
        self.assertEqual(status.get_json()["source"]["workbook"], "DATA_FOR_MAPPING-1.xlsx")
        self.assertTrue(any(i["code"] == "coordinate_outlier" for i in status.get_json()["issues"]))

    def test_csv_exports_full_and_filtered_rows_without_deduplication(self):
        selected = next(s for s in self.data["species"] if s["name"] == "Makahiya")
        for species_id in (None, selected["id"]):
            with self.subTest(species_id=species_id):
                expected = [o for o in self.data["observations"] if species_id is None or o["species_id"] == species_id]
                response = self.client.get("/download/observations.csv", query_string={"species": species_id} if species_id else {})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "text/csv")
                self.assertIn("attachment", response.headers["Content-Disposition"])
                rows = list(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
                self.assertEqual(len(rows), len(expected))
                self.assertEqual([row["id"] for row in rows], [o["id"] for o in expected])
                for row, original in zip(rows, expected):
                    self.assertEqual((float(row["latitude"]), float(row["longitude"])), (original["latitude"], original["longitude"]))
                    self.assertEqual(row["name"], original["name"])
                    self.assertEqual(row["scientific_name"], original["scientific_name"] or "")
                    self.assertEqual(int(row["source_row"]), original["source_row"])
        self.assertEqual(len(expected), 97)
        self.assertLess(len({(o["latitude"], o["longitude"]) for o in expected}), len(expected))

    def test_geojson_exports_longitude_latitude_and_all_original_records(self):
        selected = next(s for s in self.data["species"] if s["name"] == "Makahiya")
        for species_id in (None, selected["id"]):
            with self.subTest(species_id=species_id):
                expected = [o for o in self.data["observations"] if species_id is None or o["species_id"] == species_id]
                response = self.client.get("/download/observations.geojson", query_string={"species": species_id} if species_id else {})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "application/geo+json")
                self.assertIn("attachment", response.headers["Content-Disposition"])
                collection = response.get_json()
                self.assertEqual(collection["type"], "FeatureCollection")
                self.assertEqual(len(collection["features"]), len(expected))
                self.assertEqual([f["id"] for f in collection["features"]], [o["id"] for o in expected])
                for feature, original in zip(collection["features"], expected):
                    self.assertEqual(feature["geometry"], {"type": "Point", "coordinates": [original["longitude"], original["latitude"]]})
                    self.assertEqual(feature["properties"]["source_row"], original["source_row"])
                    self.assertEqual(feature["properties"]["species_id"], original["species_id"])

    def test_unknown_species_does_not_export_unfiltered_records(self):
        for route in ("/download/observations.csv", "/download/observations.geojson"):
            with self.subTest(route=route):
                self.assertEqual(self.client.get(route, query_string={"species": "unknown-plant"}).status_code, 404)

    def test_original_photo_and_oriented_thumbnail_are_served(self):
        url = self.photos["thumbnail"]
        with self.client.get(url) as original_response:
            self.assertEqual(original_response.status_code, 200)
            original_bytes = original_response.data
        with Image.open(io.BytesIO(original_bytes)) as original:
            expected = ImageOps.exif_transpose(original)
            expected.thumbnail((120, 120), Image.Resampling.LANCZOS)
            expected_size = expected.size
        thumbnail_response = self.client.get(url, query_string={"size": "120"})
        self.assertEqual(thumbnail_response.status_code, 200)
        self.assertEqual(thumbnail_response.mimetype, "image/jpeg")
        with Image.open(io.BytesIO(thumbnail_response.data)) as thumbnail:
            self.assertEqual(thumbnail.size, expected_size)
            self.assertLessEqual(max(thumbnail.size), 120)
        with self.client.get(url) as response:
            self.assertEqual(response.data, original_bytes)

    def test_invalid_media_requests_and_path_traversal_are_rejected(self):
        self.assertEqual(self.client.get(self.photos["thumbnail"], query_string={"size": "large"}).status_code, 400)
        self.assertEqual(self.client.get("/media/missing/photo.jpeg").status_code, 404)
        self.assertEqual(self.client.get("/media/../DATA_FOR_MAPPING-1.xlsx").status_code, 404)
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            assets = directory / "assets"
            assets.mkdir()
            Image.new("RGB", (16, 16)).save(directory / "outside.jpg")
            with patch.dict(self.app.config, {"ASSETS_DIR": str(assets)}):
                response = self.client.get("/media/..%2Foutside.jpg")
                self.assertEqual(response.status_code, 404)

    def test_missing_workbook_returns_actionable_503_on_pages_and_apis(self):
        with TemporaryDirectory() as folder:
            missing_app = create_app({"TESTING": True, "DATA_FILE": str(Path(folder) / "missing.xlsx")})
            client = missing_app.test_client()
            for route in ("/", "/map", "/api/data", "/api/status", "/download/observations.csv", "/download/observations.geojson"):
                with self.subTest(route=route):
                    response = client.get(route)
                    self.assertEqual(response.status_code, 503)
                    self.assertIn("Workbook not found", response.get_data(as_text=True))
                    self.assertIn("missing.xlsx", response.get_data(as_text=True))
                    if route.startswith("/api/"):
                        self.assertEqual(response.get_json()["status"], "error")


if __name__ == "__main__":
    unittest.main()
