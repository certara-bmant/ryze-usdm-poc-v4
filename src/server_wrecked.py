import json

from flask import Flask, send_file, request
from flask_cors import CORS

import utils
from api import Api
from session_data import SessionData

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB
CORS(app)

study = None
api = Api()
session_data = SessionData()


@app.route("/")
def render_index():
    return send_file("templates/index.html")


@app.route("/study", methods=['POST'])
def post_study():
    file_storage = request.files.get('file')

    if not file_storage:
        return "No file uploaded. Please send a file in the 'file' field of the form data.", 400

    try:
        # Read file as UTF-8 string
        file_contents = file_storage.read().decode('utf-8')

        # Convert JSON into study object
        session_data.study = utils.study_json_to_object(file_contents)

        # Get standards
        standards = api.get_standards()
        return standards
    except Exception as error:
        print(error)
        return "Error converting SoA file to study object. Ensure the contents of your file are correct.", 400


@app.route('/standard-forms/<standard_aid>/<standard_version>')
def get_standard_forms(standard_aid, standard_version):
    try:
        session_data.associated_standard = {"AID": standard_aid, "Version": standard_version}
        session_data.standard_forms = api.get_standard_forms(standard_aid, standard_version)
        return session_data.standard_forms
    except Exception as error:
        print(error)
        return "Error getting standard forms from ryze. Check server logs.", 500


@app.route('/study-activities')
def get_study_activities():
    try:
        return session_data.study["activities"]
    except Exception as error:
        print(error)
        return "Error getting study activities. Check server logs.", 500


@app.route("/mappings", methods=['POST'])
def post_mappings():
    try:
        # Check if study is loaded
        if not session_data.study:
            return "No study loaded. Please POST to /study first.", 400

        # Check if standard forms are loaded
        if not session_data.standard_forms:
            return "No standard forms loaded. Please GET /standard-forms/<aid>/<version> first.", 400

        form_mappings = json.loads(request.form.get('mappings', '{}'))

        # Ensure mappings is a dict
        if not isinstance(form_mappings, dict):
            return "Invalid mappings format. Expected JSON object.", 400

        form_name_to_aid_mappings = session_data.standard_forms or {}
        activity_to_form_mappings = {}

        for activity, form_name in form_mappings.items():
            form_info = form_name_to_aid_mappings.get(form_name)
            if form_info and "aid" in form_info:
                activity_to_form_mappings[activity] = form_info["aid"]
            else:
                print(f"Warning: No AID found for form '{form_name}' in mappings.")

        # Call API methods
        study_aid = api.create_study(session_data.study)
        api.associate_libraries(study_aid, session_data.associated_standard)
        asset_group_aid = api.create_form_asset_group(study_aid)
        api.import_forms(study_aid, asset_group_aid, session_data.associated_standard, activity_to_form_mappings)
        api.create_visit_schedules(study_aid, session_data.study, activity_to_form_mappings, form_name_to_aid_mappings)

        return "OK"

    except Exception as error:
        print("Error in /mappings:", error)
        return "Error creating study from mappings. Check server logs.", 500
