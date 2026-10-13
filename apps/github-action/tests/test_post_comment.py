import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import post_comment  # noqa: E402
from post_comment import MARKER, GitHub, GitHubError, publish  # noqa: E402


class FakeApi:
    """In-memory issue comments, answering the requests GitHub would."""

    def __init__(self, comments=None, forbidden_ids=(), fail_with=None):
        self.comments = list(comments or [])
        self.forbidden_ids = set(forbidden_ids)
        self.fail_with = fail_with
        self.calls = []
        self.next_id = 1000

    def __call__(self, method, url, body):
        self.calls.append((method, url))
        if self.fail_with:
            return self.fail_with, {"message": "Resource not accessible by integration"}
        if method == "GET":
            page = int(url.rsplit("page=", 1)[1])
            return 200, self.comments[(page - 1) * 100 : page * 100]
        if method == "POST":
            self.next_id += 1
            comment = {"id": self.next_id, "body": body["body"], "user": {"type": "Bot"}}
            self.comments.append(comment)
            return 201, comment
        if method == "PATCH":
            comment_id = int(url.rsplit("/", 1)[1])
            if comment_id in self.forbidden_ids:
                return 403, {"message": "Forbidden"}
            comment = next(c for c in self.comments if c["id"] == comment_id)
            comment["body"] = body["body"]
            return 200, comment
        raise AssertionError(method)


def _gh(api):
    return GitHub("token", "https://api.example", "acme/models", request=api)


def test_sticky_creates_then_updates():
    api = FakeApi()
    gh = _gh(api)
    assert publish(gh, 7, "first", "sticky", files=1) == "created"
    assert publish(gh, 7, "second", "sticky", files=1) == "updated"
    assert len(api.comments) == 1
    assert api.comments[0]["body"] == f"{MARKER}\nsecond"
    assert publish(gh, 7, "second", "sticky", files=1) == "unchanged"


def test_sticky_without_ifc_changes():
    api = FakeApi()
    assert publish(_gh(api), 7, "nothing", "sticky", files=0) == "skipped"
    assert not api.comments

    # An earlier comment is corrected when the IFC changes are gone again.
    api = FakeApi([{"id": 1, "body": f"{MARKER}\nold", "user": {"type": "Bot"}}])
    assert publish(_gh(api), 7, "none now", "sticky", files=0) == "updated"


def test_sticky_skips_comments_it_cannot_edit():
    pasted = {"id": 1, "body": f"look: {MARKER}", "user": {"type": "User"}}
    api = FakeApi([pasted], forbidden_ids={1})
    assert publish(_gh(api), 7, "report", "sticky", files=1) == "created"
    assert pasted["body"] == f"look: {MARKER}"


def test_sticky_prefers_bot_comment():
    user = {"id": 1, "body": MARKER, "user": {"type": "User"}}
    bot = {"id": 2, "body": f"{MARKER}\nold", "user": {"type": "Bot"}}
    api = FakeApi([user, bot])
    publish(_gh(api), 7, "new", "sticky", files=1)
    assert bot["body"] == f"{MARKER}\nnew"
    assert user["body"] == MARKER


def test_paginates():
    others = [{"id": i, "body": "hi", "user": {"type": "User"}} for i in range(150)]
    bot = {"id": 999, "body": f"{MARKER}\nold", "user": {"type": "Bot"}}
    api = FakeApi([*others, bot])
    assert publish(_gh(api), 7, "new", "sticky", files=1) == "updated"
    assert [m for m, _ in api.calls].count("GET") == 2


def test_new_mode_always_creates():
    api = FakeApi([{"id": 1, "body": f"{MARKER}\nold", "user": {"type": "Bot"}}])
    assert publish(_gh(api), 7, "again", "new", files=1) == "created"
    assert len(api.comments) == 2


def test_errors_raise():
    with pytest.raises(GitHubError) as info:
        publish(_gh(FakeApi(fail_with=500)), 7, "x", "sticky", files=1)
    assert info.value.status == 500


@pytest.fixture
def action_env(tmp_path, monkeypatch):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"number": 7}}))
    report = tmp_path / "report.md"
    report.write_text("## BIMDelta review\n\nbody\n\n---\n<sub>bimdelta</sub>\n")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    monkeypatch.setenv("GITHUB_REPOSITORY", "acme/models")
    return report


def test_main_fork_without_permission_warns(action_env, monkeypatch, capsys):
    api = FakeApi(fail_with=403)
    monkeypatch.setattr(post_comment.GitHub, "_urllib_request", lambda self, *a: api(*a))
    assert post_comment.main([str(action_env)]) == 0
    assert "::warning::" in capsys.readouterr().out


def test_main_private_note(action_env, monkeypatch):
    api = FakeApi()
    monkeypatch.setattr(post_comment.GitHub, "_urllib_request", lambda self, *a: api(*a))
    assert post_comment.main([str(action_env), "--private"]) == 0
    body = api.comments[0]["body"]
    assert body.startswith(MARKER)
    assert body.index(post_comment.PRIVATE_NOTE) < body.index("<sub>")


def test_main_outside_pull_request(action_env, tmp_path, monkeypatch, capsys):
    event = tmp_path / "push.json"
    event.write_text("{}")
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    assert post_comment.main([str(action_env)]) == 0
    assert "Not a pull request" in capsys.readouterr().out
