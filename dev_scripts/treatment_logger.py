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
                patient = env + ' - ' + action['casualty']
                tool = action['treatment']
                loc = action['treatmentLocation']
                inj = action['injuryType']
                full_string = patient + ' - ' + loc + ' ' + inj + ' - ' + tool
                if full_string not in self.treatments_applied_by_pid[pid]:
                    self.treatments_applied_by_pid[pid][full_string] = 0
                self.treatments_applied_by_pid[pid][full_string] += 1

                patientless_string = loc + ' ' + inj + ' - ' + tool
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


    def generate_treatment_csv(self):
        '''
        Call after all update_logger_from_json calls are complete.
        Generates a csv that organizes the treatment data.
        '''
        f = open('treatments_per_patient.csv', 'w', encoding='utf-8')
        writer = csv.writer(f)
        header = []
        for patient in self.num_pids_who_applied_per_patient:
            for treatment in self.num_pids_who_applied_per_patient[patient]:
                clean_treatment = treatment.replace('Full Body', '').replace('  - ', '').replace('  ', ' ').replace(' None', '').replace('Nostril - ', '').strip()
                total_applied_treatments = '# ' + clean_treatment + ' applied'
                if total_applied_treatments not in header:
                    header.append(total_applied_treatments)
        header.sort()
        header = [item for pair in zip(header, ['# participants']*len(header)) for item in pair]

        header.insert(0, 'PatientID')
        writer.writerow(header)
        for patient in self.num_pids_who_applied_per_patient:
            row = [patient]
            for _ in range(len(header)-1):
                row.append(0)
            for treatment in self.num_pids_who_applied_per_patient[patient]:
                clean_treatment = treatment.replace('Full Body', '').replace('  - ', '').replace('  ', ' ').replace(' None', '').replace('Nostril - ', '').strip()
                total_applied_treatments = '# ' + clean_treatment + ' applied'
                # record total treatments applied
                row[header.index(total_applied_treatments)] = row[header.index(total_applied_treatments)] + self.treatments_applied_per_patient[patient][treatment]
                # record # participants who applied this treatment
                row[header.index(total_applied_treatments)+1] = row[header.index(total_applied_treatments)+1] + self.num_pids_who_applied_per_patient[patient][treatment]
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

    treatment_logger.generate_treatment_csv()