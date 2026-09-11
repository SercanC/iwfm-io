"""CI guard: fail when fewer than N tests passed.

The data-dependent tests skip silently when the sample model is missing,
so a green run can hide a mass skip. ``pytest --junitxml=report.xml`` then
``python tests/_ci/min_passed.py report.xml 700`` turns that into a failure.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: min_passed.py REPORT.xml MIN_PASSED", file=sys.stderr)
        return 2
    report, threshold = argv[0], int(argv[1])
    root = ET.parse(report).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = failures = errors = skipped = 0
    for s in suites:
        total += int(s.get("tests", 0))
        failures += int(s.get("failures", 0))
        errors += int(s.get("errors", 0))
        skipped += int(s.get("skipped", 0))
    passed = total - failures - errors - skipped
    print(f"tests={total} passed={passed} failed={failures} errors={errors} skipped={skipped}")
    if passed < threshold:
        print(f"only {passed} tests passed; expected at least {threshold} — "
              "is the sample model missing?", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
