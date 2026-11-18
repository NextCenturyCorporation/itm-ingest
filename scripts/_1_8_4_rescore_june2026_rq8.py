import os
import subprocess
import sys
from pathlib import Path

from old_repop_scripts.june2026_text_repop import main as june_redo

def main(mongo_db):
    june_redo(mongo_db)

    # Re-run the June 2026 probe matcher.
    repo_root = Path(__file__).resolve().parent.parent
    command = [
        sys.executable,
        str(repo_root / "old_probe_matchers" / "june2026_probe_matcher.py"),
        "-i", "ph2_sim_files/june2026/",
        "-o", "output_june2026/",
        "-k",
        "-m",
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    subprocess.run(command, cwd=str(repo_root), env=env, check=True)