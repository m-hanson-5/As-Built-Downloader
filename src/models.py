import os
from datetime import datetime
import logging
from dataclasses import dataclass, field
from typing import Optional, List
import psutil
import subprocess
import json
import arcpy

user = os.getlogin()

# Get the path to config.json, doubling up os.path.dirname to go up one level from src
# Running setup.py guides the user through creating this file. If you haven't run that, do so first
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')

# load the config json file
with open(config_path, 'r') as f:
    config = json.load(f)


survey = config.get('survey_path', "UNDEFINED")

# get plan_areas_path from config
plan_areas = config.get('plan_areas_path', "UNDEFINED")

# get approved_emails from config
approved_emails_list = config.get('approved_emails', [])
approved_emails = tuple(approved_emails_list)  # convert to tuple for easier use in arcpy
admin_email = config.get('admin_email', None)  # optional; can be None

'''
This dataclass represents a survey record with various attributes related to the survey.
It includes methods to initialize and process the data.

Feel free to update these fields to match your survey schema, or, if you don't want to hunt down every reference, it
may be easier to just update the part of the code where the survey is loaded into this dataclass. 
'''
@dataclass
class SurveyRecord:
    GlobalId: str
    email: str
    desired_output: str
    CreationDate: Optional[datetime] = None
    FulfilledDate: Optional[datetime] = None
    as_built_fulfilled: Optional[datetime] = None
    gis_files_fulfilled: Optional[datetime] = None
    specify_desired_output_folder_n: str = ""
    folder: str = "" # the above field will store here based on the output folder name specified by the user in the survey
    utilities: str = ""
    utilities_other: str = ""
    other: str = ""
    other: bool = False
    as_built: bool = False
    gis_files: bool = False
    utilities_list: list = field(default_factory=list)      # Improves Optional[list] by initializing empty list / avoiding NoneTypeError
    outputs_list: list = field(default_factory=list)


    def __post_init__(self):
        self.GlobalId = self.GlobalId.strip()

        # Set the folder name based on long field name
        if self.specify_desired_output_folder_n:
            self.folder = self.specify_desired_output_folder_n.strip()

        # Also, set as_built and gis_files flags from desired_output
        self.outputs_list = self.desired_output.lower().split(",") if self.desired_output else []
        self.as_built = 'as_built' in self.outputs_list
        self.gis_files = 'gis_files' in self.outputs_list
        self.utilities_list = self.utilities.split(",") if self.utilities else []


# **** UPDATE THIS **** Input the layers you would like to include in your GIS files output here,
# along with the fields you would like to include and the path or url to the feature server for each layer
# Note that the field names are case-sensitive and must match exactly
# This is used exclusively by the process_gis_files.py script
# Below is an example of Rosemount's utility layer structure
layer_dict = {
    'Curb Stop': {
        "fields": ["FacilityID", "Diameter", "InstallYear", "LifeCycleStatus"],
        "path": "/layers/curb_stop"
    },
    'System Valve': {
        "fields": ["FacilityID", "Diameter", "ValveType", "WaterType", "LifeCycleStatus"],
        "path": "/layers/system_valve"
    },
    'Fire Hydrant': {
        "fields": ["FacilityID", "LifeCycleStatus", "WaterType"],
        "path": "/layers/fire_hydrant"
    },
    'Water Main': {
        "fields": ["FacilityID", "LifeCycleStatus", "Material", "Diamater", "WaterType"],
        "path": "/layers/water_main"
    },
    'Water Lateral': {
        "fields": ["FacilityID", "LifeCycleStatus", "Material", "Size", "Type", "WaterType"],
        "path": "/layers/water_lateral"
    },
    'Sanitary Clean Out': {
        "fields": ["FacilityID", "LifeCycleStatus", "TopElev"],
        "path": "/layers/sanitary_clean_out"
    },
    'Sanitary Gravity Main': {
        "fields": ["FacilityID", "LifeCycleStatus", "Material", "Diameter", "InstallYear"],
        "path": "/layers/sanitary_gravity_main"
    },
    'Sanitary Force Main': {
        "fields": ["FacilityID", "LifeCycleStatus", "Material", "Size", "InstallYear"],
        "path": "/layers/sanitary_force_main"
    },
    'Sanitary Lateral Line': {
        "fields": ["FacilityID", "Material", "Diameter", "InstallYear", "LifeCycleStatus"],
        "path": "/layers/sanitary_lateral_line"
    },
    'Sanitary Manhole': {
        "fields": ["FacilityID", "LifeCycleStatus", "InstallYear", "TopElev"],
        "path": "/layers/sanitary_manhole"
    },
    'Sanitary Valve': {
        "fields": ["FacilityID", "LifeCycleStatus"],
        "path": "/layers/sanitary_valve"
    },
    'Sanitary Lift Station': {
        "fields": ["FacilityID"],
        "path": "/layers/sanitary_lift_station"
    },
    'Storm Mains': {
        "fields": ["FacilityID", "Material", "Measurement1", "InstallDate", "LifeCycleStatus"],
        "path": "/layers/storm_mains"
    },
    'Storm Inlets': {
        "fields": ["FacilityID", "LifeCycleStatus", "Type", "InstallDate"],
        "path": "/layers/storm_inlets"
    },
    'Storm Forcemains': {
        "fields": ["FacilityID", "Material", "Measurement1", "InstallDate", "LifeCycleStatus"],
        "path": "/layers/storm_forcemains"
    },
    'Storm Lift Station': {
        "fields": ["FacilityID", "LifeCycleStatus"],
        "path": "/layers/storm_lift_station"
    },
    'Storm Manholes': {
        "fields": ["FacilityID", "LifeCycleStatus", "Type"],
        "path": "/layers/storm_manholes"
    },
    'Storm Outlets': {
        "fields": ["FacilityID", "Type", "Sump", "LifeCycleStatus"],
        "path": "/layers/storm_outlets"
    }
}


# ****UPDATE THIS**** Further categorize layers for easier selection based on survey inputs. Ensure all layers above are included in one of these lists
water_layers = ["Curb Stop", "System Valve", "Fire Hydrant", "Water Main", "Water Lateral"]
sanitary_layers = ["Sanitary Clean Out", "Sanitary Gravity Main", "Sanitary Force Main", "Sanitary Lateral Line",
                   "Sanitary Manhole", "Sanitary Valve", "Sanitary Lift Station"]
storm_layers = ["Storm Mains", "Storm Inlets", "Storm Forcemains", "Storm Lift Station", "Storm Manholes", "Storm Outlets"]

# In Rosemount, we send the initial request confirmation email from PowerAutomate, but this function is used to send the final email
# with the file path link, as well as any error notifications to the GIS team
def send_email(email_from=admin_email, email_to=admin_email, subject="",
               line1="", line2="", html_table=None, line3="", cc=None, attachment_list: Optional[List[str]] = None):
    '''
    This function sends an email using Microsoft Graph API with the provided details.
    It supports HTML content and can send to multiple recipients.
    Lines 1-3 are offered as parameters to make more user-friend, but if you prefer to configure the whole body in line1 using html, that's fine too.

    Parameters:
    - email_from: The sender's email address. The default is the admin_email from config.json.
    - email_to: Handles a single string or list of recipient email addresses. The default is the admin_email from config.json.
    - cc: A list of CC email addresses. Default is None.
    - subject: The subject of the email.
    - line1: The first line of the email body.
    - line2: The second line of the email body.
    - html_table: An optional HTML table to include in the email body.
    - line3: An optional third line of the email body below the optional html table.
    - attachment_list: Optional list of file paths to attach to the email.


    '''
    
    import msal
    import requests
    import base64
    import mimetypes  # for discerning attachment file types

    # Azure AD App credentials
    # These are retrieved from the config file, which is configured by running setup.py
    # **** UPDATE **** This will work as-is, if you supplied these credentials when running setup.py, but you may want to make more secure.
    # Consider using environment variables or a secure vault instead.
    # to get from environment variables, use: os.environ.get("client_id"). 
    # These can be setup in cmd with: setx client_id "your_client_id_here"
    # If you switch to a more secure method, open config.json and remove the values you previously supplied

    # **** UPDATE **** - these lines retrieve from config, but you may want to change how you retrieve these values
    # to get from environment variables, use: os.environ.get("client_id"). Environment Variables can be set up in cmd with: setx client_id "your_client_id_here"  (include quotes)
    client_id = config.get("client_id")       
    tenant_id = config.get("tenant_id")
    client_secret = config.get("client_secret")

    # The email information
    email_from = email_from.strip().strip('"').strip("'") if email_from else None
    if isinstance(email_to, str):  # Check if it's a single email address as a string
        email_to = [email_to.strip().strip('"').strip("'")]  # Make it a list of one element
    else:
        email_to = [email.strip().strip('"').strip("'") for email in email_to]

    if cc is not None:
        if isinstance(cc, str):
            cc = [cc.strip().strip('"').strip("'")]
        else:
            cc = [email.strip().strip('"').strip("'") for email in cc]

    subject = subject
    line1 = line1
    line2 = line2    # optional; can configure the whole body in line1
    html_table = html_table
    line3 = line3 # optional; any text after the table (if there is one)


    # Create an instance of the MSAL confidential client
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=authority,
        client_credential=client_secret,
        token_cache=None
    )

    # Acquire a token for the Microsoft Graph API
    scope = ["https://graph.microsoft.com/.default"]
    result = app.acquire_token_for_client(scopes=scope)


    if 'access_token' in result:
        # Create the email message payload
        # Email data with the HTML table

        # Read folium_map HTML content if provided
        folium_map_content = None

        attachments = []

        if attachment_list:
            for path in attachment_list:
                with open(path, 'rb') as file:
                    attachment_content = base64.b64encode(file.read()).decode('utf-8')
                    mime_type, _ = mimetypes.guess_type(path)
                    if not mime_type:
                        mime_type = "application/octet-stream"
                    attachments.append({
                        "@odata.type": "#microsoft.graph.fileAttachment",
                        "name": os.path.basename(path),
                        "contentType": mime_type,
                        "contentBytes": attachment_content
                    })

        email_content = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",  # Set content type to HTML
                    "content": f"""
                        <html>
                            <body>
                                <p>{line1}</p>
                                <p>{line2}</p>
                                {html_table + '<br>' if html_table is not None else ""}
                                {line3 + '<br>' if line3 != '' else ""}
                            </body>
                        </html>
                    """
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": email
                        }
                    } for email in email_to
                ],
                "ccRecipients": [
                    {
                        "emailAddress": {
                            "address": email
                        }
                    } for email in cc
                ] if cc else []
            },
            "saveToSentItems": "true"
        }

        # attach folium map
        # Add attachment directly from the file path (local file)
        if attachments:
            email_content["message"]["attachments"] = attachments   

        # Send the email using Microsoft Graph API
        graph_api_endpoint = f'https://graph.microsoft.com/v1.0/users/{email_from}/sendMail'
        headers = {
            'Authorization': 'Bearer ' + result['access_token'],
            'Content-Type': 'application/json' #,
            # 'x-anchor-mailbox': email_from
        }
        response = requests.post(graph_api_endpoint, json=email_content, headers=headers)

        if response.status_code == 202:
            print("Email sent successfully")
        else:
            print(f"Failed to send email. Status code: {response.status_code}, Response: {response.text}")
    else:
        print(f"Failed to acquire token: {result.get('error_description')}")

# Sign in to Portal
def sign_in_to_portal():
    '''

     Sign in to ArcGIS Portal using credentials from config.json.
     **** UPDATE **** - if a more secure method is desired
     
     Note: this function uses user credentials stored in config.json, which is not the most secure method.
     Consider using environment variables or a secure vault instead. If you do so, clean up config.json by removing these values after.
     
     '''

    try:
        portal_url = config.get("portal_url")
        if not portal_url:
            print("Portal URL not configured in config.json.")
            portal_url = input("Input Portal URL and press Enter to continue...: ")
            config["portal_url"] = portal_url
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            print("Portal URL saved to config.json.")

        portal_username = config.get("portal_username")
        if not portal_username:
            print("Portal username not configured in config.json.")
            portal_username = input("Input Portal Username and press Enter to continue...: ")
            config["portal_username"] = portal_username
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            print("Portal username saved to config.json.")

        portal_password = config.get("portal_password")
        if not portal_password:
            print("Portal password not configured in config.json.")
            portal_password = input("Input Portal Password and press Enter to continue...: ")
            config["portal_password"] = portal_password
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            print("Portal password saved to config.json.")

        arcpy.SignInToPortal(portal_url,
                             portal_username,
                             portal_password)
        print(f"Successfully signed in to: {portal_url}")
    except Exception as e:
        print(f"Failed to sign in: {e}")

def sign_in_to_agol():
    try:
        agol_url = r"https://www.arcgis.com"

        agol_username = config.get("agol_username")
        if not agol_username:
            print("ArcGIS Online username not configured in config.json.")
            agol_username = input("Input ArcGIS Online Username and press Enter to continue...: ")
            config["agol_username"] = agol_username
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            print("ArcGIS Online username saved to config.json.")

        agol_password = config.get("agol_password")
        if not agol_password:
            print("ArcGIS Online password not configured in config.json.")
            agol_password = input("Input ArcGIS Online Password and press Enter to continue...: ")
            config["agol_password"] = agol_password
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=4)
            print("ArcGIS Online password saved to config.json.")

        arcpy.SignInToPortal(agol_url,
                             agol_username,
                             agol_password)
        print(f"Successfully signed in to: {agol_url}")

    except Exception as e:
        print(f"Failed to sign in: {e}")



def delete_old_files(directory, days=10):
    """
    Deletes files older than a specified number of days in a given directory.
    This is used in this script to clean up old log files to keep it clean.
    
    Args:
        directory (str): The path to the directory to clean up.
        days (int): The age of files in days to delete. Default is 30 days.
    """
    import os
    import time

    now = time.time()
    cutoff = now - (days * 86400)  # Convert days to seconds

    print(f"Deleting files older than {days} days in directory: {directory}")
    print("Deleting files from the following dates:\n\n")
    for filename in os.listdir(directory):
        file_path = os.path.join(directory, filename)
        mod_date = time.ctime(os.path.getmtime(file_path))
        if os.path.isfile(file_path) and os.path.getmtime(file_path) < cutoff:
            print(mod_date)
            os.remove(file_path)
