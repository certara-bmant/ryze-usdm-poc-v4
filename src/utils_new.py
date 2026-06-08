import json

def study_json_to_object(file):
    print("CONVERTING STUDY DEFINITION JSON TO STUDY OBJECT")
    response = json.loads(file)

    # Handle list-wrapped JSON
    if isinstance(response, list):
        response = response[0]

    # Handle flat or nested structure
    study_data = response.get("study", response)
    study = {}

    study["label"] = study_data.get("name", "Unnamed Study")

    versions = study_data.get("versions", [])
    study_designs = []

    if versions and isinstance(versions[0], dict) and "studyDesigns" in versions[0]:
        study_designs = versions[0]["studyDesigns"]
    elif "studyDesigns" in study_data:
        study_designs = study_data["studyDesigns"]
    else:
        raise Exception("No study designs found in JSON.")

    if not isinstance(study_designs, list):
        raise Exception("studyDesigns is not a list.")

    if not study_designs:
        raise Exception("studyDesigns list is empty.")

    study_design = study_designs[0]

    if not isinstance(study_design, dict):
        raise Exception("study_design is not a dictionary.")

    timelines = study_design.get("scheduleTimelines", [])
    if len(timelines) > 1:
        for schedule_timeline in timelines:
            if schedule_timeline.get("mainTimeline"):
                print(schedule_timeline.get("name", "") + " is main timeline")
                study["schedule_timeline"] = schedule_timeline
                break
    elif len(timelines) == 1:
        study["schedule_timeline"] = timelines[0]
    else:
        raise Exception("No study schedule timeline found in 'scheduleTimelines'")

    study["encounters"] = study_design.get("encounters", [])

    raw_activities = study_design.get("activities") or study_data.get("activities", [])
    if not isinstance(raw_activities, list):
        raise Exception("Activities is not a list.")

    study["activities"] = []
    for activity in raw_activities:
        if isinstance(activity, dict):
            extension_attrs = activity.get("extensionAttributes", {})
            name = extension_attrs.get("name") if isinstance(extension_attrs, dict) else None
            if not name:
                name = activity.get("name", "Unnamed Activity")
            study["activities"].append({**activity, "activityName": name})
        else:
            print("Skipping non-dict activity:", activity)

    return study