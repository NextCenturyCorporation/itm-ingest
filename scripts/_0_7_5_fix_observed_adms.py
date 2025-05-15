"""
Ticket:
https://nextcentury.atlassian.net/browse/ITM-1000
"""

from decouple import config
import requests
import utils.db_utils as db_utils


def main(mongo_db):
    observed_adms = mongo_db["delegationADMRuns"]
    comp_collec = mongo_db["humanToADMComparison"]
    observed_adms_cursor = observed_adms.find({"evalNumber": 5})
    full_adms = mongo_db["admTargetRuns"]

    for adm in observed_adms_cursor:

        if "MJ2" in adm["scenario"]:

            """
            Scenario MJ2 Moral Judgement
            Inserts response `Response 3-B.2-C` for probe `Probe 3-B.2`
            ONLY IF there is no response for that probe, otherwise leave it alone.
            This addresses moral judgement scoring discrepancy in scenario MJ2
            """

            if "Moral judgement" in adm["target"]:
                probe_exists = any(
                    probe.get("probe_id") == "Probe 3-B.2" for probe in adm["probes"]
                )
                if not probe_exists:
                    # probe doesn't exist, insert and re run
                    probes = adm["probes"].copy()
                    probes.append(
                        {
                            "choice": "Response 3-B.2-C",
                            "justification": "justification",
                            "probe_id": "Probe 3-B.2",
                            "scenario_id": "DryRunEval-MJ2-eval",
                        }
                    )

                    run_adm(adm, probes, observed_adms, comp_collec)

            """
            Scenario MJ2 Ingroup Bias
            Probe 4 and Probe 4-B.1 should not be used, instead use response to Probe 4-B1-B1.
            If they didn't answer Probe 4-B1-B1, respond to it using their response to Probe 4-B1.
            If they didn't answer Probe 4-B1, respond to Probe 4-B1-B1 with their answer to Probe 4
            """

            if "Ingroup Bias" in adm["target"]:
                remove_probes = ["Probe 4", "Probe 4-B.1", "Probe 4-B.1-B.1"]
                cleaned_probes = [
                    probe
                    for probe in adm["probes"]
                    if probe.get("probe_id") not in remove_probes
                ]

                matching_adm = full_adms.find_one(
                    {
                        "evalNumber": 5,
                        "adm_name": adm["adm_name"],
                        "scenario": adm["scenario"],
                        "alignment_target": adm["target"],
                    }
                )

                if matching_adm and "history" in matching_adm:
                    # go down the list of options
                    for probe_id in ["Probe 4-B.1-B.1", "Probe 4-B.1", "Probe 4"]:
                        probe_entry = next(
                            (
                                entry
                                for entry in matching_adm["history"]
                                if entry.get("parameters", {}).get("probe_id")
                                == probe_id
                            ),
                            None,
                        )
                        if probe_entry:
                            probe_choice = probe_entry.get("parameters", {}).get(
                                "choice"
                            )
                            if probe_id == "Probe 4-B.1-B.1":
                                new_choice = probe_choice
                            elif probe_choice.endswith("-A"):
                                new_choice = "Response 4-B.1-B.1-A"
                            else:
                                new_choice = "Response 4-B.1-B.1-B"

                            cleaned_probes.append(
                                {
                                    "probe_id": "Probe 4-B.1-B.1",
                                    "scenario_id": adm["scenario"],
                                    "choice": new_choice,
                                    "justification": probe_entry["parameters"].get(
                                        "justification", ""
                                    ),
                                }
                            )
                            run_adm(adm, cleaned_probes, observed_adms, comp_collec)
                            break

        """
        Scenario MJ4 Moral Judgement
        Probe 10-A.1 was used instead of Probe 10 for some calculations, that will be fixed in the following block.
        """

        if "MJ4" in adm["scenario"] and "Moral judgement" in adm["target"]:
            problem_probe_exists = any(
                probe.get("probe_id") == "Probe 10-A.1" for probe in adm["probes"]
            )

            if problem_probe_exists:
                # remove probe 10-A.1
                cleaned_probes = [
                    probe
                    for probe in adm["probes"]
                    if probe.get("probe_id") != "Probe 10-A.1"
                ]

                matching_adm = full_adms.find_one(
                    {
                        "evalNumber": 5,
                        "adm_name": adm["adm_name"],
                        "scenario": adm["scenario"],
                        "alignment_target": adm["target"],
                    }
                )
                if matching_adm and "history" in matching_adm:
                    # find response to probe 10
                    probe_10_entry = next(
                        (
                            entry
                            for entry in matching_adm["history"]
                            if entry.get("parameters", {}).get("probe_id") == "Probe 10"
                        ),
                        None,
                    )
                    if probe_10_entry:
                        cleaned_probes.append(
                            {
                                "probe_id": "Probe 10",
                                "scenario_id": adm["scenario"],
                                "choice": probe_10_entry["parameters"].get(
                                    "choice", ""
                                ),
                                "justification": probe_10_entry["parameters"].get(
                                    "justification", ""
                                ),
                            }
                        )

                        run_adm(adm, cleaned_probes, observed_adms, comp_collec)

        if "MJ5" in adm["scenario"]:
            """
            Scenario MJ5 Ingroup Bias
            Every time an ADM answered Probe 8 with Response 8-A, Probe 8-A.1-A.1 needs to be answered as well.
            If the adm answered Probe 8-A.1, we need to drop that from the calculation and instead use Probe 8-A.1-A.1.
            If they didn't answer Probe 8-A.1-A.1 but did answer Probe 8-A.1, we will use that answer to respond to Probe 8-A.1-A.1
            """

            if "Ingroup Bias" in adm["target"]:
                # Check if probe 8 was answered with Response 8-A
                probe_answer = any(
                    probe.get("probe_id") == "Probe 8"
                    and probe.get("choice") == "Response 8-A"
                    for probe in adm["probes"]
                )

                if probe_answer:
                    # Check if they already have a response to Probe 8-A.1-A.1
                    follow_up_probe = any(
                        probe.get("probe_id") == "Probe 8-A.1-A.1"
                        for probe in adm["probes"]
                    )

                    # If they do not have a response to Probe 8-A.1-A.1 in our calculation
                    if not follow_up_probe:
                        matching_adm = full_adms.find_one(
                            {
                                "evalNumber": 5,
                                "adm_name": adm["adm_name"],
                                "scenario": adm["scenario"],
                                "alignment_target": adm["target"],
                            }
                        )

                        if matching_adm and "history" in matching_adm:
                            # try to use Probe 8-A.1-A.1, otherwise fall back on Probe 8-A.1
                            probe = next(
                                (
                                    entry
                                    for entry in matching_adm["history"]
                                    if entry.get("parameters", {}).get("probe_id")
                                    == "Probe 8-A.1-A.1"
                                ),
                                None,
                            )

                            if not probe:
                                probe = next(
                                    (
                                        entry
                                        for entry in matching_adm["history"]
                                        if entry.get("parameters", {}).get("probe_id")
                                        == "Probe 8-A.1"
                                    ),
                                    None,
                                )

                            original_choice = probe.get("parameters", {}).get(
                                "choice", ""
                            )
                            choice = (
                                "Response 8-A.1-A.1-A"
                                if original_choice.endswith("-A")
                                else "Response 8-A.1-A.1-B"
                            )

                            cleaned_probes = adm["probes"].copy()
                            cleaned_probes.append(
                                {
                                    "probe_id": "Probe 8-A.1-A.1",
                                    "scenario_id": adm["scenario"],
                                    "choice": choice,
                                    "justification": probe["parameters"].get(
                                        "justification", ""
                                    ),
                                }
                            )

                            run_adm(adm, cleaned_probes, observed_adms, comp_collec)

            """
            Scenario MJ5 Moral judgement
            Probes 2-B.1 and 2-A.1 should be removed from the calculation
            Make sure Probe 2-A.1-A.1 or Probe 2-B.1-A.1 answered depending on Probe 2 response
            """

            if "Moral judgement" in adm["target"]:
                problem_probes = ["Probe 2-B.1", "Probe 2-A.1"]
                has_problem_probes = any(
                    probe.get("probe_id") in problem_probes for probe in adm["probes"]
                )

                probe_2_response_B = next(
                    (
                        probe
                        for probe in adm["probes"]
                        if probe.get("probe_id") == "Probe 2"
                        and probe.get("choice") == "Response 2-B"
                    ),
                    None,
                )
                probe_2_A1_A1 = next(
                    (
                        probe
                        for probe in adm["probes"]
                        if probe.get("probe_id") == "Probe 2-A.1-A.1"
                    ),
                    None,
                )

                need_changes = False

                cleaned_probes = adm["probes"].copy()

                if has_problem_probes:
                    cleaned_probes = [
                        probe
                        for probe in cleaned_probes
                        if probe.get("probe_id") not in problem_probes
                    ]
                    need_changes = True

                if probe_2_response_B and probe_2_A1_A1:
                    cleaned_probes = [
                        probe
                        for probe in cleaned_probes
                        if probe.get("probe_id") != "Probe 2-A.1-A.1"
                    ]
                    choice = (
                        "Response 2-B.1-A.1-A"
                        if probe_2_A1_A1.get("choice", "").endswith("A")
                        else "Response 2-B.1-A.1-B"
                    )

                    cleaned_probes.append(
                        {
                            "probe_id": "Probe 2-B.1-A.1",
                            "scenario_id": adm["scenario"],
                            "choice": choice,
                            "justification": probe_2_A1_A1.get("justification", ""),
                        }
                    )
                    need_changes = True

                if need_changes:
                    run_adm(adm, cleaned_probes, observed_adms, comp_collec)


def run_adm(adm, probes, observed_adms, comparison_collec):
    """
    Grab all of the comparison docs that point to this old session id and update them with the new adm run's session id and comp score.
    Deletes the old ADM document after creating a new one.
    """
    eval_num = adm["evalNumber"]

    dre_ph1_run = adm.get("dre_ph1_run", False)
    ph1_in_dre_server_run = adm.get("ph1_in_dre_server_run", False)

    ADEPT_URL = (
        config("ADEPT_DRE_URL")
        if (
            (eval_num == 4 and not dre_ph1_run)
            or (eval_num == 5 or eval_num == 6)
            and ph1_in_dre_server_run
        )
        else config("ADEPT_URL")
    )

    old_session_id = adm["session_id"]
    old_id = adm["_id"]

    # run observed adm with updated probes. new doc in delegationADMRuns
    new_observed_adm = db_utils.mini_adm_run(
        5,
        observed_adms,
        probes,
        adm["target"],
        adm.get("adm_name", ""),
        dre_ph1_run,
        ph1_in_dre_server_run,
        True,
    )
    new_session_id = new_observed_adm["session_id"]

    # delete old document because we just made a new one
    delete_result = observed_adms.delete_one({"_id": old_id})
    if delete_result.deleted_count > 0:
        print(
            f"Deleted old ADM document with ID: {old_id}, session_id: {old_session_id}"
        )
    else:
        print(f"Failed to delete old ADM document with ID: {old_id}")

    matching_comps = comparison_collec.find({"adm_session_id": old_session_id})

    # update comparison scores to participants
    for comp in matching_comps:
        human_sid = comp["text_session_id"]
        if "Moral" in adm["target"]:
            score = requests.get(
                f"{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={human_sid}&session_id_2_or_target_id={new_session_id}&target_pop_id=ADEPT-DryRun-Moral%20judgement-Population-All"
            ).json()
        else:
            score = requests.get(
                f"{ADEPT_URL}api/v1/alignment/compare_sessions_population?session_id_1_or_target_id={human_sid}&session_id_2_or_target_id={new_session_id}&target_pop_id=ADEPT-DryRun-Ingroup%20Bias-Population-All"
            ).json()

        # replace adm session id and (population) score on comparison document
        comparison_collec.update_one(
            {"_id": comp["_id"]},
            {"$set": {"score": score["score"], "adm_session_id": new_session_id}},
        )

        # updates distance based score as well
        if comp.get("distance_based_score") is not None:
            if "Moral" in adm["target"]:
                score = requests.get(
                    f"{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={human_sid}&session_id_2={new_session_id}&kdma_filter=Moral%20judgement"
                ).json()
            else:
                score = requests.get(
                    f"{ADEPT_URL}api/v1/alignment/compare_sessions?session_id_1={human_sid}&session_id_2={new_session_id}&kdma_filter=Ingroup%20Bias"
                ).json()
            comparison_collec.update_one(
                {"_id": comp["_id"]},
                {
                    "$set": {
                        "distance_based_score": score["score"],
                        "adm_session_id": new_session_id,
                    }
                },
            )
