# As-Built & GIS Request Automation Tool

This tool automates the processing of survey requests for as-built drawings and GIS data files. It monitors the specified survey feature class for new requests—specifically, new features where the `FulfilledDate` field is `null` (unfulfilled).

## How It Works

- **New Request Detection:**  
  Checks for new requests by looking for features with a `FulfilledDate` of `None`.
- **Processing Requests:**  
  When a new request is found, the tool calls functions from `process_as_built.py` and/or `process_gis_files.py`, depending on the desired outputs specified by the survey respondent.
- **Notifications & Error Handling:**  
  Handles error logging and sends email notifications to both the requester and admin as needed.

## Survey Layer Fields

- **`FulfilledDate`:**  
  Used to check if the request has been fulfilled. If `None`, the request is new.
- **`utilities`:**  
  Text field containing a comma-separated list of requested utilities (`Water`, `Sanitary`, `Storm`, `All`). This comes from a multi-choice question in the survey.
- **`email`:**  
  The requester’s email address.
- **`specify_desired_output_folder_n`:**  
  Desired output folder name specified by the user.
- **`desired_output`:**  
  Text field with a comma-separated list of desired outputs (`as_builts`, `gis_files`, or both), from a multi-choice question in the survey.

## Setup Instructions

1. **Run `setup.py`:**  
   Generates the `config.json` file with necessary configurations.
2. **Configuration:**  
   You may manually update `config.json` as needed. This file should remain in the main directory alongside this script.

## About

This tool was developed by **Mike Hanson**, GIS/Asset Management Technician for the City of Rosemount, MN, to assist with fulfilling as-built and GIS file requests.

Learn more:
