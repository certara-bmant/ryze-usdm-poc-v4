$scope.uploadStudy = function() {
    $scope.studyUploadMessage = "Uploading SoA and retrieving standards in the Activities program...";
    var f = document.getElementById('study').files[0];

    const formData = new FormData();
    formData.append('file', f);

    $http({
        method: 'POST',
        url: 'http://127.0.0.1:5000/study',
        data: formData,
        transformRequest: angular.identity,
        headers: {'Content-Type': undefined}
    }).then(
        function(resp){
            $scope.standards = resp.data;
            $scope.standardSelections = Object.keys(resp.data);
            $scope.studyUploadMessage = "2 - Select an Activities program standard.";
        },
        function(err){
            $scope.studyUploadMessage = err.data;
        }
    );
}

       r.readAsBinaryString(f);
    }

    const getStandardForms = function() {
       $http({
           method: 'GET',
           url: 'http://127.0.0.1:5000/standard-forms/' + $scope.standards[$scope.selectedStandard].aid + '/' + $scope.standards[$scope.selectedStandard].version
       }).then(
           function(resp){
               $scope.standardSelectionsMessage = "Getting study activities...";
               $scope.standardForms = resp.data;
               getStudyActivities();
           },
           function(err){
               $scope.standardSelectionsMessage = err.data;
           }
       );
    }

    const getStudyActivities = function() {
       $http({
           method: 'GET',
           url: 'http://127.0.0.1:5000/study-activities'
       }).then(
           function(resp){
               $scope.standardSelectionsMessage = "Populating activity mapping fields...";
               $scope.studyActivities = resp.data;
               populateActivityMappingFields();
           },
           function(err){
               $scope.standardSelectionsMessage = err.data;
           }
       );
    }

    const populateActivityMappingFields = function() {
        // Get form selections as array
        forms = []
        for (form in $scope.standardForms){
            forms.push(form);
        }
        $scope.formSelections = forms;

        // Generate mapping field HTML
        let html = "<table>";
        for (activity of $scope.studyActivities){
            html += ("<tr>");
            html += ("<td class='activity-column'>" + activity.activityName + ": </td>");

            // If the activity has a BC, and that BC contains a mapping, and a form has a corresponding alias, preselect the mapping field value
            const activityHasBiomedicalConcepts = activity.biomedicalConcepts && activity.biomedicalConcepts.length > 0;
            if (activityHasBiomedicalConcepts){
                biomedicalConcept = activity.biomedicalConcepts[0];
                const biomedicalConceptIsMapping = biomedicalConcept.bcConceptCode && biomedicalConcept.bcConceptCode.standardCode && biomedicalConcept.bcConceptCode.standardCode.codeSystem == "https://ryze.formedix.com";
                if (biomedicalConceptIsMapping){
                    console.log(activity.activityId + " has ryze Form Mapping BC " + biomedicalConcept.bcConceptCode.standardCode.code);
                    mapping = biomedicalConcept.bcConceptCode.standardCode.code;
                    for (form in $scope.standardForms){
                        const aliasCorrespondsToMapping = $scope.standardForms[form].alias && $scope.standardForms[form].alias == mapping;
                        if(aliasCorrespondsToMapping){
                            console.log("Standard form " + form + " has corresponding mapping " + $scope.standardForms[form].alias);
                            const formIndex = $scope.formSelections.indexOf(form);
                            html += ("<td>");
                            html += ("<select ng-init='mappings." + activity.activityId + " = formSelections[" + formIndex + "]' ng-model='mappings." + activity.activityId + "' ng-options='x for x in formSelections'>");
                            html += ("</select>");
                            html += ("</td>");
                        }
                    }
                }
            }
            // Otherwise, generate the mapping field dropdown without preselecting the value
            else{
                html += ("<td><select ng-model='mappings." + activity.activityId + "' ng-options='x for x in formSelections'></select></td>");
            }

            html += ("</tr>");
        }
        html += ("</table><button ng-click='confirmMappings()' class='top-margin'>Confirm Mappings</button>");

        const div = document.getElementById('activityToFormMappings');
        div.innerHTML += html;
        const directiveElement = angular.element(div);
        $compile(directiveElement)($scope);

        $scope.standardSelectionsMessage = "3 - Map the activities on the left to your standard forms on the right. Unmapped activities will be excluded from import.";
    }

    $scope.confirmStandard = function() {
        $scope.standardSelectionsMessage = "Getting standard forms..."
        getStandardForms();
    }

    $scope.confirmMappings = function() {
        $scope.activityToFormMappingsMessage = "Uploading mapping and creating ryze study...";
        console.log($scope.mappings);
        const formData = new FormData();
        formData.append('mappings', JSON.stringify($scope.mappings));
        const transformRequest = angular.identity;
        const headers = {'Content-Type': undefined};
        $http({
            method: 'POST',
            url: 'http://127.0.0.1:5000/mappings',
            data: formData,
            transformRequest: angular.identity,
            headers: {'Content-Type': undefined}
        }).then(
            function(resp){
                $scope.activityToFormMappingsMessage = "Study creation complete. Check ryze to see your converted study.";
            },
            function(err){
                $scope.activityToFormMappingsMessage = err.data;
            }
        );
    }
})