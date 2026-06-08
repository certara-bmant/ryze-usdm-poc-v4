import json

import requests


def _field(obj, *keys):
    """Case-insensitive field getter for ryze API responses.
    Handles both camelCase (old env) and lowercase (new env) field names.
    """
    for k in keys:
        if k in obj:
            return obj[k]
    for k in keys:
        if k.lower() in obj:
            return obj[k.lower()]
    return None


def _safe_json(response, label=""):
    """Parse response JSON safely; returns None and logs if response is non-JSON or empty."""
    text = response.text.strip() if response.text else ""
    if not text or text in ("null", "[]", "{}"):
        print("Empty/null response" + (" for " + label if label else "") +
              " (status " + str(response.status_code) + ")")
        return None
    try:
        return json.loads(text)
    except ValueError as e:
        print("JSON parse error" + (" for " + label if label else "") +
              ": " + str(e) + " | First 200 chars: " + text[:200])
        return None


class Api:
    def __init__(self):
        self.url = "https://staging.ryze.test.certara.net/fws/api/"
        self.access_token = None

    def get_standards(self):
        print("AUTHENTICATING TO RYZE API")

        with open("ryze-Keys.txt", "r") as keys_file:
            lines = keys_file.readlines()
            client_id = lines[0].rstrip()
            client_secret = lines[1].rstrip()
            # Optional line 3+: pre-configured standard(s) in format  label|aid|version
            # e.g.  Ben CRF|1dc3df17-67e8-4a4d-8aa7-325aebc26610|1
            # Skips the full container scan — much faster on large environments.
            preconfigured = {}
            self.owner_uuid = None
            for line in lines[2:]:
                line = line.strip()
                if not line:
                    continue
                if "|" in line:
                    parts = line.split("|")
                    if len(parts) == 3:
                        std_label, std_aid, std_ver = parts[0].strip(), parts[1].strip(), parts[2].strip()
                        preconfigured[std_label] = {"aid": std_aid, "version": std_ver}
                        print("Pre-configured standard: '" + std_label + "' aid=" + std_aid)
                elif not self.owner_uuid:
                    # Plain UUID line = owner UUID for study creation
                    self.owner_uuid = line
                    print("Owner UUID loaded from keys file: " + line)

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

        # If standards were pre-configured in ryze-Keys.txt, skip the expensive scan
        if preconfigured:
            print("Using pre-configured standards — skipping container scan")
            print()
            return preconfigured

        response = requests.get(self.url + "repository/container", headers={'Content-Type': 'application/json',
                                                                            'Authorization': 'Bearer {}'.format(
                                                                                self.access_token)})
        response_json = json.loads(response.text)
        print("Get containers response: " + str(response_json))

        standards = {}
        standard_containers = [
            c for c in response_json
            if (_field((c.get("versions") or [{}])[0], "containerType", "containertype") or "").upper() == "STANDARD"
        ]
        print("Found " + str(len(standard_containers)) + " STANDARD containers (skipping " +
              str(len(response_json) - len(standard_containers)) + " non-standard)")

        for container in standard_containers:
            versions = container.get("versions") or []
            v0 = versions[0] if versions else {}
            version_number = _field(v0, "version") or 0

            r_detail = requests.get(
                self.url + "repository/container/" + container["aid"] + "/" + str(version_number),
                headers={'Content-Type': 'application/json',
                         'Authorization': 'Bearer {}'.format(self.access_token)})

            if r_detail.status_code != 200 or not r_detail.text.strip():
                print("Skip container " + container["aid"] + " — status " + str(r_detail.status_code))
                continue

            detail = json.loads(r_detail.text)
            print("Container detail: aid=" + str(_field(detail, "aid")) +
                  " program=" + str(_field(detail, "program")))

            detail_type = _field(detail, "containerType", "containertype") or ""
            program = _field(detail, "program") or ""
            if detail_type.upper() == "STANDARD" and program == "Activities":
                label = _field(v0, "label") or _field(v0, "versionLabel") or container["aid"]
                aid = _field(detail, "aid") or container["aid"]
                version_val = _field(detail, "version") or version_number
                print("Found Activities standard: '" + str(label) + "' aid=" + str(aid))
                standards[label] = {"aid": aid, "version": version_val}
        print()

        return standards

    def get_standard_forms(self, standard_aid, standard_version):
        """
        Returns: {formLabel: {aid, alias, questions: [{label, sdtmCode, aid}]}}

        Strategy:
        1. Get forms list (filtered by FORM type) — existing approach.
        2. Get ALL assets flat (one call) — build an asset index by AID so
           question labels and aliases can be looked up in O(1).
        3. For each form, call GET .../asset/{formAid} to get full form detail,
           which includes the form's sections array.
           (The flat list returns summaries only; sections are not included.)
        4. For each section AID in the form detail, call GET .../asset/{sectionAid}
           to get the section's questions array.
        5. For each question AID, look it up in the flat index for its label and
           SDTM submission variable / alias. This enables BC→question→form matching.

        Extra API calls: O(forms + sections) — typically 10-30 calls for a POC standard.
        Fails gracefully: if detail calls fail, questions stay empty and matching
        falls back to form-level name tiers.
        """
        print("GETTING FORM TO NAME MAPPINGS")
        headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer {}'.format(self.access_token)
        }

        # Step 1: find the DATA_ACQUISITION asset group
        response = requests.get(
            self.url + "repository/container/" + standard_aid + "/" + standard_version + "/assetgroup",
            headers=headers)
        response_json = _safe_json(response, "asset groups") or []
        print("Get asset groups response: " + str(response_json))

        forms = {}
        if not response_json:
            print("Warning: no asset groups found for standard " + standard_aid +
                  " — standard may have no asset groups yet, or the API returned no data.")
            return forms

        for asset_group in response_json:
            if (_field(asset_group, "assetGroupType", "assetgrouptype") or "") .upper() == "DATA_ACQUISITION":
                ag_aid = asset_group["aid"]
                base = self.url + "repository/container/" + standard_aid + "/" + standard_version + "/assetgroup/" + ag_aid

                # Step 2: get forms list
                # Try uppercase FORM first (old env), then lowercase form (new env)
                for form_path in ("/FORM", "/form"):
                    r_forms = requests.get(base + form_path, headers=headers)
                    print("GET " + base + form_path + " -> status " + str(r_forms.status_code))
                    if r_forms.status_code == 200 and r_forms.text.strip() and r_forms.text.strip() != "null":
                        break
                if not r_forms.text.strip() or r_forms.text.strip() == "null":
                    print("Warning: empty form list response")
                    break
                form_list = _safe_json(r_forms, "form list") or []
                print("Get forms response: " + str(form_list))

                for form in form_list:
                    form_data = {"aid": form["aid"], "questions": []}
                    for alias in form.get("alias", []):
                        if alias["context"] == "Activity Mapping":
                            form_data["alias"] = alias["name"]
                            break
                    forms[form["label"]] = form_data

                # Step 3: flat all-assets call — gives us question labels/aliases in one shot
                try:
                    response = requests.get(base + "/asset", headers=headers)
                    all_assets = _safe_json(response, "flat asset list") or []
                    print("Flat asset list: " + str(len(all_assets)) + " assets")
                    # Index every asset by AID for O(1) question lookup later
                    asset_index = {a["aid"]: a for a in all_assets if isinstance(a, dict) and "aid" in a}
                except Exception as e:
                    print("Warning: flat asset list failed — " + str(e))
                    asset_index = {}

                # Steps 4-5: per-form detail call to get sections, then per-section for questions
                for form_label, form_data in forms.items():
                    try:
                        # GET full form detail — should include sections: [{aid, ...}]
                        r_form = requests.get(base + "/asset/" + form_data["aid"], headers=headers)
                        if r_form.status_code != 200:
                            continue
                        form_detail = _safe_json(r_form, "form detail") or {}
                        sections = form_detail.get("sections", [])
                        print("Form '" + form_label + "': " + str(len(sections)) + " sections")

                        for section_ref in sections:
                            section_aid = section_ref["aid"] if isinstance(section_ref, dict) else section_ref

                            # GET full section detail — should include questions: [{aid, ...}]
                            r_sec = requests.get(base + "/asset/" + section_aid, headers=headers)
                            if r_sec.status_code != 200:
                                continue
                            section_detail = _safe_json(r_sec, "section detail") or {}
                            question_refs = section_detail.get("questions", [])

                            for question_ref in question_refs:
                                q_aid = question_ref["aid"] if isinstance(question_ref, dict) else question_ref
                                # Use the flat index for question label/SDTM — avoids one call per question
                                question_asset = asset_index.get(q_aid, {})
                                if not question_asset:
                                    # Not in flat index — try a direct call as fallback
                                    try:
                                        r_q = requests.get(base + "/asset/" + q_aid, headers=headers)
                                        if r_q.status_code == 200:
                                            question_asset = _safe_json(r_q, "question detail") or {}
                                    except Exception:
                                        continue

                                q_label = question_asset.get("label", "")
                                if not q_label:
                                    continue

                                # SDTM code: submissionVariable field, or alias with SDTM context
                                q_sdtm = question_asset.get(
                                    "submissionVariable",
                                    question_asset.get("submissionvariable", ""))
                                if not q_sdtm:
                                    for alias in question_asset.get("alias", []):
                                        ctx = alias.get("context", "").upper()
                                        if ctx in ("SDTM", "SUBMISSION", "SUBMISSION VARIABLE"):
                                            q_sdtm = alias.get("name", "")
                                            break

                                form_data["questions"].append({
                                    "aid": q_aid,
                                    "label": q_label,
                                    "sdtmCode": q_sdtm.upper() if q_sdtm else "",
                                })

                    except Exception as e:
                        print("Warning: could not get questions for form '" + form_label + "': " + str(e))

                q_total = sum(len(f["questions"]) for f in forms.values())
                print("Question inventory: " + str(q_total) + " questions across " + str(len(forms)) + " forms")
                break
        print()
        return forms

    def create_study(self, study):
        print("CREATING STUDY")

        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.access_token)
        }

        owner = getattr(self, "owner_uuid", None) or "6ae58291-320f-466c-ad41-41b4ed79e45f"
        if not getattr(self, "owner_uuid", None):
            print("Warning: owner UUID not set in ryze-Keys.txt — using default. "
                  "Add your UUID as a plain line (line 4+) in ryze-Keys.txt.")

        body = {
            "containerType": "STUDY",
            "versionLabel": "1",
            "label": study["label"],
            "name": "",
            "identifier": "SDY",
            "therapeuticArea": [""],
            "sponsor": "",
            "program": "",
            "protocolID": "",
            "protocolName": "",
            "protocolTitle": "",
            "owner": owner
        }
        print("Creating Study with JSON: " + str(body))

        response = requests.post(self.url + "repository/container", headers=headers, json=body)
        print("Study creation response: " + str(response.text))

        response_json = _safe_json(response, "create study") or {}
        if "error" in response_json:
            raise Exception("Study creation failed: " + str(response_json))
        if "aid" not in response_json:
            raise Exception("Study creation returned no AID. Response: " + str(response_json))
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
            response_json = _safe_json(response, "visit creation") or {}
            if "aid" not in response_json:
                print("Warning: visit creation returned no AID — response: " + str(response_json))
                visit_order_number += 1
                continue
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
        response_json = _safe_json(response, "visit schedule creation") or {}
        print("Visit Schedule creation response: " + str(response_json))
        print()
