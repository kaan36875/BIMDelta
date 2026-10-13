from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from bimdelta_server.api.diff import http_client
from bimdelta_server.config import server_settings
from bimdelta_server.main import app

RAW = "https://raw.githubusercontent.com/acme/models"
MEDIA = "https://media.githubusercontent.com/media/acme/models"
POINTER = b"version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 1\n"


@pytest.fixture
def serve(basic_diff_files: tuple[Path, Path]):
    """Install a fake internet: ``serve(routes)`` maps URLs to responses."""
    v1, v2 = basic_diff_files
    files = {"v1": v1.read_bytes(), "v2": v2.read_bytes()}
    requested: list[str] = []

    def install(routes: dict[str, httpx.Response | bytes | str]):
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            requested.append(url)
            value = routes.get(url, httpx.Response(404))
            if isinstance(value, str):
                return httpx.Response(200, content=files[value])
            if isinstance(value, bytes):
                return httpx.Response(200, content=value)
            return value

        async def client():
            transport = httpx.MockTransport(handler)
            async with httpx.AsyncClient(transport=transport, follow_redirects=False) as c:
                yield c

        app.dependency_overrides[http_client] = client
        return requested

    yield install
    app.dependency_overrides.clear()


def _post(v1_url: str, v2_url: str) -> httpx.Response:
    return TestClient(app).post("/api/diff/url", json={"v1_url": v1_url, "v2_url": v2_url})


def test_diff_from_urls(serve):
    serve({f"{RAW}/a1/house.ifc": "v1", f"{RAW}/b2/house%20v2.ifc": "v2"})
    resp = _post(f"{RAW}/a1/house.ifc", f"{RAW}/b2/house%20v2.ifc")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["v1_filename"] == "house.ifc"
    assert data["v2_filename"] == "house v2.ifc"
    assert (data["summary"]["added"], data["summary"]["removed"]) == (1, 1)


def test_lfs_pointer_is_resolved_through_media_host(serve):
    requested = serve(
        {
            f"{RAW}/a1/m.ifc": POINTER,
            f"{MEDIA}/a1/m.ifc": "v1",
            f"{RAW}/b2/m.ifc": "v2",
        }
    )
    resp = _post(f"{RAW}/a1/m.ifc", f"{RAW}/b2/m.ifc")
    assert resp.status_code == 200, resp.text
    assert f"{MEDIA}/a1/m.ifc" in requested


def test_redirect_to_allowed_host(serve):
    serve(
        {
            f"{MEDIA}/a1/m.ifc": httpx.Response(
                302, headers={"location": "https://objects.githubusercontent.com/x"}
            ),
            "https://objects.githubusercontent.com/x": "v1",
            f"{RAW}/b2/m.ifc": "v2",
        }
    )
    assert _post(f"{MEDIA}/a1/m.ifc", f"{RAW}/b2/m.ifc").status_code == 200


def test_redirect_to_other_host_is_refused(serve):
    requested = serve(
        {
            f"{RAW}/a1/m.ifc": httpx.Response(
                302, headers={"location": "http://169.254.169.254/latest/meta-data"}
            ),
            f"{RAW}/b2/m.ifc": "v2",
        }
    )
    resp = _post(f"{RAW}/a1/m.ifc", f"{RAW}/b2/m.ifc")
    assert resp.status_code == 400
    assert not any("169.254" in url for url in requested)


@pytest.mark.parametrize(
    "url",
    [
        "http://raw.githubusercontent.com/acme/models/a1/m.ifc",
        "https://example.com/m.ifc",
        "https://raw.githubusercontent.com.evil.example/m.ifc",
        "https://user:pw@raw.githubusercontent.com/m.ifc",
        "https://raw.githubusercontent.com:8443/m.ifc",
        "file:///etc/passwd",
    ],
)
def test_disallowed_urls_are_not_fetched(serve, url):
    requested = serve({})
    resp = _post(url, f"{RAW}/b2/m.ifc")
    assert resp.status_code == 400
    assert requested == []


def test_missing_or_private_file(serve):
    serve({f"{RAW}/b2/m.ifc": "v2"})
    resp = _post(f"{RAW}/a1/m.ifc", f"{RAW}/b2/m.ifc")
    assert resp.status_code == 404
    assert "public repositories" in resp.json()["detail"]


def test_size_limit(serve, monkeypatch):
    monkeypatch.setattr(server_settings, "max_upload_bytes", 1000)
    serve({f"{RAW}/a1/m.ifc": "v1", f"{RAW}/b2/m.ifc": "v2"})
    resp = _post(f"{RAW}/a1/m.ifc", f"{RAW}/b2/m.ifc")
    assert resp.status_code == 413
    assert "command line" in resp.json()["detail"]


def test_not_a_model(serve):
    serve({f"{RAW}/a1/m.ifc": b"<html>nope</html>", f"{RAW}/b2/m.ifc": "v2"})
    assert _post(f"{RAW}/a1/m.ifc", f"{RAW}/b2/m.ifc").status_code == 400
