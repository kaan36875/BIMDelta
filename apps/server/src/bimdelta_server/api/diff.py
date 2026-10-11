from __future__ import annotations

import asyncio
import logging
import tempfile
from functools import partial
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from bimdelta_core import DiffResult, run_diff

from ..config import diff_settings, server_settings

logger = logging.getLogger(__name__)

router = APIRouter()

CHUNK_SIZE = 64 * 1024  # 64 KB


@router.post("/diff", response_model=DiffResult)
async def create_diff(v1: UploadFile, v2: UploadFile) -> DiffResult:
    if not _valid_extension(v1.filename):
        raise HTTPException(400, f"v1: expected .ifc file, got '{v1.filename}'")
    if not _valid_extension(v2.filename):
        raise HTTPException(400, f"v2: expected .ifc file, got '{v2.filename}'")

    with tempfile.TemporaryDirectory() as tmp_dir:
        v1_path = Path(tmp_dir) / "v1.ifc"
        v2_path = Path(tmp_dir) / "v2.ifc"

        await _save_upload(v1, v1_path, server_settings.max_upload_bytes)
        await _save_upload(v2, v2_path, server_settings.max_upload_bytes)

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                partial(
                    run_diff,
                    str(v1_path),
                    v1.filename or "v1.ifc",
                    str(v2_path),
                    v2.filename or "v2.ifc",
                    diff_settings,
                ),
            )
        except Exception as exc:
            logger.exception("Diff failed")
            raise HTTPException(400, f"Failed to process IFC files: {exc}") from exc

    return result


async def _save_upload(file: UploadFile, dest: Path, max_bytes: int) -> None:
    if file.size and file.size > max_bytes:
        raise HTTPException(
            413,
            f"File '{file.filename}' exceeds {max_bytes // (1024 * 1024)} MB limit",
        )

    total = 0
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    413,
                    f"File '{file.filename}' exceeds {max_bytes // (1024 * 1024)} MB limit",
                )
            f.write(chunk)


def _valid_extension(filename: str | None) -> bool:
    if not filename:
        return False
    return filename.lower().endswith(".ifc")
