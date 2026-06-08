// ======================================================================
//  SoA Preview — vanilla JS (no Angular needed, purely presentational)
// ======================================================================

var EPOCH_COLOURS = [
    { bg: '#e8f5e9', header: '#2e7d32', text: '#1b5e20' },
    { bg: '#e3f2fd', header: '#1565c0', text: '#0d47a1' },
    { bg: '#f3e5f5', header: '#6a1b9a', text: '#4a148c' },
    { bg: '#fce4ec', header: '#c62828', text: '#880e4f' },
    { bg: '#fff3e0', header: '#e65100', text: '#bf360c' },
    { bg: '#e0f7fa', header: '#00695c', text: '#004d40' },
];

var soaData = null;

function buildSoAPreview(data) {
    soaData = data;
    var epochs = data.epochs;
    var columns = data.columns;
    var rows = data.rows;
    var epochColour = {};
    epochs.forEach(function(ep, i) {
        epochColour[ep.epochId] = EPOCH_COLOURS[i % EPOCH_COLOURS.length];
    });
    var epochSpans = [];
    var lastEpoch = null;
    columns.forEach(function(col) {
        if (col.epochId !== lastEpoch) {
            epochSpans.push({ epochId: col.epochId, epochName: col.epochName, span: 1 });
            lastEpoch = col.epochId;
        } else {
            epochSpans[epochSpans.length - 1].span++;
        }
    });

    var html = '<table class="soa-tbl" id="soaTable"><thead>';
    html += '<tr class="soa-epoch-row"><th class="soa-act-col">Activity / Procedure</th>';
    epochSpans.forEach(function(ep) {
        var c = epochColour[ep.epochId] || EPOCH_COLOURS[0];
        html += '<th colspan="' + ep.span + '" style="background:' + c.header + ';color:#fff">' + escHtml(ep.epochName) + '</th>';
    });
    html += '</tr>';
    html += '<tr class="soa-visit-row"><th class="soa-act-col"></th>';
    columns.forEach(function(col) {
        var c = epochColour[col.epochId] || EPOCH_COLOURS[0];
        var label = col.instanceName || col.encounterName || '-';
        html += '<th class="soa-visit-cell" style="background:' + c.header + 'cc;color:#fff" title="' + escHtml(col.encounterName) + '">' + escHtml(label) + '</th>';
    });
    html += '</tr>';
    html += '<tr class="soa-enc-row"><th class="soa-act-col" style="font-size:9px;color:#aaa">Encounter</th>';
    columns.forEach(function(col) {
        var c = epochColour[col.epochId] || EPOCH_COLOURS[0];
        html += '<th class="soa-enc-cell" style="background:' + c.bg + ';color:' + c.text + '">' + escHtml(col.encounterName) + '</th>';
    });
    html += '</tr></thead><tbody>';
    rows.forEach(function(row) {
        var bcBadge = row.bcCount > 0 ? ' <span class="bc-badge" title="' + row.bcCount + ' BC links">BC\xd7' + row.bcCount + '</span>' : '';
        html += '<tr class="soa-row" data-n="' + escHtml(row.activityName.toLowerCase()) + '">';
        html += '<td class="soa-act-name">' + escHtml(row.activityName) + bcBadge + '</td>';
        row.presence.forEach(function(present, ci) {
            var c = epochColour[columns[ci].epochId] || EPOCH_COLOURS[0];
            html += '<td class="soa-dot-cell" style="background:' + c.bg + '">' + (present ? '<span class="soa-dot">&#9679;</span>' : '') + '</td>';
        });
        html += '</tr>';
    });
    html += '</tbody></table>';
    document.getElementById('soaTableContainer').innerHTML = html;

    var legendHtml = '<strong>Epochs:</strong> ';
    epochSpans.forEach(function(ep) {
        var c = epochColour[ep.epochId] || EPOCH_COLOURS[0];
        legendHtml += '<span class="epoch-swatch" style="background:' + c.header + '">' + escHtml(ep.epochName) + '</span> ';
    });
    legendHtml += '&nbsp;&nbsp;<span style="color:#1565c0;font-weight:700">&#9679;</span> = scheduled';
    if (data.rows.some(function(r) { return r.bcCount > 0; })) {
        legendHtml += '&nbsp;&nbsp;<span class="bc-badge">BC\xd7N</span> = Biomedical Concept links';
    }
    document.getElementById('soaLegend').innerHTML = legendHtml;

    var scheduledCells = rows.reduce(function(n, r) { return n + r.presence.filter(function(p) { return p; }).length; }, 0);
    document.getElementById('soaPreviewMeta').textContent =
        rows.length + ' activities \xb7 ' + columns.length + ' visits \xb7 ' + scheduledCells + ' scheduled cells' +
        (data.usdmVersion ? ' \xb7 USDM ' + data.usdmVersion : '');
    document.getElementById('soaPreviewTitle').textContent =
        'Schedule of Activities — ' + (data.timelineName || 'Main Timeline');
}

function escHtml(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function toggleSoA() {
    var body = document.getElementById('soaPreviewBody');
    var icon = document.getElementById('soaToggleIcon');
    var collapsed = body.style.display === 'none';
    body.style.display = collapsed ? 'block' : 'none';
    icon.textContent = collapsed ? '▼' : '▶';
}

function filterSoARows(val) {
    var q = val.toLowerCase().trim();
    document.querySelectorAll('tr.soa-row').forEach(function(tr) {
        tr.style.display = (!q || (tr.getAttribute('data-n') || '').indexOf(q) >= 0) ? '' : 'none';
    });
}

// ======================================================================
app.controller("MainController", function($scope, $compile, $http) {
    $scope.studyUploadMessage = "";
    $scope.standardSelectionsMessage = "";
    $scope.activityToFormMappingsMessage = "";
    $scope.mappings = {};

    // ------------------------------------------------------------------ //
    //  Word normalisation + overlap (used by all matching tiers)          //
    // ------------------------------------------------------------------ //
    function normWord(w) {
        // basic plural/suffix stripping: medications->medication, assessments->assessment
        if (w.length > 5 && w.slice(-2) === 'es') return w.slice(0, -2);
        if (w.length > 4 && w.slice(-1) === 's')  return w.slice(0, -1);
        return w;
    }

    function wordOverlap(a, b) {
        var stop = {and:1,or:1,of:1,the:1,a:1,an:1,for:1,in:1,on:1,at:1,to:1};
        function words(str) {
            // Strip parenthetical content (e.g. activity names like "Vital Signs (Supine BP...)")
            // then replace remaining punctuation with spaces so commas/parens don't attach to words
            str = str.replace(/\([^)]*\)/g, ' ').replace(/[^a-z0-9\s]/g, ' ');
            return str.toLowerCase().split(/\s+/).filter(function(w) {
                return w.length > 1 && !stop[w];
            }).map(normWord);
        }
        var wa = words(a), wb = words(b);
        if (!wa.length || !wb.length) return 0;
        var setB = {};
        wb.forEach(function(w) { setB[w] = true; });
        return wa.filter(function(w) { return setB[w]; }).length / Math.min(wa.length, wb.length);
    }

    // ------------------------------------------------------------------ //
    //  Priority 1: BC → question SDTM code → form  (highest precision)   //
    //  Requires standardForms[label].questions from the enriched api.py.  //
    // ------------------------------------------------------------------ //
    function findBestBCQuestionMatch(resolvedBCs, standardForms, formLabels) {
        if (!resolvedBCs || !resolvedBCs.length) return null;

        // Collect all SDTM codes this activity's BCs carry
        var bcSdtmCodes = {};
        resolvedBCs.forEach(function(bc) {
            if (bc.sdtmCode) bcSdtmCodes[bc.sdtmCode] = true;
        });

        // Priority A: exact SDTM code match (BC sdtmCode == question sdtmCode)
        for (var fi = 0; fi < formLabels.length; fi++) {
            var formInfo = standardForms[formLabels[fi]];
            var questions = (formInfo && formInfo.questions) || [];
            for (var qi = 0; qi < questions.length; qi++) {
                var qCode = (questions[qi].sdtmCode || '').toUpperCase();
                if (qCode && bcSdtmCodes[qCode]) {
                    console.log('BC Question SDTM match: ' + qCode + ' -> ' + formLabels[fi]);
                    return formLabels[fi];
                }
            }
        }

        // Priority B: fuzzy BC name/synonym vs question label (>=0.75 threshold)
        var bcTexts = [];
        resolvedBCs.forEach(function(bc) {
            if (bc.name)  bcTexts.push(bc.name);
            if (bc.label && bc.label !== bc.name) bcTexts.push(bc.label);
            (bc.synonyms || []).forEach(function(s) { if (s) bcTexts.push(s); });
        });
        var bestLabel = null, bestScore = 0;
        for (var fi2 = 0; fi2 < formLabels.length; fi2++) {
            var formInfo2 = standardForms[formLabels[fi2]];
            var questions2 = (formInfo2 && formInfo2.questions) || [];
            for (var qi2 = 0; qi2 < questions2.length; qi2++) {
                var qLabel = questions2[qi2].label || '';
                for (var ti = 0; ti < bcTexts.length; ti++) {
                    var score = wordOverlap(bcTexts[ti], qLabel);
                    if (score > bestScore) { bestScore = score; bestLabel = formLabels[fi2]; }
                }
            }
        }
        return bestScore >= 0.75 ? bestLabel : null;
    }

    // ------------------------------------------------------------------ //
    //  Priority 3: BC name/synonym vs form label  (form-level fuzzy)     //
    // ------------------------------------------------------------------ //
    function findBestBCNameMatch(resolvedBCs, formLabels) {
        if (!resolvedBCs || !resolvedBCs.length) return null;
        var bestLabel = null, bestScore = 0;
        for (var bi = 0; bi < resolvedBCs.length; bi++) {
            var bc = resolvedBCs[bi];
            var candidates = [];
            if (bc.name)  candidates.push(bc.name);
            if (bc.label && bc.label !== bc.name) candidates.push(bc.label);
            (bc.synonyms || []).forEach(function(s) { if (s) candidates.push(s); });
            for (var ci = 0; ci < candidates.length; ci++) {
                for (var fi = 0; fi < formLabels.length; fi++) {
                    var score = wordOverlap(candidates[ci], formLabels[fi]);
                    if (score > bestScore) { bestScore = score; bestLabel = formLabels[fi]; }
                }
            }
        }
        return bestScore >= 0.70 ? bestLabel : null;
    }

    // ------------------------------------------------------------------ //
    //  Priority 5: fuzzy activity name vs form label                      //
    // ------------------------------------------------------------------ //
    function findBestFormMatch(activityName, formLabels) {
        var bestLabel = null, bestScore = 0;
        for (var i = 0; i < formLabels.length; i++) {
            var score = wordOverlap(activityName, formLabels[i]);
            if (score > bestScore) { bestScore = score; bestLabel = formLabels[i]; }
        }
        return bestScore >= 0.75 ? bestLabel : null;
    }

    // ------------------------------------------------------------------ //
    //  Step 1: Upload USDM JSON                                           //
    // ------------------------------------------------------------------ //
    $scope.uploadStudy = function() {
        $scope.studyUploadMessage = "Uploading USDM definition and retrieving standards...";
        var file = document.getElementById('study').files[0];
        if (!file) { $scope.studyUploadMessage = "Please select a JSON file first."; return; }
        var reader = new FileReader();
        reader.onloadend = function(e) {
            var studyObj;
            try { studyObj = JSON.parse(e.target.result); }
            catch (err) {
                $scope.$apply(function() { $scope.studyUploadMessage = "Invalid JSON: " + err.message; });
                return;
            }
            $http({
                method: 'POST', url: 'http://127.0.0.1:5000/study',
                data: { study: studyObj }, headers: { 'Content-Type': 'application/json' }
            }).then(
                function(resp) {
                    $scope.standards = resp.data;
                    $scope.standardSelections = Object.keys(resp.data);
                    $scope.studyUploadMessage = "2 - Select an Activities program standard.";
                    $http.get('http://127.0.0.1:5000/study-soa-data').then(
                        function(soaResp) {
                            document.getElementById('soaPreviewSection').style.display = 'block';
                            buildSoAPreview(soaResp.data);
                        },
                        function() {}
                    );
                },
                function(err) { $scope.studyUploadMessage = err.data || "Upload failed. Check server logs."; }
            );
        };
        reader.readAsText(file);
    };

    // ------------------------------------------------------------------ //
    //  Step 2a: Standard forms (with question inventory)                  //
    // ------------------------------------------------------------------ //
    var getStandardForms = function() {
        var selected = $scope.standards[$scope.selectedStandard];
        $http({
            method: 'GET',
            url: 'http://127.0.0.1:5000/standard-forms/' + selected.aid + '/' + selected.version
        }).then(
            function(resp) {
                $scope.standardSelectionsMessage = "Getting study activities...";
                $scope.standardForms = resp.data;
                getStudyActivities();
            },
            function(err) { $scope.standardSelectionsMessage = err.data || "Failed to load standard forms."; }
        );
    };

    // ------------------------------------------------------------------ //
    //  Step 2b: Study activities                                           //
    // ------------------------------------------------------------------ //
    var getStudyActivities = function() {
        $http({ method: 'GET', url: 'http://127.0.0.1:5000/study-activities' }).then(
            function(resp) {
                $scope.standardSelectionsMessage = "Populating activity mapping fields...";
                $scope.studyActivities = resp.data;
                populateActivityMappingFields();
            },
            function(err) { $scope.standardSelectionsMessage = err.data || "Failed to load study activities."; }
        );
    };

    // ------------------------------------------------------------------ //
    //  Step 3: Mapping table with 5-tier auto-matching                    //
    // ------------------------------------------------------------------ //
    var populateActivityMappingFields = function() {
        var formLabels = Object.keys($scope.standardForms);
        $scope.formSelections = formLabels;

        var autoMappedCount = 0;
        var html = "<table><thead><tr>"
                 + "<th>USDM Activity</th><th>ryze Form</th><th>Match</th>"
                 + "</tr></thead><tbody>";

        for (var i = 0; i < $scope.studyActivities.length; i++) {
            var activity = $scope.studyActivities[i];
            var activityId   = activity.activityId;
            var activityName = activity.activityName || "(unnamed)";
            var preselectedIndex = -1;
            var matchMethod = "";

            // Priority 1: BC question SDTM code match (question-level, most precise)
            if (preselectedIndex === -1) {
                var qMatch = findBestBCQuestionMatch(
                    activity.resolvedBCs, $scope.standardForms, formLabels);
                if (qMatch !== null) {
                    preselectedIndex = formLabels.indexOf(qMatch);
                    matchMethod = "BC Question";
                }
            }

            // Priority 2: BC alias (ryze code system) — v1 exact alias match
            if (preselectedIndex === -1) {
                var hasBCs = activity.biomedicalConcepts && activity.biomedicalConcepts.length > 0;
                if (hasBCs) {
                    var bc = activity.biomedicalConcepts[0];
                    var isRyzeMapping = bc.bcConceptCode &&
                        bc.bcConceptCode.standardCode &&
                        bc.bcConceptCode.standardCode.codeSystem === "https://ryze.formedix.com";
                    if (isRyzeMapping) {
                        var mappingCode = bc.bcConceptCode.standardCode.code;
                        for (var fi = 0; fi < formLabels.length; fi++) {
                            var formInfo = $scope.standardForms[formLabels[fi]];
                            if (formInfo.alias && formInfo.alias === mappingCode) {
                                preselectedIndex = fi;
                                matchMethod = "BC";
                                break;
                            }
                        }
                    }
                }
            }

            // Priority 3: BC name/synonym word overlap vs form label
            if (preselectedIndex === -1) {
                var bcNameMatch = findBestBCNameMatch(activity.resolvedBCs, formLabels);
                if (bcNameMatch !== null) {
                    preselectedIndex = formLabels.indexOf(bcNameMatch);
                    matchMethod = "BC Name";
                }
            }

            // Priority 4: Exact activity label match
            if (preselectedIndex === -1) {
                var exactIdx = formLabels.indexOf(activityName);
                if (exactIdx !== -1) { preselectedIndex = exactIdx; matchMethod = "Exact"; }
            }

            // Priority 5: Fuzzy activity name word overlap
            if (preselectedIndex === -1) {
                var fuzzyMatch = findBestFormMatch(activityName, formLabels);
                if (fuzzyMatch !== null) {
                    preselectedIndex = formLabels.indexOf(fuzzyMatch);
                    matchMethod = "Fuzzy";
                }
            }

            if (preselectedIndex !== -1) autoMappedCount++;

            var badgeClass = matchMethod ? "match-" + matchMethod.toLowerCase().replace(/ /g, '') : "match-none";
            var badgeText  = matchMethod || "Manual";
            var matchBadge = "<span class='match-badge " + badgeClass + "'>" + badgeText + "</span>";

            var ngModel = "mappings['" + activityId + "']";
            var selectHtml = preselectedIndex !== -1
                ? "<select ng-init=\"" + ngModel + "=formSelections[" + preselectedIndex + "]\" ng-model=\"" + ngModel + "\" ng-options='x for x in formSelections'></select>"
                : "<select ng-model=\"" + ngModel + "\" ng-options='x for x in formSelections'></select>";

            html += "<tr><td class='activity-column'>" + activityName + "</td>"
                  + "<td>" + selectHtml + "</td>"
                  + "<td>" + matchBadge + "</td></tr>";
        }

        html += "</tbody></table>";
        html += "<p class='auto-map-summary'>" + autoMappedCount + " of " + $scope.studyActivities.length + " activities auto-mapped.</p>";
        html += "<button ng-click='confirmMappings()' class='top-margin'>Confirm Mappings</button>";

        var div = document.getElementById('activityToFormMappings');
        div.innerHTML = html;
        $compile(angular.element(div))($scope);
        $scope.standardSelectionsMessage = "3 - Review auto-mapped activities and adjust as needed, then confirm.";
    };

    $scope.confirmStandard = function() {
        $scope.standardSelectionsMessage = "Getting standard forms...";
        getStandardForms();
    };

    // ------------------------------------------------------------------ //
    //  Step 4: Confirm mappings                                            //
    // ------------------------------------------------------------------ //
    $scope.confirmMappings = function() {
        $scope.activityToFormMappingsMessage = "Creating ryze study...";
        $http({
            method: 'POST', url: 'http://127.0.0.1:5000/mappings',
            data: { mappings: $scope.mappings }, headers: { 'Content-Type': 'application/json' }
        }).then(
            function() { $scope.activityToFormMappingsMessage = "Study creation complete. Check ryze to see your converted study."; },
            function(err) { $scope.activityToFormMappingsMessage = err.data || "Error creating study. Check server logs."; }
        );
    };
});
