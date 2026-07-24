from adm_probe_matcher_april2026 import main as run_matcher
def main(mongo_db, delete_bad_adms=True):
    run_matcher(mongo_db, delete_bad_adms)