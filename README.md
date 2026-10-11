<p align="center">
  <h1 align="center">BIMDelta</h1>
  <p align="center">
    Compare two IFC building models and visualise every change in an interactive 3D viewer.
  </p>
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=vahFeB2o-zM">Video Demo</a>
</p>

<p align="center">
  <a href="https://bimdelta.vercel.app/">Demo Website</a>
</p>

<p align="center">
  <img src="screenshots/2_fullscreen-model.png" width="100%" alt="3D colour-coded diff view" />
</p>

Upload a base model and an updated model — BIMDelta parses both IFC files, matches elements by GlobalId, by the authoring tool's element id, or by placement, and classifies every element as **added**, **removed**, **modified**, or **unchanged**. Export artefacts (different export settings, worksharing metadata) are filtered out and reported separately, so a model exported twice without changes produces an empty diff. Results are rendered in a colour-coded 3D scene where you can click any element to isolate it, inspect property-level changes, and query the diff in natural language.

## Screenshots

<table>
  <tr>
    <td width="50%">
      <img src="screenshots/1_upload-models.png" alt="Upload screen" />
      <p align="center"><strong>Upload</strong> — drag & drop two IFC files</p>
    </td>
    <td width="50%">
      <img src="screenshots/4_modified-element.png" alt="Modified element isolated" />
      <p align="center"><strong>Isolate</strong> — click to highlight with outline</p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="screenshots/3_removed-element.png" alt="Removed element shown at original position" />
      <p align="center"><strong>Removed</strong> — shown at original position in red</p>
    </td>
    <td width="50%">
      <img src="screenshots/5_ask-which-slabs-modify.png" alt="Natural language query" />
      <p align="center"><strong>Query</strong> — ask "which slabs are modified?"</p>
    </td>
  </tr>
  <tr>
    <td width="50%">
      <img src="screenshots/6_ask-which-columns-removed.png" alt="Query removed columns" />
      <p align="center"><strong>Query</strong> — "which columns are removed?"</p>
    </td>
    <td width="50%">
      <img src="screenshots/7_html-report.png" alt="Exported HTML report" />
      <p align="center"><strong>Export</strong> — downloadable HTML change report</p>
    </td>
  </tr>
</table>

## Features

- **IFC diff engine** — compares properties, placement, type, and geometry with configurable tolerances; usable as a Python library (`bimdelta-core`)
- **Stable element matching** — GlobalId, then the authoring tool's element id (`IfcElement.Tag`), then placement; see [element identity](docs/globalid-stability.md)
- **Noise filter** — export-setting differences and volatile metadata are reported once instead of on every element; see [noise filter](docs/noise-filter.md)
- **3D colour-coded viewer** — merged single-mesh rendering for 60 fps on large models (2800+ elements)
- **Element isolation** — click any element to isolate it with solid fill and black outline
- **Removed element visualisation** — removed elements shown as red ghosts at their original position
- **Natural-language query** — ask questions like *"which walls were modified?"* or *"show removed columns"*
- **Change summary** — breakdown by IFC class and storey, filterable element table
- **HTML export** — download a standalone change report
- **Performance optimised** — geometry is only tessellated when its IFC definition differs; pre-allocated typed arrays in the viewer

## Tech Stack

| Layer    | Stack                                                  |
|----------|--------------------------------------------------------|
| Backend  | Python 3.12 · FastAPI · IfcOpenShell · NumPy           |
| Frontend | React 19 · TypeScript · Vite · Tailwind CSS v4 · three.js · web-ifc · Zustand |
| Infra    | Docker · GitHub Actions CI                             |

## Quick Start

### Backend

```bash
python -m venv .venv
.venv/Scripts/activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -e "packages/bimdelta-core[dev]" -e "apps/server[dev]"
uvicorn bimdelta_server.main:app --port 8001
```

### Frontend

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:5173 — the dev server proxies `/api` requests to the backend on port 8001.

### As a library

```python
from bimdelta_core import load_settings, run_diff

result = run_diff("rev-a.ifc", "rev-a.ifc", "rev-b.ifc", "rev-b.ifc", load_settings())
print(result.summary.added, result.summary.removed, result.summary.modified)
```

### Docker

```bash
docker compose up --build
```

Frontend on http://localhost:3000, backend on http://localhost:8001.

### Tests

```bash
pytest packages/bimdelta-core
pytest apps/server
```

## Deploy

### Frontend → Vercel

1. Import the repo on [vercel.com](https://vercel.com)
2. Set **Root Directory** to `apps/web`
3. Set **Build Command** to `npm run build`
4. Set **Output Directory** to `dist`
5. Add environment variable `VITE_API_URL` with your backend URL

### Backend → Render

1. Create a new **Web Service** on [render.com](https://render.com)
2. Connect the repo and leave **Root Directory** empty (the image needs `packages/` too)
3. Select **Docker** runtime with **Dockerfile Path** `apps/server/Dockerfile`
4. Set **Health Check Path** to `/api/health`

## Project Structure

```
packages/
  bimdelta-core/      # Diff engine as a Python package
    src/bimdelta_core/
      parser.py       # IFC → elements, properties, placements, storeys
      matcher.py      # GlobalId → Tag → placement matching
      comparator.py   # Per-element comparison
      geometry.py     # Geometry fingerprint and signature
      noise.py        # Noise filter
      engine.py       # run_diff()
      schemas.py      # Pydantic result models
      config.py       # Settings, tolerances, .bimdelta.yml loading
    tests/
apps/
  server/             # FastAPI wrapper around bimdelta-core
  web/                # React + three.js viewer
docs/                 # Noise filter, element identity
samples/roundtrip/    # Recorded Revit export pairs for the round-trip battery
scripts/              # Benchmark and synthetic-revision tools
```

## How It Works

1. **Parse** — both IFC files are parsed with IfcOpenShell, extracting elements, properties, quantities, placements, and storey assignments
2. **Match** — elements are matched by GlobalId, then by the authoring tool's element id in `IfcElement.Tag`, then by class, name and storey within 50 mm ([details](docs/globalid-stability.md))
3. **Filter** — property sets that exist in only one file and ignored properties are taken out of the comparison and reported in the summary ([details](docs/noise-filter.md))
4. **Compare** — matched pairs are diffed across properties, placement, type, storey and geometry. Geometry is compared by a content hash of its IFC definition first and only tessellated (bounding box + volume) when that differs
5. **Render** — the frontend merges all element geometry into a single three.js mesh with per-vertex colours for 60 fps rendering at any model size

## Performance

Measured on a laptop with public sample models, using [`scripts/benchmark.py`](scripts/benchmark.py). The revisions were generated with [`scripts/make_revision.py`](scripts/make_revision.py), which applies a known set of edits to 2 % of the elements per edit type (moved, property changed, reshaped, deleted, GlobalId regenerated); the diff matched the expected result element for element, except where geometry could not be evaluated, which is reported.

| Model | Authoring tool | Size | Elements | Diff, unchanged | Diff, revision | Peak memory |
|---|---|---|---|---|---|---|
| Duplex | Revit 2011 | 2.3 MB | 218 | 1.3 s | 1.3 s | 110 MB |
| Advanced model | Revit 2021 | 34 MB | 6,442 | 21 s | 20 s | 710 MB |
| Schependomlaan | ArchiCAD | 47 MB | 3,621 | 22 s | 22 s | 940 MB |

Both files are held in memory, so peak memory is roughly 20× the file size; the hosted demo accepts files up to 50 MB.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/diff` | `POST` | Upload two IFC files (multipart `v1`, `v2`), returns full diff JSON |
| `/api/health` | `GET` | Health check — `{"status": "ok"}` |

## License

MIT
