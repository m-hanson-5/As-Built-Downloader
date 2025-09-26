'''
This script copies PDF files from the as-built drive to a new folder based on selections in the 'Plan Areas' feature class.
It is powered from a survey123 survey
The script also sends an email to the requester with a clickable link to the new folder.
Make sure to update the source and target file paths accordingly.

DEBUGGING
1. Check the log file for errors. See log folder in the main project directory.
2. Make a backup before making changes
3. Change fromEmail to your own. search #debugging3 (2 instances)
3. Turn off Power Automate flow to avoid overloading PWADM and GIS Helpdesk with emails

UPDATES
3/20/2025 - updated to not use map objects since higher processing demands downloading map

Once confirmed working, remove the commented out code
'''

import logging
from datetime import datetime
import os
import sys
import pandas as pd
import shutil
import json
import arcpy
from src.models import survey, plan_areas, approved_emails, send_email
from dataclasses import asdict

config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')  # this should work if config.json is in the main directory (one level up from src)
if not os.path.exists(config_path):
    print("config.json not found. Please run setup.py to generate this file in the main directory.")
    sys.exit(1)
with open(config_path, 'r') as f:
    config = json.load(f)  # Load existing config


def run_as_built_process(Record, selected_survey,target_dir, sharepoint_link, errors, error_counter):
    '''
    This function processes the as-built request by copying PDF files from the source directory to the target directory.

    :param Record: an instance of the SurveyRecord dataclass containing survey data for the current request being processed
    :param selected_survey: the survey being processed by main.py
    :param target_dir: the folder destination in the I: drive based on the user-input output folder name
    :param sharepoint_link: the SharePoint link to the target directory
    :param errors: a dictionary to store error messages
    :param error_counter: a counter to keep track of the number of errors
    :return: error_counter, errors
    '''
    try:

        error_counter = 0
        print("Running as_built process...")
        logging.info("Running as_built process")

        globalID = Record.GlobalId
        requester_email = Record.email
        folder = Record.folder
        target_dir = os.path.join(target_dir, "As-Builts")

        # create the target directory if it doesn't exist
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        # pull in desired variables from SurveyData dictionary, e.g. the values from keys email, water, sanitary, storm, utilities_all, other, as_built, gis_files


        # **** UPDATE ****
        '''
        establish which columns to keep in plan areas layer.
        the ones kept will be used to output a csv file called Index.csv in the target directory.
        This csv file will have a list of all the plan areas that were included in the request and help the requester find the pdf's they need to reference.
        
        '''
        
        all_columns = [
            'OBJECTID', 'ID', 'AB_Date', 'Water', 'Sanitary', 'Storm', 'FiberElec',
            'Grading', 'Hyperlink', 'Comments', 'created_user', 'created_date',
            'last_edited_user', 'last_edited_date', 'Street', 'ProjectNum',
            'ProjectName', 'Shape', 'GDB_GEOMATTR_DATA', 'LFID', 'GlobalID',
            'InstallYear', 'PlanType', 'Irrigation'
        ]

        columns_to_exclude = [
            'created_user', 'created_date', 'last_edited_user', 'last_edited_date',
            'LFID', 'GlobalID', 'PlanType', 'GDB_GEOMATTR_DATA'
        ]

        # Determine columns to keep for final index.csv output file
        columns_to_keep = [col for col in all_columns if col not in columns_to_exclude]
        print(f"Columns to keep: {columns_to_keep}")
        logging.info(f"Columns to keep: {columns_to_keep}")

        # # reselect the new feature in the survey layer based on the global ID passed from main.py
        # selected_survey = "survey_selected"
        # arcpy.MakeFeatureLayer_management(survey, selected_survey)
        # arcpy.SelectLayerByAttribute_management(selected_survey, "NEW_SELECTION",
        #                                         f"globalid = '{GlobalID}'")

        # Select the corresponding feature in the Plan Areas layer based on the selected feature in the Survey layer

        selected_plan_areas = "plan_areas selected"
        arcpy.MakeFeatureLayer_management(plan_areas, selected_plan_areas)

        arcpy.SelectLayerByLocation_management(selected_plan_areas, "INTERSECT", selected_survey)

        # Retrieve the list of selected plan areas and create a list of corresponding PDF filenames
        # Retrieve the selected plan areas and save to planAreaData
        data = []

        # Build the where clause to filter records where fields in utilities_list equal "Yes"
        # first step, construct a list of where clauses for each utility that was checked
        # **** UPDATE **** The below presumes the plan areas layer has yes/no fields for each utility type (Water, Sanitary, Storm)
        if not 'All' in Record.utilities_list:

            # use list comprehension to build the list of where clauses
            where_clauses: list[str] = [f"{util} = 'Yes'" for util in Record.utilities_list if util in columns_to_keep]
            where_clause: str = " OR ".join(where_clauses)  # Use OR to ensure either specified fields is 'Yes'

            # utilities_list example: ['Water', 'Sanitary'] -> where_clause: "Water = 'Yes' OR Sanitary = 'Yes'"
            print(f"Where Clause: {where_clause}")
            logging.info(f"Where Clause: {where_clause}")

        else:
            where_clause: str = "1=1"  # Select all records if 'All' is checked

        # Add the where clause to the selected plan areas layer
        with arcpy.da.SearchCursor(selected_plan_areas, columns_to_keep, where_clause=where_clause) as cursor:
            for row in cursor:
                data.append(row)

        # Convert to DataFrame for easy conversion to csv later
        planAreaData = pd.DataFrame(data, columns=columns_to_keep)

        # Retrieve the list of selected plan areas and create a list of corresponding PDF filenames
        # save pdf_list from the planAreaData "ID" column

        # Retrieve the list of PDF filenames from the "ID" column in the DataFrame
        pdf_list = [str(id) + ".pdf" for id in planAreaData['ID']]
        print(f"PDF List: {pdf_list}")
        logging.info(f"PDF List: {pdf_list}")

        source_directory = config.get('as_built_directory')
        if not source_directory or not os.path.exists(source_directory):
            print(f"Source directory {source_directory} does not exist. Please check the path in config.json.")
            logging.error(f"Source directory {source_directory} does not exist. Please check the path in config.json.")
            error_counter += 1
            errors[error_counter] = f"Source directory {source_directory} does not exist."
            return error_counter, errors

        pdfCount = 0
        missing_pdfs = []
        # Copy PDF files from the source to the target directory
        try:
            for pdf_name in pdf_list:
                source_path = os.path.join(source_directory, pdf_name)
                target_path = os.path.join(target_dir, pdf_name)

                # Check if the source_path exists, and if not, extract the path from the corresponding hyperlink in the planAreaData
                if not os.path.exists(source_path):

                    filtered_data = planAreaData.loc[planAreaData['ID'] == pdf_name.split('.')[0]]
                    if filtered_data.empty:
                        print(f"No matching record found for pdf_name: {pdf_name}")
                        logging.error(f"No matching record found for pdf_name: {pdf_name}")
                        missing_pdfs.append(pdf_name)
                        #if it's empty, it will go to the next iteration in the loop, bypassing the below
                        continue

                else:
                    print(f"Valid source path: {pdf_name}. Copying to target directory")
                    logging.error(f"pdf_name source path exists: {pdf_name}")

                    print(f"Target path (raw): {target_path}")
                    print(f"Target path (repr): {repr(target_path)}")

                    shutil.copyfile(source_path, target_path)
                    print("Copied")
                    pdfCount += 1
                    print("Incremented counter")

            # Print the number of hyperlinks found for the missing pdfs
            print(f"Total count of missing pdfs: {len(missing_pdfs)}")
            logging.info(f"Total count of missing pdfs with hyperlinks: {len(missing_pdfs)}")

            print("Missing pdf's:", missing_pdfs)
            logging.info(f"Missing pdf's: {missing_pdfs}")

            print(
                f"\nNew folder with requested PDFs created for GlobalID {globalID} at this location: {target_dir}")
            logging.info(
                f"New folder with requested PDFs created for GlobalID {globalID} at this location: {target_dir}")
            print(f"There should be {pdfCount} PDFs in the folder.")
            logging.info(f"There should be {pdfCount} PDFs in the folder.")

        except Exception as e:
            print(f"An error occurred while processing GlobalID {globalID}: {e}")
            logging.error(f"An error occurred while processing GlobalID {globalID}: {e}")

            # increment error counter and add to the dictionary
            error_counter += 1
            errors[error_counter] = e

            return error_counter, errors


        logging.info("Preparing data for csv export")

        # add field to planAreaData dataframe called status. This will be included in the index.csv file to help the requester know which plan areas were included in the request
        # set the default value to 'Included'
        planAreaData['Status'] = 'Included'
        # strip the .pdf from the missing pdfs
        missing_pdfs = [pdf.split('.')[0] for pdf in missing_pdfs]
        # update Status column for missing pdfs and set to 'Not found'
        planAreaData.loc[planAreaData['ID'].isin(missing_pdfs), 'Status'] = 'Not found'
        # move the status column right after the ID column and remove the OBJECTID and Comments columns
        planAreaData = planAreaData[['ID', 'Status', 'AB_Date', 'Water', 'Sanitary', 'Storm', 'FiberElec', 'Grading', 'Street', 'Hyperlink', 'ProjectNum', 'ProjectName', 'InstallYear', 'Irrigation']]

        print(rf"Saving to a csv at: {target_dir}\Index.csv")
        logging.info(rf"Saving to a csv at: {target_dir}\Index.csv")
        # save the df to a csv file
        planAreaData.to_csv(os.path.join(target_dir, 'Index.csv'), index=False)

        try:
            # **** UPDATE THIS **** change name of the 'as_builts_fulfilled' field to whatever you named it in your survey results layer
            # This as-built tracking field is required, as it is the basis for the script to determine which requests have not yet been fulfilled
            # # populate the 'as_builts_fulfilled' field with the current date
            if error_counter == 0:
                with arcpy.da.UpdateCursor(survey, ["globalid", "as_builts_fulfilled"]) as cursor:
                    for row in cursor:
                        if row[0] == globalID:
                            row[1] = datetime.now()
                            cursor.updateRow(row)
                            print(f"as_builts_fulfilled updated for GlobalID {globalID}")
                            print("\n\n")
        except Exception as e:
            print(f"An error occurred while updating the as_builts_fulfilled date for GlobalID {globalID}: {e}")
            logging.error(f"An error occurred while updating the as_builts_fulfilled date for GlobalID {globalID}: {e}")

            # increment error counter and add to the dictionary
            error_counter += 1
            errors[error_counter] = e

            return error_counter, errors


        ##### DEFINE MODULAR PIECES OF EMAIL FUNCTION ######


        # Create a clickable link for the target directory
        TEXT_no_gis_files = f"""
         <html>
             <body>
                 <p>Your As-Built download request [{folder}] has been fulfilled. A total of {pdfCount} as-built records was found in the specified search area.</p>
                 <p>Please find the requested pdfs at the below link. It may take several minutes for the files to upload.</p>
                 <p><a href="{sharepoint_link}">Click Here to View Files</a></p>
                 <p>Thank you for using the As-Built Downloader.</p>
                 <p>[This is an autogenerated email]</p>
                 <p></p>
             </body>
         </html>
         """

        TEXT_gis_files = f"""
         <html>
             <body>
                 <p>Your As-Built download request [{folder}] has been fulfilled. A total of {pdfCount} as-built records were found in the specified search area.</p>
                 <p>Please find the requested pdfs at the below link, as well as GIS files (shapefiles and Esri File Geodatabase). It may take several minutes for the files to upload.</p>
                 <p><a href="{sharepoint_link}">Click Here to View Files</a></p>
                 <p>Thank you for using the As-Built Downloader.</p>
                 <p>[This is an autogenerated email]</p>
                 <p></p>
             </body>
         </html>
         """

        TEXT_Unknown_User = f"""
        <html>
            <body>
                <p>An As-Built download request has been submitted by an unknown user. A total of {pdfCount} records were found in the specified search area.</p>
                <p>The unknown user's email address is: {requester_email}</p>
                <p>If this is a valid user, please forward the files to the appropriate recipient and add them to the approved list in the config.json file.</p>
                <p>The requested files can be found at the following location:</p>
                <p><a href="{sharepoint_link}">Click Here to View Files</a></p>
                <p>Thank you for using the As-Built Downloader.</p>
                <p>[This is an autogenerated email]</p>
                <p></p>
            </body>
        </html>
        """

        Subject = "Your As-Built Download Request Has Been Fulfilled"
        Subject2 = "Your As-Built Download Request Has Been Partially Fulfilled"
        Subject_Unknown_User = "! As-Built Requester Unknown: " + requester_email

        try:

            # **** UPDATE THIS **** no change needed if approved emails are configured in config.json (from setup.py)
            # Also change email_from and email_to if needed
            if requester_email.lower() in approved_emails:
                # Send an email to the requester with the target directory link

                # change to pwad when not debugging, own email while debugging (#debugging3)
                email_from = config.get('admin_email')   # you may choose to hardcode another email here
                email_to = requester_email
                subject = Subject
                line1 = TEXT_gis_files if 'gis_files' in Record.outputs_list else TEXT_no_gis_files
                send_email(email_from, email_to, subject, line1)

            else:
                # send to the Admin or GIS Helpdesk if unknown user (requester email not on approved_emails list in config.json)
                email_from = config.get('admin_email')   # you may choose to hardcode another email here
                email_to = config.get('admin_email')   # you may choose to hardcode another email here, such as a GIS Helpdesk email
                subject = Subject_Unknown_User
                line1 = TEXT_Unknown_User
                # convert surveyData to a DataFrame
                df_survey = pd.DataFrame([asdict(Record)])
                html_table = df_survey.to_html(index=False, border=1)

                send_email(email_from, email_to, subject, line1, html_table)

        except Exception as e:
            print(f"An error occurred while sending the email: {e}")
            logging.error(f"An error occurred while sending the email: {e}")

            # increment error counter and add to the dictionary
            error_counter += 1
            errors[error_counter] = e
            print("Error counter incremented")

            return error_counter, errors

    except Exception as e:
        print(f"An error occurred while sending the email: {e}")
        logging.error(f"An error occurred while sending the email: {e}")

        # increment error counter and add to the dictionary
        error_counter += 1
        errors[error_counter] = e
        print("Error counter incremented")

        return error_counter, errors

    return error_counter, errors   # this is passed to main.py
    print("end as-built process")

    # print("Cleaning up log csv") # this isn't working as expected. Come back to it sometime
    # # open the log csv and delete all records where (the Timestamp is more than 12 hours old and the Summary is "No new records"). If the record is not "No new records", keep it.
    # df = pd.read_csv(log_csv)
    # df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%m/%d/%Y  %I:%M:%S %p', errors='coerce')
    # df = df[(df['Timestamp'] > datetime.now() - pd.Timedelta(hours=12)) | (df['Summary'] != "No new records")]
    # # sort newest to oldest
    # df = df.sort_values(by='Timestamp', ascending=False)
    # df.to_csv(log_csv, index=False)



