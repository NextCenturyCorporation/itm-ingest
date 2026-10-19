"""Process the October Canada sim runs for eval 18."""

import os
from pathlib import Path
import subprocess
import sys


def main(mongo_db):
    repo_root = Path(__file__).resolve().parent.parent
    matcher_script = repo_root / "oct2026_probe_matcher.py"
    input_dir = repo_root / "ph2_sim_files" / "oct2026_canada"
    output_dir = repo_root / "output_oct2026"

    if not matcher_script.is_file():
        raise FileNotFoundError(f"Required script not found: {matcher_script}")
    if not input_dir.is_dir():
        raise FileNotFoundError(f"Canada sim input directory not found: {input_dir}")

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    command = [
        sys.executable, str(matcher_script),
        "--eval-number", "18",
        "-i", str(input_dir),
        "-o", str(output_dir),
        "-k", "-m",
    ]
    print("Running the October Canada probe matcher...", flush=True)
    subprocess.run(command, cwd=str(repo_root), env=environment, check=True)

    print("October Canada probe matching completed.", flush=True)
