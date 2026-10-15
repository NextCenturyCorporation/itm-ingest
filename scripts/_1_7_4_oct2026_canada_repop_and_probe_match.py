"""Repopulate eval 18 text sessions, then process the October Canada sim runs."""

import os
from pathlib import Path
import subprocess
import sys


def main(mongo_db):
    repo_root = Path(__file__).resolve().parent.parent
    repop_script = repo_root / "text_repop.py"
    matcher_script = repo_root / "oct2026_probe_matcher.py"
    input_dir = repo_root / "ph2_sim_files" / "oct2026_canada"
    output_dir = repo_root / "output_oct2026"

    for script in (repop_script, matcher_script):
        if not script.is_file():
            raise FileNotFoundError(f"Required script not found: {script}")
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Canada sim input directory not found: {input_dir}")

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    commands = [
        (
            "Step 1/2: Repopulating text sessions for eval 18...",
            [sys.executable, str(repop_script), "--eval-number", "18"],
        ),
        (
            "Step 2/2: Running the October Canada probe matcher...",
            [
                sys.executable, str(matcher_script),
                "--eval-number", "18",
                "-i", str(input_dir),
                "-o", str(output_dir),
                "-k", "-m",
            ],
        ),
    ]
    for label, command in commands:
        print(label, flush=True)
        subprocess.run(command, cwd=str(repo_root), env=environment, check=True)

    print("Eval 18 text repopulation and October Canada probe matching completed.", flush=True)
