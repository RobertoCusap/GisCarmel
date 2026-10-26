"""Prepare small static assets for local use and Vercel's CDN.

Run normally after changing assets/. Vercel runs --check against the committed
web copies, so original photographs never need to enter the function bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from PIL import Image, ImageOps

from plant_data import IMAGE_EXTENSIONS


ROOT = Path(__file__).resolve().parent
MANIFEST_VERSION = 1
STATIC_FILES = (
    "styles.css", "app.js", "map.css", "map.js", "favicon.svg",
    "vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "vendor/leaflet/LICENSE",
    "vendor/leaflet/images/layers.png", "vendor/leaflet/images/layers-2x.png",
    "vendor/leaflet/images/marker-icon.png", "vendor/leaflet/images/marker-icon-2x.png",
    "vendor/leaflet/images/marker-shadow.png",
)


def prepare_photos(root: Path) -> dict:
    source = root / "assets"
    if not source.is_dir():
        raise ValueError("Original assets/ folder is missing. Use --check to verify prepared web photos.")
    folders: dict[str, list[str]] = {}
    source_hashes: dict[str, str] = {}
    source_bytes = 0
    for folder in sorted(source.iterdir(), key=lambda p: p.name.casefold()):
        if not folder.is_dir():
            continue
        names = []
        for path in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
            if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            relative = path.relative_to(source).as_posix()
            # Keep the original extension in the stem to prevent filename collisions.
            target_name = relative + ".webp"
            source_bytes += path.stat().st_size
            with path.open("rb") as original:
                source_hashes[relative] = hashlib.file_digest(original, "sha256").hexdigest()
            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original).convert("RGB")
                for directory, edge, quality in (("media", 1200, 82), ("thumbnails", 120, 78)):
                    resized = image.copy()
                    resized.thumbnail((edge, edge), Image.Resampling.LANCZOS)
                    target = root / "public" / directory / target_name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    resized.save(target, "WEBP", quality=quality, method=6)
            names.append(target_name)
        if names:
            folders[folder.name] = names
    if not folders:
        raise ValueError("No supported photographs found in assets/.")
    manifest = {"version": MANIFEST_VERSION, "folders": folders,
                "original_bytes": source_bytes, "original_sha256": source_hashes}
    active = {name for names in folders.values() for name in names}
    for directory in ("media", "thumbnails"):
        destination = (root / "public" / directory).resolve()
        for stale in destination.rglob("*.webp"):
            if stale.resolve().is_relative_to(destination) and stale.relative_to(destination).as_posix() not in active:
                stale.unlink()
    destination = root / "data" / "photo_manifest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_photos(root: Path) -> dict:
    manifest_path = root / "data" / "photo_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("Missing data/photo_manifest.json. Run python build.py locally and commit data/ and public/.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != MANIFEST_VERSION or not manifest.get("folders"):
        raise ValueError("Unsupported or empty photo manifest. Run python build.py again.")
    count = web_bytes = 0
    for folder, files in manifest["folders"].items():
        if not isinstance(files, list) or not files:
            raise ValueError(f"Invalid photo list: {folder}")
        for relative in files:
            parts = Path(relative).parts
            if (Path(relative).is_absolute() or len(parts) != 2 or parts[0] != folder
                    or folder in {".", ".."} or Path(relative).suffix.lower() != ".webp" or "\\" in relative):
                raise ValueError(f"Invalid web photo path: {relative}")
            count += 1
            for directory, edge in (("media", 1200), ("thumbnails", 120)):
                image_path = root / "public" / directory / relative
                if not image_path.is_file():
                    raise ValueError(f"Missing public/{directory}/{relative}. Run python build.py and commit public/.")
                with Image.open(image_path) as image:
                    if image.format != "WEBP" or max(image.size) > edge:
                        raise ValueError(f"Invalid or oversized prepared image: {image_path}")
                    image.verify()
                web_bytes += image_path.stat().st_size
    return {"photos": count, "original_bytes": manifest.get("original_bytes", 0), "web_bytes": web_bytes}


def verify_static(root: Path) -> None:
    # These are source files committed directly, rather than generated copies.
    # Both the local Flask server and Vercel's CDN use the same directory.
    for name in STATIC_FILES:
        path = root / "public" / "static" / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing public/static/{name}. Include public/static/ in the Git commit and deployment.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify committed photos without reading the originals")
    args = parser.parse_args()
    try:
        if not args.check:
            prepare_photos(ROOT)
        stats = verify_photos(ROOT)
        verify_static(ROOT)
    except (OSError, ValueError) as exc:
        print(f"Asset build failed: {exc}", file=sys.stderr)
        return 1
    print(f"Verified {stats['photos']} photos and thumbnails.")
    print(f"Originals: {stats['original_bytes'] / 1_000_000:.2f} MB; web copies: {stats['web_bytes'] / 1_000_000:.2f} MB.")
    print("Verified website assets in public/static/. Original photos are unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
