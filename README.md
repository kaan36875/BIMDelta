# BIMDelta

A web application that compares two IFC building model versions and visualises the differences in an interactive 3D viewer.

Upload a base model and an updated model — BIMDelta parses both files, matches elements by GlobalId (with placement-based fallback), and classifies every element as **added**, **removed**, **modified**, or **unchanged**. Results are shown in a colour-coded 3D scene with element isolation, property diff details, and a natural-language query bar.

## Features

- **IFC diff engine** — property, placement, type, and geometry comparison with configurable tolerances
- **3D colour-coded viewer** — merged single-mesh rendering for 60 fps on large models (2000+ elements)
- **Element isolation** — click any element to isolate it with outline highlighting; removed elements shown at their original position
- **Natural-language query** — ask questions like *"which walls were modified?"* or *"show added doors on floor 2"*
- **Summary & table** — breakdown by class and storey, sortable/filterable element table, JSON export
- **Performance optimised** — parallel IFC parsing, lazy geometry computation, batch tessellation, pre-allocated typed arrays

## Tech Stack

| Layer    | Stack                                                  |
|----------|--------------------------------------------------------|
| Backend  | Python 3.12, FastAPI, IfcOpenShell, NumPy              |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS v4, three.js, web-ifc, Zustand |

## Quick Start

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install ".[dev]"
uvicorn app.main:app --port 8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the dev server proxies `/api` requests to the backend on port 8001.

## Docker

```bash
docker compose up --build
```

Frontend on http://localhost:3000, backend on http://localhost:8001.

## Deploy

### Frontend (Vercel)

1. Import the repo on [vercel.com](https://vercel.com)
2. Set **Root Directory** to `frontend`
3. Set **Build Command** to `npm run build`
4. Set **Output Directory** to `dist`
5. Add environment variable `VITE_API_URL` with your backend URL (e.g. `https://bimdelta-api.onrender.com`)

### Backend (Render / Railway / Fly.io)

Deploy the `backend` directory as a Docker service:

- **Dockerfile path:** `backend/Dockerfile`
- **Port:** `8001`
- **Health check:** `GET /api/health`

Make sure to set CORS origins in production (update `app/main.py` `allow_origins`).

## Project Structure

```
backend/
  app/
    api/          # FastAPI routes
    diff/         # Diff engine (parser, matcher, comparator, geometry)
    schemas/      # Pydantic models
    config.py     # Settings & tolerances
    main.py       # App entrypoint
  tests/          # Pytest suite
  Dockerfile

frontend/
  src/
    api/          # API client
    components/   # React components (Viewer3D, QueryBar, ChangeTable, etc.)
    store/        # Zustand state
    types/        # TypeScript interfaces
    utils/        # IFC loader, query engine, colours
  Dockerfile
```

## API

### `POST /api/diff`

Upload two IFC files as multipart form data (`v1` and `v2`). Returns a JSON diff result with element-level changes, property diffs, and summary statistics.

### `GET /api/health`

Returns `{"status": "ok"}`.

## License

MIT
