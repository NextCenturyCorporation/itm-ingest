import sys

sys.path.insert(0, "..")
from pymongo import MongoClient
from decouple import config
import json, time, copy, base64, os
from logger import LogLevel, Logger


"""
The delegation survey python tool adds the delegation survey questions to the database 
and can modify, add, order, and delete questions from the survey config.
"""
LOGGER = Logger("Delegation Tool")
QUIET_SAVE = True

class SurveyElement:
    def __init__(
        self,
        minimum=None,
        visible_if=None,
        input_type=None,
        question_choices=None,
        decision_makers=None,
        actions=None,
        is_required=None,
        show_other=None,
        el_title=None,
        patients=None,
        el_type=None,
        show_none_item=None,
        explanation=None,
        none_text=None,
        other_text=None,
        el_name=None,
        situation=None,
        visible=None,
        dm_name=None,
        supplies=None,
        html=None,
    ):
        self.element_data = {
            "min": minimum,
            "visibleIf": visible_if,
            "inputType": input_type,
            "choices": question_choices,
            "decisionMakers": decision_makers,
            "actions": actions,
            "isRequired": is_required,
            "showOtherItem": show_other,
            "title": el_title,
            "patients": patients,
            "type": el_type,
            "showNoneItem": show_none_item,
            "explanation": explanation,
            "noneText": none_text,
            "otherText": other_text,
            "name": el_name,
            "situation": situation,
            "visible": visible,
            "dmName": dm_name,
            "supplies": supplies,
            "html": html,
        }

    def get_clean_element(self):
        """
        Converts a survey element object to the correct json format for the survey config
        """
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
    medics_mongo_collection = None
    changes_summary = []
    cur_import_file = ""

    def __init__(self, version):
        # get the current survey data
        client = MongoClient(config("MONGO_URL"))
        db = client.dashboard

        # create new collection for survey, or simply get the existing collection
        self.survey_mongo_collection = db["delegationConfig"]
        obj_id = "delegation_v" + str(version)
        self.survey_id = obj_id

        # create new collection for sim screenshots, or simply get the existing collection
        self.image_mongo_collection = db["delegationMedia"]

        # get the collection for medics
        self.medics_mongo_collection = db["admMedics"]

        # search for version in database
        self.survey = self.survey_mongo_collection.find({"_id": obj_id})
        found_version = False
        for document in self.survey:
            found_version = True
            self.survey = document
            break

        # version does not exist in database, add the initial outline with the correct version number
        if not found_version:
            self.changes_summary.append(
                f"Added new survey version '{version}' to database"
            )
            self.initialize_survey(version, True)
            self.survey_mongo_collection.insert_one(
                {"_id": obj_id, "survey": self.survey}
            )

        if "survey" in self.survey:
            self.survey = self.survey["survey"]

    def add_page_by_json(self, page, index=None):
        if index is None:
            self.survey["pages"].append(page)
            self.changes_summary.append(
                f"Appended new page '{page['name']}' to survey"
            )
        else:
            self.survey["pages"].insert(index, page)
            self.changes_summary.append(
                f"Added new page '{page['name']}' to survey at index {index}"
            )
        LOGGER.log(
            LogLevel.INFO, f"Successfully added new page with name '{page['name']}'"
        )

    def add_page(
        self, page_name, scenario_name="", page_type="", scenario_index=None, index=None
    ):
        """
        Adds a new page to the survey
        """
        # check for existing page with name before adding
        if not self.handle_existing_page(page_name):
            return
        page = {"name": page_name, "elements": []}
        if scenario_name != "":
            page["scenarioName"] = scenario_name
        if page_type != "":
            page["pageType"] = page_type
        if scenario_index is not None:
            page["scenarioIndex"] = scenario_index
        if index is None:
            self.survey["pages"].append(page)
        else:
            self.survey["pages"].insert(index, page)
        self.changes_summary.append(
            f"Added new page '{page_name}' to database at index {index}"
        )
        LOGGER.log(
            LogLevel.INFO, f"Successfully added new page with name '{page_name}'"
        )

    def delete_page(self, page_name, update=False):
        """
        Deletes the first page with the given name from the survey
        """
        page = self.get_page_by_name(page_name)
        if not update:
            LOGGER.log(
                LogLevel.WARN,
                f"Are you sure you want to delete page '{page_name}'? (y/n)",
            )
            resp = input("")
        else:
            resp = "y"
        if resp.strip() in ["y", "Y"]:
            try:
                self.survey["pages"].remove(page)
                if not update:
                    self.changes_summary.append(f"Deleted page '{page_name}'.")
                return
            except:
                LOGGER.log(
                    LogLevel.WARN,
                    f"Page '{page_name}' was not found. Could not {'delete' if not update else 'update'}.",
                )
        else:
            LOGGER.log(LogLevel.INFO, f"Not deleting page '{page_name}'")

    def add_element(self, page_name, survey_el, index=None):
        """
        Adds a survey element to a page in the survey at the specified index
        """
        el = survey_el.get_clean_element()
        page = self.get_page_by_name(page_name)
        # check for existing element in page with data before adding
        for page_el in page["elements"]:
            if "name" in page_el and page_el["name"] == el["name"]:
                LOGGER.log(
                    LogLevel.WARN,
                    f"Element with name '{el['name']}' already exists on page '{page_name}'. Add anyway? (y/n)",
                )
                resp = input("")
                if resp.strip() not in ["y", "Y"]:
                    LOGGER.log(LogLevel.INFO, "Skipping element addition...")
                    return
            if "title" in page_el and page_el["title"] == el["title"]:
                LOGGER.log(
                    LogLevel.WARN,
                    f"Element with title '{el['title']}' already exists on page '{page_name}'. Add anyway? (y/n)",
                )
                resp = input("")
                if resp.strip() not in ["y", "Y"]:
                    LOGGER.log(LogLevel.INFO, "Skipping element addition...")
                    return
        if index is None:
            page["elements"].append(el)
        else:
            page["elements"].insert(index, el)
        self.changes_summary.append(
            f"Added new element '{survey_el['title'] if 'title' in survey_el else survey_el['name']}' to page {page_name} at index {index}"
        )

    def get_page_by_name(self, page_name):
        """
        Returns the first page in the survey that matches page_name
        """
        for page in self.survey["pages"]:
            if page["name"] == page_name:
                return page
        return False

    def initialize_survey(self, version, is_new):
        """
        Adds the initial survey base to the database
        """
        if not is_new:
            LOGGER.log(
                LogLevel.WARN,
                "This will overwrite all previous delegation survey data in the database. Are you sure you want to do this? (y/n) ",
            )
            overwrite = input("")
        if is_new or overwrite.strip() in ["y", "Y"]:
            self.survey = {
                "title": "ITM Delegation Survey",
                "logoPosition": "right",
                "version": version,
                "completedHtml": "<h3>Thank you for completing the survey</h3>",
                "pages": [],
                "widthMode": "responsive",
                "showTitle": False,
                "showQuestionNumbers": False,
                "showProgressBar": "top",
            }
        else:
            LOGGER.log(LogLevel.INFO, "Skipping initialization step")

    def update_version(self, new_version):
        """
        Updates the survey version in the database
        """
        obj_id = "delegation_v" + str(new_version)
        found_docs = self.survey_mongo_collection.find({"_id": obj_id})
        found_version = False
        for document in found_docs:
            found_version = True
            found_docs = document
            LOGGER.log(
                LogLevel.WARN,
                f"Survey version '{new_version}' already exists in database. Cannot update.",
            )
            return

        # version does not exist in database, add the initial outline with the correct version number
        if not found_version:
            prev = self.survey["version"]
            # create a new version in the database and put the current survey in
            self.survey["version"] = new_version
            self.survey_mongo_collection.insert_one(
                {"_id": obj_id, "survey": self.survey}
            )
            self.changes_summary.append(
                f"Created new survey version '{new_version}' from version '{prev}'"
            )
            LOGGER.log(
                LogLevel.INFO,
                f"Created new survey version '{new_version}' from version '{prev}'",
            )

    def push_changes(self):
        """
        Submits changes to the database
        """
        if len(self.changes_summary) == 0:
            LOGGER.log(LogLevel.CRITICAL_INFO, "No changes have been made.")
            return
        if not QUIET_SAVE:
            LOGGER.log(LogLevel.CRITICAL_INFO, "Below are the changes you've made so far:")
            # Check to make sure user wants to update; show list of changes
            for x in self.changes_summary:
                print("\t" + x)
                if len(self.changes_summary) < 5:
                    time.sleep(0.25)
                else:
                    time.sleep(0.02)
        LOGGER.log(LogLevel.WARN, "Push all to database? (y/n) ")
        resp = input("")
        if resp.strip() in ["y", "Y"]:
            try:
                self.survey_mongo_collection.update_one(
                    {"_id": self.survey_id},
                    {"$set": {"_id": self.survey_id, "survey": self.survey}},
                )
            except:
                # strip pictures out of json
                for page in self.survey["pages"]:
                    for el in page["elements"]:
                        for pat in el.get("patients", []):
                            if "imgUrl" in pat and len(pat["imgUrl"]) > 100:
                                # see if imgurl is already in image database
                                res = self.image_mongo_collection.find(
                                    {"url": pat["imgUrl"]}
                                )
                                found = False
                                for doc in res:
                                    pat["imgUrl"] = doc["_id"]
                                    found = True
                                    break
                                if not found:
                                    res = self.image_mongo_collection.insert_one(
                                        {
                                            "url": pat["imgUrl"],
                                            "patientIds": [pat["name"]],
                                            "description": pat["description"],
                                            "scenario": page["scenarioIndex"],
                                            "mediaType": "img",
                                        }
                                    )
                                    pat["imgUrl"] = res.inserted_id

                # need to update one page at a time or else it gets too big
                for k in self.survey:
                    if k != "pages":
                        self.survey_mongo_collection.update_one(
                            {"_id": self.survey_id},
                            {"$set": {f"survey.{k}": self.survey[k]}},
                        )
                for p in self.survey["pages"]:
                    res = self.survey_mongo_collection.find(
                        {
                            "_id": self.survey_id,
                            "survey.pages": {"$elemMatch": {"name": p["name"]}},
                        }
                    )
                    doc_found = False
                    for _ in res:
                        doc_found = True
                        break
                    if doc_found:
                        res = self.survey_mongo_collection.update_one(
                            {"_id": self.survey_id},
                            {"$set": {"survey.pages.$[elem]": p}},
                            array_filters=[{"elem.name": p["name"]}],
                            upsert=True,
                        )
                    else:
                        # push page
                        res = self.survey_mongo_collection.update_one(
                            {"_id": self.survey_id},
                            {"$push": {"survey.pages": p}},
                            upsert=True,
                        )
            LOGGER.log(LogLevel.CRITICAL_INFO, "Survey successfully updated in mongo!")
            self.changes_summary = []
        else:
            LOGGER.log(LogLevel.CRITICAL_INFO, "Okay, not updating survey.")

    def import_page_from_json(self, json_dest, page_name, index=None):
        """
        Move a page with page_name from a json file to the survey
        """
        self.cur_import_file = json_dest
        f = open(json_dest, "r", encoding="utf-8")
        data = json.load(f)
        if "pages" not in data:
            LOGGER.log(
                LogLevel.WARN,
                "Error: json needs a 'pages' key at the top level to run 'import_page_from_json",
            )
            f.close()
            return
        for x in data["pages"]:
            if x["name"] == page_name:
                # check for existing page in survey object before pushing
                if not self.handle_existing_page(page_name):
                    f.close()
                    return
                if index is None:
                    self.survey["pages"].append(x)
                else:
                    self.survey["pages"].insert(index, x)
                self.changes_summary.append(
                    f"Imported page '{page_name}' from json file '{json_dest}' to {f'index {index}' if index is not None else 'end of survey'} "
                )
                LOGGER.log(LogLevel.INFO, "Page successfully imported to survey!")
                f.close()
                return
        LOGGER.log(
            LogLevel.WARN,
            f"Could not find page named '{page_name}' in file '{json_dest}",
        )
        f.close()

    def handle_existing_page(self, page_name):
        """
        Checks if a page with page_name already exists in the survey.
        Confirms next action with user
        Returns a boolean. True = continue, False = abort
        """
        for x in self.survey["pages"]:
            if x["name"] == page_name:
                LOGGER.log(
                    LogLevel.WARN,
                    f"Page with name '{page_name}' already exists in survey. Override? (y/n) ",
                )
                resp = input("")
                if resp.strip() in ["y", "Y"]:
                    LOGGER.log(
                        LogLevel.INFO,
                        f"Okay, overriding page '{page_name}' with new data",
                    )
                    self.delete_page(page_name, True)
                    return True
                else:
                    LOGGER.log(
                        LogLevel.INFO,
                        f"Okay, skipping update of existing page '{page_name}'",
                    )
                    return False
        return True

    def import_full_survey(self, path):
        """
        Places an entire json full of survey data (found at path) in the survey
        """
        LOGGER.log(
            LogLevel.WARN,
            "This will overwrite all current survey data. Are you sure you want to continue? (y/n)",
        )
        resp = input("")
        if resp.strip() in ["y", "Y"]:
            f = open(path, "r", encoding="utf-8")
            self.cur_import_file = path
            cur_version = self.survey["version"]
            data = json.load(f)
            self.survey = data
            self.survey["version"] = cur_version
            self.changes_summary.append(f"Survey data overwritten using '{path}'")
            LOGGER.log(LogLevel.INFO, f"Imported survey data from '{path}'")
            f.close()
        else:
            LOGGER.log(LogLevel.INFO, "Not importing survey data")

    def add_img_to_db(self, img_path, patient_id, description, scenario_index):
        """
        Takes patient data and a path to an image and adds it to the delegationMedia database
        """
        img_file = open(img_path, "rb")
        img_url = base64.b64encode(img_file.read()).decode("utf-8")
        img_file.close()
        # see if imgurl is already in image database
        res = self.image_mongo_collection.find({"url": img_url})
        found = False
        for doc in res:
            self.image_mongo_collection.update_one(
                {"_id": doc["_id"]}, {"$push": {"patientIds": patient_id}}
            )
            return doc["_id"]
        if not found:
            res = self.image_mongo_collection.insert_one(
                {
                    "url": img_url,
                    "patientIds": [patient_id],
                    "description": description,
                    "scenario": scenario_index,
                    "mediaType": "img",
                }
            )
            return res.inserted_id

    def add_db_medic_to_survey_by_name(self, medic_name):
        """
        Finds a document from the adm medic colleciton in mongo that matches the name given.
        Adds it to the survey at the end of all singleMedics
        """
        found_docs = self.medics_mongo_collection.find({"name": medic_name})
        found_medic = False
        for doc in found_docs:
            found_medic = True
            self.insert_new_medic(doc)
            break
        if not found_medic:
            LOGGER.log(
                LogLevel.WARN,
                "Could not find medic to add to survey. Please check that all details match.",
            )

    def add_db_medic_to_survey_by_details(
        self, adm_name, adm_alignment, scenario_writer, environment=None, scenario_id=None, append=False
    ):
        """
        Finds a document from the adm medic colleciton in mongo that matches the parameters given.
        Adds it to the survey at the end of all singleMedics
        """
        if adm_name not in [
            "kitware-single-kdma-adm-aligned-no-negatives",
            "kitware-single-kdma-adm-baseline",
            "kitware-hybrid-kaleido-aligned",
            "TAD aligned",
            "TAD baseline",
            "TAD severity-baseline",
            "TAD misaligned",
            'ALIGN-ADM-OutlinesBaseline', 
            'ALIGN-ADM-ComparativeRegression-ICL-Template', 
            'TAD-severity-baseline',
            'TAD-aligned'
        ]:
            LOGGER.log(
                LogLevel.WARN,
                "ADM name must be one of ['ALIGN-ADM-OutlinesBaseline__486af8ca-fd13-4b16-acc3-fbaa1ac5b69b', 'TAD', 'ALIGN-ADM-OutlinesBaseline__458d3d8a-d716-4944-bcc4-d20ec0a9d98c', 'ALIGN-ADM-Random__9e0997cb-70cb-4f5d-a085-10f359636517', 'ALIGN-ADM-HybridRegression__065fac00-4446-4e9c-895f-83691abc7f49', 'TAD-severity-baseline', 'TAD-baseline', 'TAD-aligned', 'kitware-single-kdma-adm-aligned-no-negatives', 'kitware-single-kdma-adm-baseline', 'kitware-hybrid-kaleido-aligned', 'TAD aligned', 'TAD baseline', 'TAD severity-baseline', 'TAD misaligned']. Cannot add medic",
            )
            return
        adm_alignment = adm_alignment
        if adm_alignment not in ['high', 'low', 'vol-human-8022671-SplitHighMulti', 'qol-human-2932740-HighExtreme', 'vol-human-1774519-SplitHighMulti', 'qol-human-6349649-SplitHighMulti', 
               'vol-human-6403274-SplitEvenBinary', 'qol-human-3447902-SplitHighMulti', 'vol-human-7040555-SplitEvenBinary', 'qol-human-7040555-SplitHighMulti', 
               'vol-human-2637411-SplitEvenMulti', 'qol-human-3043871-SplitHighBinary', 'vol-human-2932740-SplitEvenMulti', 'qol-human-6403274-SplitHighBinary', 
               'vol-human-8478698-SplitLowMulti', 'qol-human-1774519-SplitEvenBinary', 'vol-human-3043871-SplitLowMulti', 'qol-human-9157688-SplitEvenBinary', 
               'vol-human-5032922-SplitLowMulti', 'qol-human-0000001-SplitEvenMulti', 'vol-synth-LowExtreme', 'qol-human-8022671-SplitLowMulti', 'vol-synth-HighExtreme', 
               'qol-human-5032922-SplitLowMulti', 'vol-synth-HighCluster', 'qol-synth-LowExtreme', 'vol-synth-LowCluster', 'qol-synth-HighExtreme', 'vol-synth-SplitLowBinary', 
               'qol-synth-HighCluster', 'qol-synth-LowCluster', 'qol-synth-SplitLowBinary', 
               'ADEPT-DryRun-Moral judgement-0.0', 'ADEPT-DryRun-Ingroup Bias-0.0', 'ADEPT-DryRun-Moral judgement-0.1', 'ADEPT-DryRun-Ingroup Bias-0.1', 'ADEPT-DryRun-Moral judgement-0.2', 'ADEPT-DryRun-Ingroup Bias-0.2', 'ADEPT-DryRun-Moral judgement-0.3', 
               'ADEPT-DryRun-Ingroup Bias-0.3', 'ADEPT-DryRun-Moral judgement-0.4', 'ADEPT-DryRun-Ingroup Bias-0.4', 'ADEPT-DryRun-Moral judgement-0.5', 'ADEPT-DryRun-Ingroup Bias-0.5', 'ADEPT-DryRun-Moral judgement-0.6', 'ADEPT-DryRun-Ingroup Bias-0.6', 'ADEPT-DryRun-Moral judgement-0.7', 'ADEPT-DryRun-Ingroup Bias-0.7', 'ADEPT-DryRun-Moral judgement-0.8', 
               'ADEPT-DryRun-Ingroup Bias-0.8', 'ADEPT-DryRun-Moral judgement-0.9', 'ADEPT-DryRun-Ingroup Bias-0.9', 'ADEPT-DryRun-Moral judgement-1.0', 'ADEPT-DryRun-Ingroup Bias-1.0']:
            LOGGER.log(
                LogLevel.WARN,
                f"ADM Alignment is invalid: {adm_alignment}. Cannot add medic.",
            )
            return
        if scenario_writer not in ["Adept", "SoarTech"]:
            LOGGER.log(
                LogLevel.WARN,
                "Scenario writer must be either 'Adept' or 'SoarTech'. Cannot add medic.",
            )
            return
        found_docs = []
        if environment is not None:
            environment = environment[0].upper() + environment[1:].lower()
            if environment not in ["Desert", "Jungle", "Urban", "Submarine"]:
                LOGGER.log(
                    LogLevel.WARN,
                    "Environment must be one of ['Desert', 'Jungle', 'Urban', 'Submarine']. Cannot add medic.",
                )
                return
            found_docs = self.medics_mongo_collection.find(
                {
                    "admName": adm_name,
                    "admAlignment": adm_alignment,
                    "scenarioName": scenario_writer + " " + environment,
                }
            )
        elif scenario_id is not None:
                found_docs = self.medics_mongo_collection.find(
                {
                    "admName": adm_name,
                    "admAlignment": adm_alignment,
                    "scenarioIndex": scenario_id,
                }
            )
        found_medic = False
        for doc in found_docs:
            found_medic = True
            if not append:
                self.insert_new_medic(doc)
            else:
                del doc["_id"]
                self.survey["pages"].append(doc)
                self.changes_summary.append(
                    f"Appended new medic '{doc['name']}' to survey"
                )
            return doc["name"]
        if not found_medic:
            if (scenario_id is None):
                LOGGER.log(
                    LogLevel.WARN,
                    f"Could not find medic to add to survey. Please check that all details match. adm_name: {adm_name}, adm_alignment: {adm_alignment}, scenario_writer: {scenario_writer}, environment: {environment}",
                )
            else:
                LOGGER.log(
                    LogLevel.WARN,
                    f"Could not find medic to add to survey. Please check that all details match. Scenario: {scenario_id}, ADM Alignment: {adm_alignment}, ADM Name: {adm_name}",
                )
            return None

    def insert_new_medic(self, doc):
        """
        Inserts a new medic at the end of all singleMedics in the survey config
        """
        del doc["_id"]
        i = 0
        insert_ind = -1
        for page in self.survey["pages"]:
            if "omnibus" in page.get("name", "").lower():
                insert_ind = i
                break
            i += 1
        if insert_ind > -1:
            self.survey["pages"].insert(insert_ind, doc)
        else:
            self.survey["pages"].insert(3, doc)
        self.changes_summary.append(
            f"Inserted new medic '{doc['name']}' at index {insert_ind if insert_ind > -1 else 3}"
        )

    def export_survey_json(self, path):
        """
        Exports the current state of the survey to a json file
        """
        f = open(path, "w", encoding="utf-8")
        survey_copy = copy.deepcopy(self.survey)
        for p in survey_copy["pages"]:
            for e in p["elements"]:
                if "patients" in e:
                    for pat in e["patients"]:
                        pat["imgUrl"] = str(pat["imgUrl"])
        json.dump(survey_copy, f, indent=4)
        f.close()

    def clear_survey_version(self):
        """
        Restarts a survey version with the bare bones.
        """
        self.initialize_survey(self.survey["version"], False)
        self.changes_summary.append("Cleared all data from survey")

    def append_comparison_page(self, name1, name2, scenario_index, alignment):
        """
        Given the names of two medics, a scenario index, and an alignment label,
        adds a new comparison page to the survey
        """
        f = open(
            os.path.join("templates", "comparison_template.json"), "r", encoding="utf-8"
        )
        template = json.load(f)
        f.close()
        template["scenarioIndex"] = scenario_index
        template["alignment"] = alignment
        template["name"] = (
            template["name"].replace("Medic-ST1", name1).replace("Medic-ST2", name2)
        )
        for el in template["elements"]:
            el["name"] = (
                el["name"].replace("Medic-ST1", name1).replace("Medic-ST2", name2)
            )
            el["title"] = (
                el["title"].replace("Medic-ST1", name1).replace("Medic-ST2", name2)
            )
            tmp_choices = []
            for choice in el.get("choices", []):
                tmp_choices.append(
                    choice.replace("Medic-ST1", name1).replace("Medic-ST2", name2)
                )
            if len(tmp_choices) > 0:
                el["choices"] = tmp_choices
            tmp_dms = []
            for dm in el.get("decisionMakers", []):
                tmp_dms.append(
                    dm.replace("Medic-ST1", name1).replace("Medic-ST2", name2)
                )
            if len(tmp_dms) > 0:
                el["decisionMakers"] = tmp_dms
        self.survey["pages"].append(template)
        self.changes_summary.append(
            f"Appended new medic comparison '{template['name']}' to survey"
        )

    def setup_omnibus_pages(
        self,
        first_medics,
        second_medics,
        first_name,
        second_name,
        scenario_name,
        scenario_index,
        alignment,
    ):
        """
        Adds the single and comparison omnibus pages for the given medics with the assigned names
        """

        def single_omni_page(medics, name):
            """
            Sub-function to create a single omnibus page. Returns the created page in json
            """
            f = open(
                os.path.join("templates", "single_omni_template.json"),
                "r",
                encoding="utf-8",
            )
            single_template = json.load(f)
            f.close()
            single_template["name"] = single_template["name"].replace("Medic-D", name)
            single_template["scenarioName"] = scenario_name
            single_template["scenarioIndex"] = scenario_index
            single_template["alignment"] = alignment
            for el in single_template["elements"]:
                if "decisionMakers" in el:
                    el["decisionMakers"] = medics
                el["name"] = el["name"].replace("Medic-D", name)
                el["title"] = el["title"].replace("Medic-D", name)
                if "dmName" in el:
                    el["dmName"] = el["dmName"].replace("Medic-D", name)
                new_choices = []
                for choice in el.get("choices", []):
                    new_choices.append(choice.replace("Medic-D", name))
                if len(new_choices) > 0:
                    el["choices"] = new_choices
            return single_template

        self.survey["pages"].append(single_omni_page(first_medics, first_name))
        self.changes_summary.append(
            f"Appended omnibus page '{first_name}' for '{scenario_name}' to survey"
        )
        self.survey["pages"].append(single_omni_page(second_medics, second_name))
        self.changes_summary.append(
            f"Appended omnibus page '{second_name}' for '{scenario_name}' to survey"
        )

        f = open(
            os.path.join("templates", "comparison_omni_template.json"),
            "r",
            encoding="utf-8",
        )
        comparison_template = json.load(f)
        f.close()
        comparison_template["name"] = (
            comparison_template["name"]
            .replace("Medic-C", first_name)
            .replace("Medic-D", second_name)
        )
        comparison_template["scenarioIndex"] = scenario_index
        comparison_template["scenarioName"] = scenario_name
        comparison_template["alignment"] = alignment
        for el in comparison_template["elements"]:
            new_dms = []
            for dm in el.get("decisionMakers", []):
                new_dms.append(
                    dm.replace("Medic-C", first_name).replace("Medic-D", second_name)
                )
            if len(new_dms) > 0:
                el["decisionMakers"] = new_dms
            el["name"] = (
                el["name"]
                .replace("Medic-C", first_name)
                .replace("Medic-D", second_name)
            )
            el["title"] = (
                el["title"]
                .replace("Medic-C", first_name)
                .replace("Medic-D", second_name)
            )
            new_choices = []
            for choice in el.get("choices", []):
                new_choices.append(
                    choice.replace("Medic-C", first_name).replace(
                        "Medic-D", second_name
                    )
                )
            if len(new_choices) > 0:
                el["choices"] = new_choices

        self.survey["pages"].append(comparison_template)
        self.changes_summary.append(
            f"Appended omnibus comparison page for '{first_name}' vs '{second_name}' for '{scenario_name}' to survey"
        )


def one_time_db_initialization():
    """
    Adds survey configs 1 and 2 to the database along with the test config (survey config #2 with no requirements).
    It also adds patient ids to images for adm medic translation
    """
    tool = DelegationTool(1.0)
    tool.import_full_survey(os.path.join("survey-configs", "surveyConfig1x.json"))
    tool.push_changes()

    tool = DelegationTool(2.0)
    tool.import_full_survey(os.path.join("survey-configs", "surveyConfig2x.json"))
    tool.push_changes()

    tool = DelegationTool(2.1)
    tool.import_full_survey(os.path.join("survey-configs", "surveyConfig2.1.json"))
    tool.push_changes()

    tool = DelegationTool(0.0)
    tool.import_full_survey(os.path.join("survey-configs", "test_config.json"))
    tool.push_changes()

    # adding images doesn't need a version
    img_dir = os.path.join("patient_images", "metrics_eval")
    tool.add_img_to_db(
        os.path.join(img_dir, "ad_desert_local.png"),
        "local_soldier_1",
        "Male, mid-30s; local military uniform.  Tried to break up fight between US soldiers.  Major compound fracture from wall collapse.",
        7,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "ad_desert_us.png"),
        "us_soldier_1",
        "Male, mid-30s; US military uniform.  Started fight with another US soldier.  Major compound fracture from wall collapse.",
        7,
    )

    tool.add_img_to_db(
        os.path.join(img_dir, "ad_jungle_bad.png"),
        "civilian_1",
        "Male, mid-30s; local civilian.  Found IED, reported it, and accidentally triggered it while taking a closer look.  Located closer to the IED materials.",
        6,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "ad_jungle_innocent.png"),
        "civilian_2",
        "Male, mid-30s; local civilian.  Just happened to be nearby, located further from the IED materials.",
        6,
    )

    tool.add_img_to_db(
        os.path.join(img_dir, "ad_sub_bystander.png"),
        "sailor_1",
        "Male, mid-30s.  Was waiting to excercise.  Major burns.",
        5,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "ad_sub_electrician.png"),
        "electricians_mate",
        "Male, mid-30s.  Major burns.",
        5,
    )

    tool.add_img_to_db(
        os.path.join(img_dir, "ad_urb_shooter.png"),
        "patient_1_shooter",
        "Male; mid-30s; civilian; all black clothing.  Involved in shooting with other civilian.",
        8,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "ad_urb_victim.png"),
        "patient_2_victim",
        "Male; mid-30s; civilian; civilian clothing.  Involved in shooting with other civilian.",
        8,
    )

    tool.add_img_to_db(
        os.path.join(img_dir, "st_desert_amp.png"),
        "casualty_v",
        "Has a partial below the knee leg amputation with severe bleeding.",
        3,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_desert_lac.png"),
        "casualty_u",
        "Has an uncontrolled hemorrhage of the right forearm from glass, severing an artery.",
        3,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_desert_leg.png"),
        "casualty_x",
        "Closed femur fracture of the right thigh with a potential pelvic fracture on the right side.",
        3,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_desert_shoulder.png"),
        "casualty_w",
        "Has an injury to the chest with multiple rib fractures on the left chest and progressively worsening difficulty in breathing.",
        3,
    )

    tool.add_img_to_db(
        os.path.join(img_dir, "st_jungle_burn_female.png"),
        "casualty_u",
        "Has a circumferential second and third degree burn on the right forearm encompassing 9% of body surface area.",
        2,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_jungle_burn_male.png"),
        "casualty_v",
        "Has a second and third degree burn of the left forearm encompassing 9% of body surface area.",
        2,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_jungle_leg.png"),
        "casualty_x",
        "Closed femur fracture of the right thigh with a potential pelvic fracture on the right side.",
        2,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_jungle_shoulder.png"),
        "casualty_w",
        "Has an injury to the chest with multiple rib fractures on the left chest and progressively worsening difficulty in breathing.",
        2,
    )

    tool.add_img_to_db(
        os.path.join(img_dir, "st_sub_burn_female.png"),
        "casualty_u",
        "Has a circumferential second and third degree burn on the right forearm encompassing 9% of body surface area.",
        1,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_sub_burn_male.png"),
        "casualty_v",
        "Has a second and third degree burn of the left forearm encompassing 9% of body surface area.",
        1,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_sub_leg.png"),
        "casualty_x",
        "Closed femur fracture of the right thigh with a potential pelvic fracture on the right side.",
        1,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_sub_shoulder.png"),
        "casualty_w",
        "Has an injury to the chest with multiple rib fractures on the left chest and progressively worsening difficulty in breathing.",
        1,
    )

    tool.add_img_to_db(
        os.path.join(img_dir, "st_urb_amp.png"),
        "casualty_v",
        "Has a partial below the knee leg amputation with severe bleeding.",
        4,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_urb_lac.png"),
        "casualty_u",
        "Has an uncontrolled hemorrhage of the right forearm from glass, severing an artery.",
        4,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_urb_leg.png"),
        "casualty_x",
        "Closed femur fracture of the right thigh with a potential pelvic fracture on the right side.",
        4,
    )
    tool.add_img_to_db(
        os.path.join(img_dir, "st_urb_shoulder.png"),
        "casualty_w",
        "Has an injury to the chest with multiple rib fractures on the left chest and progressively worsening difficulty in breathing.",
        4,
    )


def version3_setup():
    """
    Creates survey version 3.0
    """
    tool = DelegationTool(3.0)
    tool.clear_survey_version()

    # add starting pages to survey
    tool.import_page_from_json(
        os.path.join("survey-configs", "surveyConfig2x.json"),
        "Participant ID Page",
        None,
    )
    tool.import_page_from_json(
        os.path.join("survey-configs", "surveyConfig2x.json"),
        "Survey Introduction",
        None,
    )
    tool.import_page_from_json(
        os.path.join("survey-configs", "surveyConfig2x.json"), "Note page", None
    )

    # add comparison options to survey
    tool.survey["validSingleSets"] = []
    tool.survey["validOmniSets"] = []

    # add all medics to survey
    alignments = ["high", "low"]
    envs = ["Desert", "Submarine", "Jungle", "Urban"]
    writers = ["Adept", "SoarTech"]
    scenario_indices = {
        "Adept Urban": 8,
        "Adept Jungle": 6,
        "Adept Desert": 7,
        "Adept Submarine": 5,
        "SoarTech Desert": 3,
        "SoarTech Jungle": 2,
        "SoarTech Submarine": 1,
        "SoarTech Urban": 4,
    }

    # optionally, some of this (like comparison pages and omnibus) can be done inside the dashboard
    # to avoid bloating the database, but we want to try to keep processing outside of the dashboard
    # for better performance
    omni_ind = 1  # start at 1 for O1, O2, O3 instead of O0
    scenario_ind = 9  # start at 9 for omnibus
    medic_map = {}
    omni_map = {}
    valid_single_sets = [
        [
            "ST high kitware jungle",
            "AD low kitware desert",
            "ST low TAD urban",
            "AD high TAD submarine",
        ],
        [
            "ST high kitware desert",
            "AD low kitware jungle",
            "ST low TAD submarine",
            "AD high TAD urban",
        ],
        [
            "ST high kitware urban",
            "AD low kitware submarine",
            "ST low TAD jungle",
            "AD high TAD desert",
        ],
        [
            "ST high kitware submarine",
            "AD low kitware urban",
            "ST low TAD desert",
            "AD high TAD jungle",
        ],
        [
            "ST low kitware jungle",
            "AD high kitware desert",
            "ST high TAD urban",
            "AD low TAD submarine",
        ],
        [
            "ST low kitware desert",
            "AD high kitware jungle",
            "ST high TAD submarine",
            "AD low TAD urban",
        ],
        [
            "ST low kitware urban",
            "AD high kitware submarine",
            "ST high TAD jungle",
            "AD low TAD desert",
        ],
        [
            "ST low kitware submarine",
            "AD high kitware urban",
            "ST high TAD desert",
            "AD low TAD jungle",
        ],
    ]
    valid_omni_sets = [
        ["ST high kitware", "AD low TAD"],
        ["ST low kitware", "AD high TAD"],
        ["AD high kitware", "ST low TAD"],
        ["AD low kitware", "ST high TAD"],
    ]
    for writer in writers:
        # keep track of the names of each medic for each writer over all 4 environments (for omnibus)
        tad_aligned = []
        tad_baseline = []
        kit_aligned = []
        kit_baseline = []
        for env in envs:
            # create individual medic pages for parallax
            name1 = tool.add_db_medic_to_survey_by_details(
                "TAD aligned", "high", writer, environment=env, append=True
            )
            tad_aligned.append(name1)
            name2 = tool.add_db_medic_to_survey_by_details(
                "TAD aligned", "low", writer, environment=env, append=True
            )
            tad_baseline.append(name2)
            # create comparison pages
            tool.append_comparison_page(
                name1, name2, scenario_indices[writer + " " + env], "high vs low"
            )

            # create individual medic pages for kitware
            name3 = tool.add_db_medic_to_survey_by_details(
                "kitware-hybrid-kaleido-aligned", "high", writer, environment=env, append=True
            )
            kit_aligned.append(name3)
            name4 = tool.add_db_medic_to_survey_by_details(
                "kitware-hybrid-kaleido-aligned", "low", writer, environment=env, append=True
            )
            kit_baseline.append(name4)
            # create comparison pages
            tool.append_comparison_page(
                name3, name4, scenario_indices[writer + " " + env], "high vs low"
            )

            medic_map[
                f"{'ST' if writer == 'SoarTech' else 'AD'} {'high vs low'} TAD {env.lower()}"
            ] = [name1, name2]
            medic_map[
                f"{'ST' if writer == 'SoarTech' else 'AD'} {'high vs low'} kitware {env.lower()}"
            ] = [name3, name4]
        """ commenting out for now since 7-16 data collect doesn't use omnibus
        # create omnibus pages and omnibus comparison pages
        tool.setup_omnibus_pages(tad_aligned, tad_baseline, 'Medic-O'+str(omni_ind), 'Medic-O'+str(omni_ind+1), f"{writer} Omnibus - TAD ({alignment})", scenario_ind, alignment)
        omni_map[f"{'ST' if writer == 'SoarTech' else 'AD'} {alignment} TAD"] = ['Medic-O'+str(omni_ind), 'Medic-O'+str(omni_ind+1)]
        omni_ind += 2
        scenario_ind += 1

        tool.setup_omnibus_pages(kit_aligned, kit_baseline, 'Medic-O'+str(omni_ind), 'Medic-O'+str(omni_ind+1), f"{writer} Omnibus - Kitware ({alignment})", scenario_ind, alignment)
        omni_map[f"{'ST' if writer == 'SoarTech' else 'AD'} {alignment} kitware"] = ['Medic-O'+str(omni_ind), 'Medic-O'+str(omni_ind+1)]
        omni_ind += 2
        """
        scenario_ind += 1
    """ not using for 7-16
    for s in valid_single_sets:
        tmp_set = []
        for description in s:
            tmp_set.append(medic_map[description])
        tool.survey['validSingleSets'].append(tmp_set)

    for s in valid_omni_sets:
        tmp_set = []
        for description in s:
            tmp_set.append(omni_map[description])
        tool.survey['validOmniSets'].append(tmp_set)
    """
    # pages for treating as AI or Human
    agent_pages = [
        {
            "name": "Treat as Human",
            "elements": [
                {
                    "type": "expression",
                    "name": "Please evaluate these triage decision makers as if they are human medics.",
                    "title": "Please evaluate these triage decision makers as if they are human medics."
                }
            ]
        },
        {
            "name": "Treat as AI",
            "elements": [
                {
                    "type": "expression",
                    "name": "Please evaluate these triage decision makers as if they are an Artificial Intelligence (AI) medic.",
                    "title": "Please evaluate these triage decision makers as if they are an Artificial Intelligence (AI) medic."
                }
            ]
        }
    ]
    tool.survey['agentPages'] = agent_pages

    # add final page
    tool.import_page_from_json(
        os.path.join("survey-configs", "surveyConfig2.1.json"),
        "Post-Scenario Measures",
        None,
    )

    # save changes
    tool.push_changes()
    tool.export_survey_json(os.path.join("survey-configs", "surveyConfig3x.json"))


def version4_setup():
    """
    Creates survey version 4.0.

    Note that survey version 4.0 uses images from the text scenarios so that we are not storing duplicate information
    """
    tool = DelegationTool(4.0)
    tool.clear_survey_version()

    exp_page_1 = {
            "name": "Participant ID Page",
            "elements": [
                {
                    "type": "text",
                    "name": "Participant ID",
                    "title": "Enter Participant ID:",
                    "isRequired": True
                }
            ]
        }
    tool.add_page_by_json(exp_page_1)

    warning_page = {
        "name": "PID Warning",
        "elements": [
            {
                "type": "expression",
                "name": "Warning: The Participant ID you entered is not part of this experiment. Please go back and ensure you have typed in the PID correctly before continuing.",
                "title": "Warning: The Participant ID you entered is not part of this experiment. Please go back and ensure you have typed in the PID correctly before continuing."
            }
        ]
    }
    tool.add_page_by_json(warning_page)

    exp_page_2 = {
            "name": "Participant ID Page",
            "elements": [
                {
                    "type": "radiogroup",
                    "name": "VR Experience Level",
                    "title": "How much experience did you have with VR Gaming before today?",
                    "isRequired": True,
                    "choices": [
                        "0 - None at all",
                        "1 - I have used it, but not often",
                        "2 - I use it occasionally",
                        "3 - I use it often",
                        "4 - I use it all the time"
                    ]
                },
                {
                    "type": "radiogroup",
                    "name": "VR Comfort Level",
                    "title": "After completing the VR experience, my current physical state is...",
                    "isRequired": True,
                    "choices": [
                        "Very uncomfortable",
                        "Slightly uncomfortable",
                        "Neutral",
                        "Comfortable",
                        "Very comfortable"
                    ]
                },
                {
                    "type": "comment",
                    "name": "Additonal Information About Discomfort",
                    "title": "Please identify any specific discomfort (headache, disoriented, queasy, etc.)"
                },
                {
                    "type": "radiogroup",
                    "name": "Text Scenarios Completed",
                    "title": "Please verify that the following Text Scenarios have been completed:",
                    "isRequired": True,
                    "choices": [
                        "Yes",
                        "No",
                    ],
                },
                {
                    "type": "comment",
                    "name": "Additonal Information About Text Scenario Mismatch",
                    "visibleIf": "{Text Scenarios Completed} anyof ['No']",
                    "title": "Please explain why this participant has not completed these text scenarios. Or, if they have, please ensure you entered the same participant ID."
                },
                {
                    "type": "radiogroup",
                    "name": "VR Scenarios Completed",
                    "title": "Please verify that the following VR Scenarios have been completed:",
                    "isRequired": True,
                    "choices": [
                        "Yes",
                        "No",
                    ],
                },
                {
                    "type": "comment",
                    "name": "Additonal Information About VR Scenario Mismatch",
                    "visibleIf": "{VR Scenarios Completed} anyof ['No']",
                    "title": "Please explain why this participant has not completed these VR scenarios. Or, if they have, please ensure you entered the same participant ID."
                }
            ]
    }
    tool.add_page_by_json(exp_page_2)
    intro_page = {
            "name": "Survey Introduction",
            "elements": [
                {
                    "type": "html",
                    "name": "Survey21 Introduction",
                    "html": "Welcome to the <strong>Military Triage Delegation Experiment</strong>. Here you will have the chance to review the decisions of other medical professionals in difficult triage scenarios to assess whether you would delegate a triage situation in the future to those decision makers.<br/><br/>Each scenario is presented followed by how three different medics carried out their assessment and treatment separately for that situation. Their actions are listed in the order they performed them.\n<br/>\n<br/>\nEach medic vignette is then followed by a few questions to assess how you perceived the medic’s decision-making style. <br/><br/>While you work your way through each vignette imagine you have seen a lot of other observations of this medic, and the behavior you see here is typical for how they behave.<br/><br/> Some of the scenarios will seem familiar to you. Please note that there may be differences in the details of the situation you saw and the one you will be evaluating. Specifically, please pay careful attention to what information is revealed to the decision maker, and consider their actions only with respect to the information they were given. Do not consider any information from your experience that might be different or contradictory. <br/><br/>The survey should take about 30 minutes to complete. Thank you for your participation."
                }
            ]
        }
    tool.add_page_by_json(intro_page)
    tool.import_page_from_json(
        os.path.join("survey-configs", "surveyConfig2x.json"), "Note page", None
    )

    # add comparison options to survey
    tool.survey["validSingleSets"] = []
    tool.survey["validOmniSets"] = []
    adms = ['ALIGN-ADM-OutlinesBaseline', 'ALIGN-ADM-ComparativeRegression-ICL-Template', 'TAD-severity-baseline', 'TAD-aligned']
    st_targets = ['vol-human-8022671-SplitHighMulti', 'qol-human-2932740-HighExtreme', 'vol-human-1774519-SplitHighMulti', 'qol-human-6349649-SplitHighMulti', 
                    'vol-human-6403274-SplitEvenBinary', 'qol-human-3447902-SplitHighMulti', 'vol-human-7040555-SplitEvenBinary', 'qol-human-7040555-SplitHighMulti', 
                    'vol-human-2637411-SplitEvenMulti', 'qol-human-3043871-SplitHighBinary', 'vol-human-2932740-SplitEvenMulti', 'qol-human-6403274-SplitHighBinary', 
                    'vol-human-8478698-SplitLowMulti', 'qol-human-1774519-SplitEvenBinary', 'vol-human-3043871-SplitLowMulti', 'qol-human-9157688-SplitEvenBinary', 
                    'vol-human-5032922-SplitLowMulti', 'qol-human-0000001-SplitEvenMulti', 'vol-synth-LowExtreme', 'qol-human-8022671-SplitLowMulti', 'vol-synth-HighExtreme', 
                    'qol-human-5032922-SplitLowMulti', 'vol-synth-HighCluster', 'qol-synth-LowExtreme', 'vol-synth-LowCluster', 'qol-synth-HighExtreme', 'vol-synth-SplitLowBinary', 
                    'qol-synth-HighCluster', 'qol-synth-LowCluster', 'qol-synth-SplitLowBinary']
    ad_targets = ['ADEPT-DryRun-Moral judgement-0.0', 'ADEPT-DryRun-Ingroup Bias-0.0', 'ADEPT-DryRun-Moral judgement-0.1', 'ADEPT-DryRun-Ingroup Bias-0.1', 'ADEPT-DryRun-Moral judgement-0.2', 'ADEPT-DryRun-Ingroup Bias-0.2', 'ADEPT-DryRun-Moral judgement-0.3', 
                    'ADEPT-DryRun-Ingroup Bias-0.3', 'ADEPT-DryRun-Moral judgement-0.4', 'ADEPT-DryRun-Ingroup Bias-0.4', 'ADEPT-DryRun-Moral judgement-0.5', 'ADEPT-DryRun-Ingroup Bias-0.5', 'ADEPT-DryRun-Moral judgement-0.6', 'ADEPT-DryRun-Ingroup Bias-0.6', 'ADEPT-DryRun-Moral judgement-0.7', 'ADEPT-DryRun-Ingroup Bias-0.7', 'ADEPT-DryRun-Moral judgement-0.8', 
                    'ADEPT-DryRun-Ingroup Bias-0.8', 'ADEPT-DryRun-Moral judgement-0.9', 'ADEPT-DryRun-Ingroup Bias-0.9', 'ADEPT-DryRun-Moral judgement-1.0', 'ADEPT-DryRun-Ingroup Bias-1.0']
    for t in st_targets:
        for adm in adms:
            if 'qol' in t:
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'SoarTech', scenario_id='qol-dre-1-eval', append=True
                )
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'SoarTech', scenario_id='qol-dre-2-eval', append=True
                )
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'SoarTech', scenario_id='qol-dre-3-eval', append=True
                )
            else:
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'SoarTech', scenario_id='vol-dre-1-eval', append=True
                )
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'SoarTech', scenario_id='vol-dre-2-eval', append=True
                )
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'SoarTech', scenario_id='vol-dre-3-eval', append=True
                )
    for t in ad_targets:
        for adm in adms:
            if 'Moral' in t:
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'Adept', scenario_id='DryRunEval-MJ2-eval', append=True
                )
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'Adept', scenario_id='DryRunEval-MJ4-eval', append=True
                )
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'Adept', scenario_id='DryRunEval-MJ5-eval', append=True
                )
            else:
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'Adept', scenario_id='DryRunEval-IO2-eval', append=True
                )
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'Adept', scenario_id='DryRunEval-IO4-eval', append=True
                )
                tool.add_db_medic_to_survey_by_details(
                    adm, t, 'Adept', scenario_id='DryRunEval-IO5-eval', append=True
                )
    # pages for treating as AI or Human
    agent_pages = [
        {
            "name": "Treat as Human",
            "elements": [
                {
                    "type": "expression",
                    "name": "Please evaluate these triage decision makers as if they are human medics.",
                    "title": "Please evaluate these triage decision makers as if they are human medics."
                }
            ]
        },
        {
            "name": "Treat as AI",
            "elements": [
                {
                    "type": "expression",
                    "name": "Please evaluate these triage decision makers as if they are an Artificial Intelligence (AI) medic.",
                    "title": "Please evaluate these triage decision makers as if they are an Artificial Intelligence (AI) medic."
                }
            ]
        }
    ]
    tool.survey['agentPages'] = agent_pages

    # add final page
    tool.import_page_from_json(
        os.path.join("survey-configs", "surveyConfig2.1.json"),
        "Post-Scenario Measures",
        None,
    )

    # save changes
    tool.push_changes()
    tool.export_survey_json(os.path.join("survey-configs", "surveyConfig4x.json"))


if __name__ == "__main__":
    LOGGER.log(LogLevel.CRITICAL_INFO, "Welcome to the Delegation Survey Tool")
    LOGGER.log(
        LogLevel.INFO,
        "To get started, enter the version number you'd like to work on, or press enter for more options:",
    )
    resp = input("")
    if resp == "":
        resp = input(
            "Would you like to:\n\t1. Complete the one time intialization\n\t2. Setup survey version 3.0\n\t3. Setup survey version 4.0\n"
        )
        if resp == "1":
            one_time_db_initialization()
        elif resp == "2":
            version3_setup()
        elif resp == "3":
            version4_setup()
        else:
            LOGGER.log(LogLevel.WARN, "Option not recognized. Exiting...")
        exit(0)
    tool = DelegationTool(float(resp))
    while resp != "q":
        try:
            print()
            LOGGER.log(
                LogLevel.CRITICAL_INFO,
                "What would you like to do?\033[37m \n\t\n\tImport Survey from JSON (is)\n\tImport Page from JSON (ip)\n\tImport Image (ii)\n\tImport ADM Medic (m)\n\tDelete Page (dp)\n\tView Current Survey as JSON (v)\n\tExport Current Survey as JSON (e)\n\tClear Survey (c)\n\tSave Changes (s)\n\tQuit (q)",
            )
            # future options: \n\tAdd Page (ap)\n\tAdd Element to Page (ae)\n\tDelete Element From Page (de)
            resp = input("").strip().lower()
            if resp == "is":
                if tool.cur_import_file != "":
                    path = input(
                        f"Enter the path to the import file (enter for {tool.cur_import_file}): "
                    ).strip()
                else:
                    path = input("Enter the path to the import file: ").strip()
                tool.import_full_survey(path if path != "" else tool.cur_import_file)
            if resp == "ip":
                if tool.cur_import_file != "":
                    path = input(
                        f"Enter the path to the import file (enter for {tool.cur_import_file}): "
                    ).strip()
                else:
                    path = input("Enter the path to the import file: ").strip()
                page_name = input("Enter the name of the page to import: ").strip()
                ind = input(
                    "At what index should this page be inserted? (enter to append) "
                ).strip()
                tool.import_page_from_json(
                    path if path != "" else tool.cur_import_file,
                    page_name,
                    int(ind) if ind != "" else None,
                )
            if resp == "m":
                name = input(
                    f"Enter the name of the medic (enter if unknown): "
                ).strip()
                if name == "":
                    adm_name = input(
                        "Enter the name of the ADM (i.e. TAD baseline): "
                    ).strip()
                    alignment = input("Enter the alignment (high or low): ").strip()
                    scenario_writer = input(
                        "Enter the scenario writer (Adept or SoarTech): "
                    )
                    env = input(
                        "Enter the environment (Desert, Submarine, Jungle, or Urban): "
                    )
                    tool.add_db_medic_to_survey_by_details(
                        adm_name, alignment, scenario_writer, environment=env
                    )
                else:
                    tool.add_db_medic_to_survey_by_name(name)
            if resp == "ii":
                path = input("Enter the path of the image to import: ").strip()
                pid = input("Enter the patient id: ").strip()
                des = input("Enter the description of the image: ").strip()
                s_ind = int(input("Enter the scenario index: ").strip())
                tool.add_img_to_db(path, pid, des, s_ind)
            if resp == "dp":
                page_name = input(
                    "Enter the name of the page to delete (only the first page found with this name will be deleted): "
                ).strip()
                tool.delete_page(page_name)
            if resp == "s":
                tool.push_changes()
            if resp == "v":
                survey_copy = copy.deepcopy(tool.survey)
                for p in survey_copy["pages"]:
                    for e in p["elements"]:
                        if "patients" in e:
                            for pat in e["patients"]:
                                pat["imgUrl"] = "Image data omitted from printout."
                print(json.dumps(survey_copy, indent=4))
            if resp == "e":
                path = input(
                    "Where would you like to store the exported json? "
                ).strip()
                tool.export_survey_json(path)
            if resp == "c":
                tool.clear_survey_version()
            if resp == "q":
                if len(tool.changes_summary) > 0:
                    LOGGER.log(
                        LogLevel.WARN,
                        "Changes are not saved. Are you sure you want to quit? (y/n)",
                    )
                    sure = input("").strip()
                    if sure in ["y", "Y", "q"]:
                        break
                    else:
                        resp = ""
        except Exception as e:
            # catch all errors because otherwise all progress will be lost!
            LOGGER.log(
                LogLevel.WARN,
                f"There was an error processing your input. Please try again. {e}",
            )
