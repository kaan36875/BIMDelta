from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health(self, client: TestClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data


class TestDiffEndpoint:
    def test_diff_returns_result(
        self, client: TestClient, basic_diff_files: tuple[Path, Path]
    ):
        v1_path, v2_path = basic_diff_files
        with open(v1_path, "rb") as f1, open(v2_path, "rb") as f2:
            resp = client.post(
                "/api/diff",
                files={
                    "v1": ("v1.ifc", f1, "application/octet-stream"),
                    "v2": ("v2.ifc", f2, "application/octet-stream"),
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["schema_version"] == "1.0.0"
        assert data["summary"]["added"] == 1
        assert data["summary"]["removed"] == 1

    def test_rejects_non_ifc(self, client: TestClient, tmp_path: Path):
        txt = tmp_path / "file.txt"
        txt.write_text("not an ifc file")
        with open(txt, "rb") as f:
            resp = client.post(
                "/api/diff",
                files={
                    "v1": ("file.txt", f, "application/octet-stream"),
                    "v2": ("file.txt", f, "application/octet-stream"),
                },
            )
        assert resp.status_code == 400

    def test_rejects_oversized_file(self, client: TestClient, tmp_path: Path):
        # Temporarily lower the limit for testing
        from app.config import settings
        original = settings.max_upload_bytes
        settings.max_upload_bytes = 100  # 100 bytes

        try:
            ifc_path = tmp_path / "big.ifc"
            ifc_path.write_bytes(b"x" * 200)
            with open(ifc_path, "rb") as f1, open(ifc_path, "rb") as f2:
                resp = client.post(
                    "/api/diff",
                    files={
                        "v1": ("big.ifc", f1, "application/octet-stream"),
                        "v2": ("big.ifc", f2, "application/octet-stream"),
                    },
                )
            assert resp.status_code == 413
        finally:
            settings.max_upload_bytes = original
