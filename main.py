import os
import arcpy
from datetime import datetime
import time
import sys
import logging
import pandas as pd
import json
from src.process_as_built import run_as_built_process  # from src folder in project directory
from src.process_gis_files import run_gis_files_process  # from src folder in project directory
from src.models import survey, SurveyRecord, sign_in_to_agol, sign_in_to_portal, send_email, delete_old_files  # from src folder in project directory

'''
This tool checks the specified survey feature class for new requests (i.e. new features with a null value in the FulfilledDate field).
If a new request is found, it processes the request by calling the appropriate functions from process_as_built.py and/or process_gis_files.py,
depending on the desired output specified by the survey respondent.

It also handles error logging and sends email notifications to the requester and admin as needed.

Some notes about the fields used in the survey layer:
- FulfilledDate is used to check if the request has already been fulfilled. If it is None, it has not been fulfilled.
- utilities is a text field with a comma-separated list of utilities requested (Water, Sanitary, Storm, All) - from multi-choice question in survey
- email is the requester's email address
- specify_desired_output_folder_n is the desired output folder name specified by the user in the
- desired_output is a text field with a comma-separated list of desired outputs (as_builts, gis_files, or both) - from multi-choice question in survey

Before running this script, ensure you have run setup.py to generate the config.json file with necessary configurations.
That file may also be updated manually as needed and should remain in the main directory with this script.

This tool was developed by Mike Hanson, GIS/Asset Mgmt Technician for the City of Rosemount, MN to assist with fulfilling as-built and GIS file requests.

Learn more:
https://github.com/m-hanson-5/As-Built_Downloader

'''

config_path = os.path.join(os.path.dirname(__file__), 'config.json')  # ensure config.json is in the same directory as this script
if not os.path.exists(config_path):
    print("config.json not found. Please run setup.py to generate this file in the main directory.")
    sys.exit(1)

with open(config_path, 'r') as f:
    config = json.load(f)  # Load existing config. This is set up with setup.py. Run that to configure this script.


# set up error variables for an error dictionary
errors = {}
error_counter = 0

def update_fulfilled_date(GlobalID):
    """
    Update the fulfilled date for a given GlobalID and field name.
    """
    # populate the 'as_builts_fulfilled' field with the current date
    if error_counter == 0:
        with arcpy.da.UpdateCursor(survey, ["globalid", "FulfilledDate"]) as cursor:
            for row in cursor:
                if row[0] == GlobalID:
                    row[1] = datetime.now()
                    cursor.updateRow(row)
                    logging.info(f"FulfilledDate updated for GlobalID {GlobalID}")
                    print("\n\n")


try:

    # Configure logging. Set up the directory in this main folder
    project_directory = os.path.dirname(os.path.abspath(__file__))
    log_dir = rf"{project_directory}\Logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    # Create a timestamped log file for file naming
    timestamp = str(datetime.now().strftime('%Y-%m-%d_%H.%M'))

    log_file = os.path.join(log_dir, f"{timestamp}.log")

    logging.basicConfig(filename=log_file, level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(message)s')

    logging.info("Script started")

    GlobalID = None  # defining at the top since error handling references it
    new_folder = None
    requester_email = None
    target_dir = None
    utilities = None
    outputs = None

    # check which environment the survey is in (AGOL or Enterprise) and sign in accordingly
    esri_env = config.get("is_arcgis_online")
    if esri_env:
        sign_in_to_agol()
    else:
        sign_in_to_portal()


    # clear selection in map
    arcpy.SelectLayerByAttribute_management(survey, "CLEAR_SELECTION")

    # **** UPDATE THIS **** Fields to pull from the survey layer
    fields = ["GlobalId", "FulfilledDate", "utilities",
              "email", "specify_desired_output_folder_n", "desired_output", "CreationDate"]
    
    '''
    Some notes about the above fields:

    For easiest configuring of this process, give the fields the exact names as below in your survey layer. Otherwise, adjust all references to these fields in the script.

    - FulfilledDate is used to check if the request has already been fulfilled. If it is None, it has not been fulfilled.
    - utilities is a text field with a comma-separated list of utilities requested (Water, Sanitary, Storm, All) - from multi-choice question in survey
    - email is the requester's email address
    - specify_desired_output_folder_n is the desired output folder name specified by the user in the survey
    - desired_output is a text field with a comma-separated list of desired outputs (as_builts, gis_files, or both) - from multi-choice question in survey
    - CreationDate is used to sort requests by date created, in case multiple requests come in during a single polling interval
    '''

    ## unpacking from esri into SurveyRecord dataclass, stored in dict with globalid as key
    surveyData = {}
    with arcpy.da.SearchCursor(survey, fields) as cursor:
        for row in cursor:
            if row[1] is None: # FulfilledDate is None (i.e. not fulfilled)
          
                # Create a dictionary from the row values and field names
                record_dict = dict(zip(fields, row))

                # Create a SurveyRecord dataclass instance from the dict using keyword argument (kwarg) unpacking
                survey_record = SurveyRecord(**record_dict)
                globalid = survey_record.GlobalId.strip()  # Clean up the GlobalId

                # Store it in a dictionary keyed by globalid
                surveyData[globalid] = survey_record

    # if no valid globalIDs are found, notify the user and exit
    if not surveyData:
        print("No valid GlobalIDs found after checking the FulfilledDate field. Exiting Script.")
        logging.info("No valid GlobalIDs found after checking the FulfilledDate field. Exiting Script.")
        logging.shutdown()
        time.sleep(1)  # Short delay before deleting the log file

        # Delete the log file since we don't need to save these every 15 minutes, or however often this script is set to run
        if os.path.exists(log_file):
            os.remove(log_file)

        sys.exit()

    globalID_list = list(surveyData.keys())

    # Print valid GlobalIDs for debugging
    print("New GlobalIDs:", globalID_list)
    logging.info(f"New GlobalIDs: {globalID_list}")


    ##########################
    # Get spatial data from survey ###
    ##########################

    # Loop through each new survey feature and call the as-built or gis-file processing scripts as needed
    for GlobalID, Record in surveyData.items():
        # GlobalID = GlobalID.strip()  # Clean early

        print(f"Processing GlobalID: {GlobalID}")
        logging.info(f"Processing GlobalID: {GlobalID}")

        # Create a temporary layer from the selection
        selected_survey = "survey_selected"
        arcpy.MakeFeatureLayer_management(survey, selected_survey)
        arcpy.SelectLayerByAttribute_management(
            selected_survey,
            "NEW_SELECTION",
            f"globalid = '{GlobalID}'"
        )


        # Create new_folder variable that takes the value from the "specify_desired_output_folder_n" field from the selected feature in the Survey layer
        folder = Record.folder.strip()
        print(f"New folder name: {folder}")
        logging.info(f"New folder name: {folder}")


        # Check if the folder already exists and if so, append a number to the end of the folder name with an underscore
        # This can be a network path, or a local path that is synced to SharePoint via OneDrive, which is what we do in Rosemount for easy sharing with external requesters
        # **** UPDATE THIS PATH TO YOUR DESIRED OUTPUT LOCATION ****
        target_dir = os.path.join(project_directory, folder)
        
        if os.path.exists(target_dir):
            i = 1
            while os.path.exists(target_dir + "_" + str(i)):
                i += 1
            folder = folder + "_" + str(i)
            target_dir = os.path.join(project_directory, folder)
            print(f"Folder already exists. New folder name: {folder}")
            logging.info(f"Folder already exists. New folder name: {folder}")

        os.mkdir(target_dir)

        # **** UPDATE THIS **** If your output target directory is a onedrive synced folder, you can set it up here. Otherwise, just use the target_dir variable as is.
        # This example assumes you have a OneDrive folder set up to sync with SharePoint,
        one_drive_sync = config.get("onedrive_synced", False)
        if one_drive_sync:
            sharepoint_link = config.get("sharepoint_url") + "/" + folder  # base SharePoint URL from config.json + folder name
            print(f"SharePoint link: {sharepoint_link}")
        else:
            sharepoint_link = target_dir  # if not using OneDrive synced folder, just use the local/network path
        

        as_built_fulfilled = False
        gis_files_fulfilled = False

        # clean up the outputs list in the dictionary by checking if either output has already been fulfilled
        # the original outputs list will be preserved in the feature class. This is just for tracking while running the script
        if Record.as_built_fulfilled is not None and "as_builts" in Record.outputs_list:
            Record.outputs_list.remove("as_builts")

        if Record.gis_files_fulfilled is not None and "gis_files" in Record.outputs_list:
            Record.outputs_list.remove("gis_files")


        ## run the processing scripts depending on desired output (specified in desired_output field)
        if "as_builts" in Record.outputs_list and "gis_files" in Record.outputs_list:
            print("running for both as-builts and GIS files")


            error_counter, errors = run_gis_files_process(Record, selected_survey, target_dir,
                                                          errors, error_counter)

            error_counter, errors = run_as_built_process(Record, selected_survey,target_dir, sharepoint_link,
                                                         errors, error_counter)

            print("Finished processing both as-builts and gis files")

            # update the gis_files_fulfilled field in the survey layer using an update cursor
            update_fulfilled_date(GlobalID)
            print("FulfilledDate updated for GlobalID:", GlobalID)
            logging.info(f"FulfilledDate updated for GlobalID: {GlobalID}")

            print(f"Find files at this directory: {target_dir}")

        elif "as_builts" in Record.outputs_list:
            print("running for as-builts only")
            error_counter, errors = run_as_built_process(Record, selected_survey,target_dir, sharepoint_link,
                                                         errors, error_counter)

            print("Finished processing as-builts only")
            print(f"Find files at this directory: {target_dir}")

            # update the gis_files_fulfilled field in the survey layer using an update cursor
            update_fulfilled_date(GlobalID)
            print("FulfilledDate updated for GlobalID:", GlobalID)
            logging.info(f"FulfilledDate updated for GlobalID: {GlobalID}")

        elif "gis_files" in Record.outputs_list:
            print("running for GIS files only")
            error_counter, errors = run_gis_files_process(Record, selected_survey, target_dir,
                                                          errors, error_counter)
            print("Finished processing gis files only")
            print(f"Find files at this directory: {target_dir}")

            # update the gis_files_fulfilled field in the survey layer using an update cursor
            update_fulfilled_date(GlobalID)
            print("FulfilledDate updated for GlobalID:", GlobalID)
            logging.info(f"FulfilledDate updated for GlobalID: {GlobalID}")

            email_from = config.get("admin_email")    # **** UPDATE THIS IF DESIRED **** Defaults to admin email in config.json otherwise
            subject = "Your GIS Files Request has been Processed"
            line1 = f"Your GIS files have been processed. <br><br><a href='{sharepoint_link}'>Click Here to View Files</a> <br><br><br>Requested Utilities: {utilities}<br>"
            line2 = f"Thanks for using the As-Built / GIS File Downloader."
            line3 = "This is an autogenerated email."
            try:

                send_email(email_from=email_from, email_to=requester_email, subject=subject,
                                line1=line1, line2=line2, line3=line3)
            except Exception as e:
                print(f"Error sending email: {e}")
                logging.error(f"Error sending email to requester: {e}")

        else:
            print("No valid output options selected.")

        # clean up the selected survey layer
        arcpy.management.Delete(selected_survey)

        # clean up old log files
        try:
            delete_old_files(log_dir, days=10)
        except Exception as e:
            print(f"Error deleting old log files: {e}")
            logging.error(f"Error deleting old log files: {e}")

except Exception as e:
    error_counter += 1
    errors[error_counter] = str(e)
    print(f"Error: {e}")
    logging.error(f"Error: {e}")

    if len(errors) > 0:
        timestamp2 = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Convert dictionary to DataFrame
        df_errors = pd.DataFrame(list(errors.items()), columns=['Error Number', 'Error Message'])

        # Convert DataFrame to HTML
        html_errors = df_errors.to_html(index=False)

        # Send an email to admin with the error message
        email = config.get('admin_email')
        send_email(email_from=email, email_to=email, subject="Error in As-Built Downloader Script",
                        line1=f"An error occurred: <br><br>Check the log file for more details: {log_file}<br><br>GloablID: {GlobalID}<br>Folder: {new_folder}<br>Email: {requester_email}<br>Utilities: {utilities}<br>",
                        html_table=html_errors)

        logging.shutdown()
        time.sleep(1)