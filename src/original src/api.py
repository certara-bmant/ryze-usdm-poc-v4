import json

import requests


class Api:
    def __init__(self):
        self.url = "https://ryze-staging.formedix.com/fws/api/"
        self.access_token = None

    def get_standards(self):
        print("AUTHENTICATING TO RYZE API")

        with open("ryze-Keys.txt", "r") as keys_file:
            lines = keys_file.readlines()
            client_id = lines[0].rstrip()
            client_secret = lines[1].rstrip()

        body = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret
        }
        response = requests.post(self.url + "oauth/token", body)
        response_json = json.loads(response.text)
        self.access_token = response_json["access_token"]

        response = requests.get(self.url + "oauth/test", headers={'Content-Type': 'application/json',
                                                                  'Authorization': 'Bearer {}'.format(
                                                                      self.access_token)})
        print("Token test response: " + str(response.text))

        response = requests.get(self.url + "repository/container", headers={'Content-Type': 'application/json',
                                                                            'Authorization': 'Bearer {}'.format(
                                                                                self.access_token)})
        response_json = json.loads(response.text)
        print("Get containers response: " + str(response_json))

        standards = {}
        for container in response_json:
            if container["versions"][0]["containerType"] == "STANDARD":
                response = requests.get(
                    self.url + "repository/container/" + container["aid"] + "/" + str(
                        container["versions"][0]["version"]),
                    headers={'Content-Type': 'application/json',
                             'Authorization': 'Bearer {}'.format(self.access_token)})

                response_json = json.loads(response.text)
                print("Get container details response: " + str(response_json))

                if response_json["containerType"] == "STANDARD" and "program" in response_json and response_json[
                    "program"] == "Activities":
                    label = container["versions"][0]["label"]
                    aid = response_json["aid"]
                    standards[label] = {"aid": aid, "version": response_json["version"]}
        print()

        return standards

    def get_standard_forms(self, standard_aid, standard_version):
        # PROBLEM: Unless the forms are in an asset group there's no way of retrieving them using the API
        print("GETTING FORM TO NAME MAPPINGS")
        response = requests.get(
            self.url + "repository/container/" + standard_aid + "/" + standard_version + "/assetgroup",
            headers={'Content-Type': 'application/json',
                     'Authorization': 'Bearer {}'.format(self.access_token)})
        response_json = json.loads(response.text)
        print("Get asset groups response: " + str(response_json))

        forms = {}
        for asset_group in response_json:
            if asset_group["assetGroupType"] == "DATA_ACQUISITION":
                response = requests.get(
                    self.url + "repository/container/" + standard_aid + "/" + standard_version + "/assetgroup/" +
                    asset_group["aid"] + "/FORM",
                    headers={'Content-Type': 'application/json',
                             'Authorization': 'Bearer {}'.format(self.access_token)})
                response_json = json.loads(response.text)
                print("Get assets response: " + str(response_json))
                for form in response_json:
                    form_data = {}
                    form_data["aid"] = form["aid"]
                    if len(form["alias"]) > 0:
                        for alias in form["alias"]:
                            if alias["context"] == "Activity Mapping":
                                form_data["alias"] = alias["name"]
                                break
                    forms[form["label"]] = form_data
                break
        print()

        return forms

    def create_study(self, study):
        print("CREATING STUDY")

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.access_token)
        }

        # TODO: better identifier generation
        body = {
            "containerType": "STUDY",
            "versionLabel": "1",
            "label": study["label"],
            "name": "",
            "identifier": "SDY",
            "therapeuticArea": [
                ""
            ],
            "sponsor": "",
            "program": "",
            "protocolID": "",
            "protocolName": "",
            "protocolTitle": "",
            "owner": "0beea876-81bc-4b54-997f-a67d594d4198"
        }
        print("Creating Study with JSON: " + str(body))

        response = requests.post(self.url + "repository/container", headers=headers, json=body)
        print("Study creation response: " + str(response.text))

        # TODO: Also capture version?
        response_json = json.loads(response.text)
        aid = response_json["aid"]
        print()

        return aid

    def associate_libraries(self, aid, associated_standard):
        print("ASSOCIATING LIBRARIES")

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.access_token)
        }

        response = requests.put(
            self.url + "repository/container/" + aid + "/1/libraries/" + associated_standard["AID"] + "/" +
            associated_standard["Version"],
            headers=headers)
        print("Associate libraries response: " + str(response.text))

        response = requests.get(self.url + "repository/container/" + aid + "/1/libraries", headers=headers)
        print("View associated libraries response: " + str(response.text))
        print()

    def create_form_asset_group(self, aid):
        print("CREATING ASSET GROUP FOR FORMS")

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.access_token)
        }

        # TODO: better identifier generation
        body = {
            "assetGroupType": "DATA_ACQUISITION",
            "label": "Forms",
            "name": "",
            "identifier": "AG_1",
            "standardName": None,
            "standardVersion": None,
            "forSubmission": None
        }
        print("Creating Form asset group with JSON: " + str(body))

        response = requests.post(self.url + "repository/container/" + aid + "/1/assetgroup", headers=headers, json=body)
        print("Form asset group creation response: " + str(response.text))

        response_json = json.loads(response.text)
        asset_group_aid = response_json["aid"]

        print()
        return asset_group_aid

    def import_forms(self, aid, asset_group_aid, associated_standard, activity_to_form_mappings):
        print("IMPORTING FORMS")

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.access_token)
        }

        form_aids = []
        for form_aid in activity_to_form_mappings.values():
            form_aids.append(form_aid)

        # TODO: better identifier generation
        body = {
            "sourceContainer": associated_standard["AID"],
            "sourceVersion": 1,
            "targetAssetGroup": asset_group_aid,
            "assets": form_aids
        }
        print("Importing forms with JSON: " + str(body))

        response = requests.post(self.url + "repository/container/" + aid + "/1/library/import", headers=headers,
                                 json=body)
        print("Import forms response: " + str(response.text))
        print()

    def create_visit_schedules(self, aid, study, activity_to_form_mappings, form_to_name_mappings):
        print("CREATING VISIT SCHEDULES")
        headers = {'Content-Type': 'application/json',
                   'Authorization': 'Bearer {}'.format(self.access_token)}

        # Get all asset groups for study
        response = requests.get(self.url + "repository/container/" + aid + "/1/assetgroup",
                                headers=headers)
        response_json = json.loads(response.text)
        print("View asset groups response: " + str(response_json))

        activity_to_aid_mappings = {}
        for asset_group in response_json:
            # Find asset group containing forms
            if asset_group["label"] == "Forms":
                forms_asset_group_aid = asset_group["aid"]
                response = requests.get(
                    self.url + "repository/container/" + aid + "/1/assetgroup/" + forms_asset_group_aid + "/asset",
                    headers=headers)
                response_json = json.loads(response.text)
                print("View assets for asset group " + forms_asset_group_aid + " response: " + str(response_json))

                # If this forms asset group is not empty
                if (len(response_json) > 0):

                    # Populate activity_to_aid_mappings with AID of the form assets from this asset group
                    for asset in response_json:
                        if (asset["label"] in form_to_name_mappings.keys()):
                            activity_to_aid_mappings[form_to_name_mappings[asset["label"]]["aid"]] = asset["aid"]
                    break
        print("activity_to_aid_mappings: " + str(activity_to_aid_mappings))

        # Create visits
        visit_order_number = 0
        visits = []

        for schedule in study["schedule_timeline"]["scheduleTimelineInstances"]:
            print("schedule")
            print(schedule)
            activities = schedule["activityIds"]
            order_number = 0
            forms = []
            for activity in activities:
                print("activity")
                print(activity)
                if activity in activity_to_form_mappings:
                    forms.append({"aid": activity_to_aid_mappings[activity_to_form_mappings[activity]],
                                  "orderNumber": order_number})
                    order_number += 1

            encounter_label = schedule["scheduledActivityInstanceEncounterId"]
            for encounter in study["encounters"]:
                print("encounter")
                print(encounter)
                if encounter["encounterId"] == schedule["scheduledActivityInstanceEncounterId"]:
                    encounter_label = encounter["encounterName"]

            body = {
                "assetType": "VISIT",
                "label": encounter_label,
                "identifier": "VS_" + str(visit_order_number),
                "visitType": "SCHEDULED",
                "forms": forms
            }

            print("Creating Visit with JSON: " + str(body))

            response = requests.post(self.url + "repository/container/" + aid + "/1/asset", headers=headers,
                                     json=body)

            response_json = json.loads(response.text)
            print("Visit creation response: " + str(response_json))

            visits.append({"aid": response_json["aid"], "orderNumber": visit_order_number})
            visit_order_number += 1

        body = {
            "assetType": "VISIT_SCHEDULE",
            "label": study["schedule_timeline"]["scheduleTimelineName"],
            "identifier": "MAIN_TIMELINE",
            "visits": visits
        }

        print("Creating Visit Schedule with JSON: " + str(body))

        response = requests.post(self.url + "repository/container/" + aid + "/1/asset", headers=headers, json=body)
        response_json = json.loads(response.text)
        print("Visit Schedule creation response: " + str(response_json))
        print()
