import requests, os, sys, csv, random
from pymongo import MongoClient
from decouple import config
import math

EVAL_NUM = 11
ADEPT_URL = config("ADEPT_URL")
HIT_TA1_SERVER = True  # Useful if you can't reach the TA1 server
PYTHON_CMD = "python3"
FOUR_D_COLLECTION = "multiKdmaData4D"


def get_kdma_value(kdmas, kdma_name):
    """
    Returns the kdma value for the requested kdma name (aka attribute)
    """
    for kdma_obj in kdmas:
        if kdma_obj["kdma"] == kdma_name:
            return kdma_obj["value"]


def main(mongo_db):
    # Create a new DB to store all the data.
    multi_kdmas_4d = mongo_db[FOUR_D_COLLECTION]
    multi_kdmas_4d.drop()

    adm_collection = mongo_db["admTargetRuns"]
    actual_adm_runs = adm_collection.find(
        {"evalNumber": EVAL_NUM, "synthetic": {"$exists": False}}
    )
    synthetic_aligned_runs = adm_collection.find(
        {"evalNumber": EVAL_NUM, "synthetic": True, "evaluation.adm_profile": "aligned"}
    )

    # Maps a synthetic alignment target id (e.g., "target1") to a list of kdma values that define the alignment target.
    target_map: dict = {}

    # Because the synthetic alignment target ID wasn't saved from the ADM runs, let's make that mapping now.
    # TBD:  Right now, target 13 and 39 are the same.  Is this a problem?  Are there others?
    for actual_adm_run in actual_adm_runs:
        for history_entry in actual_adm_run["history"]:
            if history_entry["command"] == "Alignment Target":
                synthetic_id = history_entry["response"]["id"]
                if synthetic_id not in target_map.keys():
                    af = history_entry["response"]["kdma_values"][0]["value"]
                    mf = history_entry["response"]["kdma_values"][1]["value"]
                    ps = history_entry["response"]["kdma_values"][2]["value"]
                    ss = history_entry["response"]["kdma_values"][3]["value"]
                    kdmas: dict = {
                        "affiliation": af,
                        "merit": mf,
                        "personal_safety": ps,
                        "search": ss,
                    }
                    # print(f"Adding mapping of {synthetic_id} to {kdmas}")
                    target_map[synthetic_id] = kdmas

    # An "adm group" consists of aligned adms with the same name and synthetic alignment targets--
    # one for each ADEPT kdma-- and a TA1 session ID that can be used for comparison to that target.
    adm_groups = {}
    group_count = 0

    def find_target(target_kdmas: list) -> str:
        for id in target_map:
            if (
                target_map[id]["affiliation"]
                == get_kdma_value(target_kdmas, "affiliation")
                and target_map[id]["merit"] == get_kdma_value(target_kdmas, "merit")
                and target_map[id]["personal_safety"]
                == get_kdma_value(target_kdmas, "personal_safety")
                and target_map[id]["search"] == get_kdma_value(target_kdmas, "search")
            ):
                return id
        print(f"Warning: couldn't find target for {kdmas}")
        return None

    # generate the adm groups, organized by adm_name, then target_id
    adms_added = 0
    for synthetic_aligned_run in synthetic_aligned_runs:
        adm_name = synthetic_aligned_run["adm_name"]
        target_id = find_target(synthetic_aligned_run["evaluation"]["human_kdmas"])
        human_session_id = adm_name
        if adm_name not in adm_groups:
            adm_groups[adm_name] = {}
        if target_id not in adm_groups[adm_name]:
            adm_groups[adm_name][target_id] = []
            group_count += 1
        adm_groups[adm_name][target_id].append(synthetic_aligned_run)
        adms_added += 1

    # Run the dev script to get human kdmas; store in list for easy indexing.
    os.system(f"{PYTHON_CMD} dev_scripts/get_p2_4d_text_kdmas.py")
    file = open("text_kdmas.csv", "r", encoding="utf-8")
    reader = csv.reader(file)
    text_kdma_header = next(reader)
    text_kdmas = []
    for line in reader:
        if len(line) > 2:  # Skip blank lines
            text_kdmas.append(line)
    # clean up csv file
    file.close()

    completed_groups = 0
    for adm_name in adm_groups:
        for target_id in adm_groups[adm_name]:
            sys.stdout.write(
                f"\rAnalyzing ADM group {completed_groups+1} of {group_count}\n"
            )
            first_adm = adm_groups[adm_name][target_id][
                0
            ]  # human kdmas will be the same in all ADMs
            target_af = get_kdma_value(
                first_adm["evaluation"]["human_kdmas"], "affiliation"
            )
            target_mf = get_kdma_value(first_adm["evaluation"]["human_kdmas"], "merit")
            target_ps = get_kdma_value(
                first_adm["evaluation"]["human_kdmas"], "personal_safety"
            )
            target_ss = get_kdma_value(first_adm["evaluation"]["human_kdmas"], "search")
            # get af/mf/ps/ss kdma target values to find matching human(s)
            matching_pids = []
            matching_pids = get_humans_with_kdmas(
                text_kdmas, text_kdma_header, target_af, target_mf, target_ps, target_ss
            )

            # run the comparison for all unique entries
            for pid in matching_pids:
                new_doc = {
                    "admName": adm_name,
                    "evalNumber": EVAL_NUM,
                    "pid": pid,
                    "afTarget": float(target_af),
                    "mfTarget": float(target_mf),
                    "psTarget": float(target_ps),
                    "ssTarget": float(target_ss),
                    "af_align_ave": -1,
                    "mf_align_ave": -1,
                    "ps_align_ave": -1,
                    "ss_align_ave": -1,
                    "af_base_ave": -1,
                    "mf_base_ave": -1,
                    "ps_base_ave": -1,
                    "ss_base_ave": -1,
                    "ave_aligned_alignment": -1,
                    "ave_baseline_alignment": -1,
                }
                af_align_sum = 0
                mf_align_sum = 0
                ps_align_sum = 0
                ss_align_sum = 0
                af_align_count = 0
                mf_align_count = 0
                ps_align_count = 0
                ss_align_count = 0
                aligned_alignment_sum = 0
                aligned_alignment_count = 0

                for adm in adm_groups[adm_name][target_id]:
                    # get kdmas and averages for each scenario
                    sys.stdout.flush()
                    sys.stdout.write(
                        f"\rAnalyzing ADM group {completed_groups+1} of {group_count} - get adm kdmas"
                    )
                    kdma_name = adm["results"]["kdmas"][0]["kdma"]
                    kdma_value = adm["results"]["kdmas"][0]["value"]
                    if kdma_name == "affiliation":
                        af_align_sum += kdma_value
                        af_align_count += 1
                    elif kdma_name == "merit":
                        mf_align_sum += kdma_value
                        mf_align_count += 1
                    elif kdma_name == "personal_safety":
                        ps_align_sum += kdma_value
                        ps_align_count += 1
                    elif kdma_name == "search":
                        ss_align_sum += kdma_value
                        ss_align_count += 1

                    sys.stdout.flush()
                    sys.stdout.write(
                        f"\rAnalyzing ADM group {completed_groups+1} of {group_count}                                          "
                    )
                    adm_session_id = adm["results"]["ta1_session_id"]
                    human_session_id = adm["evaluation"]["alignment_target_id"]
                    # get the comparison between the human and adm
                    sys.stdout.flush()
                    sys.stdout.write(
                        f"\rAnalyzing ADM group {completed_groups+1} of {group_count} - get comparison (text|adm)       "
                    )
                    sys.stdout.flush()
                    res = (
                        requests.get(
                            f"{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={human_session_id}&session_id_2={adm_session_id}"
                        ).json()
                        if HIT_TA1_SERVER
                        else {"score": random.random()}
                    )

                    if "score" in res:
                        # update average alignment
                        aligned_alignment_sum += res["score"]
                        aligned_alignment_count += 1
                    else:
                        print(
                            f"Could not get comparison score for (text session {human_session_id}; adm session {adm_session_id})"
                        )

                new_doc["af_align_ave"] = af_align_sum / max(1, af_align_count)
                new_doc["mf_align_ave"] = mf_align_sum / max(1, mf_align_count)
                new_doc["ps_align_ave"] = ps_align_sum / max(1, ps_align_count)
                new_doc["ss_align_ave"] = ss_align_sum / max(1, ss_align_count)
                new_doc["ave_aligned_alignment"] = aligned_alignment_sum / max(
                    1, aligned_alignment_count
                )
                # euclidean distance
                new_doc["4D_Alignment_Aligned_30_Random_Sets"] = 1 - math.sqrt(
                    (new_doc["af_align_ave"] - new_doc["afTarget"]) ** 2
                    + (new_doc["mf_align_ave"] - new_doc["mfTarget"]) ** 2
                    + (new_doc["ps_align_ave"] - new_doc["psTarget"]) ** 2
                    + (new_doc["ss_align_ave"] - new_doc["ssTarget"]) ** 2
                )
                multi_kdmas_4d.insert_one(new_doc)
            completed_groups += 1
            sys.stdout.flush()
    print("\nAligned data collection complete.")

    # Add baseline data
    print("\nAdding baseline data.")
    pids = []
    for line in text_kdmas:
        pids.append(line[text_kdma_header.index("PID")])

    pid_count = len(pids)
    pid_num = 0
    for pid in pids:

        target_af = None
        target_mf = None
        target_ps = None
        target_ss = None
        for line in text_kdmas:
            if line[text_kdma_header.index("PID")] == pid:
                target_af = float(line[text_kdma_header.index("AF")])
                target_mf = float(line[text_kdma_header.index("MF")])
                target_ps = float(line[text_kdma_header.index("PS")])
                target_ss = float(line[text_kdma_header.index("SS")])
                break
        
        if target_af is None:
            print(f"Could not find target values for pid {pid}, skipping.")
            continue

        cursor = adm_collection.find(
            {
                "evalNumber": EVAL_NUM,
                "synthetic": True,
                "evaluation.adm_profile": "baseline",
                "evaluation.human_pid": pid,
                "scenario": {"$regex": "July2025-"},
            }
        )
        baselines = list(cursor)
        if (
            len(baselines) == 0
        ):  # Go find ADM with matching pids and grab those baselines instead
            print(f"Missing pid {pid}.")
            print(
                f"  Looking for matching baseline ADM with MF={target_mf},AF={target_af},PS={target_ps},SS={target_ss}."
            )
            cursor = adm_collection.find(
                {
                    "evalNumber": EVAL_NUM,
                    "synthetic": True,
                    "evaluation.adm_profile": "baseline",
                    "scenario": {"$regex": "July2025-"},
                    "evaluation.human_kdmas": {
                        "$all": [
                            {"$elemMatch": {"kdma": "merit", "value": target_mf}},
                            {"$elemMatch": {"kdma": "personal_safety", "value": target_ps}},
                            {"$elemMatch": {"kdma": "affiliation", "value": target_af}},
                            {"$elemMatch": {"kdma": "search", "value": target_ss}},
                        ]
                    },
                }
            )
            baselines = list(cursor)
            if len(baselines) == 0:
                print(f"  STILL Missing pid {pid}, so skipping.")
            else:
                print(f"  Found at pid {baselines[0]['evaluation']['human_pid']}.")

        pid_num += 1
        print(f"Processing pid {pid} (#{pid_num} of {pid_count}).")
        af_base_sum = 0
        mf_base_sum = 0
        ps_base_sum = 0
        ss_base_sum = 0
        baseline_alignment_sum = 0
        af_base_count = 0
        mf_base_count = 0
        ps_base_count = 0
        ss_base_count = 0
        baseline_alignment_count = 0
        for adm in baselines:
            kdma_name = adm["results"]["kdmas"][0]["kdma"]
            kdma_value = adm["results"]["kdmas"][0]["value"]
            # TBD:  Only have to do this once for baseline as the kdmas shouldn't vary.  If it saved us a trip to TA1, we'd cache.
            if kdma_name == "affiliation":
                af_base_sum += kdma_value
                af_base_count += 1
            elif kdma_name == "merit":
                mf_base_sum += kdma_value
                mf_base_count += 1
            elif kdma_name == "personal_safety":
                ps_base_sum += kdma_value
                ps_base_count += 1
            elif kdma_name == "search":
                ss_base_sum += kdma_value
                ss_base_count += 1
            adm_session_id = adm["results"]["ta1_session_id"]
            human_session_id = adm["evaluation"]["alignment_target_id"]
            res = (
                requests.get(
                    f"{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={human_session_id}&session_id_2={adm_session_id}"
                ).json()
                if HIT_TA1_SERVER
                else {"score": random.random()}
            )
            if "score" in res:
                # update average alignment
                baseline_alignment_sum += res["score"]
                baseline_alignment_count += 1
            else:
                print(
                    f"Could not get comparison score for (text session {human_session_id}; adm session {adm_session_id})"
                )
        af_base_ave = af_base_sum / max(1, af_base_count)
        mf_base_ave = mf_base_sum / max(1, mf_base_count)
        ps_base_ave = ps_base_sum / max(1, ps_base_count)
        ss_base_ave = ss_base_sum / max(1, ss_base_count)
        ave_baseline_alignment = baseline_alignment_sum / max(1, baseline_alignment_count)
        
        # Calculate baseline euclidean distance alignment
        baseline_4d_alignment = 1 - math.sqrt(
            (af_base_ave - target_af) ** 2
            + (mf_base_ave - target_mf) ** 2
            + (ps_base_ave - target_ps) ** 2
            + (ss_base_ave - target_ss) ** 2
        )

        # Update the multi-kdma record with baseline data
        multi_kdmas_4d.update_one(
            {"pid": pid},
            {
                "$set": {
                    "af_base_ave": af_base_ave,
                    "mf_base_ave": mf_base_ave,
                    "ps_base_ave": ps_base_ave,
                    "ss_base_ave": ss_base_ave,
                    "ave_baseline_alignment": ave_baseline_alignment,
                    "4D_Alignment_Baseline_30_Random_Sets": baseline_4d_alignment,
                }
            },
        )
    print("Baseline data collection complete.")

    print(
        f"\nMulti-KDMA Data collection '{FOUR_D_COLLECTION}' has been created and populated."
    )


def get_humans_with_kdmas(text_kdmas, kdma_header, af, mf, ps, ss) -> list:
    """
    Takes in the text_kdmas list along with kdma values to find.
    Returns a list of pids that match.
    There may be more than one matching entry for this kdma set.
    Return all.
    """
    matches = []
    for line in text_kdmas:
        line_af = float(line[kdma_header.index("AF")])
        line_mf = float(line[kdma_header.index("MF")])
        line_ps = float(line[kdma_header.index("PS")])
        line_ss = float(line[kdma_header.index("SS")])
        if af == line_af and mf == line_mf and ps == line_ps and ss == line_ss:
            matches.append(line[kdma_header.index("PID")])
    # This should never happen, so we exit if it does.
    if len(matches) == 0:
        print(f"FATAL: Could not find match for AF={af}, MF={mf}, PS={ps}, SS={ss}")
        exit(1)

    return matches


if __name__ == "__main__":
    # Instantiate mongo client
    client = MongoClient(config("MONGO_URL"))
    mongo_db = client.dashboard
    main(mongo_db)
