from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.diff import router as diff_router

app = FastAPI(title="BIMDelta", version=__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diff_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": __version__}
