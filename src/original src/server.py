import json

from flask import Flask, send_file, request
from flask_cors import CORS

import utils
from api import Api
from session_data import SessionData

app = Flask(__name__)
CORS(app)

study = None
api = Api()
session_data = SessionData()


@app.route("/")
def render_index():
    return send_file("templates/index.html")


@app.route("/study", methods=['POST'])
def post_study():
    file = request.form.get('file')
    try:
        session_data.study = utils.study_json_to_object(file)
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
        # Create the activity_to_form_mappings object as used in the mockup code
        form_mappings = json.loads(request.form.get('mappings'))
        form_name_to_aid_mappings = session_data.standard_forms
        activity_to_form_mappings = {}
        for activity in form_mappings.keys():
            form_name = form_mappings[activity]
            if form_name in form_name_to_aid_mappings:
                activity_to_form_mappings[activity] = form_name_to_aid_mappings[form_name]["aid"]

        study_aid = api.create_study(session_data.study)
        api.associate_libraries(study_aid, session_data.associated_standard)
        asset_group_aid = api.create_form_asset_group(study_aid)
        # PROBLEM: Imported form request doesn't return the new study form's AIDs, so I have to associate them through the labels
        api.import_forms(study_aid, asset_group_aid, session_data.associated_standard, activity_to_form_mappings)
        api.create_visit_schedules(study_aid, session_data.study, activity_to_form_mappings, form_name_to_aid_mappings)
        # PROBLEM: Can't delete a study once it's been created through the API?? This has made a mess
        # PROBLEM: Can't grant anyone access rights to the study through the API so they can delete/edit it?
        return "OK"
    except Exception as error:
        print(error)
        return "Error creating study from mappings. Check server logs.", 500
