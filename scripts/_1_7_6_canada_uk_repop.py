"""Repopulate Canada and UK ADEPT sessions before October processing."""

import os
from pathlib import Path
import subprocess
import sys

from decouple import config


def main(mongo_db, dry_run=False):
    if mongo_db is None:
        raise RuntimeError("The deployment framework did not provide a Mongo database.")
    for key in ("MONGO_URL", "ADEPT_URL"):
        if not str(config(key, default="") or "").strip():
            raise RuntimeError(f"{key} is not configured.")

    repo_root = Path(__file__).resolve().parent.parent
    scripts = [repo_root / "text_repop.py", repo_root / "openworld_repop.py"]
    for script in scripts:
        if not script.is_file():
            raise FileNotFoundError(f"Required repopulation script not found: {script}")

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    for eval_number in (18, 19):
        for script in scripts:
            command = [sys.executable, str(script), "--eval-number", str(eval_number)]
            if dry_run:
                command.append("--dry-run")
            print(f"Running {script.name} for eval {eval_number} (dry_run={dry_run})...", flush=True)
            subprocess.run(command, cwd=str(repo_root), env=environment, check=True)

    print("Canada and UK repopulation " + ("dry run completed." if dry_run else "completed."), flush=True)
