from delegation_survey.phase2_covert_adm_to_del_materials import main as convert_adms
from delegation_survey.update_survey_config import version10_setup
def main(mongo_db):
    adm_runs = mongo_db['admTargetRuns'].find({'evalNumber': 15})
    
    # Define the ADM configurations
    MF_SS_ADMS = {
        'DeepSeek Llama': {
            'baseline': 'ALIGN-ADM-OutlinesBaseline-DeepSeek-R1-Distill-Llama-8B',
            'aligned': 'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-DeepSeek-R1-Distill-Llama-8B'
        },
        'Spectrum Llama': {
            'baseline': 'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1',
            'aligned': 'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Llama-3.1-8B-v1'
        }
    }
    
    AF_PS_ADMS = {
        'Mistral': {
            'baseline': 'ALIGN-ADM-OutlinesBaseline-Mistral-7B-Instruct-v0.3',
            'aligned': 'ALIGN-ADM-Ph2-DirectRegression-BertRelevance-Mistral-7B-Instruct-v0.3'
        },
        'Spectrum Llama': {
            'baseline': 'ALIGN-ADM-OutlinesBaseline-spectrum-Llama-3.1-8B-v1',
            'aligned': 'ALIGN-ADM-Ph2-ComparativeRegression-BertRelevance-spectrum-Llama-3.1-8B-v1'
        }
    }
    
    # Collect all valid ADM names for each scenario type
    mf_ss_valid_adms = set()
    for model_config in MF_SS_ADMS.values():
        mf_ss_valid_adms.add(model_config['baseline'])
        mf_ss_valid_adms.add(model_config['aligned'])
    
    af_ps_valid_adms = set()
    for model_config in AF_PS_ADMS.values():
        af_ps_valid_adms.add(model_config['baseline'])
        af_ps_valid_adms.add(model_config['aligned'])
    
    # Filter ADMs based on scenario type and ADM name
    included_adms = []
    
    for adm_run in adm_runs:
        scenario = adm_run.get('scenario', '')
        adm_name = adm_run.get('adm_name', '')
        
        # Check if this ADM run should be included
        should_include = False
        
        # Include all MF3 scenarios regardless of ADM
        if 'MF3' in scenario:
            should_include = True
        
        elif 'AF-PS' in scenario or 'AF1-PS1' in scenario:
            # Check if adm_name matches any AF-PS ADM
            for valid_adm in af_ps_valid_adms:
                if valid_adm in adm_name:
                    should_include = True
                    break
        
        elif 'MF-SS' in scenario or 'MF1-SS1' in scenario:
            # Check if adm_name matches any MF-SS ADM
            for valid_adm in mf_ss_valid_adms:
                if valid_adm in adm_name:
                    should_include = True
                    break
        
        if should_include:
            included_adms.append(adm_run)
    
    # Convert the filtered ADMs
    convert_adms(mongo_db, 15, 'feb2026/admrun',included_adms)
    
    print(f"Total ADM runs found: {len(list(mongo_db['admTargetRuns'].find({'evalNumber': 15})))}")
    print(f"Included ADM runs: {len(included_adms)}")

    version10_setup(auto_confirm=True)