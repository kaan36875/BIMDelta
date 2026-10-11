from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Runs in a fresh interpreter: the failure happens when two threads make the process's *first*
# use of an IFC schema at the same time, which a warmed-up test process never does.
_SCRIPT = """
import sys, threading
from bimdelta_core import Settings, run_diff

v1, v2 = sys.argv[1], sys.argv[2]
start = threading.Barrier(2)
results, errors = [], []

def diff():
    start.wait()
    try:
        s = run_diff(v1, "v1", v2, "v2", Settings()).summary
        results.append((s.added, s.removed, s.modified, s.unchanged))
    except BaseException as exc:
        errors.append(repr(exc))

threads = [threading.Thread(target=diff) for _ in range(2)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print(results, errors)
sys.exit(0 if not errors and set(results) == {(1, 1, 1, 4)} else 1)
"""


def test_concurrent_first_use_in_fresh_process(basic_diff_files: tuple[Path, Path]):
    """Two diffs requested at once right after start-up, e.g. on a server cold start.

    Unserialized, this crashes the process or leaves IfcOpenShell unable to parse any file.
    The race is intermittent, so it is repeated.
    """
    v1, v2 = (str(p) for p in basic_diff_files)
    for attempt in range(6):
        proc = subprocess.run(
            [sys.executable, "-c", _SCRIPT, v1, v2], capture_output=True, text=True, timeout=120
        )
        assert proc.returncode == 0, (
            f"attempt {attempt}: exit {proc.returncode}\n{proc.stdout}\n{proc.stderr[-2000:]}"
        )
