"""
Run the June 2026 Open World probe matcher.

This script is intended to be run by the deployment script or with:

    py redo.py 150

It runs the June 2026 probe matcher with KDMA calculation enabled (-k)
and Mongo upload enabled (-m).
"""

import os
import subprocess
import sys


EVAL_INPUT_DIR = os.path.join("ph2_sim_files", "june2026")
EVAL_OUTPUT_DIR = "output_june2026"
PROBE_MATCHER_SCRIPT = "june2026_probe_matcher.py"


def main(mongo_db):
    """Run the June 2026 probe matcher.

    The deployment framework passes mongo_db into every script's main function.
    This script does not need to use that object directly because the probe
    matcher handles Mongo upload through its own -m flag and environment config.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    probe_matcher_path = os.path.join(repo_root, PROBE_MATCHER_SCRIPT)
    input_path = os.path.join(repo_root, EVAL_INPUT_DIR)
    output_path = os.path.join(repo_root, EVAL_OUTPUT_DIR)

    if not os.path.exists(probe_matcher_path):
        raise FileNotFoundError(f"Could not find probe matcher script: {probe_matcher_path}")

    if not os.path.isdir(input_path):
        raise FileNotFoundError(f"Could not find June 2026 sim input directory: {input_path}")

    os.makedirs(output_path, exist_ok=True)

    command = [
        sys.executable,
        probe_matcher_path,
        "-i",
        input_path,
        "-o",
        output_path,
        "-k",
        "-m",
    ]

    print("Running June 2026 probe matcher...")
    print("Command:", " ".join(f'"{part}"' if " " in part else part for part in command))

    subprocess.run(command, cwd=repo_root, check=True)

    print("June 2026 probe matcher completed successfully.")
