<div id="destinationHeading" style="font-weight: bold;"></div>
<div id="jsonOutput"></div>
<script>
  let useMetricUnits = false;
  let previousUuid = null;
  let jsonData = null;

  async function loadNavdirectionsData() {
    try {
      const response = await fetch('navdirections.json'); // Load navdirections.json

      if (!response.ok) {
        throw new Error(`Failed to fetch JSON file. Status: ${response.status}`);
      }

      const json = await response.json();

      if (json.uuid !== previousUuid) {
        // Update the `previousUuid` and `jsonData`
        previousUuid = json.uuid;
        jsonData = json;
      }

      return jsonData;
    } catch (error) {
      console.error('Error fetching or parsing JSON data:', error);
      return jsonData; // Return the existing data on error
    }
  }

  async function loadCurrentStep() {
    try {
      const response = await fetch('CurrentStep.json'); // Load CurrentStep.json

      if (!response.ok) {
        throw new Error('Failed to fetch CurrentStep.json.');
      }

      const json = await response.json();
      return json;
    } catch (error) {
      console.error('Error fetching or parsing CurrentStep.json:', error);
      return null;
    }
  }

  async function fetchAndDisplayData() {
    const navdirectionsData = await loadNavdirectionsData();

    if (navdirectionsData) {
      // Access the data you need from the loaded JSON
      const firstRoute = navdirectionsData.routes[0];
      const firstLeg = firstRoute.legs[0];
      const steps = firstLeg.steps;
      const destination = firstRoute.Destination;

      // Determine whether to use metric or imperial units based on the 'Metric' key
      const useMetricUnits = firstRoute.Metric === true;

      // Display the 'destination' value on the webpage
      const destinationHeading = document.getElementById('destinationHeading');
      destinationHeading.textContent = `Destination: ${destination}`;
      const currentStepData = await loadCurrentStep();

      if (currentStepData !== null) {
        // Display values from the steps
        const jsonOutputDiv = document.getElementById('jsonOutput');
        jsonOutputDiv.innerHTML = '';

        for (let i = currentStepData.CurrentStep; i < steps.length - 1; i++) {
          const step = steps[i];
          const instruction0 = steps[i].maneuver.instruction;
          const instruction = steps[i + 1].maneuver.instruction;
          let distance = step.distance;

          if (!useMetricUnits) {
            // Convert distance to miles if using imperial units
            distance = distance * 0.000621371;
          } else {
            distance = distance / 1000; // Convert meters to kilometers
          }

          // Display the values on the webpage
          if (i === 0) {
            jsonOutputDiv.innerHTML += `
              <p>${instruction0}</p>
              <hr>
            `;
          }
          jsonOutputDiv.innerHTML += `
            <p>In ${distance.toFixed(1)} ${useMetricUnits ? 'km' : 'miles'}: ${instruction}</p>
            <hr>
          `;
        }
      }
    }
  }

  // Load `CurrentStep.json` initially
  loadCurrentStep().then((currentStepData) => {
    if (currentStepData !== null) {
      // Set the initial value for `currentStep` based on `CurrentStep.json`
      previousUuid = currentStepData.uuid;
      jsonData = null; // Ensure `jsonData` is not loaded initially
      // Fetch and display data initially
      fetchAndDisplayData();
    }
  });

  // Periodically fetch `CurrentStep.json` and display data every 5 seconds
  setInterval(fetchAndDisplayData, 5000); // Adjust the interval as needed (in milliseconds)
</script>
