"""Post a BIMDelta review as a pull request comment.

Standard library only, so the action needs nothing beyond bimdelta itself.

    python post_comment.py REPORT.md --mode sticky|new [--files N] [--private]

Reads GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_API_URL and the pull request number from
GITHUB_EVENT_PATH. In sticky mode the comment carrying MARKER is edited in place, so a pull
request keeps one BIMDelta comment however often it is pushed to.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

MARKER = "<!-- bimdelta-bot -->"
PRIVATE_NOTE = (
    "> 3D viewer links are left out: the viewer can only open files from public repositories."
)

# (method, url, body) -> (status, parsed JSON)
Request = Callable[[str, str, dict | None], tuple[int, object]]


class GitHub:
    def __init__(self, token: str, api_url: str, repo: str, request: Request | None = None):
        self.token = token
        self.base = f"{api_url.rstrip('/')}/repos/{repo}"
        self.request = request or self._urllib_request

    def _urllib_request(self, method: str, url: str, body: dict | None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"null")

    def comments(self, number: int) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            status, data = self.request(
                "GET", f"{self.base}/issues/{number}/comments?per_page=100&page={page}", None
            )
            _check(status, data, "list comments")
            out.extend(data)
            if len(data) < 100:
                return out
            page += 1

    def create(self, number: int, body: str) -> dict:
        status, data = self.request("POST", f"{self.base}/issues/{number}/comments", {"body": body})
        _check(status, data, "create comment")
        return data

    def update(self, comment_id: int, body: str) -> dict:
        status, data = self.request(
            "PATCH", f"{self.base}/issues/comments/{comment_id}", {"body": body}
        )
        _check(status, data, "update comment")
        return data


class GitHubError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _check(status: int, data: object, what: str) -> None:
    if status >= 300:
        message = data.get("message") if isinstance(data, dict) else None
        raise GitHubError(status, f"{what}: HTTP {status} {message or ''}".strip())


def publish(gh: GitHub, number: int, report: str, mode: str, files: int) -> str:
    """Post or update the comment. Returns what happened: created, updated or skipped."""
    body = f"{MARKER}\n{report}"
    if mode == "new":
        if files == 0:
            return "skipped"
        gh.create(number, body)
        return "created"

    # Bot comments first: anyone can paste the marker into a comment, and only the token's own
    # comments can be edited.
    marked = [c for c in gh.comments(number) if MARKER in (c.get("body") or "")]
    marked.sort(key=lambda c: (c.get("user") or {}).get("type") != "Bot")
    for existing in marked:
        if existing.get("body") == body:
            return "unchanged"
        try:
            gh.update(existing["id"], body)
        except GitHubError as exc:
            if exc.status == 403:
                continue
            raise
        return "updated"
    if files == 0:
        # Nothing to report and nothing to correct.
        return "skipped"
    gh.create(number, body)
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report")
    parser.add_argument("--mode", choices=("sticky", "new"), default="sticky")
    parser.add_argument("--files", type=int, default=1, help="Number of changed IFC files.")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args(argv)

    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as f:
        event = json.load(f)
    pr = event.get("pull_request") or {}
    number = pr.get("number")
    if number is None:
        print("Not a pull request event; no comment posted.")
        return 0

    with open(args.report, encoding="utf-8") as f:
        report = f.read()
    if args.private:
        report = report.replace("\n---\n", f"\n{PRIVATE_NOTE}\n\n---\n", 1)

    gh = GitHub(
        os.environ["GITHUB_TOKEN"],
        os.environ.get("GITHUB_API_URL", "https://api.github.com"),
        os.environ["GITHUB_REPOSITORY"],
    )
    try:
        outcome = publish(gh, number, report, args.mode, args.files)
    except GitHubError as exc:
        if exc.status in (403, 404):
            # Typical for pull requests from forks, whose token cannot write comments.
            print(
                f"::warning::BIMDelta could not comment on this pull request ({exc}). "
                "The review is in the job summary."
            )
            return 0
        raise
    print(f"BIMDelta comment {outcome} on #{number}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
