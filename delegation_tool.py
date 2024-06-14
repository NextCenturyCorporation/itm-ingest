
from pymongo import MongoClient
from decouple import config 
import json, time, copy
from logger import LogLevel, Logger

'''
The delegation survey python tool adds the delegation survey questions to the database 
and can modify, add, order, and delete questions from the survey config.
'''
LOGGER = Logger('Delegation Tool')


class SurveyElement:
    def __init__(self, minimum=None, visible_if=None, input_type=None, question_choices=None,
                 decision_makers=None, actions=None, is_required=None, show_other=None,
                 el_title=None, patients=None, el_type=None, show_none_item=None, explanation=None,
                 none_text=None, other_text=None, el_name=None, situation=None, visible=None,
                 dm_name=None, supplies=None, html=None):
        self.element_data = {
            'min': minimum, 
            'visibleIf': visible_if, 
            'inputType': input_type, 
            'choices': question_choices, 
            'decisionMakers': decision_makers, 
            'actions': actions, 
            'isRequired': is_required, 
            'showOtherItem': show_other, 
            'title': el_title, 
            'patients': patients, 
            'type': el_type, 
            'showNoneItem': show_none_item, 
            'explanation': explanation, 
            'noneText': none_text,
            'otherText': other_text,
            'name': el_name, 
            'situation': situation, 
            'visible': visible, 
            'dmName': dm_name, 
            'supplies': supplies, 
            'html': html
        }

        
    def get_clean_element(self):
        '''
        Converts a survey element object to the correct json format for the survey config
        '''
        # only add what is necessary/what is given
        el = copy.deepcopy(self.element_data)
        for x in self.element_data:
            if self.element_data[x] is None:
                del el[x]
        return el


class DelegationTool:
    survey = {}
    survey_id = None
    survey_mongo_collection = None
    image_mongo_collection = None
    changes_summary = []
    cur_import_file = ''

    def __init__(self, version):
        # get the current survey data
        client = MongoClient(config('MONGO_URL'))
        db = client.dashboard

        # create new collection for survey, or simply get the existing collection
        self.survey_mongo_collection = db['delegationConfig']
        obj_id = 'delegation_v'+str(version)
        self.survey_id = obj_id

        # create new collection for sim screenshots, or simply get the existing collection
        self.image_mongo_collection = db['screenshotImages']

        # search for version in database
        self.survey = self.survey_mongo_collection.find({'_id': obj_id})
        found_version = False
        for document in self.survey:
            found_version = True
            self.survey = document
            break

        # version does not exist in database, add the initial outline with the correct version number
        if not found_version:
            self.changes_summary.append(f"Added new survey version '{version}' to database")
            self.initialize_survey(version, True)
            self.survey_mongo_collection.insert_one({'_id': obj_id, 'survey': self.survey})
        
        if 'survey' in self.survey:
            self.survey = self.survey['survey']


    def add_page(self, page_name, scenario_name='', page_type='', scenario_index=None, index=None):
        '''
        Adds a new page to the survey
        '''
        # check for existing page with name before adding
        if not self.handle_existing_page(page_name):
            return
        page = {"name": page_name, "elements": []}
        if scenario_name != '':
            page['scenarioName'] = scenario_name
        if page_type != '':
            page['pageType'] = page_type
        if scenario_index is not None:
            page['scenarioIndex'] = scenario_index
        if index is None:
            self.survey['pages'].append(page)
        else:
            self.survey['pages'].insert(index, page)
        self.changes_summary.append(f"Added new page '{page_name}' to database at index {index}")
        LOGGER.log(LogLevel.INFO, f"Successfully added new page with name '{page_name}'")

    
    def delete_page(self, page_name, update=False):
        '''
        Deletes the first page with the given name from the survey
        '''
        page = self.get_page_by_name(page_name)
        if not update:
            LOGGER.log(LogLevel.WARN, f"Are you sure you want to delete page '{page_name}'? (y/n)")
            resp = input("")
        else:
            resp = 'y'
        if resp.strip() in ['y', 'Y']:
            try:
                self.survey['pages'].remove(page)
                if not update:
                    self.changes_summary.append(f"Deleted page '{page_name}'.")
                return
            except:
                LOGGER.log(LogLevel.WARN, f"Page '{page_name}' was not found. Could not {'delete' if not update else 'update'}.")
        else:
            LOGGER.log(LogLevel.INFO, f"Not deleting page '{page_name}'")


    def add_element(self, page_name, survey_el, index=None):
        '''
        Adds a survey element to a page in the survey at the specified index
        '''
        el = survey_el.get_clean_element()
        page = self.get_page_by_name(page_name)
        # check for existing element in page with data before adding
        for page_el in page['elements']:
            if 'name' in page_el and page_el['name'] == el['name']:
                LOGGER.log(LogLevel.WARN, f"Element with name '{el['name']}' already exists on page '{page_name}'. Add anyway? (y/n)")
                resp = input("")
                if resp.strip() not in ['y', 'Y']:
                    LOGGER.log(LogLevel.INFO, "Skipping element addition...")
                    return
            if 'title' in page_el and page_el['title'] == el['title']:
                LOGGER.log(LogLevel.WARN, f"Element with title '{el['title']}' already exists on page '{page_name}'. Add anyway? (y/n)")
                resp = input("")
                if resp.strip() not in ['y', 'Y']:
                    LOGGER.log(LogLevel.INFO, "Skipping element addition...")
                    return
        if index is None:
            page['elements'].append(el)
        else:
            page['elements'].insert(index, el)
        self.changes_summary.append(f"Added new element '{survey_el['title'] if 'title' in survey_el else survey_el['name']}' to page {page_name} at index {index}")


    def get_page_by_name(self, page_name):
        '''
        Returns the first page in the survey that matches page_name
        '''
        for page in self.survey['pages']:
            if page['name'] == page_name:
                return page
        return False


    def initialize_survey(self, version, is_new):
        '''
        Adds the initial survey base to the database
        '''
        if not is_new:
            overwrite = input("This will overwrite all previous delegation survey data in the database. Are you sure you want to do this? (y/n) ")
        if is_new or overwrite.strip() in ['y', 'Y']:
            self.survey = {
                "title": "ITM Delegation Survey",
                "logoPosition": "right",
                "version": version,
                "completedHtml": "<h3>Thank you for completing the survey</h3>",
                "pages": [],
                "widthMode": "responsive",
                "showTitle": False,
                "showQuestionNumbers": False,
                "showProgressBar": "top"
            }
        else:
            LOGGER.log(LogLevel.INFO, "Skipping initialization step")


    def update_version(self, new_version):
        '''
        Updates the survey version in the database
        '''
        obj_id = 'delegation_v'+str(new_version)
        found_docs = self.survey_mongo_collection.find({'_id': obj_id})
        found_version = False
        for document in found_docs:
            found_version = True
            found_docs = document
            LOGGER.log(LogLevel.WARN, f"Survey version '{new_version}' already exists in database. Cannot update.")
            return

        # version does not exist in database, add the initial outline with the correct version number
        if not found_version:
            prev = self.survey['version']
            # create a new version in the database and put the current survey in
            self.survey['version'] = new_version
            self.survey_mongo_collection.insert_one({'_id': obj_id, 'survey': self.survey})
            self.changes_summary.append(f"Created new survey version '{new_version}' from version '{prev}'")
            LOGGER.log(LogLevel.INFO, f"Created new survey version '{new_version}' from version '{prev}'")


    def push_changes(self):
        '''
        Submits changes to the database
        '''
        if len(self.changes_summary) == 0:
            LOGGER.log(LogLevel.CRITICAL_INFO, "No changes have been made.")
            return
        LOGGER.log(LogLevel.CRITICAL_INFO, "Below are the changes you've made so far:")
        # Check to make sure user wants to update; show list of changes
        for x in self.changes_summary:
            print('\t'+x)
            time.sleep(0.25)
        LOGGER.log(LogLevel.WARN, "Push all to database? (y/n) ")
        resp = input("")
        if resp.strip() in ['y', 'Y']:
            try:
                self.survey_mongo_collection.update_one({'_id': self.survey_id}, {'$set': {'_id': self.survey_id, 'survey': self.survey}})
            except:
                # strip pictures out of json
                for page in self.survey['pages']:
                    for el in page['elements']:
                        for pat in el.get('patients', []):
                            if 'imgUrl' in pat and len(pat['imgUrl']) > 100:
                                # see if imgurl is already in image database
                                res = self.image_mongo_collection.find({'url': pat['imgUrl']})
                                found = False
                                for doc in res:
                                    pat['imgUrl'] = doc['_id']
                                    found = True
                                    break
                                if not found:
                                    res = self.image_mongo_collection.insert_one({'url': pat['imgUrl']})
                                    pat['imgUrl'] = res.inserted_id

                # need to update one page at a time or else it gets too big
                for k in self.survey:
                    if k != 'pages':
                        self.survey_mongo_collection.update_one({'_id': self.survey_id}, {'$set': {f'survey.{k}': self.survey[k]}})
                for p in self.survey['pages']:
                    res = self.survey_mongo_collection.find({'_id': self.survey_id, "survey.pages": {"$elemMatch": {"name": p['name']}}})
                    doc_found = False
                    for _ in res:
                        doc_found = True
                        break
                    if doc_found:
                        res = self.survey_mongo_collection.update_one({'_id': self.survey_id}, 
                                            {'$set': {'survey.pages.$[elem]': p}}, array_filters=[{"elem.name": p['name']}], upsert=True)
                    else:
                        # push page 
                        res = self.survey_mongo_collection.update_one({'_id': self.survey_id}, {'$push': {'survey.pages': p}}, upsert=True)
            LOGGER.log(LogLevel.CRITICAL_INFO, "Survey successfully updated in mongo!")
            self.changes_summary = []
        else:
            LOGGER.log(LogLevel.CRITICAL_INFO, "Okay, not updating survey.")


    def import_page_from_json(self, json_dest, page_name, index=None):
        '''
        Move a page with page_name from a json file to the survey 
        '''
        self.cur_import_file = json_dest
        f = open(json_dest, 'r')
        data = json.load(f)
        if 'pages' not in data:
            LOGGER.log(LogLevel.WARN, "Error: json needs a 'pages' key at the top level to run 'import_page_from_json")
            f.close()
            return
        for x in data['pages']:
            if x['name'] == page_name:
                # check for existing page in survey object before pushing
                if not self.handle_existing_page(page_name):
                    f.close()
                    return
                if index is None:
                    self.survey['pages'].append(x)
                else:
                    self.survey['pages'].insert(index, x)
                self.changes_summary.append(f"Imported page '{page_name}' from json file '{json_dest}' to {f'index {index}' if index is not None else 'end of survey'} ")
                LOGGER.log(LogLevel.INFO, "Page successfully imported to survey!")
                f.close()
                return
        LOGGER.log(LogLevel.WARN, f"Could not find page named '{page_name}' in file '{json_dest}")
        f.close()

    
    def handle_existing_page(self, page_name):
        '''
        Checks if a page with page_name already exists in the survey.
        Confirms next action with user
        Returns a boolean. True = continue, False = abort
        '''
        for x in self.survey['pages']:
            if x['name'] == page_name:
                LOGGER.log(LogLevel.WARN, f"Page with name '{page_name}' already exists in survey. Override? (y/n) ")
                resp = input("")
                if resp.strip() in ['y', 'Y']:
                    LOGGER.log(LogLevel.INFO, f"Okay, overriding page '{page_name}' with new data")
                    self.delete_page(page_name, True)
                    return True
                else:
                    LOGGER.log(LogLevel.INFO, f"Okay, skipping update of existing page '{page_name}'")
                    return False
        return True
    

    def import_full_survey(self, path):
        '''
        Places an entire json full of survey data (found at path) in the survey
        '''
        LOGGER.log(LogLevel.WARN, "This overwrites all current survey data. Are you sure you want to continue? (y/n)")
        resp = input("")
        if resp.strip() in ['y', 'Y']:
            f = open(path, 'r')
            self.cur_import_file = path
            data = json.load(f)
            self.survey = data
            self.changes_summary.append(f"Survey data overwritten using '{path}'")
            LOGGER.log(LogLevel.INFO, f"Imported survey data from '{path}'")
            f.close()
        else:
            LOGGER.log(LogLevel.INFO, "Not importing survey data")


if __name__ == '__main__':
    LOGGER.log(LogLevel.CRITICAL_INFO, 'Welcome to the Delegation Survey Tool')
    LOGGER.log(LogLevel.INFO, "To get started, enter the version number you'd like to work on:")
    resp = float(input(""))
    tool = DelegationTool(resp)
    while resp != 'q':
        try:
            print()
            LOGGER.log(LogLevel.CRITICAL_INFO, "What would you like to do?\033[37m \n\t\n\tImport Survey from JSON (is)\n\tImport Page from JSON (ip)\n\tAdd Page (ap)\n\tDelete Page (dp)\n\tAdd Element to Page (ae)\n\tDelete Element From Page (de)\n\tView Current Survey as JSON (v)\n\tSave Changes (s)\n\tQuit (q)")
            resp = input("").strip().lower()
            if resp == 'is':
                if tool.cur_import_file != '':
                    path = input(f"Enter the path to the import file (enter for {tool.cur_import_file}): ")
                else:
                    path = input("Enter the path to the import file: ")
                tool.import_full_survey(path if path != '' else tool.cur_import_file)
            if resp == 'ip':
                if tool.cur_import_file != '':
                    path = input(f"Enter the path to the import file (enter for {tool.cur_import_file}): ")
                else:
                    path = input("Enter the path to the import file: ")
                page_name = input("Enter the name of the page to import: ")
                ind = input("At what index should this page be inserted? (enter to append) ")
                tool.import_page_from_json(path if path != '' else tool.cur_import_file, page_name, int(ind) if ind != '' else None) 
            if resp == 'dp':
                page_name = input("Enter the name of the page to delete (only the first page found with this name will be deleted): ")
                tool.delete_page(page_name)
            if resp == 's':
                tool.push_changes()
            if resp == 'v':
                print(json.dumps(tool.survey, indent=4))
            if resp == 'q':
                if len(tool.changes_summary) > 0:
                    LOGGER.log(LogLevel.WARN, "Changes are not saved. Are you sure you want to quit? (y/n)")
                    sure = input("").strip()
                    if sure in ['y', 'Y', 'q']:
                        break
                    else:
                        resp = ''
        except Exception as e:
            # catch all errors because otherwise all progress will be lost!
            LOGGER.log(LogLevel.WARN, f"There was an error processing your input. Please try again. {e}")


    # tool.push_changes()
    # tool.add_page("Participant ID Page")
    # el1 = SurveyElement(el_type="text", el_name="Participant ID", el_title="Enter Participant ID:", is_required=True)
    # tool.add_element("Participant ID Page", el1)
    # el2 = SurveyElement(el_type="checkbox", el_name="VR Scenarios Completed", el_title="Have you completed the VR simulator? Select all that apply", is_required=True, 
    #                     question_choices=["I have completed the VR desert environment ",
    #                     "I have completed the VR urban environment",
    #                     "I have completed the VR submarine environment ",
    #                     "I have completed the VR  jungle environment"], show_none_item=True, none_text="I have not completed any VR environments")
    # tool.add_element("Participant ID Page", el2)
    # el3 = SurveyElement(el_type="radiogroup", el_name="VR Comfort Level", visible_if="{VR Scenarios Completed} anyof ['I have completed the VR desert environment ', 'I have completed the VR urban environment', 'I have completed the VR submarine environment ', 'I have completed the VR  jungle environment']",
    #                     el_title="After completing the VR experience, my current physical state is...", is_required=True,
    #                     question_choices=["Very uncomfortable", "Slightly uncomfortable", "Neutral", "Comfortable", "Very comfortable"])
    # tool.add_element("Participant ID Page", el3)
    # el4 = SurveyElement(el_type="comment", el_name="Additional Information About Discomfort")