"""The ``bimdelta`` command."""

from __future__ import annotations

import json
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import Annotated, NoReturn

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

import bimdelta_core
from bimdelta_core import (
    CONFIG_FILENAME,
    Settings,
    filter_result,
    load_settings,
    quantity_delta,
    run_diff,
)
from bimdelta_core.engine import IFC_LOCK
from bimdelta_core.parser import parse_ifc

from . import __version__, gitdriver
from .blame import BlameError
from .blame import blame as run_blame
from .filters import FilterError, parse_filter
from .gitutil import GitError, repo_root, resolve_lfs
from .render import has_changes, md_escape, print_table, to_markdown
from .review import ViewerLinks
from .review import review as run_review
from .review import to_markdown as review_markdown
from .snapshot import snapshot

app = typer.Typer(
    name="bimdelta",
    help="Code review for building models: element-level diffs of IFC files.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode=None,
)

console = Console()
# For messages: long paths and commit subjects should not be broken across lines.
say = Console(soft_wrap=True)
err = Console(stderr=True, soft_wrap=True)

EXIT_CHANGES = 1
EXIT_ERROR = 2


class Format(str, Enum):
    table = "table"
    json = "json"
    markdown = "markdown"


class GroupBy(str, Enum):
    by_class = "class"
    material = "material"


def _fail(message: str) -> NoReturn:
    err.print(Text(f"error: {message}", style="red"))
    raise typer.Exit(EXIT_ERROR)


def _utf8_stdout() -> None:
    # Windows consoles and pipes default to a legacy code page; output contains → and ∅.
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def find_config(start: Path) -> Path | None:
    """The nearest ``.bimdelta.yml`` in ``start`` or one of its parents."""
    for directory in (start.resolve(), *start.resolve().parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def _settings(config: Path | None, strict: bool) -> Settings:
    path = config if config is not None else find_config(Path.cwd())
    overrides = {"strict": True} if strict else {}
    try:
        return load_settings(path, **overrides)
    except (OSError, ValueError) as exc:
        _fail(str(exc))


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"bimdelta {__version__} (bimdelta-core {bimdelta_core.__version__})")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    _utf8_stdout()


ConfigOption = Annotated[
    Path | None,
    typer.Option(
        "--config",
        help=f"Settings file. Default: the nearest {CONFIG_FILENAME} here or in a parent.",
        dir_okay=False,
    ),
]
StrictOption = Annotated[
    bool, typer.Option("--strict", help="Turn the noise filter off and report every difference.")
]
ExistingFile = Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)]


@app.command()
def diff(
    v1: ExistingFile,
    v2: ExistingFile,
    format: Annotated[Format, typer.Option("--format", "-f", help="Output format.")] = Format.table,
    summary_only: Annotated[
        bool, typer.Option("--summary-only", help="Counts only, no element list.")
    ] = False,
    filter: Annotated[
        str | None,
        typer.Option(
            "--filter",
            help="Keep matching elements only, e.g. 'class=IfcWall*,storey=Level 1'. "
            "Keys: class, storey, change, name, id. Same key = OR, different keys = AND.",
        ),
    ] = None,
    strict: StrictOption = False,
    config: ConfigOption = None,
    limit: Annotated[
        int, typer.Option(help="Most elements to list in table/markdown output; 0 = all.")
    ] = 100,
    exit_code: Annotated[
        bool, typer.Option("--exit-code", help="Exit with 1 if there are changes, like git diff.")
    ] = False,
) -> None:
    """Compare two versions of an IFC model."""
    cfg = _settings(config, strict)
    keep = None
    if filter:
        try:
            keep = parse_filter(filter)
        except FilterError as exc:
            _fail(f"--filter: {exc}")

    try:
        result = run_diff(str(v1), v1.name, str(v2), v2.name, cfg)
    except Exception as exc:
        _fail(f"could not compare the models: {exc}")
    if keep is not None:
        result = filter_result(result, keep)

    if format == Format.json:
        payload = result.summary if summary_only else result
        sys.stdout.write(payload.model_dump_json(indent=2) + "\n")
    elif format == Format.markdown:
        sys.stdout.write(to_markdown(result, summary_only=summary_only, limit=limit))
    else:
        print_table(console, result, summary_only=summary_only, limit=limit)

    if exit_code and has_changes(result):
        raise typer.Exit(EXIT_CHANGES)


@app.command()
def quantities(
    v1: ExistingFile,
    v2: ExistingFile,
    by: Annotated[GroupBy, typer.Option("--by", help="Group by IFC class or material.")] = (
        GroupBy.by_class
    ),
    format: Annotated[Format, typer.Option("--format", "-f")] = Format.table,
) -> None:
    """Quantity take-off of two versions and the change, from the exported quantity sets."""
    try:
        result = quantity_delta(str(v1), v1.name, str(v2), v2.name, by.value)
    except Exception as exc:
        _fail(f"could not read quantities: {exc}")

    if format == Format.json:
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return

    rows = [*result.rows, result.total]
    head = [
        "Class" if by == GroupBy.by_class else "Material",
        "Count",
        "Length m",
        "Area m²",
        "Volume m³",
    ]

    def cells(row) -> list[str]:
        out = [f"{row.v2.count} ({row.delta.count:+d})"]
        for attr in ("length", "area", "volume"):
            new, delta = getattr(row.v2, attr), getattr(row.delta, attr)
            out.append(f"{new:,.2f} ({delta:+,.2f})")
        return out

    missing = [
        f"{n} element(s) in {name} have no quantities (export base quantities to include them)."
        for n, name in (
            (result.v1_without_quantities, result.v1_filename),
            (result.v2_without_quantities, result.v2_filename),
        )
        if n
    ]

    if format == Format.markdown:
        lines = [
            f"### Quantities: {md_escape(result.v1_filename)} → {md_escape(result.v2_filename)}",
            "",
            "| " + " | ".join(head) + " |",
            "|---|" + "---:|" * (len(head) - 1),
        ]
        for row in rows:
            group = f"**{row.group}**" if row is result.total else md_escape(row.group)
            lines.append(f"| {group} | " + " | ".join(cells(row)) + " |")
        lines += [f"\n> {m}" for m in missing]
        sys.stdout.write("\n".join(lines) + "\n")
        return

    table = Table(title=f"{result.v1_filename} → {result.v2_filename}  (v2 value, change)")
    for i, h in enumerate(head):
        table.add_column(h, justify="left" if i == 0 else "right")
    for row in result.rows:
        table.add_row(Text(row.group), *cells(row))
    table.add_section()
    table.add_row(Text("Total", "bold"), *cells(result.total))
    console.print(table)
    for m in missing:
        console.print(Text(m, "dim"))


@app.command()
def textconv(
    path: ExistingFile,
    strict: StrictOption = False,
    config: ConfigOption = None,
) -> None:
    """Print one model as stable text (Git textconv protocol)."""
    cfg = _settings(config, strict)
    with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
        try:
            model = resolve_lfs(path, Path(tmp))
            sys.stdout.write(snapshot(str(model), path.name, cfg))
        except Exception as exc:
            # A failure here would abort the whole `git log -p`; print a line instead.
            sys.stdout.write(f"# bimdelta: could not read {path.name}: {exc}\n")


@app.command("git-diff", hidden=True)
def git_diff(
    args: Annotated[list[str], typer.Argument(help="Arguments passed by Git.")],
    strict: StrictOption = False,
    config: ConfigOption = None,
) -> None:
    """External diff driver: path old-file old-hex old-mode new-file new-hex new-mode."""
    if len(args) < 7:
        _fail("git-diff expects the 7 arguments of GIT_EXTERNAL_DIFF")
    name, old_file, _old_hex, old_mode, new_file, _new_hex, new_mode = args[:7]
    cfg = _settings(config, strict)

    sys.stdout.write(f"diff --bimdelta a/{name} b/{name}\n")
    with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
        try:
            old = None if old_mode == "." else resolve_lfs(Path(old_file), Path(tmp))
            new = None if new_mode == "." else resolve_lfs(Path(new_file), Path(tmp))
            if old is None or new is None:
                present = old or new
                with IFC_LOCK:
                    count = len(parse_ifc(str(present), name).elements)
                state = "new file" if old is None else "deleted file"
                sys.stdout.write(f"### BIMDelta: {md_escape(name)} ({state}, {count} elements)\n")
                return
            result = run_diff(str(old), name, str(new), name, cfg)
            sys.stdout.write(to_markdown(result, title=name))
        except Exception as exc:
            sys.stdout.write(f"bimdelta: could not compare {name}: {exc}\n")
        finally:
            sys.stdout.flush()


@app.command("install-git-driver")
def install_git_driver(
    global_: Annotated[
        bool, typer.Option("--global", help="Configure for all repositories of this user.")
    ] = False,
    command: Annotated[
        str | None,
        typer.Option(help="How Git should run bimdelta. Default: detected from this install."),
    ] = None,
    uninstall: Annotated[
        bool, typer.Option("--uninstall", help="Remove the driver configuration.")
    ] = False,
) -> None:
    """Make `git diff`, `git log -p` and `git show` understand .ifc files."""
    try:
        if uninstall:
            gitdriver.uninstall(global_)
            say.print("Removed the [bold]diff.ifc[/] driver configuration.")
            return
        report = gitdriver.install(global_, command)
    except GitError as exc:
        _fail(str(exc))

    say.print(f"Configured the [bold]diff.ifc[/] driver ({report.scope}): {escape(report.command)}")
    if report.attributes_changed:
        say.print(f"Added '*.ifc diff=ifc' to {escape(str(report.attributes_file))}")
    else:
        say.print(f"{escape(str(report.attributes_file))} already maps *.ifc to the driver")
    if not global_:
        say.print(
            Text(
                "Commit .gitattributes so others get the mapping; each clone still needs "
                "`bimdelta install-git-driver` once.",
                "dim",
            )
        )


@app.command()
def blame(
    global_id: Annotated[str, typer.Argument(metavar="GLOBALID", help="Element GlobalId.")],
    path: Annotated[
        str | None,
        typer.Argument(help="IFC file in the repository. Optional if only one is tracked."),
    ] = None,
    repo: Annotated[Path, typer.Option(help="Repository directory.", file_okay=False)] = Path("."),
    rev: Annotated[str, typer.Option(help="Revision to start from.")] = "HEAD",
    max_commits: Annotated[
        int | None, typer.Option("--max-commits", min=1, help="Only look at the N latest commits.")
    ] = None,
    format: Annotated[Format, typer.Option("--format", "-f")] = Format.table,
    strict: StrictOption = False,
    config: ConfigOption = None,
) -> None:
    """Show the commits that added, changed or removed an element."""
    cfg = _settings(config if config is not None else find_config(repo), strict)
    try:
        result = run_blame(global_id, path, cfg, repo=repo, rev=rev, max_commits=max_commits)
    except (BlameError, GitError) as exc:
        _fail(str(exc))

    if format == Format.json:
        sys.stdout.write(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n")
        return

    md = format == Format.markdown
    if md:
        sys.stdout.write(f"### History of `{result.global_id}` in {md_escape(result.path)}\n\n")
    for ev in result.events:
        what = f"{ev.ifc_class or ''} {ev.name or ''}".strip()
        line = f'{ev.change} @ {ev.sha[:10]} ({ev.author}, {ev.date[:10]}): "{ev.subject}"'
        if md:
            sys.stdout.write(f"- {md_escape(line)}\n")
            for d in ev.details:
                sys.stdout.write(f"  - {md_escape(d)}\n")
            continue
        style = {"added": "green", "removed": "red", "modified": "yellow"}.get(ev.change, "cyan")
        say.print(
            Text.assemble(
                (f"{ev.change:<12}", style),
                (ev.sha[:10], "bold"),
                "  ",
                f"{ev.date[:10]}  {ev.author}  ",
                (f'"{ev.subject}"', "italic"),
                (f"  {what}" if what else "", "dim"),
            )
        )
        for d in ev.details:
            say.print(Text(f"{'':12}{d}", "dim"))
    tail = []
    if result.present_before:
        tail.append(f"already present before the {result.commits_scanned} commit(s) scanned")
    elif result.truncated:
        tail.append(f"history limited to {result.commits_scanned} commits")
    if not result.events and not tail:
        tail.append("no changes found")
    for t in tail:
        if md:
            sys.stdout.write(f"\n_{md_escape(t)}_\n")
        else:
            say.print(Text(t, "dim"))


@app.command()
def review(
    base: Annotated[str, typer.Argument(help="Base revision, e.g. the pull request target.")],
    head: Annotated[str, typer.Argument(help="Head revision.")] = "HEAD",
    repo: Annotated[Path, typer.Option(help="Repository directory.", file_okay=False)] = Path("."),
    format: Annotated[Format, typer.Option("--format", "-f")] = Format.markdown,
    viewer_url: Annotated[
        str | None,
        typer.Option(help="Add 'View 3D diff' links to this viewer (needs --github-repo)."),
    ] = None,
    github_repo: Annotated[
        str | None, typer.Option(help="owner/name of the public GitHub repository.")
    ] = None,
    head_repo: Annotated[
        str | None, typer.Option(help="owner/name holding the head commit, if a fork.")
    ] = None,
    limit: Annotated[int, typer.Option(help="Most elements listed per change type.")] = 50,
    max_chars: Annotated[
        int | None, typer.Option(help="Shorten the Markdown to fit this many characters.")
    ] = None,
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Write to this file.", dir_okay=False)
    ] = None,
    exit_code: Annotated[
        bool, typer.Option("--exit-code", help="Exit with 1 if any model changed.")
    ] = False,
    strict: StrictOption = False,
    config: ConfigOption = None,
) -> None:
    """Review every IFC file changed between two revisions."""
    if viewer_url and not github_repo:
        _fail("--viewer-url needs --github-repo")
    cfg = _settings(config if config is not None else find_config(repo), strict)
    try:
        rv = run_review(repo_root(repo), base, head, cfg)
    except GitError as exc:
        _fail(str(exc))

    if format == Format.json:
        payload = {
            "base": rv.base,
            "head": rv.head,
            "files": [
                {
                    "path": f.path,
                    "status": f.status,
                    "old_path": f.old_path,
                    "element_count": f.element_count,
                    "error": f.error,
                    "result": f.result.model_dump(mode="json") if f.result else None,
                }
                for f in rv.files
            ],
        }
        text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    elif format == Format.markdown:
        links = ViewerLinks(viewer_url, github_repo, head_repo) if viewer_url else None
        text = review_markdown(rv, links, limit=limit, max_chars=max_chars)
    else:
        _fail("review supports --format markdown or json")

    if output is not None:
        output.write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)

    if exit_code and rv.changed:
        raise typer.Exit(EXIT_CHANGES)
