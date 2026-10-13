"""``bimdelta serve``: the viewer for a local repository, on 127.0.0.1.

Serves the web app (bundled into this package at release) and a small JSON API over the
repository: the commits that touched each IFC file, the file at any commit or in the working
tree, the diff between two of them and an element's history. Diffs are cached in
``<git dir>/bimdelta-cache`` keyed by blob ids, like ``bimdelta blame``.

Only loopback connections are served and the Host header must name the loopback address,
so a web page cannot reach the API through DNS rebinding.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import tempfile
import threading
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from bimdelta_core import Settings, __version__, run_diff

from .blame import CACHE_DIRNAME, BlameError
from .blame import blame as run_blame
from .gitutil import GitError, git, git_dir, git_text, repo_root

WORKTREE = "worktree"
LOCAL_MARKER = "<script>window.BIMDELTA_LOCAL=true</script>"
_SEP = "\x1f"


def bundled_web_dir() -> Path | None:
    web = files("bimdelta_cli") / "web"
    path = Path(str(web))
    return path if (path / "index.html").is_file() else None


class LocalRepo:
    def __init__(self, root: Path, cfg: Settings):
        self.root = root
        self.cfg = cfg
        self.cache_dir = git_dir(root) / CACHE_DIRNAME
        key = f"serve|{__version__}|{cfg.model_dump_json()}"
        self.settings_key = hashlib.blake2b(key.encode(), digest_size=8).hexdigest()
        self._lock = threading.Lock()

    # --- What is in the repository ----------------------------------------------------

    def info(self) -> dict:
        tracked = self._ifc_paths(git_text("ls-files", "-z", cwd=self.root).split("\0"))
        changed = set(
            self._ifc_paths(git_text("diff", "--name-only", "-z", cwd=self.root).split("\0"))
        )
        untracked = self._ifc_paths(
            git_text("ls-files", "--others", "--exclude-standard", "-z", cwd=self.root).split("\0")
        )
        try:
            head = git_text("rev-parse", "HEAD", cwd=self.root)
        except GitError:
            head = None
        return {
            "name": self.root.name,
            "head": head,
            "version": __version__,
            "files": [
                {"path": p, "worktree_changed": p in changed or p in untracked}
                for p in sorted(set(tracked) | set(untracked))
            ],
        }

    def log(self, path: str, limit: int = 200) -> dict:
        self.check_path(path)
        try:
            out = git_text(
                "log",
                f"--max-count={limit}",
                f"--format=%H{_SEP}%an{_SEP}%aI{_SEP}%s",
                "HEAD",
                "--",
                path,
                cwd=self.root,
            )
        except GitError:
            out = ""  # no commits yet
        commits = []
        for line in out.splitlines():
            sha, author, date, subject = line.split(_SEP, 3)
            commits.append({"sha": sha, "author": author, "date": date, "subject": subject})
        worktree = self._worktree_blob(path)
        latest = self._blob(commits[0]["sha"], path) if commits else None
        return {
            "path": path,
            "commits": commits,  # newest first
            "worktree_changed": worktree is not None and worktree != latest,
        }

    # --- Contents ---------------------------------------------------------------------

    def model(self, path: str, rev: str) -> bytes:
        self.check_path(path)
        if rev == WORKTREE:
            return (self.root / path).read_bytes()
        sha = self.check_rev(rev)
        # --filters applies smudge filters, so Git LFS pointers come back as content.
        return git("cat-file", "--filters", f"{sha}:{path}", cwd=self.root)

    def diff(self, path: str, base: str, head: str) -> str:
        self.check_path(path)
        old_blob = self._blob_for(path, base)
        new_blob = self._blob_for(path, head)
        cache = self.cache_dir / f"diff-{old_blob}-{new_blob}-{self.settings_key}.json"
        # One computation per pair, however many requests ask for it at once.
        with self._lock:
            try:
                return cache.read_text(encoding="utf-8")
            except OSError:
                pass
            name = Path(path).name
            with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
                old = Path(tmp) / "old.ifc"
                new = Path(tmp) / "new.ifc"
                old.write_bytes(self.model(path, base))
                new.write_bytes(self.model(path, head))
                result = run_diff(str(old), name, str(new), name, self.cfg)
            text = result.model_dump_json()
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                cache.write_text(text, encoding="utf-8")
            except OSError:
                pass
            return text

    def blame(self, path: str, global_id: str, rev: str, max_commits: int | None) -> dict:
        self.check_path(path)
        sha = self.check_rev(rev)
        with self._lock:
            result = run_blame(
                global_id,
                str(self.root / path),
                self.cfg,
                repo=self.root,
                rev=sha,
                max_commits=max_commits,
            )
        return asdict(result)

    # --- Validation -------------------------------------------------------------------

    def check_path(self, path: str) -> None:
        if not path or not path.lower().endswith(".ifc") or path.startswith(("/", "\\")):
            raise BadRequestError(f"not an IFC file in this repository: {path}")
        full = (self.root / path).resolve()
        if self.root.resolve() not in full.parents:
            raise BadRequestError(f"not an IFC file in this repository: {path}")

    def check_rev(self, rev: str) -> str:
        if not rev or rev.startswith("-"):
            raise BadRequestError(f"bad revision: {rev}")
        try:
            return git_text("rev-parse", "--verify", "--quiet", f"{rev}^{{commit}}", cwd=self.root)
        except GitError:
            raise BadRequestError(f"unknown revision: {rev}") from None

    def _blob_for(self, path: str, rev: str) -> str:
        if rev == WORKTREE:
            blob = self._worktree_blob(path)
            if blob is None:
                raise NotFoundError(f"{path} is not in the working tree")
            return blob
        blob = self._blob(self.check_rev(rev), path)
        if blob is None:
            raise NotFoundError(f"{path} does not exist at {rev}")
        return blob

    def _blob(self, sha: str, path: str) -> str | None:
        try:
            return git_text("rev-parse", "--verify", "--quiet", f"{sha}:{path}", cwd=self.root)
        except GitError:
            return None

    def _worktree_blob(self, path: str) -> str | None:
        if not (self.root / path).is_file():
            return None
        # Same id Git would store, after clean filters (Git LFS), so caches line up.
        return git_text("hash-object", "--", path, cwd=self.root)

    @staticmethod
    def _ifc_paths(paths: list[str]) -> list[str]:
        return [p for p in paths if p.lower().endswith(".ifc")]


class BadRequestError(Exception):
    status = HTTPStatus.BAD_REQUEST


class NotFoundError(Exception):
    status = HTTPStatus.NOT_FOUND


def make_handler(repo: LocalRepo, web_dir: Path | None):
    allowed_hosts = {"127.0.0.1", "localhost", "[::1]"}

    class Handler(BaseHTTPRequestHandler):
        server_version = f"bimdelta/{__version__}"

        def log_message(self, format, *args):  # noqa: A002
            pass  # quiet; errors are reported to the client

        def do_GET(self):  # noqa: N802
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            if host not in allowed_hosts:
                return self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
            url = urlsplit(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path.startswith("/api/local/"):
                    return self._api(url.path.removeprefix("/api/local/"), query)
                return self._static(url.path)
            except (BadRequestError, NotFoundError) as exc:
                return self._json(exc.status, {"detail": str(exc)})
            except (GitError, BlameError) as exc:
                return self._json(HTTPStatus.BAD_REQUEST, {"detail": str(exc)})
            except Exception as exc:  # pragma: no cover - reported to the viewer
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"detail": str(exc)})

        def _api(self, name: str, q: dict[str, str]):
            if name == "info":
                return self._json(HTTPStatus.OK, repo.info())
            if name == "log":
                return self._json(HTTPStatus.OK, repo.log(q.get("path", "")))
            if name == "model":
                data = repo.model(q.get("path", ""), q.get("rev", ""))
                return self._send(HTTPStatus.OK, data, "application/octet-stream")
            if name == "diff":
                text = repo.diff(q.get("path", ""), q.get("base", ""), q.get("head", ""))
                return self._send(HTTPStatus.OK, text.encode(), "application/json")
            if name == "blame":
                limit = q.get("max_commits")
                return self._json(
                    HTTPStatus.OK,
                    repo.blame(
                        q.get("path", ""),
                        q.get("global_id", ""),
                        q.get("rev", "HEAD"),
                        int(limit) if limit and limit.isdigit() else None,
                    ),
                )
            raise NotFoundError(f"no such endpoint: {name}")

        def _static(self, path: str):
            if web_dir is None:
                return self._send(
                    HTTPStatus.NOT_FOUND,
                    b"This bimdelta installation has no bundled viewer.",
                    "text/plain",
                )
            target = (web_dir / path.lstrip("/")).resolve()
            if web_dir.resolve() not in target.parents or not target.is_file():
                target = web_dir / "index.html"  # single-page app routes
            data = target.read_bytes()
            if target.name == "index.html":
                data = data.replace(b"<head>", b"<head>" + LOCAL_MARKER.encode(), 1)
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.suffix == ".wasm":
                ctype = "application/wasm"
            return self._send(HTTPStatus.OK, data, ctype)

        def _json(self, status, payload):
            return self._send(status, json.dumps(payload).encode(), "application/json")

        def _send(self, status, data: bytes, ctype: str):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

    return Handler


def create_server(
    root: Path, cfg: Settings, port: int = 0, web_dir: Path | None = None
) -> ThreadingHTTPServer:
    repo = LocalRepo(repo_root(root), cfg)
    return ThreadingHTTPServer(("127.0.0.1", port), make_handler(repo, web_dir))
