"""Repopulate June 2026 ADEPT sessions and rerun the production probe matcher.

This migration is intentionally ordered:

1. Recreate the June 2026 text sessions on the ADEPT server configured by
   ``ADEPT_URL`` and write their session IDs/KDMAs to ``userScenarioResults``.
2. Run the June 2026 probe matcher against the refreshed text sessions and
   upsert its raw/analysis documents to Mongo.

The deployment framework imports this file from ``scripts/`` and calls
``main(mongo_db)``. The scripts being executed live in the repository root.
"""

import os
from pathlib import Path
import subprocess
import sys

try:
    from decouple import config
except ImportError:
    def config(key, default=None, **kwargs):
        return os.environ.get(key, default)


EVAL_NUMBER = 17
REPOP_SCRIPT = "june2026_text_repop.py"
PROBE_MATCHER_SCRIPT = "june2026_probe_matcher.py"
PROBE_INPUT_DIR = Path("ph2_sim_files") / "june2026"
PROBE_OUTPUT_DIR = Path("output_june2026")


def _require_configuration() -> None:
    """Fail before changing data if required service settings are missing."""
    mongo_url = str(config("MONGO_URL", default="") or "").strip()
    adept_url = str(config("ADEPT_URL", default="") or "").strip()

    if not mongo_url:
        raise RuntimeError("MONGO_URL is not configured.")
    if not adept_url:
        raise RuntimeError("ADEPT_URL is not configured.")

    print(f"Using ADEPT server: {adept_url}", flush=True)


def _require_repo_paths(repo_root: Path) -> None:
    """Verify the root-level scripts and June input data exist."""
    required_paths = [
        repo_root / REPOP_SCRIPT,
        repo_root / PROBE_MATCHER_SCRIPT,
        repo_root / PROBE_INPUT_DIR,
    ]
    missing = [str(path) for path in required_paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Required June 2026 migration path(s) not found: " + ", ".join(missing)
        )


def _run(command, repo_root: Path, label: str) -> None:
    """Run one required step and stop the migration if it fails."""
    print(f"\n{label}", flush=True)
    print("Command: " + " ".join(str(part) for part in command), flush=True)

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    subprocess.run(
        [str(part) for part in command],
        cwd=str(repo_root),
        env=environment,
        check=True,
    )


def main(mongo_db):
    """Run the June repopulation before regenerating probe-match documents."""
    # ``mongo_db`` is supplied by deployment_script.py. The child scripts use
    # the same production MONGO_URL from the environment/.env configuration.
    if mongo_db is None:
        raise RuntimeError("The deployment framework did not provide a Mongo database.")

    repo_root = Path(__file__).resolve().parent.parent
    _require_configuration()
    _require_repo_paths(repo_root)

    repop_command = [
        sys.executable,
        repo_root / REPOP_SCRIPT,
        "--eval-number",
        str(EVAL_NUMBER),
        "--recreate-sessions",
    ]
    _run(
        repop_command,
        repo_root,
        "Step 1/2: Recreating June 2026 text sessions on production ADEPT...",
    )

    matcher_command = [
        sys.executable,
        repo_root / PROBE_MATCHER_SCRIPT,
        "--input_dir",
        repo_root / PROBE_INPUT_DIR,
        "--output_dir",
        repo_root / PROBE_OUTPUT_DIR,
        "--send_to_mongo",
        "--calc_kdmas",
    ]
    _run(
        matcher_command,
        repo_root,
        "Step 2/2: Recomputing June 2026 probe matches and Mongo documents...",
    )

    print("\nJune 2026 repopulation and probe matching completed successfully.", flush=True)
