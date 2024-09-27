def remove_adept_probes(mongo_db):
    text_config_collection = mongo_db['textBasedConfig']
    
    dry_run_eval_io1 = text_config_collection.find_one({"scenario_id": "DryRunEval.IO1"})
    dry_run_eval_mj1 = text_config_collection.find_one({"scenario_id": "DryRunEval.MJ1"})
    
    io1_pages_to_drop = ["P2", "P3", "P4", "P8", "P9", "P10", "P13", "P14"]
    mj1_pages_to_drop = ["P1", "P2", "P3", "P4", "P14", "P15", "P16"]
    
    if dry_run_eval_io1 and 'pages' in dry_run_eval_io1:
        original_pages = len(dry_run_eval_io1['pages'])
        dry_run_eval_io1['pages'] = [page for page in dry_run_eval_io1['pages'] if page.get('name') not in io1_pages_to_drop]
        remaining_pages = len(dry_run_eval_io1['pages'])
        
        text_config_collection.update_one(
            {"scenario_id": "DryRunEval.IO1"},
            {"$set": {"pages": dry_run_eval_io1['pages']}}
        )
        
        print(f"DryRunEval.IO1: Dropped {original_pages - remaining_pages} pages.")
        print(f"Pages dropped: {', '.join(io1_pages_to_drop)}")
    else:
        print("DryRunEval.IO1: Document not found or 'pages' field missing.")
    
    if dry_run_eval_mj1 and 'pages' in dry_run_eval_mj1:
        original_pages = len(dry_run_eval_mj1['pages'])
        dry_run_eval_mj1['pages'] = [page for page in dry_run_eval_mj1['pages'] if page.get('name') not in mj1_pages_to_drop]
        remaining_pages = len(dry_run_eval_mj1['pages'])
        
        text_config_collection.update_one(
            {"scenario_id": "DryRunEval.MJ1"},
            {"$set": {"pages": dry_run_eval_mj1['pages']}}
        )
        
        print(f"DryRunEval.MJ1: Dropped {original_pages - remaining_pages} pages.")
        print(f"Pages dropped: {', '.join(mj1_pages_to_drop)}")
    else:
        print("DryRunEval.MJ1: Document not found or 'pages' field missing.")