"""The ``bimdelta`` command."""

from __future__ import annotations

import dataclasses
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
from .conflict import find_conflicts
from .conflict import to_markdown as conflict_markdown
from .filters import FilterError, parse_filter
from .gitutil import GitError, model_input, repo_root, resolve_lfs
from .render import (
    QTY_COLUMNS,
    has_changes,
    md_escape,
    missing_quantities,
    print_table,
    quantity_cell,
    quantity_changed,
    quantity_columns,
    quantity_table,
    to_markdown,
)
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
    storey = "storey"


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
ModelArg = Annotated[str, typer.Argument(metavar="MODEL", help="An IFC file, or REV:PATH.")]


def _models(v1: str, v2: str, scratch: Path) -> list[tuple[Path, str]]:
    out = []
    for arg in (v1, v2):
        try:
            out.append(model_input(arg, scratch))
        except (GitError, OSError) as exc:
            _fail(str(exc))
    return out


@app.command()
def diff(
    v1: ModelArg,
    v2: ModelArg,
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
    """Compare two versions of an IFC model: files, or REV:PATH such as HEAD~1:model.ifc."""
    cfg = _settings(config, strict)
    keep = None
    if filter:
        try:
            keep = parse_filter(filter)
        except FilterError as exc:
            _fail(f"--filter: {exc}")

    with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
        (p1, n1), (p2, n2) = _models(v1, v2, Path(tmp))
        try:
            result = run_diff(str(p1), n1, str(p2), n2, cfg)
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
    v1: ModelArg,
    v2: ModelArg,
    by: Annotated[
        GroupBy, typer.Option("--by", help="Group by IFC class, material or storey.")
    ] = GroupBy.by_class,
    changed_only: Annotated[
        bool, typer.Option("--changed-only", help="Only groups whose quantities changed.")
    ] = False,
    format: Annotated[Format, typer.Option("--format", "-f")] = Format.table,
) -> None:
    """Quantity take-off of two versions and the change, from the exported quantity sets.

    Each version is a file or REV:PATH, e.g. HEAD~1:model.ifc.
    """
    with tempfile.TemporaryDirectory(prefix="bimdelta-") as tmp:
        (p1, n1), (p2, n2) = _models(v1, v2, Path(tmp))
        try:
            result = quantity_delta(str(p1), n1, str(p2), n2, by.value)
        except Exception as exc:
            _fail(f"could not read quantities: {exc}")

    if format == Format.json:
        sys.stdout.write(result.model_dump_json(indent=2) + "\n")
        return

    rows = [r for r in result.rows if quantity_changed(r)] if changed_only else result.rows
    label = by.value.capitalize()
    missing = missing_quantities(result, result.v1_filename, result.v2_filename)

    if format == Format.markdown:
        title = f"{md_escape(result.v1_filename)} → {md_escape(result.v2_filename)}"
        lines = [f"### Quantities: {title}", ""]
        lines += quantity_table(rows, result.total, label)
        names = md_escape(result.v1_filename), md_escape(result.v2_filename)
        lines += [f"\n> {m}" for m in missing_quantities(result, *names)]
        sys.stdout.write("\n".join(lines) + "\n")
        return

    cols = quantity_columns([*result.rows, result.total])
    heads = dict(QTY_COLUMNS)
    table = Table(title=f"{result.v1_filename} → {result.v2_filename}  (v2 value, change)")
    table.add_column(label)
    for c in cols:
        table.add_column(heads[c], justify="right")
    for row in rows:
        table.add_row(Text(row.group), *(quantity_cell(row, c) for c in cols))
    table.add_section()
    table.add_row(Text("Total", "bold"), *(quantity_cell(result.total, c) for c in cols))
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


@app.command()
def conflict(
    ours: Annotated[str, typer.Argument(help="One branch or revision.")],
    theirs: Annotated[str, typer.Argument(help="The other branch.")] = "HEAD",
    paths: Annotated[
        list[str] | None, typer.Argument(help="IFC files to check. Default: all.")
    ] = None,
    repo: Annotated[Path, typer.Option(help="Repository directory.", file_okay=False)] = Path("."),
    format: Annotated[Format, typer.Option("--format", "-f")] = Format.table,
    exit_code: Annotated[
        bool, typer.Option("--exit-code", help="Exit with 1 if there are conflicts.")
    ] = False,
    strict: StrictOption = False,
    config: ConfigOption = None,
) -> None:
    """Elements changed on both branches since they diverged. Reports only; merges nothing."""
    cfg = _settings(config if config is not None else find_config(repo), strict)
    try:
        report = find_conflicts(repo_root(repo), ours, theirs, cfg, paths)
    except GitError as exc:
        _fail(str(exc))

    if format == Format.json:
        payload = dataclasses.asdict(report) | {
            "conflicts": report.conflicts,
            "warnings": report.warnings,
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    elif format == Format.markdown:
        sys.stdout.write(conflict_markdown(report))
    else:
        say.print(
            f"Merge base {report.base[:10]}: [bold]{report.conflicts}[/] conflict(s), "
            f"{report.warnings} warning(s)."
        )
        for fc in report.files:
            say.print(Text(f"\n{fc.path}", "bold"))
            if fc.error or fc.note:
                style = "red" if fc.note else "yellow"
                say.print(Text(f"  {fc.note or 'could not compare: ' + str(fc.error)}", style))
                continue
            table = Table(show_lines=True)
            for col in ("", "Element", "Fields", ours, theirs):
                table.add_column(col)
            for e in sorted(fc.elements, key=lambda e: (e.level != "conflict", e.ifc_class)):
                table.add_row(
                    Text(e.level, "red bold" if e.level == "conflict" else "yellow"),
                    Text(f"{e.ifc_class} {e.name or '(unnamed)'}\n{e.global_id}"),
                    Text(", ".join(e.fields) or "different fields"),
                    Text("\n".join(e.ours)),
                    Text("\n".join(e.theirs)),
                )
            console.print(table)

    if exit_code and report.conflicts:
        raise typer.Exit(EXIT_CHANGES)


@app.command()
def serve(
    repo: Annotated[Path, typer.Option(help="Repository directory.", file_okay=False)] = Path("."),
    port: Annotated[int, typer.Option(help="Port on 127.0.0.1; 0 picks a free one.")] = 0,
    open_browser: Annotated[
        bool, typer.Option("--open/--no-open", help="Open the viewer in a browser.")
    ] = True,
    web_dir: Annotated[
        Path | None,
        typer.Option(help="Built web app to serve instead of the bundled one.", file_okay=False),
    ] = None,
    strict: StrictOption = False,
    config: ConfigOption = None,
) -> None:
    """Open the history of a local repository in the 3D viewer."""
    import webbrowser

    from .serve import bundled_web_dir, create_server

    cfg = _settings(config if config is not None else find_config(repo), strict)
    web = web_dir or bundled_web_dir()
    try:
        server = create_server(repo, cfg, port, web)
    except GitError as exc:
        _fail(str(exc))
    except OSError as exc:
        _fail(f"cannot listen on port {port}: {exc}")

    url = f"http://127.0.0.1:{server.server_address[1]}/"
    # The first line is read by the Revit add-in to find the port.
    sys.stdout.write(f"BIMDELTA_URL={url}\n")
    sys.stdout.flush()
    if web is None:
        err.print("warning: no bundled viewer in this installation; only the API is served")
    say.print(f"Serving {repo_root(repo)} at {url}  (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
