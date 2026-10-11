"""Time and memory for diffing IFC files.

    python scripts/benchmark.py model.ifc                # diff a model against itself
    python scripts/benchmark.py rev-a.ifc rev-b.ifc

Diffing a model against itself is the worst case: every element is matched and unchanged,
so every geometry signature has to be computed. Peak memory needs `psutil`.
"""

from __future__ import annotations

import argparse
import gc
import os
import time
from pathlib import Path

from bimdelta_core import load_settings, run_diff
from bimdelta_core.parser import parse_ifc


def _peak_rss_mb() -> float | None:
    try:
        import psutil
    except ImportError:
        return None
    info = psutil.Process(os.getpid()).memory_info()
    peak = getattr(info, "peak_wset", None)  # Windows
    if peak is None:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024  # Linux: KiB
    return peak / (1024 * 1024)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("v1", type=Path)
    parser.add_argument("v2", type=Path, nargs="?")
    parser.add_argument("--config", type=Path)
    args = parser.parse_args()

    v2 = args.v2 or args.v1
    cfg = load_settings(args.config)

    start = time.perf_counter()
    model = parse_ifc(str(args.v1), args.v1.name, cfg.include_openings)
    parse_s = time.perf_counter() - start
    del model
    gc.collect()

    start = time.perf_counter()
    result = run_diff(str(args.v1), args.v1.name, str(v2), v2.name, cfg)
    diff_s = time.perf_counter() - start

    s = result.summary
    size_mb = args.v1.stat().st_size / (1024 * 1024)
    peak = _peak_rss_mb()
    print(
        "| Model | Size | Elements | Parse one file | Full diff | Peak memory "
        "| Added / Removed / Modified | Geometry unknown |"
    )
    print("|---|---|---|---|---|---|---|---|")
    print(
        f"| {args.v1.name}{'' if args.v2 is None else ' -> ' + v2.name} | {size_mb:.1f} MB "
        f"| {s.total_v1} | {parse_s:.1f} s | {diff_s:.1f} s "
        f"| {f'{peak:.0f} MB' if peak is not None else 'n/a'} "
        f"| {s.added} / {s.removed} / {s.modified} | {s.geometry_unknown} |"
    )


if __name__ == "__main__":
    main()
