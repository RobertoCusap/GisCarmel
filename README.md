# Mt. Carmel Plant Atlas

A local GIS website for exploring the plant observations supplied for Mt. Carmel, Bayugan City, Agusan del Sur. Browse species in the left column and their recorded locations on the map. Select a dot to view the plant's source information and an available species photo.

The app uses Python for the web server, Excel ingestion, map generation, and image processing. It includes source code and local setup instructions. No hosting account, deployment, database, API key, or Node.js build is required.

## Requirements

- Python **3.11 or newer**. The supplied dependency versions support this minimum; development used Python 3.14.
- A current web browser.
- Internet access to install dependencies and display the street or satellite basemap. The workbook, plant photographs, app code, and Leaflet browser library stay local.
- The supplied `DATA_FOR_MAPPING-1.xlsx` and `assets/` folder in the project directory.

If this project is inside OneDrive, select **Always keep on this device** for the workbook and photograph folders before running it.

## Run locally on Windows

Open PowerShell in the project folder, then run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5055** in your browser. Keep the terminal open while using the app. Press **Ctrl+C** in that terminal to stop it.

These commands use the virtual environment's Python directly, so PowerShell script activation is unnecessary. If Windows does not recognize `python`, use `py` for the first command.

**Bisaya quick guide:** ablihi ang PowerShell sa project folder, padagana ang tulo ka commands sa taas, dayon ablihi ang local address sa browser. Walay kinahanglan nga hosting aron magamit kini locally.

## Run locally on macOS or Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Open **http://127.0.0.1:5055**.

## Explore the map

1. The initial view displays observations for all species. Each species has its own dot color.
2. Search the catalogue by local or scientific name. Change the sort order to browse alphabetically or by observation count.
3. Select a species to display only its observations. Select **All plant species** to restore the complete dataset.
4. Click a map dot to inspect the local name, scientific name, coordinates, source record, and an available photograph.
5. When several records share one coordinate, use the popup's observation controls to browse them. The source coordinates are preserved.
6. Use the map controls to change the basemap, zoom, fit the observations, or expand the map.
7. Download the current selection as CSV or GeoJSON when needed.

Photographs represent the selected **species**. They were supplied in species folders without links to individual coordinate records, so a displayed photo is not claimed to show the exact plant at that location. Records without a matching photograph have no image.

## Project files

- `app.py` — Flask application, page routes, image serving, and exports.
- `plant_data.py` — reads and validates the supplied Excel records and matches photograph folders.
- `mapping.py` — creates the interactive map using Python's Folium library.
- `templates/` — website HTML templates.
- `static/` — website styles and browser interactions, including the local Leaflet library.
- `DATA_FOR_MAPPING-1.xlsx` — original observation data.
- `assets/` — original species photographs.
- `requirements.txt` — Python runtime dependencies.
- `requirements-dev.txt` — runtime dependencies plus optional Playwright browser checks.
- `tests/` — automated checks.
- [Data and mapping documentation](docs/DATA_AND_MAPPING.md) — source schema, photo assignment, coordinate handling, and maintenance.

## Update the plants or photographs

Stop the app before editing the workbook. Keep the existing column names and enter one observation per row. Save the workbook, then restart `app.py` and reload the browser.

Add photographs inside the matching species folder under `assets/`. Supported image extensions and the explicit folder aliases are documented in [Data and mapping](docs/DATA_AND_MAPPING.md). Restart after changing the photo collection. The supplied collection currently provides 158 matched photographs for 18 source categories.

Keep a backup of your original data before making research edits. The application reads the workbook; it does not change its contents.

To use another workbook without renaming it, set `DATA_FILE` before starting the app:

```powershell
$env:DATA_FILE = "C:\path\to\your-observations.xlsx"
.\.venv\Scripts\python.exe app.py
```

On macOS or Linux, use `DATA_FILE="/path/to/your-observations.xlsx" .venv/bin/python app.py`. Photograph matching still uses this project's `assets/` folder. Remove the environment variable to restore the default workbook.

## Checks

Run the automated Python checks from the project folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

On macOS or Linux, use `.venv/bin/python` in place of the Windows Python path.

Optional browser checks use Playwright. Install the development dependencies and its Chromium browser once:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Start the app in one terminal, then run this in a second terminal:

```powershell
.\.venv\Scripts\python.exe tests/browser_check.py
```

Use `--url http://127.0.0.1:5056` if the app is running on another port. Add `--screenshots .qa` to save browser screenshots in the ignored `.qa/` folder. The browser dependency is for development checks only. It is not needed to use the website in your own browser.

## Troubleshooting

**The map background is blank but dots or controls appear.** Check the internet connection. Street and satellite tiles come from external providers; try the other basemap. The dataset and photos do not require an external map service account.

**A plant has no photograph.** Confirm that its matching folder contains a supported image and is available locally. A folder containing no usable images is treated as having no photo. The app does not borrow photographs from a different species.

**The workbook cannot be found or read.** Keep it at the project root with the name `DATA_FOR_MAPPING-1.xlsx`. Check that OneDrive has downloaded it and that the required columns are present. See the terminal message for the specific problem.

**Dependencies are missing.** Run the install command again using the `.venv` Python. Running the app with a different Python interpreter can use a different set of installed packages.

**Port 5055 is unavailable, already in use, or Windows reports that socket access is forbidden.** Windows can reserve some port ranges. Choose another free port, or stop the other local process if it is using the port:

```powershell
$env:PORT = "5056"
.\.venv\Scripts\python.exe app.py
```

Then open **http://127.0.0.1:5056**. On macOS or Linux, run `PORT=5056 .venv/bin/python app.py`.

## Mapping libraries and attribution

Python libraries: [Flask](https://flask.palletsprojects.com/), [Folium](https://python-visualization.github.io/folium/), [openpyxl](https://openpyxl.readthedocs.io/), and [Pillow](https://pillow.readthedocs.io/). Folium generates a browser map powered by [Leaflet](https://leafletjs.com/).

Street map data is attributed to [OpenStreetMap contributors](https://www.openstreetmap.org/copyright). Satellite imagery uses Esri's World Imagery service; provider attribution appears on the map. Preserve these credits when adapting the code.
