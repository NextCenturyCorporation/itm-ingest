# Delegation Survey Tools
There are two delegation survey tools in this directory, both of which share the goal of updating the delegation survey configuration in mongo for ease of use in the dashboard.

## Tool 1: Update Survey Config
The first tool is `update_survey_config.py`. This tool contains several functions for creating and editing survey configurations. Upon running the script, you will be presented with 2 options. 

### Option 1: Command Line Tool
If you enter a survey version number at the beginning of the script running, a menu will appear with options for editing that survey. If you enter a survey version number that does not exist, a new one will be automatically created for you. The options are as follows:
- Import Survey from JSON (is)
- Import Page from JSON (ip)
- Import Image (ii)
- Import ADM Medic (m)
- Delete Page (dp)
- View Current Survey as JSON (v)
- Save Changes (s)
- Quit (q)

Note that no changes will be saved (except for importing images) until the `s` option has been selected and confirmed.

#### Import Survey from JSON 
Parameters: 
- path of file to import
This takes survey data from a JSON file and overwrites the current survey version with that data. All other data will be lost. The survey version will be changed to whatever version you entered at the beginning of the command line tool. For example, if you import survey data with version=2.0, but you started the command line tool with version=3.0, the survey data will be imported directly from the file, except the version will now be 3.0. 

#### Import Page from JSON
Parameters:
- path of file with the page to import
- name of page to import
- the index at which to insert the page
This searches through the file found at the path given for the first page with a name matching the second parameter. If the page is found, it will be inserted at the index entered (or appended, if no index is given).

#### Import Image
Parameters:
- path of image to import
- patient id that should be attached to the image
- description of the image
- scenario index the image belongs to
This is an immediate action. It does not wait for you to confirm with a `save` command. It will convert the image from the image path into a dataurl and either add a new entry to the database for that image with the other data given, or, if the dataurl was already found in the database, it will just add the patient id to the list of valid patient ids for that image.

#### Import ADM Medic
Parameters:
- medic name
OR
- ADM name (i.e. TAD baseline)
- aliginment (high/low)
- scenario writer (Adept/SoarTech)
- environment (Desert/Submarine/Jungle/Urban)
This will search the admMedics collection in mongo to find a single adm medic, either by the medic's unique name or several parameters, which, when combined, uniquely define an ADM. Once the medic is found, it will be added to the end of the non-omnibus medic section of the survey.

#### Delete Page
Parameters:
- page name
Deletes the first page found in the survey with the given name

#### View Current Survey as JSON
Prints out the current survey, including unsaved changes.

#### Save Changes
Prints the list of changes that will be saved, and exports all changes to the databse.

#### Quit
Exits the program. Confirms your desire to quit if there are unsaved changes.


### Option 2: One-Time Initialization
If you press `Enter` upon running the script, a one-time initialization script will be run.
This script will add survey versions 0.0 (test survey config, equivalent to survey config 2x but without any required questions), 1.0, and 2.0 to the mongo database. You _must_ run this script, or use the command line tool to complete the equivalent actions, in order for the dashboard to work. This script will also add missing images, or missing patient ids for each image, to the database. This will need to be run before running Tool 2.


## Tool 2: Convert ADMs for Delegation
The overall goal is to take adm actions/responses and map them out into the proper delegation survey configuration format. Ensure you have already run the one-time initialization using Tool 1 before proceeding.

### Running the Tool
To run this tool, run `python3 convert_adms_for_delegation.py`.


## Recommendations for Setup
- Run `python3 update_survey_config.py` and press `Enter` for one-time initialization. This will add the three initial survey versions (0.0, 1.0, 2.0) and correct patient ids for images to the database.
- Run `python3 convert_adms_for_delegation.py`. This will add the adm medics to the database. 
