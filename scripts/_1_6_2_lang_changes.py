lang_dict = {
    'Patient A has a chest wound and are gasping for breath.': 'Patient A has a chest wound and is gasping for breath.',
    'Patient B has a chest wound and are gasping for breath.': 'Patient B has a chest wound and is gasping for breath.',
    'Patient A has no visible bleeding but are not breathing after their airway has been repositioned.': 'Patient A has no visible bleeding but is not breathing after their airway has been repositioned.',
    'Patient B has no visible bleeding but are not breathing after their airway has been repositioned.': 'Patient B has no visible bleeding but is not breathing after their airway has been repositioned.',
    'Patient A has no visible bleeding but are not breathing': 'Patient A has no visible bleeding but is not breathing',
    'Patient B has no visible bleeding but are not breathing': 'Patient B has no visible bleeding but is not breathing',
    'Patient A has a chest wound and are gasping for breath.': 'Patient A has a chest wound and is gasping for breath.',
    'Patient B has a chest wound and are gasping for breath.': 'Patient B has a chest wound and is gasping for breath.',
    'JLTVs': 'tactical vehicles',
    'a SMAW fired into': 'fire in',
    'They are a POW': 'They are a PW',
    'They are a US civilian contractor who works for the US military': 'They are a Canadian civilian contractor who works for the Canadian military'
}
def main(mongo_db):
    survey = mongo_db['delegationConfig'].find_one({'_id': 'delegation_v13.0'})
    for page in survey['survey']['pages']:
            for row in page['elements'][0]['rows']:
                for old_text, new_text in lang_dict.items():
                    row['probe_unstructured'] = row['probe_unstructured'].replace(old_text, new_text)

    mongo_db['delegationConfig'].update_one(
        {'_id': 'delegation_v13.0'},
        {'$set': {'survey.pages': survey['survey']['pages']}}
    )

    text_configs = list(mongo_db['textBasedConfig'].find({'eval': 'Phase 2 Canada Evaluation'}))

    for config in text_configs:
         for page in config['pages']:
              for old_text, new_text in lang_dict.items():
                   page['elements'][0]['probe_unstructured'] = page['elements'][0]['probe_unstructured'].replace(old_text, new_text)

         mongo_db['textBasedConfig'].update_one(
             {'_id': config['_id']},
             {'$set': {'pages': config['pages']}}
         )
