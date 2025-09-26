import os
import arcpy
import sys
import logging
from datetime import datetime
import json
from src.models import sign_in_to_agol, sign_in_to_portal


from src.models import layer_dict, water_layers, sanitary_layers, storm_layers, survey
from typing import List, Optional

config_path = os.path.join(os.path.dirname(__file__), 'config.json')  # ensure config.json is in the same directory as this script
if not os.path.exists(config_path):
    print("config.json not found. Please run config.json to generate this file in the main directory.")
    sys.exit(1)

with open(config_path, 'r') as f:
    config = json.load(f)  # Load existing config

'''
Use this script together with the LocateRequests.aprx document to clip utilities to a project extent.
1. Digitize the project extent
  - for this, navigate to the above aprx, Utility_Clipper map, ClipPolygons layer. Add feature for project extent.
  - Give the new feature the name you would like for the output geodatabase (ProjectName field)
2. Save edits / project
3. Run this script. It will detect the most recent feature and use that for the extent

'''


def run_gis_files_process(Record, selected_survey, target_dir, errors, error_counter):

    try:

        # Configuration
        user = os.getlogin()

        GlobalID = Record.GlobalId
        folder = Record.folder   # this is passed from the output folder name specified by the user in the survey (see dataclass definition in models.py)

        project_folder = rf"{target_dir}\GIS Files"

        layers = list(layer_dict.keys())

        # check if the survey is in AGOL or Portal, and sign in accordingly
        esri_env = config.get("is_arcgis_online")
        if esri_env:
            sign_in_to_agol()
        else:
            sign_in_to_portal()


        # Create the project folder and geodatabase
        counter = 1
        while os.path.exists(project_folder):
            project_folder = rf"{project_folder}_{counter}"
            counter += 1

        os.makedirs(project_folder, exist_ok=True)
        gdb_path = os.path.join(project_folder, f"Utilities_{folder}.gdb")
        arcpy.CreateFileGDB_management(project_folder, os.path.basename(gdb_path))

        # Clip the layers and store results with the selected fields
        # make a folder for the kmz files
        shp_folder = os.path.join(project_folder, "Shapefiles")
        if not os.path.exists(shp_folder):
            os.makedirs(shp_folder)

        # export filtered clip layer to Shapefile and feature class (in gdb) with name project_area
        # this lets the requester also see the shape they drew to request the files
        arcpy.conversion.FeatureClassToFeatureClass(selected_survey, gdb_path, "project_area")
        arcpy.conversion.FeatureClassToFeatureClass(selected_survey, shp_folder, "project_area")

        fc_output_names = []

        layers_list = []
        if "All" in Record.utilities_list or Record.utilities_list is None:
            layers_list.extend(layers)
        else:
            if "Water" in Record.utilities_list:
                layers_list.extend(water_layers)
            if "Sanitary" in Record.utilities_list:
                layers_list.extend(sanitary_layers)
            if "Storm" in Record.utilities_list:
                layers_list.extend(storm_layers)

        for layer_name in layers_list:

            # layers_dict is in models.py. It is a dictionary of dictionaries, where the key is the layer name, and the value is a dictionary with keys 'fields' and 'path'
            layer = layer_dict.get(layer_name, {}).get('path')
            if not layer:
                print(f"ATTENTION: Layer path for {layer_name} not found in layer_dict. Skipping.")
                continue

            # convert to temp layer so can use the datasource, otherwise it's just a string
            temp_layer = "temp_layer"
            arcpy.management.MakeFeatureLayer(layer, temp_layer)

            if layer:
                print(f"Clipping: {layer_name}")
                # Only select fields that are in the layer_dict for each layer
                selected_fields = layer_dict.get(layer_name, {}).get('fields', [])
                field_names = [f.name for f in arcpy.ListFields(temp_layer)]
                fields_to_select = [field for field in selected_fields if field in field_names]
                fields_to_select.append("SHAPE")
                fields_to_select.append("Shape")
                fields_to_select.append("Shape__Length")
                fields_to_select.append("OBJECTID")
                layer_name = layer_name.replace(" ", "_")

                # set output feature class path for clip operation
                out_fc = os.path.join(gdb_path, layer_name)
                arcpy.analysis.Clip(temp_layer, selected_survey, out_fc)

                # Remove unnecessary fields
                if fields_to_select:
                    arcpy.management.DeleteField(out_fc, [f for f in field_names if f not in fields_to_select])

                # clean up temp layer
                arcpy.management.Delete(temp_layer)

                # convert gdb layer to shapefile
                arcpy.conversion.FeatureClassToFeatureClass(out_fc, shp_folder, layer_name)
                print(f"shp created for: {layer_name}")

                fc_output_names.append(out_fc)

        # Output the results
        print("Clipped features:")
        for name in fc_output_names:
            print(f" - {name}")

        print("Clipping finished")

        # update the gis_files_fulfilled field in the survey layer using an update cursor
        if error_counter == 0:
            # **** UPDATE THIS **** this is a tracking field in the survey to indicate when the request has been fulfilled. Add this as a date field in your survey results layer
            # This field is required, as it is the basis for the script to determine which requests have not yet been fulfilled
            with arcpy.da.UpdateCursor(survey, ["globalid", "gis_files_fulfilled"]) as cursor:
                for row in cursor:
                    if row[0] == GlobalID:
                        row[1] = datetime.now()
                        cursor.updateRow(row)
                        print(f"gis_files_fulfilled updated for GlobalID {GlobalID}")
                        logging.info(f"gis_files_fulfilled updated for GlobalID {GlobalID}")
                        print("\n\n")

        return error_counter, errors

    except Exception as e:
        errors[error_counter] = e
        error_counter += 1
        print(f"Error in processing GIS files: {str(e)}")

        return error_counter, errors