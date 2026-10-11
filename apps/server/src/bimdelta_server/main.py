from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.diff import router as diff_router

app = FastAPI(title="BIMDelta", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diff_router, prefix="/api")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}
