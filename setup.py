import json
import os
import getpass
import platform

'''
This setup script will guide you through setting up some variables needed for the as-built downloader tool.
As you go through it, the config.json file will be created or updated with your inputs.

This setup script was put together hastily before the conference. It is by no means thoroughly vetted for all issues you may encounter,
but it worked for me. I hope it helps you get started, but if you encounter issues, please open the config.json and manually input the 
paths, credentials, and other details needed to run the tool.

Happy to receive any quick questions or suggestions by email or in github, though I am not actively maintaining this tool or available for intensive support.
This tool assumes basic familiarity with Python, ArcGIS Pro, and the command line.

- Mike Hanson, City of Rosemount GIS

'''

def main():
    
    
    # Load config.json
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')  # ensure config.json is in the same directory as this script
    if not os.path.exists(config_path):
        print("config.json not found. Please ensure it is in the same directory as this script.")
        return

    with open(config_path, 'r') as f:
        config = json.load(f)  # Load existing config

    # Prompt user for input to update config.json
    print("Let's get some configuration details for your setup. These will be saved in config.json.")

    while True:
        esri_environment = input(
            "Is your survey layer hosted in ArcGIS Online (A) or ArcGIS Enterprise (E)? (Enter 'A', 'E', or press Enter to skip): "
        ).strip().lower()
        if esri_environment == "a":
            config["is_arcgis_online"] = True
            config["agol_username"] = input("Enter your ArcGIS Online username: ").strip()
            config["agol_password"] = input("Enter your ArcGIS Online password: ").strip()
            
            config["portal_url"] = "https://yourdomain.com/portal"  # setting placeholder value
            config["portal_username"] = ""  # setting placeholder value
            config["portal_password"] = ""  # setting placeholder value
            break
        elif esri_environment == "e":
            config["is_arcgis_online"] = False
            config["portal_url"] = input("Enter your ArcGIS Enterprise portal URL (e.g. https://yourdomain.com/portal): ").strip()
            config["portal_username"] = input("Enter your ArcGIS Enterprise username: ").strip()
            config["portal_password"] = getpass.getpass("Enter your ArcGIS Enterprise password (input will be hidden): ").strip()

            config["agol_username"] = ''  # setting placeholder value
            config["agol_password"] = ''  # setting placeholder value
            break
        elif esri_environment == "":
            print("Skipping ArcGIS credential setup. Check config.json to manually configure or rerun setup.py.")
            break
        else:
            print("Invalid input. Please enter 'A' for ArcGIS Online, 'E' for ArcGIS Enterprise, or press Enter to skip.")
     

    # get path to plan areas layer, or similar spatial data source representing as-built extents
    if config.get("plan_areas_path"):
        override = input(f"Using existing plan areas path from config.json: {config.get('plan_areas_path')}. Input (O) to override: ").strip().lower()
        if override == 'o':
            print("Enter the path or endpoint below to your plan areas layer (e.g. shapefile, feature class, feature service, etc.)")
            print("Note, this layer should symbolize the extent of as-built documents and the ID field should match the filename of as-built documents.")
            print("You may need to adjust schema or process_as_built.py before running main.py if your field names are different.")
            config['plan_areas_path'] = input("Path: ").strip()
    else:
        print("Enter the path or url to your plan areas layer (e.g. shapefile, feature class, etc.)")
        config['plan_areas_path'] = input("This layer should symbolize the extent of as-built documents: ").strip()

    # save config so far
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    print("Partial config.json updated successfully.\n")

    print("\nNext, let's get the emails of approved users of this tool. They can also be updated later in config.json or by re-running setup.")

    if config.get("approved_emails"):
        emails = config.get("approved_emails", [])
        print(f"Using existing approved emails from config.json: {', '.join(emails)}. Edit in json if necessary.")
    while not config.get("approved_emails"):
        print("Enter approved emails below, separating multiple emails with commas")
        print("These emails can be adjusted as needed in config.json later. If you would like to skip this step, just press Enter.")
        emails = input("Approved emails: ")
        # Split and strip whitespace
        emails = [e.strip() for e in emails.split(",") if e.strip()]
        config["approved_emails"] = emails

    # save json progress
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    print("Json progress saved.\n")

    # get path to survey layer, or similar spatial data source representing survey records
    print("\nNow let's get the path to your survey123 results layer.")
    print("This layer holds the requests for as-built documents or gis files.")
    print("Would you like to see the City of Rosemount's survey form as an example? A browser window will open if 'y'. (y/n): ")
    if input().strip().lower() == 'y':
        survey_link = "https://survey123.arcgis.com/share/bfd1ce1dc08249688b0f8f95f962352b"
        # open the survey link in the default web browser
        if platform.system() == "Windows":
            os.startfile(survey_link)
        else:
            print("Please open the following link in your web browser:")
            print(rf"https://survey123.arcgis.com/share/bfd1ce1dc08249688b0f8f95f962352b")
    input("Press Enter when you're ready to continue...")
    print("Enter the URL or path to your survey layer (FeatureServer URL)")
    print("example: https://services2.arcgis.com/a9dgl29gs8dj/arcgis/rest/services/survey123_{item_ID_here}/FeatureServer/0")
    config['survey_path'] = input("Survey layer URL: ").strip()

    # save
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

    config['admin_email'] = input("Enter the admin email (for error notifications): ").strip()

    #save config so far
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    print("Partial config.json updated successfully.\n")

    print("\nIn order for the email functions to work as is, you must use an Outlook/Exchange email account. Please configure an app in Azure AD and generate a client secret.")
    print("You will need to configure the app with permissions to send email on behalf of the user. It works with Mail.Read, Mail.Send permissions, though not sure the minimum required.")
    print("When prompted, you will need to enter the client ID, tenant ID, and client secret.")
    app_credentials = input("Press Enter when you're ready to continue, or else enter 'skip' to skip this step (you can manually edit config.json later): ")
    if app_credentials == 'skip':
        config['client_id'] = ''  # setting placeholder value
        config['tenant_id'] = ''  # setting placeholder value
        config['client_secret'] = ''  # setting placeholder value

        print("Skipping Azure AD app credentials setup. Remember to manually edit config.json later with these credentials or set up another retrieval method.")
        print("Note: these app credentials are used in the send_email() function in models.py. There are more comments there with further security considerations.")
    else:
        config['client_id'] = input("Enter the Azure AD app client ID: ").strip()
        config['tenant_id'] = input("Enter the Azure AD tenant ID: ").strip()
        config['client_secret'] = input("Enter the Azure AD app client: ").strip()
        print("Credentials stored in config.json. Ensure you keep this file secure.")
        print("Consider storing these values in environment variables or a secure vault if concerned about security.")
        print("Note: these credentials are used in the send_email() function in models.py. There are more comments there with further security considerations.")
        print("\nMoving on..")

    # save
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

    print("Now, please provide the default output directory where you would like the as-built files to be saved.")
    print("Each request will generate a subfolder within this directory based on the user input value in the survey for 'Specify desired output folder name'.")
    if not config.get('output_directory'):
        config['output_directory'] = input("Enter the full path to your desired output directory: ").strip()

    else:
        override = input(f"Using existing output directory from config.json: {config.get('output_directory')}. Input (O) to override: ").strip().lower()
        if override == 'o':
            config['output_directory'] = input("Enter the full path to your desired output directory: ").strip()
            print("Override accepted.")
    # check if the path exists:

    # save
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    # Sharepoint / OneDrive setup (okay if not using Sharepoint)
    sharepoint_sync = input("Is this a OneDrive synced folder for SharePoint? (y/n): ").strip().lower()
    if sharepoint_sync == 'y':
        config['onedrive_synced'] = True
        print("Enter the SharePoint URL for the output directory that this folder syncs with, for linking in confirmation emails. This is the Sharepoint equivalent of the output directory.")
        print("Example: https://city.sharepoint.com/sites/GIS/Map Library/Utilities Locate Requests/Outputs")
        sharepoint_url = input("SharePoint URL: ").strip()
        while not sharepoint_url.startswith("http"):
            print("Please enter a valid URL starting with http or https.")
            sharepoint_url = input("SharePoint URL: ").strip()
            # ensure it doesn't end with a slash
        if sharepoint_url.endswith("/"):
            sharepoint_url = sharepoint_url[:-1]
        # encode the URL to replace spaces with %20
        config['sharepoint_url'] = sharepoint_url.replace(" ", "%20").replace("\\", "/")

    # save
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

    if not config.get('as_built_directory'):
        config['as_built_directory'] = ''
        print("\nNow let's configure the location where your as-built documents are stored.")
        print("\nThis can be a local path, network path, or a path synced to SharePoint via OneDrive.")
        config['as_built_directory'] = input("Enter the path to the folder where as-builts are stored: ")
    else:
        override = input(f"Using existing as built directory {config.get('as_built_directory')}. Press Enter to keep or 'O' to override: ")
        if override.lower() == 'o':
            config['as_built_directory'] = input("Enter the full path to your as-built documents directory: ").strip()
            print("Override accepted")

    print("\nUpdated config:")
    for k, v in config.items():
        if 'secret' in k.lower() or 'password' in k.lower():
            print(f"{k}: {'*' * len(v)}")
        else:
            print(f"{k}: {v}")

    # save config
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    print("config.json updated successfully.")

    print("\nSetup complete!")
    print("\nPlease take some time verifying the details in config.json. Also, search for the text '**** UPDATE' in main.py"
    "as well as the python files in the src folder to adjust any hardcoded paths or field names to match your setup.\n")

if __name__ == "__main__":
    main()