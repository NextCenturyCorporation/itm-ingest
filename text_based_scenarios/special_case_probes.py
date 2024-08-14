special_case_probes = {
    'DryRunEval-MJ2-eval': {
        'Probe 2': {
            'elements': [
                {
                    'title': 'What do you want to do?',
                    'type': 'comment',
                    'probe_id': 'Probe 2 Prelim',
                    'name': 'probe Probe 2 Prelim',
                    'isRequired': True
                },
                {
                    'title': 'What action do you take?',
                    'name': 'probe Probe 2-F.1',
                    'probe_id': 'Probe 2-F.1',
                    'isRequired': True,
                    'visibleIf': '{probe Probe 2 Prelim} notempty',
                    'type': 'radiogroup',
                    'choices': [
                        {
                            'value': 'Assess the shooter.',
                            'text': 'Assess the shooter.'
                        },
                        {
                            'value': 'Assess the victim.',
                            'text': 'Assess the victim.'
                        }
                    ],
                    'question_mapping': {
                        'Assess the shooter.': {
                            'probe_id': 'Probe 2-F.1',
                            'choice': 'Response 2-F.1-A'
                        },
                        'Assess the victim.': {
                            'probe_id': 'Probe 2-F.1',
                            'choice': 'Response 2-F.1-B'
                        }
                    }
                }
            ]
        }
    }
}