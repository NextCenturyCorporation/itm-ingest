import csv, argparse, os, json

class TreatmentLogger:
    treatments_applied_by_pid = {}
    treatments_applied_per_patient = {}
    num_pids_who_applied_per_patient = {}
    desert_participants = 0
    urban_participants = 0

    def update_logger_from_json(self, pid, json_file):
        '''
        Counts the number of treatments applied to each patient.
        Organizes by total number of treatments applied, and total number
        of participants who applied a specific treatment. 
        Call this for every open world json. 
        '''
        data = json.load(json_file)
        env = data['configData']['scene'].split('im-')[1].split('-sanitized')[0]
        if env == 'desert':
            self.desert_participants += 1
        else:
            self.urban_participants += 1
        if pid not in self.treatments_applied_by_pid:
            self.treatments_applied_by_pid[pid] = {}

        actions = data['actionList']
        treatments_counted = []
        for action in actions:
            if action['actionType'] == 'Treatment':
                patient = action['casualty'] + f' ({env})'
                tool = action['treatment']
                loc = action['treatmentLocation']
                inj = action['injuryType']
                full_string = patient + ' - ' + tool + ' - ' + loc + ' ' + inj
                if full_string not in self.treatments_applied_by_pid[pid]:
                    self.treatments_applied_by_pid[pid][full_string] = 0
                self.treatments_applied_by_pid[pid][full_string] += 1

                patientless_string = tool + ' - ' + loc + ' ' + inj
                if patient not in self.treatments_applied_per_patient:
                    self.treatments_applied_per_patient[patient] = {}
                    self.num_pids_who_applied_per_patient[patient] = {}
                if patientless_string not in self.treatments_applied_per_patient[patient]:
                    self.treatments_applied_per_patient[patient][patientless_string] = 0
                    self.num_pids_who_applied_per_patient[patient][patientless_string] = 0
                self.treatments_applied_per_patient[patient][patientless_string] += 1
                if full_string not in treatments_counted:
                    self.num_pids_who_applied_per_patient[patient][patientless_string] += 1
                    treatments_counted.append(full_string)
                    
    def generate_treatment_csv(self, total):
        '''
        Call after all update_logger_from_json calls are complete.
        Generates a csv that organizes the treatment data.
        '''
        f = open('number_of_people_who_treated_each_patient_with_treatment.csv' if not total else 'total_treatments_per_patient.csv', 'w', encoding='utf-8')
        writer = csv.writer(f)
        inverted = {}
        treatments = []
        header = []
        dict_to_use = self.num_pids_who_applied_per_patient if not total else self.treatments_applied_per_patient
        for patient in dict_to_use:
            header.append(patient)
            for treatment in dict_to_use[patient]:
                formattedTreatment = treatment.replace(' -  ', '').replace('None', '(No Applicable Injury)').replace(' - Full Body ', '')
                if formattedTreatment not in treatments:
                    treatments.append(formattedTreatment)
                if formattedTreatment not in inverted:
                    inverted[formattedTreatment] = {}
                if patient not in inverted[formattedTreatment]:
                    inverted[formattedTreatment][patient] = 0
                inverted[formattedTreatment][patient] += dict_to_use[patient][treatment]
        treatments.sort()
        print(json.dumps(inverted, indent=4))

        header.insert(0, 'Treatment')
        writer.writerow(header)
        for treatment in treatments:
            row = [treatment]
            for _ in range(len(header)-1):
                row.append(0)
            for patient in inverted[treatment]:
                row[header.index(patient)] = inverted[treatment][patient]
            writer.writerow(row)
        writer.writerow(['Total Desert Participants', self.desert_participants])
        writer.writerow(['Total Urban Participants', self.urban_participants])
        f.close()



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=f"ITM - Treatment Logger", usage='treatment_logger.py [-h] -i PATH')
    parser.add_argument('-i', '--input_dir', dest='input_dir', type=str, help='The path to the directory where all participant files are. Required.')
    
    args = parser.parse_args()

    if not args.input_dir:
        print("Input directory (-i PATH) is required to run the probe matcher.")
        exit(1)

    treatment_logger = TreatmentLogger()

    # Go through the input directory and find all sub directories
    sub_dirs = [name for name in os.listdir(args.input_dir) if os.path.isdir(os.path.join(args.input_dir, name))]
    # For each subdirectory, see if a json file exists
    for dir in sub_dirs:
        parent = os.path.join(args.input_dir, dir)

        if os.path.isdir(parent):
            for f in os.listdir(parent):
                if '.json' in f:
                    open_file = open(os.path.join(parent, f), encoding='utf-8')
                    treatment_logger.update_logger_from_json(f.split('_')[-1].split('.json')[0], open_file)
                    open_file.close()
                    continue

    treatment_logger.generate_treatment_csv(True)
    treatment_logger.generate_treatment_csv(False)