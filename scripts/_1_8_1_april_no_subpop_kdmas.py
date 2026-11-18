import os
import subprocess
import sys
from pathlib import Path

from old_repop_scripts.ph2_repop_eval_16 import main as eval_16_repop


def main(mongo_db):
    eval_16_repop(mongo_db)

    # re runs probe matcher
    repo_root = Path(__file__).resolve().parent.parent
    command = [
        sys.executable,
        str(repo_root / "old_probe_matchers" / "april2026_probe_matcher.py"),
        "-i", "ph2_sim_files/april2026/",
        "-o", "output_april2026/",
        "-k",
        "-m",
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    subprocess.run(command, cwd=str(repo_root), env=env, check=True)
    
    mongo_db['humanSimulator'].delete_one({"pid": "202604155"})
    mongo_db['humanSimulator'].delete_many({"pid": "202604192"})
