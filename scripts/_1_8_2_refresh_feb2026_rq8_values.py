"""Refresh February 2026 RQ8 values (eval 15), with resumable original-value preservation.

Run: py redo.py 182
Preview: py scripts/_1_8_2_refresh_feb2026_rq8_values.py --dry-run
Requires MONGO_URL, ADEPT_URL, and the recorded scenarios on ADEPT.
"""

from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rq8_refresh import FEBRUARY, cli as refresh_cli, main as refresh_main


def main(mongo_db, dry_run=False, pids=None, verify_only=False, scoring_workers=2):
    return refresh_main(mongo_db, dry_run=dry_run, pids=pids, verify_only=verify_only,
                        scoring_workers=scoring_workers, config=FEBRUARY)


def cli(argv=None):
    return refresh_cli(argv, config=FEBRUARY)


if __name__ == "__main__":
    raise SystemExit(cli())
