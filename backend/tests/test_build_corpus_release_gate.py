from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_corpus import (
    REQUIRED_PTBXL_FILES,
    REQUIRED_PTBXL_PLUS_FILES,
    _missing_required_inputs,
    _release_completion_blockers,
    main,
)


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def test_required_inputs_include_fiducials_for_a_release_build(tmp_path: Path) -> None:
    ptbxl_root = tmp_path / "ptbxl"
    plus_root = tmp_path / "ptbxl-plus"

    for relative_path in REQUIRED_PTBXL_FILES:
        _touch(ptbxl_root / relative_path)
    for relative_path in REQUIRED_PTBXL_PLUS_FILES:
        _touch(plus_root / relative_path)

    missing = _missing_required_inputs(ptbxl_root, plus_root, require_fiducials=True)
    assert missing == [plus_root / "fiducial_points" / "ecgdeli"]

    (plus_root / "fiducial_points" / "ecgdeli").mkdir(parents=True)
    assert _missing_required_inputs(ptbxl_root, plus_root, require_fiducials=True) == []


def test_release_completion_blockers_reject_partial_or_degraded_builds() -> None:
    complete = {
        "limit": 0,
        "scan_rows": 0,
        "errors": 0,
        "skipped": 0,
        "fiducials_enabled": True,
        "expected_ptbxl_rows": 22_497,
        "stored_ptbxl_rows": 22_497,
    }
    assert _release_completion_blockers(**complete) == []

    degraded_values = {
        "limit": 300,
        "scan_rows": 300,
        "errors": 1,
        "skipped": 1,
        "fiducials_enabled": False,
        "stored_ptbxl_rows": 22_496,
    }
    for key, value in degraded_values.items():
        candidate = {**complete, key: value}
        assert _release_completion_blockers(**candidate), key


def test_missing_inputs_remove_a_stale_complete_manifest(
    tmp_path: Path, monkeypatch
) -> None:
    output_root = tmp_path / "corpus"
    output_root.mkdir()
    manifest = output_root / "manifest.json"
    manifest.write_text('{"complete": true}', encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_corpus.py",
            "--ptbxl-root",
            str(tmp_path / "missing-ptbxl"),
            "--plus-root",
            str(tmp_path / "missing-plus"),
            "--out",
            str(output_root),
        ],
    )

    assert main() == 2
    assert not manifest.exists()
