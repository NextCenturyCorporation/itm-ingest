"""Process the October UK sim runs for eval 19."""

import os
from pathlib import Path
import subprocess
import sys


def main(mongo_db):
    repo_root = Path(__file__).resolve().parent.parent
    matcher_script = repo_root / "oct2026_probe_matcher.py"
    input_dir = repo_root / "ph2_sim_files" / "oct2026_uk"
    output_dir = repo_root / "output_oct2026"

    if not matcher_script.is_file():
        raise FileNotFoundError(f"Required script not found: {matcher_script}")
    if not input_dir.is_dir():
        raise FileNotFoundError(f"UK sim input directory not found: {input_dir}")

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"
    command = [
        sys.executable, str(matcher_script),
        "--eval-number", "19",
        "--eval-name", "October 2026 UK Evaluation",
        "-i", str(input_dir),
        "-o", str(output_dir),
        "-k", "-m",
    ]
    print("Running the October UK probe matcher...", flush=True)
    subprocess.run(command, cwd=str(repo_root), env=environment, check=True)

    print("October UK probe matching completed.", flush=True)
