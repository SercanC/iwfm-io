"""Drop ``xfail(strict=True)`` markers from regression tests that now pass.

Usage: ``python tests/_ci/unxfail.py tests/regression/test_x.py [...]``

Runs each module with ``--runxfail`` into a JUnit report, then removes
the ``@pytest.mark.xfail(...)`` decorator line directly above every test
function whose cases ALL passed (a parametrised test keeps its marker
until every parameter passes). Re-run the module afterwards without
``--runxfail`` to confirm only passes/xfails/skips remain.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def passed_tests(module: Path) -> set[str]:
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "r.xml"
        subprocess.run([sys.executable, "-m", "pytest", str(module), "-q",
                        "-p", "no:cacheprovider", "--runxfail",
                        f"--junitxml={report}"],
                       capture_output=True)
        if not report.exists():
            return set()
        root = ET.parse(report).getroot()
    passed, failed = set(), set()
    for tc in root.iter("testcase"):
        base = tc.get("name").split("[")[0]
        if tc.find("failure") is not None or tc.find("error") is not None:
            failed.add(base)
        elif tc.find("skipped") is None:
            passed.add(base)
    return passed - failed


def unmark(module: Path, names: set[str]) -> int:
    lines = module.read_text(encoding="utf-8").splitlines(keepends=True)
    out, removed = [], 0
    for i, line in enumerate(lines):
        if "pytest.mark.xfail(" in line:
            # the def may sit below further decorators (parametrize ...)
            j = i + 1
            while j < len(lines) and lines[j].lstrip().startswith("@"):
                j += 1
            m = re.match(r"^\s*def (test_\w+)\(", lines[j]) if j < len(lines) else None
            if m and m.group(1) in names:
                removed += 1
                continue
        out.append(line)
    if removed:
        module.write_text("".join(out), encoding="utf-8")
    return removed


def main(argv):
    for arg in argv:
        module = Path(arg)
        n = unmark(module, passed_tests(module))
        print(f"{module}: {n} marker(s) removed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
