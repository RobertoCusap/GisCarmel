# Data and mapping documentation

## Scope

Mt. Carmel Plant Atlas displays the locations and plant identities supplied in the project's workbook. It provides GIS visualization, species filtering, record inspection, and data export. It does not infer a surveyed boundary, identify plants from photographs, or add botanical descriptions that are absent from the source.

## Source workbook

The app reads `DATA_FOR_MAPPING-1.xlsx` from the project root by default. Set the `DATA_FILE` environment variable to an alternate workbook path before startup to use another dataset. The supplied workbook contains one worksheet, `Makahiya`, whose name does not limit its contents to that plant.

The supplied source columns are:

- `LOCAL NAME` — the plant's source local-name category.
- `SCIENTIFIC NAME` — the scientific name recorded by the data collector; optional for newly added datasets.
- `LONGITUDE` — longitude in decimal degrees, east positive.
- `LATITUDE` — latitude in decimal degrees, north positive.

The loader requires a local name, longitude, and latitude. It also accepts an optional elevation column. The supplied file contains **459 observation rows**, **43 distinct local-name entries**, and **319 unique coordinate pairs**. These are observation counts, not counts of individual plants or proof of complete species coverage.

Local-name categories remain separate even when their scientific names match. Scientific names and identifications are displayed from the workbook; the app does not validate their taxonomy. Source-sheet and row references allow a displayed observation to be traced back to Excel.

## Coordinate handling

The map interprets coordinates as WGS 84 latitude and longitude. This assumes the supplied decimal coordinates use that common GPS coordinate reference system. Confirm the coordinate reference system with the data collector if combining these records with other survey layers.

The supplied coordinates are decimal degrees. The loader also accepts unambiguous degree-minute-second values and compass directions. Parsed coordinates must be finite and within the valid latitude and longitude ranges. Records that fail validation are excluded from the map and reported as data issues. The app does not fill in missing coordinates, relocate observations, or silently swap coordinate columns.

Repeated coordinates are retained. The supplied data has 140 records beyond the first record at each coordinate, including 92 repeated positions within the same local-name category. Overlapping circles can therefore represent more than one observation. The popup provides controls to browse the records at that location under the current species selection.

The supplied **Gabon record at worksheet row 340** has latitude **8.87968**, noticeably north of the main group. It remains plotted at its source coordinate and is flagged for review. This flag is a prompt to check the original field record; it does not establish that the coordinate is wrong.

The map fits the recorded locations. An outlying point can make the initial view cover a wider area. Select a species and zoom in to inspect dense groups.

## Species identifiers and colors

The data loader gives each source species category an application identifier and a distinct color. The same identifier connects the catalogue, map, photograph assignment, and export filter. Colors identify categories visually; the plant name and popup information remain the primary identifiers.

Selecting a species filters the existing map layers without modifying the workbook. Search narrows the catalogue; selecting a search result applies that species filter to the map.

## Photograph matching

Photographs originate in the supplied `assets/` subfolders. A folder is matched to its corresponding source local name, with explicit aliases for supplied folder names that differ from the workbook. A photo is assigned only within its matched species category. After `python build.py`, the app reads the same folder/filename catalogue from `data/photo_manifest.json` and uses the optimized copies in `public/`. It does not need to open the originals to match species at runtime.

The known folder aliases include:

- `Kakawate / Madre de cacao` → `KAKAWATE`
- `Guava / Bayabas` → `GUAVA`
- `katakataka` → `KALANCHOE PINNATA`

The loader sorts the available filenames and assigns photographs in a deterministic rotation across that species' observations. The same inputs therefore produce the same assignments. A species with one photograph may show that photograph for several observations.

These are **representative species photographs**. They are not evidence that the pictured individual was photographed at the displayed coordinate. This distinction appears in the popup.

If no matching folder or usable photo exists, the observation has no image. Unmatched photo folders are not assigned to a different species. The supplied `Hydrocotyle verticillata` folder is unused because the workbook has no matching category. The collection provides 158 matched photographs across 18 source categories. The original photographs are preserved; the app can serve resized versions for display.

Supported source file extensions are `.jpg`, `.jpeg`, `.png`, `.webp`, and `.gif`. Place photos in the appropriate species folder, run `python build.py`, then restart the app. If a folder uses a different name, add a deliberate alias in `plant_data.py` after checking its identity.

## Web photos and deployment size

The build creates a WebP display copy with a maximum edge of 1200 pixels and a separate 120-pixel thumbnail for each source photo. It corrects EXIF orientation and omits embedded metadata. Original files are never overwritten. Generated names append `.webp` to the original filename so files sharing a stem with different extensions cannot collide.

The manifest stores the folder catalogue and source SHA-256 fingerprints. Observation assignment uses the same source filename order and source categories. The format change does not move coordinates, merge categories, or associate a photo with another species.

On Vercel, photos and browser libraries are served as static files from `public/`. Both `assets/` and `public/` are excluded from the Python function. The small manifest stays in the function so species photo links remain available without either image directory. Local Flask routes serve the same URLs from disk.

`python build.py --check` verifies prepared images without reading originals and checks that the committed website assets exist in `public/static/`. Vercel runs this command. Stylesheets, scripts, and Leaflet files live directly in that tracked directory; no deployment-time copy is required. Regenerate photos locally with `python build.py` after adding, replacing, or removing source photos; removed source photos are removed from the generated collection. Commit the updated manifest and prepared photos together.

## Application architecture

1. Flask starts the local web server and loads the workbook through `plant_data.py`.
2. `openpyxl` reads Excel values without modifying the original workbook. The loader validates observations and builds species metadata, photo links, summary counts, and data issues.
3. `mapping.py` uses Folium to create map geometry, species layers, and the configuration needed by the browser map.
4. The main HTML page displays the species catalogue and embeds the map from `/map` in a same-origin iframe.
5. Small browser scripts connect the species selection and map controls to Leaflet. Popup controls let users inspect observations sharing a coordinate.
6. Pillow prepares optimized photos and thumbnails; local Flask can also resize a requested image. Vercel's CDN serves the prepared files directly. CSV and GeoJSON downloads are assembled from the source observations under the active species filter.

Python owns data preparation and map construction. JavaScript handles browser interactions because Folium displays its maps using Leaflet.

The app has no database. Local use does not submit observations to a hosted service. If you deploy it, the workbook and prepared images are included in your deployment and the app's data routes are accessible to the site's visitors. Restart after workbook changes; rebuild photos and restart after photograph changes.

## Basemaps and connectivity

Leaflet's JavaScript and CSS are bundled in `public/static/vendor/leaflet/`. Locally Flask serves `public/static/` under `/static/`; Vercel serves the same files from its CDN. The application interface, data, and images can be served locally without a content delivery network.

Street map tiles and satellite imagery are requested by the browser from their map providers. Those backgrounds need internet access. Using a local server does not make externally supplied basemaps available offline.

No API key is required for the configured basemaps. Attribution must remain visible. Provider availability and usage policies still apply when you later deploy or adapt the application.

## Exports

CSV and GeoJSON exports contain the records under the current species filter, or all observations when **All plant species** is selected. A catalogue search alone does not redefine the selected map species.

GeoJSON uses standard point coordinate order: **`[longitude, latitude]`**. This differs from the **`[latitude, longitude]`** order used when constructing Leaflet/Folium markers.

Downloads preserve source observations, including repeated coordinate records. Photo assignments do not establish a verified record-to-photo relationship.

The CSV includes the observation ID, local name, scientific name, latitude, longitude, source sheet, and source row. It uses UTF-8 with a byte-order mark so Excel recognizes the encoding. GeoJSON includes observation properties, such as representative photo links, alongside the point geometry.

## Local routes

All paths below are served by the local Flask app at `http://127.0.0.1:5055` by default:

- `/` — the plant catalogue and map interface.
- `/map` — the generated Folium map HTML embedded in the main page.
- `/api/data` — the loaded species, observations, summary statistics, bounds, source metadata, and data issues as JSON.
- `/api/status` — status, summary statistics, source metadata, and data issues as JSON.
- `/media/<folder>/<filename>` — a prepared WebP from `public/media/`, or an original photograph from `assets/` for legacy photo URLs. Local file paths are checked to stay within their photo directories.
- `/thumbnails/<folder>/<filename>` — the small prepared species thumbnail from `public/thumbnails/`.
- Adding `?size=640` locally requests a resized JPEG, limited to 80–1200 pixels. On Vercel, the static CDN serves the already optimized variant; a size query does not dynamically resize it. The species list uses separate small thumbnail files.
- `/download/observations.csv` — all usable observations in CSV format.
- `/download/observations.geojson` — all usable observations as a GeoJSON FeatureCollection.

Append `?species=<id>` to either download route to export one source category. Obtain the category's `id` from `/api/data`; an unknown category returns HTTP 404. The site updates these download links automatically when a species is selected.

If the workbook is missing, unreadable, or contains no usable mapping data, the page presents a setup error and the API responds with HTTP 503. Fix the reported source problem and restart the app.

## Maintenance checklist

1. Stop the local app.
2. Back up the source workbook before editing research data.
3. Keep the required headers and enter one observation per row.
4. Use valid decimal latitude and longitude values; retain the intended source category and scientific name.
5. Place any new species photos in the correct folder and review folder aliases where names differ.
6. Run `python build.py` if photos changed, then restart the app and reload the browser.
7. Review observation totals, data issues, selected-species locations, and several photo popups.
8. Run `python -m unittest discover -s tests -v` using the project's virtual environment after code changes.

Local startup and manual Vercel deployment preparation are documented in [README.md](../README.md). Preparation never pushes or deploys the project automatically.
