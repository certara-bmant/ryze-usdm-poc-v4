import json


def study_json_to_object(file):
    print("CONVERTING STUDY DEFINITION JSON TO STUDY OBJECT")

    response = json.loads(file)

    study = {}
    study["label"] = response["study"]["studyTitle"]

    study_design = response["study"]["studyDesigns"][0]

    # Get schedules
    if len(study_design["studyScheduleTimelines"]) > 1:
        for study_schedule_timeline in study_design["studyScheduleTimelines"]:
            if study_schedule_timeline["mainTimeline"]:
                print(study_schedule_timeline["scheduleTimelineName"] + " is main timeline")
                study["schedule_timeline"] = study_schedule_timeline
                break
    elif len(study_design["studyScheduleTimelines"]) == 1:
        study["schedule_timeline"] = study_design["studyScheduleTimelines"][0]
    else:
        raise Exception("No study schedule timeline")

    # Get encounters
    study["encounters"] = study_design["encounters"]

    # Get activities
    study["activities"] = study_design["activities"]



    # for study_schedule_timeline in study_design['studyScheduleTimelines']:
    #     timeline = {}
    #     timeline["name"] = study_schedule_timeline['scheduleTimelineName']
    #     schedule_timeline_soa = study_schedule_timeline['scheduleTimelineSoA']
    #
    #     activities = []
    #     for order in schedule_timeline_soa['orderOfActivities']:
    #         activities.append(order)
    #     timeline["activities"] = activities
    #
    #     schedules = []
    #     for schedule in schedule_timeline_soa['SoA']:
    #         schedules.append(schedule)
    #     timeline["schedules"] = schedules
    #
    #     timelines.append(timeline)
    # study["timelines"] = timelines

    print(json.dumps(study, sort_keys=True, indent=2))

    return study