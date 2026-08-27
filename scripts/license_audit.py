"""Fail the build if any installed distribution is AGPL/GPL licensed.

Spec Section 3: this is a commercial closed-source product. AGPL-3.0 in
particular would force releasing our source to network users. Cheaper to fail a
build than to discover the problem after a customer signs.

The copyleft determination is made from PyPI trove classifiers (the structured
`License ::` field) only. The free-text `License` field is not scanned: numpy,
scipy, and matplotlib all embed whole third-party license texts there (some of
which quote GPL/Affero notices for bundled components), so keyword matching on
it produces false positives on BSD-licensed core packages.

A short name denylist backstops the specific AGPL packages the spec calls out,
in case a future release of one ships without a classifier.

Run from a directory whose environment has the dependencies installed, e.g.
`cd edge && uv run python ../scripts/license_audit.py`.
"""

from __future__ import annotations

import sys
from importlib import metadata

# Spec Section 3: never allowed, regardless of metadata.
NAME_DENYLIST = {"ultralytics", "yolov5", "yolov8", "yolov11"}

# Reviewed and cleared. Keep short, cite why.
ALLOWLIST: dict[str, str] = {}


def classifiers(dist: metadata.Distribution) -> list[str]:
    return [c for c in dist.metadata.get_all("Classifier", []) if c.startswith("License ::")]


def copyleft_classifier(dist: metadata.Distribution) -> str | None:
    for c in classifiers(dist):
        low = c.lower()
        if "lesser" in low:  # LGPL is fine (dynamic link)
            continue
        if "gnu affero" in low or "gnu general public license" in low:
            return c
    return None


def is_copyleft(dist: metadata.Distribution) -> str | None:
    """Public for tests. Returns the offending classifier, or None."""
    return copyleft_classifier(dist)


def main() -> int:
    checked = 0
    violations: list[tuple[str, str, str]] = []
    for dist in metadata.distributions():
        checked += 1
        name = (dist.metadata.get("Name", "") or "unknown").lower()
        if name in ALLOWLIST:
            continue
        if name in NAME_DENYLIST:
            violations.append((name, dist.version or "?", "name denylist (spec Section 3)"))
            continue
        hit = copyleft_classifier(dist)
        if hit:
            violations.append((name, dist.version or "?", hit))

    if violations:
        print("License audit FAILED. Copyleft dependencies found:\n")
        for name, version, evidence in sorted(violations):
            print(f"  {name} {version}: {evidence}")
        print("\nSee docs/licenses.md. Remove the dependency or, if genuinely")
        print("misclassified, add it to ALLOWLIST with a reason.")
        return 1

    print(f"License audit OK ({checked} distributions checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
