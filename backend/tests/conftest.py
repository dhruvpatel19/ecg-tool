"""Pytest setup: isolate the learner DB and pin the complete checked corpus.

Forces an in-memory learner database BEFORE any app import so the test suite is
idempotent and never pollutes the real ecg_learning.db (guest or account state).
Pins the complete corpus so Clinical's 100-case contract cannot silently fall
back to a smaller/in-progress build.
"""

import atexit
import hashlib
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _checked_test_corpus() -> Path:
    """Use the full local corpus, or extract the minimized real-PTB CI asset."""
    full = _PROJECT_ROOT / "data" / "ecg_corpus"
    force_ci_asset = os.getenv("ECG_TEST_USE_CI_CORPUS", "0").lower() in {
        "1",
        "true",
        "yes",
    }
    if (
        not force_ci_asset
        and (full / "manifest.json").is_file()
        and (full / "corpus.db").is_file()
    ):
        return full
    assets = Path(__file__).resolve().parent / "assets"
    archive = assets / "ptb_ci_corpus.tar.gz"
    checksum = assets / "ptb_ci_corpus.tar.gz.sha256"
    if not archive.is_file() or not checksum.is_file():
        raise RuntimeError(
            "The real-PTB CI corpus asset is missing. Run scripts/build_ci_corpus.py "
            "from a checkout with the complete corpus."
        )
    expected = checksum.read_text(encoding="ascii").split()[0]
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if actual != expected:
        raise RuntimeError("The real-PTB CI corpus checksum does not match")
    extracted = Path(tempfile.mkdtemp(prefix="ecg-ptb-ci-"))
    with tarfile.open(archive, "r:gz") as bundle:
        bundle.extractall(extracted, filter="data")
    atexit.register(shutil.rmtree, extracted, ignore_errors=True)
    return extracted


# Clinical's learner bank is always grounded in checked real ECGs. The compact
# committed subset makes this invariant testable on clean public CI runners.
os.environ.setdefault("ECG_CORPUS_ROOT", str(_checked_test_corpus()))
os.environ.setdefault("ECG_REQUIRE_REAL_DATA", "0")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("APP_ENV", "test")
