import os, csv, copy, argparse, json

class SimAnalyzer:
    def __init__(self, output_dir):
        '''
        Initialize the new16 analyzer
        '''
        try:
            os.mkdir(output_dir)
        except:
            pass
        self.output_dir = output_dir
        self.by_file_data = {}
        self.tagging_data = {}
        self.tagging_accuracy_over_time = {}
        self.salt_errors = {}
        self.missed_hemorrhage = {}
        self.correct_triage = {}
        self.req_hemorrhage = []
        self.salt_order = {'still': [], 'wave': [], 'walk': []}
        self.all_req_procedures = {}
        self.json_data = None
        self.header = None


    def initialize_participant(self, pid):
        '''
        Add initialization data to the data object for a given csv id
        '''
        self.by_file_data[pid] = {'triage_time': 0, 'correct_tags': {'total': 0, 'correct': 0, 'over': 0, 'under': 0, 'critical': 0}, 'total_hc_time': 0, 'salt': False, 'salt_errors': 0, 'missed_hemorrhage_control': 0, 'errors_made': 0, 'patient_hc_time': {}, 'patient_order': [], 'tag_colors': {}}


    def listify_data(self, file_loc):
        '''
        Pulls out the data from the full csv into a usable list
        '''
        f = open(file_loc, 'r')
        reader = csv.reader(f)
        data = []
        next(reader) # Skip header
        for line in reader:
            if line[0][0] == '#':
                continue # skip "comments"
            if line[0] == 'Participant ID':
                pid = line[1]
                print("Participant ", pid)
                continue
            data.append(line)
        f.close()
        return data
    
    def load_scenario_data(self, file_loc):
        f = open(file_loc, 'r')
        reader = csv.reader(f)
        self.header = next(reader)
        header = self.header
        for row in reader:
            if row[0][0] == '#':
                continue
            if row[0] == 'PATIENT_RECORD':
                pid = row[header.index('PatientID')]
                level = row[header.index('PatientTriageLevel')].lower()
                sort = row[header.index('PatientTriageSort')]
                if pid not in self.correct_triage:
                    self.correct_triage[pid] = level
                if sort in self.salt_order and pid not in self.salt_order[sort]:
                    self.salt_order[sort].append(pid)
            elif row[0] == 'INJURY_RECORD':
                proc = row[header.index('InjuryRequiredProcedure')]
                if proc in ['tourniquet', 'woundpack']:
                    entry = [row[header.index('PatientID')], proc, row[header.index('InjuryName')]]
                    if entry not in self.req_hemorrhage:
                        self.req_hemorrhage.append(entry)
                inj = row[header.index('InjuryName')]
                pid = row[header.index('PatientID')]
                if proc and proc != 'none':
                    if pid not in self.all_req_procedures:
                        self.all_req_procedures[pid] = []
                    if inj not in self.all_req_procedures[pid]:
                        self.all_req_procedures[pid].append(inj)

        f.close()
        print('correct_triage:', self.correct_triage)
        print('req_hemorrhage:', self.req_hemorrhage)
        print('salt_order:', self.salt_order)

    def load_json_data(self, file_loc):
        with open(file_loc, 'r', encoding='utf-8') as f:
            self.json_data = json.load(f)

    def analyze_tccc(self, filename, data):
        header = self.header

        # --- patients engaged ---
        engagement_order = []
        treated = []
        for x in data:
            if x[0] in ['TOOL_APPLIED', 'TAG_APPLIED', 'SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']:
                p = x[header.index('PatientID')].split(' Root')[0]
                engagement_order.append(p)
                if x[0] == 'TOOL_APPLIED':
                    treated.append(p)
        simple_order = []
        for x in engagement_order:
            if len(simple_order) == 0 or x != simple_order[-1]:
                simple_order.append(x)
        patients_engaged = len(set(engagement_order))
        patients_treated = len(set(treated))
        engagement_times = list({item: simple_order.count(item) for item in set(simple_order)}.values())
        engage_patient = sum(engagement_times) / max(1, len(engagement_times))

        # --- assessments ---
        assessment_actions = ['SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']
        assess_count = 0
        last_done = {}
        assess_per_patient = {}
        for x in data:
            if x[0] in assessment_actions:
                t = float(x[header.index('ElapsedTime')])
                if x[0] not in last_done or (t - last_done[x[0]]) > 5000:
                    last_done[x[0]] = t
                    assess_count += 1
                    p = x[header.index('PatientID')].split(' Root')[0]
                    assess_per_patient[p] = assess_per_patient.get(p, 0) + 1

        # --- treatments ---
        treat_count = 0
        treat_per_patient = {}
        for x in data:
            if x[0] == 'TOOL_APPLIED' and 'Pulse Oximeter' not in x:
                treat_count += 1
                p = x[header.index('PatientID')].split(' Root')[0]
                treat_per_patient[p] = treat_per_patient.get(p, 0) + 1

        # --- triage performance ---
        supplemental_tools = ['IV Blood', 'Antibiotics', 'Blanket', 'Fentanyl Lollipop', 'Nasal Airway']
        to_complete = copy.deepcopy(self.all_req_procedures)
        supplemental_points = {}
        total_tools = 0
        correct_tools = 0
        for x in data:
            if x[0] == 'INJURY_TREATED':
                p = x[header.index('PatientID')]
                inj = x[header.index('InjuryName')]
                completed = str(x[header.index('InjuryTreatmentComplete')]).strip().lower() in ('true', '1', 'yes', 'y', 't')
                if completed and p in to_complete and inj in to_complete[p]:
                    to_complete[p].remove(inj)
                    correct_tools += 1
                    if len(to_complete[p]) == 0:
                        del to_complete[p]
            if x[0] == 'TOOL_APPLIED':
                total_tools += 1
                p = x[header.index('PatientID')]
                tool = x[header.index('ToolType')]
                if tool in supplemental_tools:
                    supplemental_points[p] = supplemental_points.get(p, 0) + 1
        misses = sum(len(v) for v in to_complete.values())
        for p in supplemental_points:
            if p not in to_complete:
                correct_tools += supplemental_points[p]
        triage_performance = (correct_tools / max(1, total_tools + misses)) * 100

        # --- tag expectant ---
        expectant_patients = [p for p, t in self.correct_triage.items() if t == 'expectant']
        tag_colors = self.by_file_data[filename]['tag_colors']
        tag_expectant = 'Yes' if any(tag_colors.get(p) == 'gray' for p in expectant_patients) else 'No'

        # --- evac ---
        evaced = []
        if self.json_data:
            for action in self.json_data['actionList']:
                if action.get('actionType') == 'Question' and 'evacuate' in action.get('question', '').lower():
                    evaced.append(action['casualty'])

        # --- per-patient data ---
        patient_list = sorted(self.correct_triage.keys())
        clean_order = []
        for x in simple_order:
            if x not in clean_order:
                clean_order.append(x)
        patient_interactions = self.by_file_data[filename].get('patient_interactions', {})
        per_patient = {}
        for i, sim_name in enumerate(patient_list):
            p_data = patient_interactions.get(sim_name)
            per_patient[sim_name] = {
                'time': p_data['total_time'] if p_data else '-',
                'order': clean_order.index(sim_name) + 1 if sim_name in clean_order else 'N/A',
                'evac': 'Yes' if sim_name in evaced else 'No',
                'assess': assess_per_patient.get(sim_name, 0),
                'treat': treat_per_patient.get(sim_name, 0),
                'tag': tag_colors.get(sim_name, 'None')
            }

        self.by_file_data[filename]['tccc_metrics'] = {
            'TCCC Triage Performance': triage_performance,
            'TCCC Assess_total': assess_count,
            'TCCC Assess_patient': assess_count / max(1, patients_engaged),
            'TCCC Treat_total': treat_count,
            'TCCC Treat_patient': treat_count / max(1, patients_treated),
            'TCCC Triage_time': self.by_file_data[filename]['triage_time'],
            'TCCC Triage_time_patient': self.by_file_data[filename]['triage_time'] / max(1, patients_engaged),
            'TCCC Engage_patient': engage_patient,
            'TCCC Tag_ACC': self.by_file_data[filename]['correct_tags']['correct'] / max(1, self.by_file_data[filename]['correct_tags']['total']),
            'TCCC Tag_Expectant': tag_expectant,
            'TCCC Hemorrhage control': 1 if self.by_file_data[filename]['total_hc_time'] not in [0, '-'] else 0,
            'TCCC Hemorrhage control_time': self.by_file_data[filename]['total_hc_time'] if self.by_file_data[filename]['total_hc_time'] not in [0, '-'] else None,
            'per_patient': per_patient
        }



    def get_triage_time(self, filename, data):
        '''
        Calculates the total scene triage time from SESSION_START to the final action
        '''
        if len(data) > 0:
            for line in data:
                if 'SESSION_START' in line:
                    start = float(line[1])
                    break
            # SESSION_END will be last, we want the action right before that
            end = float(data[len(data)-2][1])
            self.by_file_data[filename]['triage_time'] = ((end-start))/1000
   

    def find_tag_colors(self, filename, data):
        '''
        Find the tags given to each patient
        '''
        tags = {}
        # by default gets the last tag applied to each patient
        for x in data:
            if x[0] == 'TAG_APPLIED':
                tags[x[22]] = x[36]
        self.by_file_data[filename]['tag_colors'] = tags


    def get_tag_accuracy(self, filename, data):
        '''
        Looks through all tagging data to find accuracy of tags given
        to each patient by each participant
        '''
        tags = self.correct_triage
        translations = {
            'immediate': 'red',
            'delayed': 'yellow',
            'expectant': 'gray',
            'minimal': 'green',
            'dead': 'black'
        }
        # by default gets the last tag applied to each patient
        tags_applied = {}
        order_tagged = []
        for x in data:
            if x[0] == 'TAG_APPLIED':
                p_name = x[22]
                tags_applied[p_name] = x[36]
                if p_name in order_tagged:
                    order_tagged.remove(p_name)
                order_tagged.append(p_name)
        correct = 0
        count = 0
        under_triage = 0 # placed in lower priority
        over_triage = 0 # placed in higher priority
        critical_triage = 0 # placed into dead or expectant incorrectly
        print(f"tags_applied: {tags_applied}")
        for x in tags_applied:
            if x not in self.tagging_data:
                self.tagging_data[x] = {'correct': translations[tags[x]], 'red': 0, 'yellow': 0, 'gray': 0, 'green': 0, 'black': 0, 'kim_yellow': 0}
            # required for new metro chaotic format
            if tags_applied[x] == 'yellow_orange':
                tags_applied[x] = 'yellow'
            if tags_applied[x] == 'green_blue':
                tags_applied[x] = 'green'
            self.tagging_data[x][tags_applied[x]] += 1
            if translations[tags[x]] == tags_applied[x]:
                correct += 1
            else: 
                truth = translations[tags[x]]
                guess = tags_applied[x]
                if truth == 'black':
                    over_triage += 1
                elif guess == 'black':
                    critical_triage += 1                    
                elif truth == 'gray':
                    over_triage += 1
                elif guess == 'gray':
                    critical_triage += 1
                elif truth == 'red':
                    under_triage += 1
                elif guess == 'red':
                    over_triage += 1
                elif truth == 'yellow':
                    under_triage += 1
                elif guess == 'yellow':
                    over_triage += 1
            count += 1
        
        
        ordered_correct = [] # 0, 1 for incorrect or correct in the order tagged (1st patient, 2nd patient, 3rd, etc)
        for x in order_tagged:
            if translations[tags[x]] == tags_applied[x]:
                ordered_correct.append(1)
            else:
                ordered_correct.append(0)
        self.tagging_accuracy_over_time[filename] = ordered_correct

        self.by_file_data[filename]['correct_tags'] = {'correct': correct, 'total': count, 'over': over_triage, 'under': under_triage, 'critical': critical_triage}


    def find_time_per_patient(self, filename, data):
        '''
        Looks through each participant's interaction with each patient
        to see how much time the engagement took
        '''
        interactions = {}
        cur_p = None
        start_time = 0
        last_time = 0
        order_visited = []
        for x in data:
            # find every interaction with the patient
            p = None
            t = float(x[1])
            
            if x[0] in ['TOOL_APPLIED', 'TAG_APPLIED', 'SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN', 'PATIENT_ENGAGED']:
                p = x[22]
            if p is None or 'Level Core' in p or 'Simulation' in p or 'Player' in p:
                continue
            if p not in interactions:
                interactions[p] = []
            # initialize cur_p
            if cur_p is None:
                cur_p = p
                start_time = t
            # new patient interaction!
            if cur_p != p:
                # save start/end interaction times for previous patient
                if start_time != last_time:
                    interactions[cur_p].append((start_time, last_time))
                    order_visited.append(cur_p)
                # set start time for new patient
                start_time = t
                last_time = t
                cur_p = p
            else:
                last_time = t
        # save the last interaction set!
        interactions[cur_p].append((start_time, last_time))
        order_visited.append(cur_p)
        interaction_data = {}
        for p in interactions:
            times_visited = 0
            inds = []
            for i in range(len(order_visited)):
                v = order_visited[i]
                if v == p:
                    if len(inds) == 0 or inds[-1] != i-1:
                        times_visited += 1
                    inds.append(i)
            total_time = 0
            for x in interactions[p]:
                total_time += x[1] - x[0]
            interaction_data[p] = {
                "total_time": total_time/1000,
                "indices_visited": inds,
                "times_visited": times_visited,
                "all_data": interactions[p]
            }

        self.by_file_data[filename]['patient_interactions'] = interaction_data


    def find_hemorrhage_control(self, filename, data):
        '''
        Duration of time from the scene start time until the time that the last patient
        who requires life-threatening bleeding has been treated with hemorrhage control
        '''
        start = 0
        times_controlled = {}
        required_procedures = copy.deepcopy(self.req_hemorrhage)
        for x in data:
            if 'SESSION_START' not in x and start == 0:
                continue
            if start == 0:
                start = float(x[1])
            if x[0] == 'INJURY_TREATED':
                found = None
                for req in required_procedures:
                    if req[0] == x[22] and req[1] == x[12] and req[2] == x[10]:
                        found = req
                        p_name = req[0]
                        if p_name in times_controlled:
                            times_controlled[p_name].append({'procedure': req, 'time': x[1]})
                        else:
                            times_controlled[p_name] = [{'procedure': req, 'time': x[1]}]
                        break
                if found is not None:
                    required_procedures.remove(req)
                if len(required_procedures) == 0:
                    self.by_file_data[filename]['total_hc_time'] = (float(x[1]) - start) / 1000
                    self.get_per_patient_hc_time(filename, times_controlled)
                    return
        for proc in required_procedures:
            s = proc[0] + ' ' + proc[2]
            if s not in self.missed_hemorrhage:
                self.missed_hemorrhage[s] = 0
            self.missed_hemorrhage[s] += 1
        self.get_per_patient_hc_time(filename, times_controlled)
        self.by_file_data[filename]['total_hc_time'] = '-'
        self.by_file_data[filename]['missed_hemorrhage_control'] = len(required_procedures)

    
    def count_total_mistakes(self, filename, data):
        '''
        Counts the total number of mistakes (wrong tag, wrong treatment, missed treatment, salt errors) for each participant
        '''
        tagging_error_count = (self.by_file_data[filename]['correct_tags']['total'] - self.by_file_data[filename]['correct_tags']['correct'])
        salt_error_count = self.by_file_data[filename]['salt_errors']
        hemorrhage_missed_count = self.by_file_data[filename]['missed_hemorrhage_control']
        correct = 0
        count = 0
        header = self.header
        for x in data:
            if x[0] == 'INJURY_TREATED':
                # TODO: This needs more work/updating with current injuries/treatments
                inj = x[header.index('InjuryName')]
                if inj == 'Unspecified' or inj == '':
                    continue
                p = x[header.index('PatientID')]
                completed = str(x[header.index('InjuryTreatmentComplete')]).strip().lower() in ('true', '1', 'yes', 'y', 't')
                if p in self.all_req_procedures and inj in self.all_req_procedures[p] and completed:
                    correct += 1
                count += 1
        treatment_errors = count - correct
        total_errors = tagging_error_count + salt_error_count + hemorrhage_missed_count + treatment_errors
        self.by_file_data[filename]['errors_made'] = total_errors
        

    def get_per_patient_hc_time(self, filename, data):
        '''
        Run only after find_time_per_patient and find_hemorrhage_control have been run.
        Finds the time per each patient for hemorrhage control
        '''
        control_times = {}
        for patient in data:
            for controlled in data[patient]:
                interaction_times = self.by_file_data[filename]['patient_interactions'][patient]['all_data']
                last_t2 = 0
                last_t1 = 0
                # only count the time from the start of this visit with the patient - not from their first interaction!
                for (t1, t2) in interaction_times:
                    if t1 == last_t2:
                        # make sure if there are any mistakes in patient_interaction times we account for that
                        t1 = last_t1
                    tx = float(controlled['time'])
                    last_t1 = t1
                    last_t2 = t2
                    # if the time is in this visit-segment, calculate the time taken to control hemorrhage!
                    if tx >= t1 and tx <= t2:
                        time_to_control = (tx - t1) / 1000
                        if patient not in control_times:
                            control_times[patient] = []
                        control_times[patient].append({'procedure': controlled['procedure'], 'time': time_to_control})
                        break
        self.by_file_data[filename]['patient_hc_time'] = control_times


    def check_salt_adherance(self, filename, data):
        '''
        Add parameter to participant data noting if they evaluated patients by:
        still, able to wave, able to walk
        '''
        # original list from Nick June/July 2024
        # still = ['Helga_13', 'Gary_3', 'Lily_2', 'Bob_0', 'Gary_1', 'Mike_5', 'Lily_4', 'Mike_11', 'Mike_7']
        # wave = ['Gloria_6']
        # walk = ['Gary_12', 'Gary_9', 'Gloria_8', 'Helga_10']

        # updated list 3/19/25
        still = copy.deepcopy(self.salt_order['still'])
        wave = copy.deepcopy(self.salt_order['wave'])
        walk = copy.deepcopy(self.salt_order['walk'])


        # This is what is in the configuration file (and still makes the most sense to me...and gives better accuracy...but whatever)
        # still = ['Helga_13', 'Gary_3', 'Bob_0', 'Gary_1']
        # wave = ['Gloria_6', 'Mike_7', 'Lily_2', 'Lily_4', 'Mike_5', 'Mike_11']
        # walk = ['Gary_9', 'Gloria_8', 'Helga_10', 'Gary_12']
        followed_rules = True
        captured = []
        errors = 0
        for x in data:
            p = None
            if x[0] in ['TOOL_APPLIED', 'TAG_APPLIED', 'SP_O2_TAKEN', 'BREATHING_CHECKED', 'PULSE_TAKEN']:
                p = x[22]
            if p is None or p in captured:
                continue
            # if they interacted with a waver or walker before all still were visited, mistake!
            if len(still) > 0 and p not in still:
                if p not in self.salt_errors:
                    self.salt_errors[p] = 0
                self.salt_errors[p] += 1
                followed_rules = False
                errors += 1
                if p in wave:
                    wave.remove(p)
                if p in walk:
                    walk.remove(p)
                captured.append(p)
                continue
            # interacted with still before all still were visited - yay!
            elif len(still) > 0 and p in still:
                still.remove(p)
                captured.append(p)
                continue
            # interacted with a walker before all wavers were visited - mistake!
            if len(wave) > 0 and p not in wave:
                if p not in self.salt_errors:
                    self.salt_errors[p] = 0
                self.salt_errors[p] += 1
                followed_rules = False
                errors += 1
                if p in still:
                    still.remove(p)
                if p in walk:
                    walk.remove(p)
                captured.append(p)
                continue
            # interacted with waver correctly - yay!
            elif len(wave) > 0 and p in wave:
                wave.remove(p)
                captured.append(p)
                continue
            # interacted with a walker correctly - yay!
            if len(walk) > 0 and p in walk:
                walk.remove(p)
                captured.append(p)
                continue
            elif len(walk) == 0:
                break
        self.by_file_data[filename]['salt'] = followed_rules
        self.by_file_data[filename]['salt_errors'] = errors


    def analyze_file(self, filename, data):
        '''
        Add relevant counts and metrics to the data object
        '''
        self.check_salt_adherance(filename, data)
        self.find_time_per_patient(filename, data)
        self.get_triage_time(filename, data)
        self.get_tag_accuracy(filename, data)
        self.find_hemorrhage_control(filename, data)
        self.count_total_mistakes(filename, data)
        self.find_tag_colors(filename, data)
        self.analyze_tccc(filename, data)


    
    def generate_csv(self):
        '''
        Puts all the data collected from analyze_file into a csv
        '''
        f = open(f'{self.output_dir}/analyzed.csv', 'w')
        writer = csv.writer(f)
        patient_list = sorted(self.correct_triage.keys())
        header = ['File Name', 'PID', 'Time to Triage Scene (s)', 'Tags Applied', 'Triage Tag Accuracy', 'Over-Triage Errors', 'Under-Triage Errors', 'Critical Triage Errors', 'Total Hemorrhage Control Time (s)', 'Followed SALT', 'SALT Errors', 'Total Errors']
        header += ['TCCC Triage Performance', 'TCCC Assess_total', 'TCCC Assess_patient', 'TCCC Treat_total', 'TCCC Treat_patient', 'TCCC Triage_time', 'TCCC Triage_time_patient', 'TCCC Engage_patient', 'TCCC Tag_ACC', 'TCCC Tag_Expectant', 'TCCC Hemorrhage control', 'TCCC Hemorrhage control_time']
        for p in patient_list:
            header += [f'{p} Time', f'{p} Order', f'{p} Evac', f'{p} Assess', f'{p} Treat', f'{p} Tag']
        writer.writerow(header)
        participant_count = 0
        time_sum = 0
        tag_sum = 0
        over_sum = 0
        under_sum = 0
        critical_sum = 0
        full_hc_time_sum = 0
        hc_finished = 0
        salt_followers = 0
        salt_error_sum = 0
        total_error_sum = 0
        for filename in self.by_file_data:
            x = self.by_file_data[filename]
            correct_tag_perc = self.round_to(x['correct_tags']['correct']/max(1, x['correct_tags']['total']), 4)
            over_tag_perc = self.round_to(x['correct_tags']['over']/max(1, x['correct_tags']['total']), 4)
            under_tag_perc = self.round_to(x['correct_tags']['under']/max(1, x['correct_tags']['total']), 4)
            critical_tag_perc = self.round_to(x['correct_tags']['critical']/max(1, x['correct_tags']['total']), 4)

            # add up sums so we can get quick averages at the end
            participant_count += 1
            time_sum += x['triage_time']
            tag_sum += correct_tag_perc
            over_sum += over_tag_perc
            under_sum += under_tag_perc
            critical_sum += critical_tag_perc
            full_hc_time_sum += float(x['total_hc_time'] if x['total_hc_time'] != '-' else 0)
            if x['total_hc_time'] not in [0, '-']:
                hc_finished += 1
            if x['salt']:
                salt_followers += 1
            salt_error_sum += x['salt_errors']
            total_error_sum += x['errors_made']

            m = x.get('tccc_metrics', {})
            pp = m.get('per_patient', {})
            row = [filename, filename.split('_')[1] if '_' in filename else filename.split('-')[-1], x['triage_time'],
                x['correct_tags']['total'], correct_tag_perc, over_tag_perc, under_tag_perc, critical_tag_perc,
                x['total_hc_time'], x['salt'], x['salt_errors'], x['errors_made'],
                m.get('TCCC Triage Performance', ''), m.get('TCCC Assess_total', ''), m.get('TCCC Assess_patient', ''),
                m.get('TCCC Treat_total', ''), m.get('TCCC Treat_patient', ''), m.get('TCCC Triage_time', ''),
                m.get('TCCC Triage_time_patient', ''), m.get('TCCC Engage_patient', ''), m.get('TCCC Tag_ACC', ''),
                m.get('TCCC Tag_Expectant', ''), m.get('TCCC Hemorrhage control', ''), m.get('TCCC Hemorrhage control_time', '')]

            for p in patient_list:
                pd = pp.get(p, {})
                row += [pd.get('time', ''), pd.get('order', ''), pd.get('evac', ''),
                        pd.get('assess', ''), pd.get('treat', ''), pd.get('tag', '')]
            writer.writerow(row)

        hc_average = self.round_to(full_hc_time_sum/hc_finished, 4) if hc_finished > 0 else 'N/A'
        writer.writerow(['Average', '--', self.round_to(time_sum/participant_count, 3), '--', self.round_to(tag_sum/participant_count, 4), self.round_to(over_sum/participant_count, 4),
                         self.round_to(under_sum/participant_count, 4), self.round_to(critical_sum/participant_count, 4), hc_average, salt_followers,
                         self.round_to(salt_error_sum/participant_count, 4), self.round_to(total_error_sum/participant_count, 4)])
        f.close()


    def get_all_tagging_data(self):
        '''
        Creates a new csv with the counts of how many of each tag color were assigned to each patient, along
        with the overall accuracy of tags per patient
        '''
        f = open(f'{self.output_dir}/tag_distribution.csv', 'w')
        writer = csv.writer(f)
        header = ['Patient', 'Correct Tag Color', 'Percent Correct', '# Red', '# Yellow', '# Green', '# Gray', '# Black']
        writer.writerow(header)
        for p in self.tagging_data:
            data = self.tagging_data[p]
            total_tags = data['red'] + data['yellow'] + data['green'] + data['gray'] + data['black']
            correct_tags = data[data['correct']] + data['kim_yellow']
            writer.writerow([p, data['correct'], self.round_to(correct_tags/max(1,total_tags), 4), data['red'], data['yellow'], data['green'], data['gray'], data['black']])
        f.close()
         

    def calculate_tagging_accuracy_over_time(self):
        '''
        Creates a new csv that shows which index of patients each participant tagged correctly (1st, 2nd, 3rd, etc).
        The goal was to see if tagging got more/less accurate over time.
        '''
        f = open(f'{self.output_dir}/ordered_tagging.csv', 'w')
        writer = csv.writer(f)
        header = ['Participant', '1st Patient', '2nd Patient', '3rd Patient', '4th Patient', '5th Patient', '6th Patient', '7th Patient', '8th Patient', '9th Patient', '10th Patient', '11th Patient', '12th Patient', '13th Patient', '14th Patient', '15th Patient', '16th Patient']
        writer.writerow(header)
        sums = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        totals = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        for participant in self.tagging_accuracy_over_time:
            tags = self.tagging_accuracy_over_time[participant]
            writer.writerow([participant] + tags)
            for i in range(len(tags)):
                totals[i] += 1
                sums[i] += tags[i]
        avgs = []
        for i in range (len(sums)):
            avgs.append(self.round_to(sums[i] / max(1, totals[i]), 4))
        writer.writerow(['Average'] + avgs)
        f.close()


    def round_to(self, x, decimals):
        '''
        Rounds x to a number of decimals determined by the parameter
        '''
        if type(x) == type('str'):
            return x
        return round(x * (10**decimals)) / (10 ** decimals)


    def record_interaction_times(self):
        '''
        Records the interaction times per patient and per participant
        '''
        f = open(f'{self.output_dir}/interaction_time.csv', 'w')
        writer = csv.writer(f)
        # prepare header with each patient time and visit #
        patient_list = sorted(list(self.correct_triage.keys()))
        header = ['PID']
        for x in patient_list:
            header += [x + ' Time (s)', x + ' Visits']
        header += ['Average Time (s)']
        writer.writerow(header)
        avg_times = {}
        avg_visits = {}
        ordered = [[] for _ in range(len(patient_list))] # store average time in order of interactions
        for x in self.by_file_data:
            to_write = [x] + (['-'] * len(patient_list) * 2)
            p_avg = []
            interactions = self.by_file_data[x]['patient_interactions']
            i = 0
            for p in interactions:
                if p not in patient_list:
                    print(f"Skipping patient `{p}` because not in the list.")
                    continue
                if p not in avg_times:
                    avg_times[p] = []
                    avg_visits[p] = []
                # record numbers as part of averages
                avg_times[p].append(interactions[p]['total_time'])
                avg_visits[p].append(interactions[p]['times_visited'])
                # record individual times
                to_write[header.index(p + ' Time (s)')] = interactions[p]['total_time']
                to_write[header.index(p + ' Visits')] = interactions[p]['times_visited']
                # prepare to calculate per-participant average
                p_avg.append(interactions[p]['total_time'])
                ordered[i].append(interactions[p]['total_time'])
                i += 1
            to_write.append(self.round_to(sum(p_avg) / len(p_avg), 3))
            writer.writerow(to_write)
        for i in range(len(ordered)):
            if len(ordered[i]) > 0:
                ordered[i] = self.round_to(sum(ordered[i]) / len(ordered[i]), 3)
            else:
                ordered[i] = 0

        # calculate averages to export to last line of csv
        all_avgs = []
        for x in avg_times:
            avg_times[x] = self.round_to(sum(avg_times[x]) / len(avg_times[x]), 3)
            all_avgs.append(avg_times[x])
            avg_visits[x] = self.round_to(sum(avg_visits[x]) / len(avg_visits[x]), 3)
        # make sure all data is in the correct order to correlate with the header
        ordered = []
        for x in sorted(list(self.tagging_data.keys())):
            ordered.append(avg_times[x])
            ordered.append(avg_visits[x])
        ordered.append(self.round_to(sum(all_avgs) / len(all_avgs), 3))
        writer.writerow(["Averages"]  + ordered)
        f.close()
                

    def record_hc_times(self):
        '''
        Creates a csv of hemorrhage control times per patient
        '''
        f = open(f'{self.output_dir}/patient_hc_times.csv', 'w')
        writer = csv.writer(f)
        header = ['PID']
        for req in self.req_hemorrhage:
            p_name = req[0]
            if p_name not in header:
                header.append(p_name)
        header += ['Average']
        writer.writerow(header)
        avg_times = {}
        for patient in header[1:len(header)-1]:
            avg_times[patient] = []
        for pid in self.by_file_data:
            to_write = [pid]
            hc_patient_times = self.by_file_data[pid]['patient_hc_time']
            pid_avg = []
            for patient in header[1:len(header)-1]:
                data = hc_patient_times.get(patient, [{'time': '-'}])
                if len(data) == 1:
                    t = data[0]['time']
                    to_write.append(self.round_to(t, 3))
                    if t != '-':
                        avg_times[patient].append(t)
                        pid_avg.append(t)
                else:
                    # get highest time for this patient. This means they had more than one injury to treat
                    # we only want to count when all hemorrhaging injuries have been treated
                    cur_max = 0
                    for x in data:
                        if x['time'] > cur_max:
                            cur_max = x['time']
                    if cur_max > 0:
                        to_write.append(self.round_to(cur_max, 3))
                        avg_times[patient].append(cur_max)
                        pid_avg.append(cur_max)
            to_write.append(self.round_to(sum(pid_avg)/max(1, len(pid_avg)), 3))
            writer.writerow(to_write)
        to_write = ['Average']
        full_avg = []
        for patient in header[1:len(header)-1]:
            if len(avg_times[patient]) > 0:
                a = sum(avg_times[patient])/len(avg_times[patient])
                to_write.append(self.round_to(a, 3))
                full_avg.append(a)
            else:
                to_write.append('N/A')
        to_write.append(self.round_to(sum(full_avg)/max(1, len(full_avg)), 3))
        writer.writerow(to_write)
        f.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='New 16 Analyzer', usage='new_16_analysis.py [-h] [-i INPUT_DIR] [-o OUTPUT_DIR]')

    parser.add_argument('-i', '--input_directory', dest='input_directory', default='input_tccc', type=str, help='The path to the directory that holds all input files. Default input16.')
    parser.add_argument('-o', '--output_directory', dest='output_directory', default='output_tccc', type=str, help='The requested path to the new directory that will hold output csv files. Default output16.')
    args = parser.parse_args()

    analyzer = SimAnalyzer(args.output_directory)
    
    # any file names that have been deemed invalid for whatever reason. This is from the original New16 dataset
    SKIP_FILES = []

    # search through the input directory for every csv file
    scenario_loaded = False
    for dir in os.listdir(args.input_directory):
        if dir != '.DS_Store':
            parent = os.path.join(args.input_directory, dir)
            for file in os.listdir(parent):
                if '.csv' in file:
                    to_analyze = os.path.join(parent, file)
                    if not scenario_loaded:
                        analyzer.load_scenario_data(to_analyze)
                        scenario_loaded = True
                    filename = file.split('.csv')[0]
                    filename = filename.split('Clean')[0]
                    if '_' in filename:
                        filename = filename.split('_')[1]
                    if filename not in SKIP_FILES:
                        analyzer.initialize_participant(filename)
                        data = analyzer.listify_data(to_analyze)
                        json_path = to_analyze.replace('.csv', '.json')
                        if os.path.exists(json_path):
                            analyzer.load_json_data(json_path)
                        else:
                            analyzer.json_data = None
                        analyzer.analyze_file(filename, data)
                    else:
                        pass
    analyzer.generate_csv()
    analyzer.get_all_tagging_data()
    analyzer.calculate_tagging_accuracy_over_time()
    analyzer.record_interaction_times()
    analyzer.record_hc_times()
