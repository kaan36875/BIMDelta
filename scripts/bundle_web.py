"""Build the web app and copy it into the CLI package, for `bimdelta serve`.

    python scripts/bundle_web.py            # npm ci + npm run build, then copy
    python scripts/bundle_web.py --no-build # copy an existing apps/web/dist

Run before building the bimdelta wheel; CI and the release workflow do.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "apps" / "web"
TARGET = ROOT / "apps" / "cli" / "src" / "bimdelta_cli" / "web"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-build", action="store_true")
    args = parser.parse_args()

    if not args.no_build:
        npm = shutil.which("npm")
        if npm is None:
            sys.exit("npm not found")
        subprocess.run([npm, "ci"], cwd=WEB, check=True)
        # The local viewer talks to the server it was loaded from.
        subprocess.run([npm, "run", "build"], cwd=WEB, check=True, env=_env(VITE_API_URL=""))

    dist = WEB / "dist"
    if not (dist / "index.html").is_file():
        sys.exit(f"{dist} has no index.html; build the web app first")
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(dist, TARGET)
    size = sum(f.stat().st_size for f in TARGET.rglob("*") if f.is_file())
    print(f"Copied {dist.relative_to(ROOT)} to {TARGET.relative_to(ROOT)} ({size / 1e6:.1f} MB)")


def _env(**extra: str) -> dict[str, str]:
    import os

    return {**os.environ, **extra}


if __name__ == "__main__":
    main()
