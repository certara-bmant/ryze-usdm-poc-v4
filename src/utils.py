import json
import re


def _get(obj, *keys, default=None):
    for key in keys:
        if key in obj:
            return obj[key]
    return default


def _normalise_name(name):
    if not name:
        return ""
    return re.sub(r'[^a-z0-9]', '', name.lower())


def _sdtm_code_from_reference(reference):
    """
    Extract the SDTM specialisation ID from a BC reference path.
    e.g. '/mdr/specializations/sdtm/packages/2025-04-01/datasetspecializations/SYSBP' -> 'SYSBP'
    Returns empty string if reference is absent or does not contain a recognisable code.
    """
    if not reference:
        return ""
    segment = reference.rstrip("/").split("/")[-1]
    # Only treat it as an SDTM code if it looks like one (alphanumeric, no spaces)
    if segment and re.match(r'^[A-Z0-9_]+$', segment):
        return segment
    return ""


def _extract_bc_lookup(study_data):
    """
    Build a lookup: BC/surrogate id -> {name, label, synonyms, code, reference, sdtmCode}
    v4: BCs at study.versions[0].biomedicalConcepts and .bcSurrogates
    """
    lookup = {}
    versions = study_data.get("versions", [])
    if not versions:
        return lookup
    v = versions[0]

    for bc in v.get("biomedicalConcepts", []):
        if not isinstance(bc, dict):
            continue
        bc_id = bc.get("id", "")
        code_obj = bc.get("code") or {}
        std_code = (code_obj.get("standardCode") or {}).get("code", "")
        reference = bc.get("reference", "")
        lookup[bc_id] = {
            "id": bc_id,
            "name": bc.get("name", ""),
            "label": bc.get("label", "") or bc.get("name", ""),
            "synonyms": [s for s in bc.get("synonyms", []) if s],
            "code": std_code,
            "reference": reference,
            "sdtmCode": _sdtm_code_from_reference(reference),
        }

    for surr in v.get("bcSurrogates", []):
        if not isinstance(surr, dict):
            continue
        surr_id = surr.get("id", "")
        lookup[surr_id] = {
            "id": surr_id,
            "name": surr.get("name", ""),
            "label": surr.get("label", "") or surr.get("name", ""),
            "synonyms": [],
            "code": "",
            "reference": "",
            "sdtmCode": "",
        }

    return lookup


def study_json_to_object(data):
    """
    Parse USDM JSON into a normalised study object.
    Supports v1.x and v4.x. Output uses v1-style field names for api.py compatibility.

    Each activity gains:
      resolvedBCs: [{name, label, synonyms, code, reference, sdtmCode}]
      bcCount: total BC + surrogate count
    """
    print("CONVERTING STUDY DEFINITION JSON TO STUDY OBJECT")

    if isinstance(data, str):
        response = json.loads(data)
    elif isinstance(data, (dict, list)):
        response = data
    else:
        raise Exception("Input must be a JSON string, dict, or list.")

    if isinstance(response, list):
        response = response[0]

    study_data = response.get("study", response)
    study = {}

    usdm_version = response.get("usdmVersion", "")
    study["usdmVersion"] = usdm_version
    print("USDM version: " + (usdm_version or "not specified (assuming v1)"))

    # --- Title ---
    raw_title = _get(study_data, "studyTitle", default=None)
    if raw_title is None:
        versions_t = study_data.get("versions", [])
        if versions_t:
            titles = versions_t[0].get("titles", [])
            for t in titles:
                decode = (t.get("type") or {}).get("decode", "")
                if "Brief" in decode:
                    raw_title = t.get("text")
                    break
            if raw_title is None and titles:
                raw_title = titles[0].get("text")
    if raw_title is None:
        raw_title = _get(study_data, "label", "name", default="Unnamed Study")
    study["label"] = raw_title or "Unnamed Study"

    # --- Study designs ---
    if "studyDesigns" in study_data:
        designs = study_data["studyDesigns"]
    elif "versions" in study_data:
        versions = study_data["versions"]
        if not versions:
            raise Exception("No study versions found.")
        designs = versions[0].get("studyDesigns", [])
    else:
        raise Exception("No studyDesigns found in JSON.")

    if not designs:
        raise Exception("studyDesigns list is empty.")
    sd = designs[0]

    # --- BC lookup ---
    bc_lookup = _extract_bc_lookup(study_data)
    print("BC lookup built: " + str(len(bc_lookup)) + " entries")

    # --- Epochs ---
    epochs_raw = sd.get("epochs", [])
    norm_epochs = []
    for ep in epochs_raw:
        if not isinstance(ep, dict):
            continue
        norm_epochs.append({
            "epochId": _get(ep, "epochId", "id", default=""),
            "epochName": _get(ep, "epochName", "label", "name", default="Unnamed Epoch"),
        })
    study["epochs"] = norm_epochs
    epoch_lookup = {e["epochId"]: e["epochName"] for e in norm_epochs}

    # --- Timelines ---
    timelines = _get(sd, "studyScheduleTimelines", "scheduleTimelines", default=[])
    main_tl = None
    if len(timelines) > 1:
        for tl in timelines:
            if tl.get("mainTimeline"):
                main_tl = tl
                break
        if not main_tl:
            main_tl = timelines[0]
    elif len(timelines) == 1:
        main_tl = timelines[0]
    else:
        raise Exception("No schedule timelines found.")

    tl_name = _get(main_tl, "scheduleTimelineName", "label", "name", default="Main Timeline")
    instances_raw = _get(main_tl, "scheduleTimelineInstances", "instances", default=[])
    norm_instances = []
    for inst in instances_raw:
        enc_id = _get(inst, "scheduledActivityInstanceEncounterId", "encounterId", default="")
        epoch_id = _get(inst, "epochId", default="")
        inst_name = _get(inst, "scheduleTimelineInstanceName", "name", "label", default="")
        norm_instances.append({
            **inst,
            "scheduledActivityInstanceEncounterId": enc_id,
            "activityIds": inst.get("activityIds", []),
            "instanceName": inst_name,
            "epochId": epoch_id,
            "epochName": epoch_lookup.get(epoch_id, ""),
        })

    study["schedule_timeline"] = {
        **main_tl,
        "scheduleTimelineName": tl_name,
        "scheduleTimelineInstances": norm_instances,
    }

    # --- Encounters ---
    encounters_raw = sd.get("encounters", [])
    norm_encounters = []
    for enc in encounters_raw:
        if not isinstance(enc, dict):
            continue
        norm_encounters.append({
            **enc,
            "encounterId": _get(enc, "encounterId", "id", default=""),
            "encounterName": _get(enc, "encounterName", "label", "name", default="Unnamed Encounter"),
        })
    study["encounters"] = norm_encounters
    enc_lookup = {e["encounterId"]: e["encounterName"] for e in norm_encounters}

    for inst in study["schedule_timeline"]["scheduleTimelineInstances"]:
        if not inst.get("encounterName"):
            inst["encounterName"] = enc_lookup.get(inst["scheduledActivityInstanceEncounterId"], "")

    # --- Activities ---
    activities_raw = sd.get("activities", [])
    norm_activities = []
    for act in activities_raw:
        if not isinstance(act, dict):
            continue
        act_id = _get(act, "activityId", "id", default="")
        act_name = _get(act, "activityName", "label", "name", default="Unnamed Activity")
        bcs_embedded = act.get("biomedicalConcepts", [])

        resolved_bcs = []
        for bc_id in act.get("biomedicalConceptIds", []):
            if bc_id in bc_lookup:
                resolved_bcs.append(bc_lookup[bc_id])
        for surr_id in act.get("bcSurrogateIds", []):
            if surr_id in bc_lookup:
                resolved_bcs.append(bc_lookup[surr_id])

        bc_count = len(bcs_embedded) + len(act.get("biomedicalConceptIds", [])) + len(act.get("bcSurrogateIds", []))

        norm_activities.append({
            **act,
            "activityId": act_id,
            "activityName": act_name,
            "biomedicalConcepts": bcs_embedded,
            "resolvedBCs": resolved_bcs,
            "bcCount": bc_count,
            "_normalisedName": _normalise_name(act_name),
        })
    study["activities"] = norm_activities

    print(
        "Parsed: '" + study["label"] + "' | "
        + str(len(norm_activities)) + " activities | "
        + str(len(norm_encounters)) + " encounters | "
        + str(len(norm_epochs)) + " epochs | "
        + str(len(norm_instances)) + " schedule instances"
    )
    return study
