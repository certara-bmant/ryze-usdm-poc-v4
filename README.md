# USDM Import UI — PoC

A local Flask application for importing a USDM-compliant JSON study definition into ryze. Upload a USDM JSON, preview the Schedule of Activities, map USDM activities to ryze form assets, and create a fully structured study in ryze automatically.

Supports USDM **v1.x** and **v4.x** (including v4.0.0) JSON structures.

---

## Prerequisites

- Python 3.9+
- A ryze account with API credentials (client ID and client secret)
- Your ryze user UUID

---

## First-time setup

### 1. Clone / download the repo

```
git clone https://github.com/certara/ryze-Labs
```

Work inside the `USDM-Import-UI-PoC` folder.

### 2. Create a virtual environment

Run from **Command Prompt (as Administrator)** inside the project folder. The existing `venv` is user-specific and must be recreated.

```cmd
rmdir /s /q venv
python -m venv venv
```

### 3. Install dependencies

```cmd
venv\Scripts\pip install flask flask-cors requests
```

### 4. Configure ryze-Keys.txt

Create `ryze-Keys.txt` in the project root (next to the `.bat` files). The file supports up to four types of lines:

```
<client_id>               ← required: line 1
<client_secret>           ← required: line 2
<owner-uuid>              ← required for study creation: plain UUID, any line after line 2
<label>|<aid>|<version>   ← optional: pre-configured standard(s), pipe-separated
```

**Minimum (will perform a full container scan on each upload):**

```
your_client_id
your_client_secret
your-user-uuid-here
```

**Recommended (skips the slow container scan):**

```
your_client_id
your_client_secret
your-user-uuid-here
Ben CRF|1dc3df17-67e8-4a4d-8aa7-325aebc26610|1
```

Multiple standards can be added on separate lines. The AID and version appear in the server log as `Found Activities standard: 'Ben CRF' aid=...` on the first (slow) scan — copy them in to make all subsequent uploads instant.

**Finding your user UUID:**

```
GET /fws/api/user/current
Authorization: Bearer <your_access_token>
```

### 5. Set the ryze base URL

Open `src/api.py` and confirm the URL on line 36 matches your environment:

```python
self.url = "https://staging.ryze.test.certara.net/fws/api/"
```

---

## Running the app

### Step 1 — Activate the virtual environment

```cmd
Start-venv.bat
```

### Step 2 — Start the server

From inside the activated venv prompt:

```cmd
Run-Server.bat
```

The server starts at `http://127.0.0.1:5000`.

### Step 3 — Open the app

```
http://127.0.0.1:5000
```

---

## Using the app

**1 — Upload a USDM JSON file**

Select a USDM-compliant `.json` file and click **Upload Study**. Supported: USDM v1.x (flat) and v4.x (versioned with `versions` array).

After upload a **Schedule of Activities preview** renders automatically — an ICH M11-style table showing which activities are scheduled at each visit, colour-coded by epoch. You can filter by activity name and collapse the panel.

**2 — Select a standard**

A dropdown lists all ryze Standards with `program = Activities`. Select the one containing your form assets and click **Confirm Standard**.

**3 — Map activities to forms**

A mapping table shows every USDM activity alongside a ryze form dropdown. Five auto-matching methods are tried in priority order:

| Badge | Method | How it works |
|-------|--------|-------------|
| BC Question | SDTM code (question-level) | Extracts the SDTM specialisation code from the BC reference (e.g. `SYSBP`) and matches it against question submission variables in ryze — highest precision |
| BC | BC alias (ryze code system) | v1 only: BC has a ryze-specific alias matching a form alias exactly |
| BC Name | BC label / synonym | BC label or synonym has ≥ 70% word overlap with a form label |
| Exact | Exact label | Activity name matches form label exactly |
| Fuzzy | Word overlap | ≥ 75% word overlap between activity name and form label; parenthetical content (e.g. "Vital Signs (Supine BP...)") is stripped first |
| Manual | — | No match found — select from the dropdown |

A summary line shows how many activities were auto-mapped. Review, adjust as needed, then click **Confirm Mappings**.

**4 — Study created**

The app creates the study in ryze, associates the standard library, imports the mapped forms with all child assets, and creates visit schedules from the USDM timeline. Open ryze to see the result.

---

## ryze standard requirements

For the form mapping and study creation steps to work:

- The standard container must have `program = Activities` set.
- Forms must be inside a **DATA_ACQUISITION asset group** within the standard. Forms added directly to the container root are not accessible via the API.
- For BC Question SDTM matching, questions must have a **submission variable** set (e.g. `SYSBP`).

---

## USDM JSON files

Sample files are in the `studies/` folder:

| File | USDM version | Notes |
|------|-------------|-------|
| `Study-Definition-Mapping.json` | v1.x | Original POC file |
| `EliLilly_NCT03421379_Diabetes.json` | v4.0 | Crossover glucagon study |

**Troubleshooting large files:** Full protocol JSONs from the DDF project can exceed the upload limit or time out. Trim the file to the classes the app needs: `study`, `versions`, `studyDesigns`, `scheduleTimelines`, `instances`, `encounters`, `activities`, `epochs`.

---

## Project structure

```
USDM-Import-UI-PoC/
├── Start-venv.bat          # Activates the virtual environment
├── Run-Server.bat          # Starts the Flask server
├── ryze-Keys.txt           # Credentials + config (not committed — create manually)
├── studies/                # Sample USDM JSON files
└── src/
    ├── server.py           # Flask routes
    ├── utils.py            # USDM JSON parser (v1.x + v4.x)
    ├── api.py              # ryze API calls
    ├── session_data.py     # In-memory session state
    ├── templates/
    │   └── index.html      # App UI
    └── static/
        ├── js/
        │   ├── appModule.js        # AngularJS module
        │   └── controllerModule.js # UI logic + SoA preview renderer
        └── css/
            └── styling.css
```

---

## Known limitations

- **No persistent state** — refreshing the page clears the session; you must re-upload the JSON.
- **Single study design** — only the first `studyDesigns` entry is used.
- **Main timeline only** — sub-timelines (e.g. intra-day PK sampling) are not shown in the SoA preview or imported.
- **Standard scan latency** — environments with many standards cause a slow first upload (one API call per standard to check `program`). Use the pre-configured line in `ryze-Keys.txt` to eliminate this.
- **BC Question matching** — requires forms in a DATA_ACQUISITION asset group and questions with submission variables set; falls back to name/fuzzy matching otherwise.
