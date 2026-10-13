"""Set one version on every Python package in the repository.

bimdelta and bimdelta-core are released together; the CLI pins the exact core version.

    python scripts/set_version.py 0.4.0
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECTS = [
    ROOT / "packages" / "bimdelta-core" / "pyproject.toml",
    ROOT / "apps" / "cli" / "pyproject.toml",
    ROOT / "apps" / "server" / "pyproject.toml",
]
VERSION = re.compile(r"^\d+\.\d+\.\d+((a|b|rc)\d+)?(\.dev\d+)?$")


def main(version: str) -> None:
    if not VERSION.match(version):
        sys.exit(f"not a release version: {version}")
    for path in PYPROJECTS:
        text = path.read_text(encoding="utf-8")
        text = re.sub(r'(?m)^version = ".*"$', f'version = "{version}"', text, count=1)
        text = re.sub(r'"bimdelta-core==[^"]*"', f'"bimdelta-core=={version}"', text)
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"{path.relative_to(ROOT)}: {version}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
