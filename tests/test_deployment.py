"""Verify small prepared photos and a runtime that has no original images."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook
from PIL import Image

from app import create_app
from build import copy_static, prepare_photos, verify_photos
from plant_data import DataError, load_dataset


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.assets = self.root / "assets" / "GUAVA"
        self.assets.mkdir(parents=True)
        self.original = self.assets / "field photo.jpg"
        photo = Image.new("RGB", (1600, 800), "#537b3b")
        exif = Image.Exif()
        exif[274] = 6
        photo.save(self.original, exif=exif)
        self.book = self.root / "survey.xlsx"
        workbook = Workbook()
        workbook.active.append(["LOCAL NAME", "SCIENTIFIC NAME", "LONGITUDE", "LATITUDE"])
        workbook.active.append(["Guava / Bayabas", "Psidium guajava", 125.8, 8.7])
        workbook.active.append(["Missing photo", "Source name", 125.81, 8.71])
        workbook.save(self.book)
        workbook.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_web_copies_preserve_originals_orientation_and_unique_filenames(self):
        Image.new("RGB", (100, 80)).save(self.assets / "field photo.png")
        before = hashlib.sha256(self.original.read_bytes()).hexdigest()
        manifest = prepare_photos(self.root)
        after = hashlib.sha256(self.original.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(manifest["original_sha256"]["GUAVA/field photo.jpg"], before)
        self.assertEqual(len(set(manifest["folders"]["GUAVA"])), 2)
        for directory, expected in (("media", (600, 1200)), ("thumbnails", (60, 120))):
            with Image.open(self.root / "public" / directory / "GUAVA/field photo.jpg.webp") as prepared:
                self.assertEqual(prepared.format, "WEBP")
                self.assertEqual(prepared.size, expected)
                self.assertFalse(prepared.getexif())
        self.assertEqual(verify_photos(self.root)["photos"], 2)

    def test_runtime_keeps_species_photos_when_original_folder_is_excluded(self):
        prepare_photos(self.root)
        missing_originals = self.root / "excluded-assets"
        manifest = self.root / "data" / "photo_manifest.json"
        data = load_dataset(self.book, missing_originals, manifest)
        self.assertEqual(data["stats"]["observations"], 2)
        self.assertEqual(data["stats"]["species_with_photos"], 1)
        self.assertEqual(data["stats"]["photos"], 1)
        self.assertTrue(data["observations"][0]["image"].endswith(".webp"))
        self.assertIsNone(data["observations"][1]["image"])
        self.assertFalse(missing_originals.exists())
        app = create_app({"TESTING": True, "DATA_FILE": str(self.book), "ASSETS_DIR": str(missing_originals),
                          "PHOTO_MANIFEST": str(manifest), "PUBLIC_DIR": str(self.root / "public")})
        client = app.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/map").status_code, 200)
        species = next(s for s in data["species"] if s["thumbnail"])
        for url in (species["thumbnail"], data["observations"][0]["image"]):
            with client.get(url) as response:
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.mimetype, "image/webp")

    def test_manifest_alone_is_sufficient_for_map_metadata(self):
        prepare_photos(self.root)
        # Function bundles exclude both originals and public/. The CDN handles
        # the image URLs, while the function only needs the small manifest.
        app = create_app({"TESTING": True, "DATA_FILE": str(self.book), "ASSETS_DIR": str(self.root / "absent"),
                          "PHOTO_MANIFEST": str(self.root / "data/photo_manifest.json"),
                          "PUBLIC_DIR": str(self.root / "cdn-not-in-function")})
        client = app.test_client()
        response = client.get("/api/data")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["stats"]["photos"], 1)
        self.assertEqual(client.get("/map").status_code, 200)

    def test_missing_prepared_photo_fails_the_build_check(self):
        prepare_photos(self.root)
        (self.root / "public/media/GUAVA/field photo.jpg.webp").unlink()
        with self.assertRaisesRegex(ValueError, "Missing public/media"):
            verify_photos(self.root)

    def test_rebuild_removes_only_stale_web_copies(self):
        extra = self.assets / "removed.jpg"
        Image.new("RGB", (50, 50)).save(extra)
        prepare_photos(self.root)
        extra.unlink()
        prepare_photos(self.root)
        self.assertTrue(self.original.is_file())
        self.assertFalse((self.root / "public/media/GUAVA/removed.jpg.webp").exists())
        self.assertFalse((self.root / "public/thumbnails/GUAVA/removed.jpg.webp").exists())
        self.assertEqual(verify_photos(self.root)["photos"], 1)

    def test_manifest_paths_cannot_escape_photo_folders(self):
        prepare_photos(self.root)
        path = self.root / "data/photo_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["folders"]["GUAVA"] = ["../outside.webp"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(DataError, "Invalid photo path"):
            load_dataset(self.book, self.root / "assets", path)

    def test_build_copies_static_files_to_cdn_paths(self):
        source = self.root / "static/vendor"
        source.mkdir(parents=True)
        (source / "leaflet.js").write_text("local library", encoding="utf-8")
        copy_static(self.root)
        self.assertEqual((self.root / "public/static/vendor/leaflet.js").read_text(encoding="utf-8"), "local library")


if __name__ == "__main__":
    unittest.main()
