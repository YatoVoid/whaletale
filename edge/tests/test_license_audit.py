from __future__ import annotations

import importlib.util
from email.message import Message
from pathlib import Path
from typing import Any

_path = Path(__file__).resolve().parents[2] / "scripts" / "license_audit.py"
_spec = importlib.util.spec_from_file_location("license_audit", _path)
assert _spec and _spec.loader
license_audit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(license_audit)


def fake_dist(*, classifiers: tuple[str, ...] = (), license_field: str = "") -> Any:
    msg = Message()
    for c in classifiers:
        msg["Classifier"] = c
    if license_field:
        msg["License"] = license_field

    class _D:
        metadata = msg
        version = "1.0"

    return _D()


def test_permissive_is_clean() -> None:
    mit = fake_dist(classifiers=("License :: OSI Approved :: MIT License",))
    psf = fake_dist(classifiers=("License :: OSI Approved :: Python Software Foundation License",))
    assert license_audit.is_copyleft(mit) is None
    assert license_audit.is_copyleft(psf) is None


def test_lgpl_is_allowed() -> None:
    lgpl = fake_dist(
        classifiers=("License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",)
    )
    assert license_audit.is_copyleft(lgpl) is None


def test_agpl_classifier_is_flagged() -> None:
    agpl = fake_dist(
        classifiers=("License :: OSI Approved :: GNU Affero General Public License v3",)
    )
    assert license_audit.is_copyleft(agpl) is not None


def test_gpl_classifier_is_flagged() -> None:
    gpl = fake_dist(
        classifiers=("License :: OSI Approved :: GNU General Public License v3 (GPLv3)",)
    )
    assert license_audit.is_copyleft(gpl) is not None


def test_disjunctive_gpl_or_mpl_is_allowed() -> None:
    # pyphen ships GPLv2+ / LGPLv2+ / MPL-1.1 classifiers together; we take a
    # non-GPL arm.
    d = fake_dist(
        classifiers=(
            "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
            "License :: OSI Approved :: Mozilla Public License 1.1 (MPL 1.1)",
        )
    )
    assert license_audit.is_copyleft(d) is None


def test_gpl_alongside_bsd_is_allowed() -> None:
    d = fake_dist(
        classifiers=(
            "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
            "License :: OSI Approved :: BSD License",
        )
    )
    assert license_audit.is_copyleft(d) is None


def test_free_text_license_is_not_scanned() -> None:
    # numpy/scipy/matplotlib embed third-party license texts (some quoting GPL /
    # Affero) in the free-text field. Classifier is the authority.
    d = fake_dist(
        classifiers=("License :: OSI Approved :: BSD License",),
        license_field="... bundled component under the GNU Affero General Public License ...",
    )
    assert license_audit.is_copyleft(d) is None


def test_no_classifier_permissive_free_text_is_clean() -> None:
    assert license_audit.is_copyleft(fake_dist(license_field="MIT")) is None
