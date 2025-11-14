import pandas as pd
from pymongo import MongoClient
from decouple import config

EVAL_NUM = 14
EVALUATION_TYPE = 'July2025'

def main(mongo_db):
    '''
    get all aligned adms
    for each aligned adm
      get corresponding baseline adm
        Attribute (MF, AF, PS, SS)
        Target (0.0-1.0)
        Set construction (one of 6probe, 10probe, 8probe, Adapt6, Adapt8, or New6)
        Set (1-30)
        Probe IDs
        Aligned Server Session ID
        Aligned ADM Alignment score (ADM|Target)
        Baseline ADM Alignment score (ADM|Target)
        Baseline Server Session ID
    '''
    print('\nDumping to Excel.')
    export_data = []
    adm_collection = mongo_db['admTargetRuns']
    aligned_adm_cursor = adm_collection.find({'evalNumber': EVAL_NUM, 'synthetic': True, 'evaluation.adm_profile': 'aligned'})
    aligned_adm_runs = list(aligned_adm_cursor)
    print(f"Retrieved {len(aligned_adm_runs)} aligned adm runs from database.")
    for aligned_adm_run in aligned_adm_runs:
        # Find corresponding baseline ADM
        baseline_cursor = adm_collection.find({'evalNumber': EVAL_NUM, 'synthetic': True, 'evaluation.adm_profile': 'baseline',
                                               'alignment_target': aligned_adm_run['alignment_target'],
                                               'scenario': aligned_adm_run['scenario'],
                                               'evaluation.set_construction': aligned_adm_run['evaluation']['set_construction']})
        baseline_runs: list = list(baseline_cursor)
        brun_count = len(baseline_runs) if baseline_runs else 0
        if brun_count == 0:
            print(f"Could not find equalent baseline run for {aligned_adm_run}")
        elif brun_count > 1:
            print(f"Too many baseline runs {brun_count} for {aligned_adm_run}")
        baseline_run = baseline_runs[0]

        # Prepare data for spreadsheet
        data = {
            'Attribute': aligned_adm_run['scenario'][len(EVALUATION_TYPE)+1:len(EVALUATION_TYPE)+3],
            'Target': aligned_adm_run['evaluation']['alignment_target_id'],
            'Set construction': aligned_adm_run['evaluation']['set_construction'],
            'Set': int(aligned_adm_run['evaluation']['scenario_name'].split()[-1]),
            'Probe IDs': aligned_adm_run['probe_ids'],
            'Aligned Server Session ID': aligned_adm_run['results']['ta1_session_id'],
            'Aligned ADM Alignment score (ADM|Target)': aligned_adm_run['results']['alignment_score'],
            'Baseline ADM Alignment score (ADM|Target)': baseline_run['results']['alignment_score'] if baseline_run else '',
            'Baseline Server Session ID': baseline_run['results']['ta1_session_id'] if baseline_run else ''
            }
        export_data.append(data)

    # Create DataFrame and export
    df = pd.DataFrame(export_data)

    # Sort
    df = df.sort_values(by=['Attribute', 'Set construction', 'Set', 'Target'])

    # Export to an Excel file
    filename = 'Adaptive_WildWest.xlsx'
    print(f"Writing {len(export_data)} rows to {filename}.")
    with pd.ExcelWriter(filename) as writer:
        df.to_excel(writer, sheet_name='Adaptive', index=False)

    print("Done.")


if __name__ == '__main__':

    client = MongoClient(config('MONGO_URL'))
    main(client.dashboard)
