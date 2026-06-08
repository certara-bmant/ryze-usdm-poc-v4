import json

from flask import Flask, send_file, request, jsonify
from flask_cors import CORS

import utils
from api import Api
from session_data import SessionData

app = Flask(__name__)
# Raise content limit — but the real fix is sending JSON body (not formdata)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB
CORS(app)

api = Api()
session_data = SessionData()


@app.route("/")
def render_index():
    return send_file("templates/index.html")


@app.route("/study", methods=['POST'])
def post_study():
    """
    Accept a USDM JSON file upload.

    Expects Content-Type: application/json with body: { "study": <parsed JSON object> }

    The frontend reads the file, parses it, and sends the object — avoiding the
    413 size limit that plagued the old formdata approach.
    """
    # Stage 1: parse the USDM JSON
    try:
        body = request.get_json(force=True)
        if not body or "study" not in body:
            return "Request body must be JSON with a 'study' key.", 400
        session_data.study = utils.study_json_to_object(body["study"])
    except Exception as error:
        print("Error parsing USDM JSON:", error)
        return "Error parsing USDM file: " + str(error), 400

    # Stage 2: authenticate to ryze and fetch standards
    try:
        standards = api.get_standards()
    except Exception as error:
        print("Error connecting to ryze:", error)
        return "USDM file parsed successfully, but could not connect to ryze: " + str(error), 502

    if not standards:
        return ("USDM file parsed successfully, but no ryze Standards with "
                "program='Activities' were found. Check that the standard exists "
                "and is accessible with the supplied credentials."), 404

    return jsonify(standards)


@app.route('/standard-forms/<standard_aid>/<standard_version>')
def get_standard_forms(standard_aid, standard_version):
    try:
        session_data.associated_standard = {"AID": standard_aid, "Version": standard_version}
        session_data.standard_forms = api.get_standard_forms(standard_aid, standard_version)
        return jsonify(session_data.standard_forms)
    except Exception as error:
        print("Error in /standard-forms:", error)
        return "Error getting standard forms from ryze. Check server logs.", 500


@app.route('/study-activities')
def get_study_activities():
    try:
        return jsonify(session_data.study["activities"])
    except Exception as error:
        print("Error in /study-activities:", error)
        return "Error getting study activities. Check server logs.", 500


@app.route('/study-soa-data')
def get_study_soa_data():
    """
    Return all data needed to render the ICH M11-style SoA preview table.
    Called immediately after upload, before the mapping step.
    """
    try:
        if not session_data.study:
            return "No study loaded.", 400

        study = session_data.study
        tl = study["schedule_timeline"]
        instances = tl["scheduleTimelineInstances"]

        # Build ordered list of unique (epochId, epochName) pairs in encounter order
        seen_epochs = {}
        epoch_order = []
        for inst in instances:
            eid = inst.get("epochId", "")
            if eid and eid not in seen_epochs:
                seen_epochs[eid] = inst.get("epochName", eid)
                epoch_order.append({"epochId": eid, "epochName": inst.get("epochName", eid)})

        # Build SoA columns: one per instance, with epoch info for banding
        columns = []
        for inst in instances:
            columns.append({
                "instanceId": inst.get("id", inst.get("scheduledInstanceId", "")),
                "instanceName": inst.get("instanceName") or inst.get("name") or inst.get("label") or "",
                "encounterName": inst.get("encounterName", ""),
                "epochId": inst.get("epochId", ""),
                "epochName": inst.get("epochName", ""),
                "activityIds": inst.get("activityIds", []),
            })

        # Build SoA rows: one per activity, with a boolean presence per column
        activity_id_set = {act["activityId"] for act in study["activities"]}
        rows = []
        for act in study["activities"]:
            aid = act["activityId"]
            presence = [aid in col["activityIds"] for col in columns]
            rows.append({
                "activityId": aid,
                "activityName": act["activityName"],
                "bcCount": act.get("bcCount", 0),
                "presence": presence,
            })

        return jsonify({
            "title": study["label"],
            "usdmVersion": study.get("usdmVersion", ""),
            "timelineName": tl["scheduleTimelineName"],
            "epochs": epoch_order,
            "columns": columns,
            "rows": rows,
        })

    except Exception as error:
        print("Error in /study-soa-data:", error)
        return "Error building SoA data. Check server logs.", 500


@app.route("/mappings", methods=['POST'])
def post_mappings():
    """
    Accept confirmed activity→form mappings and create the ryze study.

    Expects Content-Type: application/json with body: { "mappings": { activityId: formLabel, ... } }
    """
    try:
        if not session_data.study:
            return "No study loaded. Please POST to /study first.", 400
        if not session_data.standard_forms:
            return "No standard forms loaded. Please GET /standard-forms/<aid>/<version> first.", 400

        body = request.get_json(force=True)
        if not body or "mappings" not in body:
            return "Request body must be JSON with a 'mappings' key.", 400

        form_mappings = body["mappings"]
        if not isinstance(form_mappings, dict):
            return "Invalid mappings format. Expected a JSON object.", 400

        form_name_to_aid_mappings = session_data.standard_forms
        activity_to_form_mappings = {}

        for activity_id, form_name in form_mappings.items():
            form_info = form_name_to_aid_mappings.get(form_name)
            if form_info and "aid" in form_info:
                activity_to_form_mappings[activity_id] = form_info["aid"]
            else:
                print(f"Warning: no AID found for form '{form_name}' — skipping.")

        study_aid = api.create_study(session_data.study)
        api.associate_libraries(study_aid, session_data.associated_standard)
        asset_group_aid = api.create_form_asset_group(study_aid)
        api.import_forms(study_aid, asset_group_aid, session_data.associated_standard, activity_to_form_mappings)
        api.create_visit_schedules(study_aid, session_data.study, activity_to_form_mappings, form_name_to_aid_mappings)

        return "OK"

    except Exception as error:
        print("Error in /mappings:", error)
        return "Error creating study from mappings. Check server logs.", 500
