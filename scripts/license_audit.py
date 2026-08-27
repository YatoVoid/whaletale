"""Fail the build if any installed distribution is AGPL/GPL licensed.

Spec Section 3: this is a commercial closed-source product. AGPL-3.0 in
particular would force releasing our source to network users. Cheaper to fail a
build than to discover the problem after a customer signs.

Run from a directory whose environment has the dependencies installed, e.g.
`cd edge && uv run python ../scripts/license_audit.py`.
"""

from __future__ import annotations

import re
import sys
from importlib import metadata

# Substrings matched case-insensitively against the License field and the
# `License ::` trove classifiers. "lgpl" is deliberately allowed (dynamic link).
BANNED = [
    r"\bagpl\b",
    r"affero",
    r"\bgpl-?[23]\b",
    r"gnu general public license",
]
BANNED_RE = re.compile("|".join(BANNED), re.IGNORECASE)

# Distributions we've reviewed and cleared despite a noisy metadata string
# (e.g. dual-licensed, or classifier lists that mention GPL for an optional
# component we don't use). Keep this list short and cite the reason.
ALLOWLIST: dict[str, str] = {}


def license_text(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    parts = [meta.get("License", "") or ""]
    parts += [c for c in meta.get_all("Classifier", []) if c.startswith("License ::")]
    return " ".join(parts)


def main() -> int:
    violations: list[tuple[str, str, str]] = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        if name in ALLOWLIST:
            continue
        text = license_text(dist)
        # LGPL contains "gpl" but is fine; strip it before matching.
        stripped = re.sub(r"lgpl", "", text, flags=re.IGNORECASE)
        if BANNED_RE.search(stripped):
            violations.append((name, dist.version or "?", text.strip()))

    if violations:
        print("License audit FAILED. Copyleft dependencies found:\n")
        for name, version, text in sorted(violations):
            print(f"  {name} {version}: {text}")
        print("\nSee docs/licenses.md. Remove the dependency or, if genuinely")
        print("misclassified, add it to ALLOWLIST with a reason.")
        return 1

    print(f"License audit OK ({len(list(metadata.distributions()))} distributions checked).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
