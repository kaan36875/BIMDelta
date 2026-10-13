import http.client
import json
import threading

import pytest

from bimdelta_cli.serve import create_server
from bimdelta_core import DiffResult, Settings

from .conftest import WALL_A, WALL_A_REEXPORTED, make_model


@pytest.fixture
def server(history, tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html><head><title>x</title></head></html>")
    (web / "app.wasm").write_bytes(b"\0asm")
    srv = create_server(history.path, Settings(), 0, web)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _get(server, path, host="127.0.0.1"):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=30)
    conn.request("GET", path, headers={"Host": f"{host}:{server.server_address[1]}"})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, resp.getheader("Content-Type"), body


def _json(server, path):
    status, _, body = _get(server, path)
    assert status == 200, body
    return json.loads(body)


def test_info_and_log(server):
    info = _json(server, "/api/local/info")
    assert info["files"] == [{"path": "model.ifc", "worktree_changed": False}]
    log = _json(server, "/api/local/log?path=model.ifc")
    assert [c["subject"] for c in log["commits"]] == [
        "Add column, remove Wall-C",
        "Re-export with new ids",
        "Initial model",
    ]
    assert log["commits"][0]["author"] == "Alice"
    assert log["worktree_changed"] is False


def test_model_and_diff(server, history):
    status, ctype, body = _get(server, "/api/local/model?path=model.ifc&rev=HEAD~2")
    assert status == 200 and ctype == "application/octet-stream"
    assert body.startswith(b"ISO-10303-21")

    result = DiffResult.model_validate(
        _json(server, "/api/local/diff?path=model.ifc&base=HEAD~2&head=HEAD")
    )
    assert (result.summary.added, result.summary.removed, result.summary.modified) == (1, 1, 1)
    cached = list((history.path / ".git" / "bimdelta-cache").glob("diff-*.json"))
    assert len(cached) == 1


def test_working_copy(server, history):
    make_model("3HR", wall_a_id=WALL_A_REEXPORTED).write(str(history.path / "model.ifc"))
    log = _json(server, "/api/local/log?path=model.ifc")
    assert log["worktree_changed"] is True
    result = DiffResult.model_validate(
        _json(server, "/api/local/diff?path=model.ifc&base=HEAD&head=worktree")
    )
    assert result.summary.modified == 1
    assert _json(server, "/api/local/info")["files"][0]["worktree_changed"] is True


def test_blame(server):
    data = _json(server, f"/api/local/blame?path=model.ifc&global_id={WALL_A_REEXPORTED}&rev=HEAD")
    assert [e["change"] for e in data["events"]] == ["modified", "added"]
    assert data["events"][1]["global_id"] == WALL_A


def test_static_files_and_local_marker(server):
    status, ctype, body = _get(server, "/")
    assert status == 200 and ctype.startswith("text/html")
    assert b"window.BIMDELTA_LOCAL=true" in body
    status, _, body = _get(server, "/some/route")
    assert b"BIMDELTA_LOCAL" in body  # single-page app fallback
    status, ctype, _ = _get(server, "/app.wasm")
    assert ctype == "application/wasm"


@pytest.mark.parametrize(
    "path",
    [
        "/api/local/model?path=../outside.ifc&rev=HEAD",
        "/api/local/model?path=notes.txt&rev=HEAD",
        "/api/local/model?path=model.ifc&rev=--output=x",
        "/api/local/model?path=model.ifc&rev=nope",
        "/api/local/diff?path=model.ifc&base=HEAD&head=worktree%2F..",
    ],
)
def test_rejects_bad_input(server, path):
    status, _, body = _get(server, path)
    assert status in (400, 404), body


def test_rejects_other_hosts(server):
    """A page on another site cannot reach the API through DNS rebinding."""
    status, _, _ = _get(server, "/api/local/info", host="attacker.example")
    assert status == 403


def test_static_traversal(server, history):
    (history.path / "secret.txt").write_text("secret")
    status, _, body = _get(server, "/../../repo/secret.txt")
    assert b"secret" not in body
