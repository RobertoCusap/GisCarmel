"""Local, Python-powered plant atlas for the Mt. Carmel field observations."""

from __future__ import annotations

import csv
from functools import lru_cache
import io
import json
import os
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_file
from PIL import Image, ImageOps, UnidentifiedImageError

from plant_data import DataError, IMAGE_EXTENSIONS, load_dataset


ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=256)
def _thumbnail(path: str, modified: int, size: int) -> bytes:
    """Cache small, correctly oriented images without altering source photos."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        if image.mode != "RGB":
            image = image.convert("RGB")
        output = io.BytesIO()
        image.save(output, "JPEG", quality=85, optimize=True)
        return output.getvalue()


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        DATA_FILE=os.environ.get("DATA_FILE", str(ROOT / "DATA_FOR_MAPPING-1.xlsx")),
        ASSETS_DIR=str(ROOT / "assets"),
        JSON_SORT_KEYS=False,
    )
    if config:
        app.config.update(config)
    app.json.sort_keys = False
    try:
        dataset = load_dataset(Path(app.config["DATA_FILE"]), Path(app.config["ASSETS_DIR"]))
        error = None
    except DataError as exc:
        dataset, error = None, str(exc)
    app.extensions["plant_dataset"] = dataset

    def get_dataset() -> dict:
        if dataset is None:
            abort(503, description=error)
        return dataset

    def selected_records() -> list[dict]:
        data = get_dataset()
        species_id = request.args.get("species", "")
        if species_id and species_id not in {s["id"] for s in data["species"]}:
            abort(404, description="That species is not in the field workbook.")
        return [o for o in data["observations"] if not species_id or o["species_id"] == species_id]

    @app.get("/")
    def index():
        return render_template("index.html", data=get_dataset())

    @lru_cache(maxsize=1)
    def rendered_map() -> str:
        from mapping import build_map
        return build_map(get_dataset())

    @app.get("/map")
    def map_view():
        return Response(rendered_map(), mimetype="text/html")

    @app.get("/api/data")
    def api_data():
        return jsonify(get_dataset())

    @app.get("/api/status")
    def status():
        data = get_dataset()
        return jsonify(status="ok", stats=data["stats"], source=data["source"], issues=data["issues"])

    @app.get("/media/<path:filename>")
    def media(filename: str):
        assets = Path(app.config["ASSETS_DIR"]).resolve()
        path = (assets / filename).resolve()
        if not path.is_relative_to(assets) or path.suffix.lower() not in IMAGE_EXTENSIONS or not path.is_file():
            abort(404)
        raw_size = request.args.get("size")
        if raw_size is None:
            return send_file(path, conditional=True, max_age=3600)
        try:
            size = max(80, min(1200, int(raw_size)))
        except ValueError:
            abort(400, description="Image size must be a number.")
        try:
            content = _thumbnail(str(path), path.stat().st_mtime_ns, size)
        except (OSError, UnidentifiedImageError):
            abort(404, description="This photo could not be opened.")
        return send_file(io.BytesIO(content), mimetype="image/jpeg", max_age=3600)

    @app.get("/download/observations.csv")
    def download_csv():
        output = io.StringIO(newline="")
        fields = ["id", "name", "scientific_name", "latitude", "longitude", "source_sheet", "source_row"]
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(selected_records())
        return Response(output.getvalue().encode("utf-8-sig"), mimetype="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="mt-carmel-observations.csv"'})

    @app.get("/download/observations.geojson")
    def download_geojson():
        records = selected_records()
        collection = {"type": "FeatureCollection", "features": [
            {"type": "Feature", "id": o["id"],
             "geometry": {"type": "Point", "coordinates": [o["longitude"], o["latitude"]]},
             "properties": {key: value for key, value in o.items() if key not in {"latitude", "longitude"}}}
            for o in records
        ]}
        return Response(json.dumps(collection, ensure_ascii=False), mimetype="application/geo+json",
                        headers={"Content-Disposition": 'attachment; filename="mt-carmel-observations.geojson"'})

    @app.errorhandler(503)
    def unavailable(exc):
        if request.path.startswith("/api/"):
            return jsonify(status="error", message=exc.description), 503
        return render_template("error.html", message=exc.description), 503

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", "5055")), debug=False)
