<button id="unitToggle">Toggle Units</button>
<div id="destinationHeading" style="font-size: 18px; font-weight: bold;"></div>
<div id="jsonOutput"></div>
    <script>
        // Function to fetch and display JSON data
        async function fetchAndDisplayData(useMetric) {
            try {
                const response = await fetch('navdirections.json'); // Provide the full path
                if (!response.ok) {
                    throw new Error(`Failed to fetch JSON file. Status: ${response.status}`);
                }
                const jsonData = await response.json();

                // Access the first route's nested structure
                const firstRoute = jsonData.routes[0]; // Access the first route
                const firstLeg = firstRoute.legs[0]; // Access the first leg
                const steps = firstLeg.steps; // Access the steps array
                const destination = firstRoute.Destination; // Access the 'Destination' value

                // Display the 'Destination' value on the webpage
                const destinationHeading = document.getElementById('destinationHeading');
                destinationHeading.textContent = `Destination: ${destination}`;

                const currentStep = firstRoute.CurrentStep;

                // Display values from the steps starting from 'CurrentStep'
                const jsonOutputDiv = document.getElementById('jsonOutput');
                jsonOutputDiv.innerHTML = '';

                for (let i = currentStep; i < steps.length - 1; i++) {
                    const instruction = steps[i + 1].maneuver.instruction;
                    let distanceValue = steps[i].distance;

                    if (useMetric) {
                        distanceValue /= 1000; // Convert to kilometers
                        jsonOutputDiv.innerHTML += `<p>In ${distanceValue.toFixed(2)} km: ${instruction}</p>`;
                    } else {
                        // Convert to miles
                        const distanceMiles = distanceValue * 0.000621371;
                        jsonOutputDiv.innerHTML += `<p>In ${distanceMiles.toFixed(2)} miles: ${instruction}</p>`;
                    }

                    jsonOutputDiv.innerHTML += `<hr>`;
                }
            } catch (error) {
                console.error('Error fetching or parsing JSON data:', error);
                // Display error message on the webpage
                const jsonOutputDiv = document.getElementById('jsonOutput');
                jsonOutputDiv.innerHTML = `<p>Error: ${error.message}</p>`;
            }
        }

        // Initial display with the default unit (imperial)
        fetchAndDisplayData(false);

        // Toggle unit button
        const unitToggleBtn = document.getElementById('unitToggle');
        let useMetricUnits = false; // Flag to track units

        unitToggleBtn.addEventListener('click', () => {
            // Toggle the unit flag and update the display
            useMetricUnits = !useMetricUnits;
            fetchAndDisplayData(useMetricUnits);
        });
    </script>

