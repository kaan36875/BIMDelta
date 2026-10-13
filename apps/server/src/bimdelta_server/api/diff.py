from __future__ import annotations

import asyncio
import logging
import tempfile
from collections.abc import AsyncIterator
from functools import partial
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel

from bimdelta_core import DiffResult, run_diff

from ..config import diff_settings, server_settings
from ..fetch import TIMEOUT, FetchError, check_url, download, filename_from_url

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


class UrlDiffRequest(BaseModel):
    v1_url: str
    v2_url: str


async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        yield client


@router.post("/diff/url", response_model=DiffResult)
async def create_diff_from_urls(
    req: UrlDiffRequest,
    client: Annotated[httpx.AsyncClient, Depends(http_client)],
) -> DiffResult:
    """Download two models from public URLs (e.g. raw.githubusercontent.com) and diff them."""
    hosts = server_settings.url_allowed_hosts
    try:
        for url in (req.v1_url, req.v2_url):
            check_url(url, hosts)
    except FetchError as exc:
        raise HTTPException(exc.status, str(exc)) from exc

    v1_name = filename_from_url(req.v1_url)
    v2_name = filename_from_url(req.v2_url)
    with tempfile.TemporaryDirectory() as tmp_dir:
        v1_path = Path(tmp_dir) / "v1.ifc"
        v2_path = Path(tmp_dir) / "v2.ifc"
        try:
            await asyncio.gather(
                download(client, req.v1_url, v1_path, hosts, server_settings.max_upload_bytes),
                download(client, req.v2_url, v2_path, hosts, server_settings.max_upload_bytes),
            )
        except FetchError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(502, f"Download failed: {exc}") from exc

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                partial(run_diff, str(v1_path), v1_name, str(v2_path), v2_name, diff_settings),
            )
        except Exception as exc:
            logger.exception("Diff failed")
            raise HTTPException(400, f"Failed to process IFC files: {exc}") from exc


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
