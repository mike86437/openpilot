    <button id="unitToggle">Toggle Units</button>
    <div id="destinationHeading" style="font-size: 18px; font-weight: bold;"></div>
    <div id="jsonOutput"></div>
    <script>
        let useMetricUnits = true;

        // Function to fetch and display JSON data
        async function fetchAndDisplayData() {
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
                const destination = firstRoute.destination; // Access the 'destination' value

                // Display the 'destination' value on the webpage
                const destinationHeading = document.getElementById('destinationHeading');
                destinationHeading.textContent = `Destination: ${destination}`;

                // Display values from the steps
                const jsonOutputDiv = document.getElementById('jsonOutput');
                jsonOutputDiv.innerHTML = '';

                for (let i = 0; i < steps.length; i++) {
                    const step = steps[i];
                    const instruction = step.maneuver.instruction;
                    let distance = step.distance;

                    if (!useMetricUnits) {
                        // Convert distance to miles if using imperial units
                        distance = distance * 0.000621371;
                    }

                    // Display the values on the webpage
                    jsonOutputDiv.innerHTML += `
                        <p>In ${distance.toFixed(1)} ${useMetricUnits ? 'km' : 'miles'}: ${instruction}</p>
                        <hr>
                    `;
                }
            } catch (error) {
                console.error('Error fetching or parsing JSON data:', error);
                // Display error message on the webpage
                const jsonOutputDiv = document.getElementById('jsonOutput');
                jsonOutputDiv.innerHTML = `<p>Error: ${error.message}</p>`;
            }
        }

        // Toggle the unit (metric/imperial) when the button is clicked
        const toggleUnitButton = document.getElementById('unitToggle'); // Corrected ID
        toggleUnitButton.addEventListener('click', () => {
            useMetricUnits = !useMetricUnits;
            // Re-fetch and display data with the updated unit
            fetchAndDisplayData();
        });

        // Fetch and display data initially
        fetchAndDisplayData();

        // Periodically fetch and display data every 5 seconds
        setInterval(fetchAndDisplayData, 5000); // Adjust the interval as needed (in milliseconds)
    </script>
