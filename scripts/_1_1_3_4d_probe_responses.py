from scripts._1_0_1_setup_p24d import main as take1
from scripts._1_0_4_setup_p24d_take2 import main as take2


def parse_probe_responses(probe_responses, target_type):
    filtered_responses = []

    for response_str in probe_responses:
        # split string: "AF Probe 5, Response 5-A"
        parts = response_str.split(", ")
        if len(parts) != 2:
            continue

        probe_part = parts[0]  
        response_part = parts[1] 

        # Check if this probe matches the target type
        if probe_part.startswith(target_type):
            #e.g. "Probe 5" from "AF Probe 5"
            probe_id = probe_part[len(target_type) :].strip() 
            filtered_responses.append({probe_id: response_part})

    return filtered_responses


def main(mongo_db):
    take1(mongo_db)
    take2(mongo_db)

    take2_collection = mongo_db["multiKdmaData4Dtake2"]
    adm_target_runs = mongo_db["admTargetRuns"]

    documents = take2_collection.find({})
    doc_count = take2_collection.count_documents({})
    
    pids_to_process = [doc.get("pid") for doc in take2_collection.find({}, {"pid": 1})]
    
    # Delete dups if re running
    print(f"\nDeleting existing eval 11 documents for {len(pids_to_process)} PIDs...")
    delete_result = adm_target_runs.delete_many({
        'evalNumber': 11,
        'evalName': 'Phase 2 4D Experiment',
        'pid': {'$in': pids_to_process}
    })
    print(f"Deleted {delete_result.deleted_count} existing documents.")

    print(f"\nCreating admTargetRuns documents for {doc_count} entries...")

    # deciphering multiKdma4Dtake2 collection into format for adm probe responses
    scenarios = [
        (
            "July2025-AF1-eval",
            "afTarget",
            "AF",
            "af_kdma_aligned_set1",
            "af_kdma_baseline_set1",
            "set1_aligned_probe_responses",
            "set1_baseline_probe_responses",
        ),
        (
            "July2025-AF2-eval",
            "afTarget",
            "AF",
            "af_kdma_aligned_set2",
            "af_kdma_baseline_set2",
            "set2_aligned_probe_responses",
            "set2_baseline_probe_responses",
        ),
        (
            "July2025-AF3-eval",
            "afTarget",
            "AF",
            "af_kdma_aligned_set3",
            "af_kdma_baseline_set3",
            "set3_aligned_probe_responses",
            "set3_baseline_probe_responses",
        ),
        (
            "July2025-MF1-eval",
            "mfTarget",
            "MF",
            "mf_kdma_aligned_set1",
            "mf_kdma_baseline_set1",
            "set1_aligned_probe_responses",
            "set1_baseline_probe_responses",
        ),
        (
            "July2025-MF2-eval",
            "mfTarget",
            "MF",
            "mf_kdma_aligned_set2",
            "mf_kdma_baseline_set2",
            "set2_aligned_probe_responses",
            "set2_baseline_probe_responses",
        ),
        (
            "July2025-MF3-eval",
            "mfTarget",
            "MF",
            "mf_kdma_aligned_set3",
            "mf_kdma_baseline_set3",
            "set3_aligned_probe_responses",
            "set3_baseline_probe_responses",
        ),
        (
            "July2025-PS1-eval",
            "psTarget",
            "PS",
            "ps_kdma_aligned_set1",
            "ps_kdma_baseline_set1",
            "set1_aligned_probe_responses",
            "set1_baseline_probe_responses",
        ),
        (
            "July2025-PS2-eval",
            "psTarget",
            "PS",
            "ps_kdma_aligned_set2",
            "ps_kdma_baseline_set2",
            "set2_aligned_probe_responses",
            "set2_baseline_probe_responses",
        ),
        (
            "July2025-PS3-eval",
            "psTarget",
            "PS",
            "ps_kdma_aligned_set3",
            "ps_kdma_baseline_set3",
            "set3_aligned_probe_responses",
            "set3_baseline_probe_responses",
        ),
        (
            "July2025-SS1-eval",
            "ssTarget",
            "SS",
            "ss_kdma_aligned_set1",
            "ss_kdma_baseline_set1",
            "set1_aligned_probe_responses",
            "set1_baseline_probe_responses",
        ),
        (
            "July2025-SS2-eval",
            "ssTarget",
            "SS",
            "ss_kdma_aligned_set2",
            "ss_kdma_baseline_set2",
            "set2_aligned_probe_responses",
            "set2_baseline_probe_responses",
        ),
        (
            "July2025-SS3-eval",
            "ssTarget",
            "SS",
            "ss_kdma_aligned_set3",
            "ss_kdma_baseline_set3",
            "set3_aligned_probe_responses",
            "set3_baseline_probe_responses",
        ),
    ]

    processed = 0
    total_docs_created = 0

    for doc in documents:
        processed += 1
        pid = doc.get("pid", "unknown")
        print(f"Processing document {processed} of {doc_count} (PID: {pid})")

        for (
            scenario,
            target_field,
            kdma_type,
            aligned_kdma_field,
            baseline_kdma_field,
            aligned_probes_field,
            baseline_probes_field,
        ) in scenarios:
            aligned_probes_raw = doc.get(aligned_probes_field, [])
            aligned_probes_parsed = parse_probe_responses(aligned_probes_raw, kdma_type)

            baseline_probes_raw = doc.get(baseline_probes_field, [])
            baseline_probes_parsed = parse_probe_responses(
                baseline_probes_raw, kdma_type
            )

            aligned_doc = {
                "evalNumber": 11,
                "evalName": "Phase 2 4D Experiment",
                "pid": pid,
                "scenario": scenario,
                "alignment_target": str(doc.get(target_field)), 
                "adm_name": doc.get("admName"),  
                "synthetic": True, 
                "probe_ids": [
                    list(pr.keys())[0] for pr in aligned_probes_parsed
                ],  
                "probe_responses": aligned_probes_parsed,
                "results": {
                    "kdmas": [
                        {
                            "kdma": (
                                scenario[9:11].lower()
                                if scenario[9:11] == "AF"
                                else (
                                    "merit"
                                    if scenario[9:11] == "MF"
                                    else (
                                        "personal_safety"
                                        if scenario[9:11] == "PS"
                                        else "search"
                                    )
                                )
                            ),
                            "value": doc.get(aligned_kdma_field),
                        }
                    ],
                },
            }
            adm_target_runs.insert_one(aligned_doc)
            total_docs_created += 1

            # Create baseline document
            baseline_doc = {
                "evalNumber": 11,
                "evalName": "Phase 2 4D Experiment",
                "pid": pid,
                "scenario": scenario,
                "alignment_target": str(doc.get(target_field)),  # Convert to string!
                "adm_name": "ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3",  # Add for consistency
                "synthetic": True,  # Add this field
                "probe_ids": [
                    list(pr.keys())[0] for pr in baseline_probes_parsed
                ],  # Add probe_ids!
                "probe_responses": baseline_probes_parsed,
                # Add results structure like eval 14
                "results": {
                    "kdmas": [
                        {
                            "kdma": (
                                scenario[9:11].lower()
                                if scenario[9:11] == "AF"
                                else (
                                    "merit"
                                    if scenario[9:11] == "MF"
                                    else (
                                        "personal_safety"
                                        if scenario[9:11] == "PS"
                                        else "search"
                                    )
                                )
                            ),
                            "value": doc.get(baseline_kdma_field),
                        }
                    ],
                },
            }
            adm_target_runs.insert_one(baseline_doc)
            total_docs_created += 1

    print(
        f"\nCreated {total_docs_created} admTargetRuns documents (24 per source document: 12 aligned + 12 baseline)"
    )