import pandas as pd

def main(mongo_db):
    config_6 = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v6.0'})
    pages = config_6['survey']['pages']
    
    # Dictionary to group pages by scenario and choices
    scenario_choice_groups = {}
    
    for page in pages:
        if 'Medic' not in page['name']:
            # non medic page
            continue
            
        scenario = page['scenarioIndex']
        adm_name = page['admName']
        adm_target = page['target']
        medic_name = page['name']
        choices = page['elements'][0]['rows']
        
        # Create a key from scenario and choices for comparison
        choices_key = tuple(
            (choice['choice'], choice['probe_unstructured']) 
            for choice in choices
        )
        
        key = (scenario, choices_key)
        
        if key not in scenario_choice_groups:
            scenario_choice_groups[key] = []
        
        scenario_choice_groups[key].append({
            'medic_name': medic_name,
            'adm_name': adm_name,
            'adm_target': adm_target,
            'scenario': scenario,
        })
    
    # Prepare data for spreadsheet
    export_data = []
    duplicate_group_id = 1
    
    for key, pages_list in scenario_choice_groups.items():
        scenario, choices_key = key
        
        if len(pages_list) > 1:
            # Check if any page in this group has 'Baseline' in the adm_name
            baseline_in_group = any('Baseline' in page['adm_name'] for page in pages_list)
            
            # Filter out pages with 'Baseline' in adm_name from being their own row
            non_baseline_pages = [page for page in pages_list if 'Baseline' not in page['adm_name']]
            
            # If all pages are baseline, skip this group
            if not non_baseline_pages:
                continue
            
            # This is a duplicate group
            for page_info in non_baseline_pages:
                # Get other targets in the same group with the same adm_name
                other_targets = [
                    p['adm_target'] 
                    for p in pages_list 
                    if p['adm_name'] == page_info['adm_name'] and p['adm_target'] != page_info['adm_target']
                ]
                
                export_data.append({
                    'Duplicate_Group_ID': duplicate_group_id,
                    'Scenario_Index': scenario,
                    'ADM_Name': page_info['adm_name'],
                    'ADM_Target': page_info['adm_target'],
                    'Baseline_Overlap': baseline_in_group,
                    'Other_Targets_in_Group': ', '.join(other_targets) if other_targets else 'None'
                })
            duplicate_group_id += 1
    
    # Create DataFrame and export
    if export_data:
        df = pd.DataFrame(export_data)
        
        # Sort by Scenario_Index, then ADM_Name, then ADM_Target
        df = df.sort_values(['Scenario_Index', 'ADM_Name', 'ADM_Target'])
        
        # Also create a summary sheet
        summary_data = []
        for group_id in df['Duplicate_Group_ID'].unique():
            group_df = df[df['Duplicate_Group_ID'] == group_id]
            
            # Get unique ADM names in this group
            unique_adms = group_df['ADM_Name'].unique()
            
            summary_data.append({
                'Duplicate_Group_ID': group_id,
                'Scenario_Index': group_df['Scenario_Index'].iloc[0],
                'Number_of_Non_Baseline_Pages': len(group_df),
                'ADMs_in_Group': ', '.join(unique_adms),
                'Has_Baseline_Overlap': group_df['Baseline_Overlap'].iloc[0]
            })
        
        summary_df = pd.DataFrame(summary_data)
        # Sort summary by Scenario_Index as well
        summary_df = summary_df.sort_values('Scenario_Index')
        
        # Export both sheets to one Excel file
        with pd.ExcelWriter('duplicate_pages_analysis.xlsx') as writer:
            df.to_excel(writer, sheet_name='Detailed_View', index=False)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        print(f"✅ Exported {len(export_data)} duplicate page records to 'duplicate_pages_analysis.xlsx'")
        print(f"📊 Found {len(summary_data)} duplicate groups")
        
        # Print summary to console
        print("\n📋 SUMMARY:")
        for _, row in summary_df.iterrows():
            print(f"Group {row['Duplicate_Group_ID']}: Scenario {row['Scenario_Index']} - {row['Number_of_Non_Baseline_Pages']} non-baseline pages")
            print(f"   ADMs: {row['ADMs_in_Group']}")
            print(f"   Has Baseline Overlap: {row['Has_Baseline_Overlap']}")
            print()
            
    else:
        print("✅ No duplicates found - no spreadsheet created")