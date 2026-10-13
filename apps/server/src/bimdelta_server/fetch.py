"""Downloading model files from URLs, for the viewer's URL mode.

Only https URLs on an allowlist of hosts are fetched (by default GitHub's raw content
hosts), redirects are followed only to allowed hosts, and downloads stop at the upload size
limit. The server never requests an address a visitor chose freely.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx

LFS_POINTER_HEADER = b"version https://git-lfs.github.com/spec/v1"
MAX_REDIRECTS = 3
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


class FetchError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def check_url(url: str, allowed_hosts: list[str]) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise FetchError(400, f"Only https URLs can be opened: {url}")
    if parts.username or parts.password or parts.port not in (None, 443):
        raise FetchError(400, f"URL not allowed: {url}")
    if (parts.hostname or "").lower() not in allowed_hosts:
        hosts = ", ".join(allowed_hosts)
        raise FetchError(400, f"Files can only be opened from {hosts}; got {parts.hostname}")


def filename_from_url(url: str) -> str:
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
    return name or "model.ifc"


def media_url(raw_url: str) -> str | None:
    """The URL serving the content of a Git LFS file whose raw URL returned its pointer."""
    parts = urlsplit(raw_url)
    if parts.hostname != "raw.githubusercontent.com":
        return None
    return f"https://media.githubusercontent.com/media{parts.path}"


async def download(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    allowed_hosts: list[str],
    max_bytes: int,
) -> None:
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        check_url(current, allowed_hosts)
        async with client.stream("GET", current) as resp:
            if resp.is_redirect:
                location = resp.headers.get("location")
                if not location:
                    raise FetchError(502, f"Redirect without a location from {current}")
                current = str(resp.url.join(location))
                continue
            if resp.status_code in (401, 403, 404):
                raise FetchError(
                    404,
                    f"Could not download {filename_from_url(url)} (HTTP {resp.status_code}). "
                    "The repository may be private or the file may not exist at that commit; "
                    "the viewer can only open files from public repositories.",
                )
            if resp.status_code != 200:
                raise FetchError(502, f"Downloading {url} failed with HTTP {resp.status_code}")

            length = resp.headers.get("content-length")
            if length and length.isdigit() and int(length) > max_bytes:
                raise FetchError(413, _too_large(url, max_bytes))
            total = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise FetchError(413, _too_large(url, max_bytes))
                    f.write(chunk)
        break
    else:
        raise FetchError(502, f"Too many redirects from {url}")

    if _is_lfs_pointer(dest):
        lfs = media_url(current)
        if lfs is None or lfs == url:
            raise FetchError(422, f"{filename_from_url(url)} is a Git LFS pointer, not a model")
        await download(client, lfs, dest, allowed_hosts, max_bytes)


def _is_lfs_pointer(path: Path) -> bool:
    if path.stat().st_size > 1024:
        return False
    return path.read_bytes().startswith(LFS_POINTER_HEADER)


def _too_large(url: str, max_bytes: int) -> str:
    mb = max_bytes // (1024 * 1024)
    return (
        f"{filename_from_url(url)} exceeds the {mb} MB limit of the hosted viewer; "
        "use the bimdelta command line for larger models."
    )
