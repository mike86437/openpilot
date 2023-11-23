<div id="debug-container" style="font-size: 28px;">
    <!-- JSON data will be displayed here -->
</div>

    <button onclick="toggleUnits()">Toggle Units</button>

    <script>
      let useMph = true;

      function fetchData() {
        fetch('debug_output.json')
          .then(response => response.json())
          .then(data => {
            // Create an HTML string for each key-value pair
            const htmlString = Object.entries(data)
              .map(([key, value]) => `<strong>${key}:</strong> ${convertValue(value)}<br>`)
              .join('');

            // Update the content in the 'debug-container' div
            document.getElementById('debug-container').innerHTML = htmlString;
          })
          .catch(error => console.error('Error fetching data:', error));
      }

      // Initial fetch
      fetchData();

      // Set up a timer to fetch data every 5 seconds
      setInterval(fetchData, 2000);

      // Function to convert values based on units
      function convertValue(value) {
        if (typeof value === 'boolean') {
          return value ? 'True' : 'False';
        } else if (typeof value === 'number') {
          return useMph ? (value * 2.23694).toFixed(2) + ' mph' : value.toFixed(2) + ' m/s';
        } else {
          return value;
        }
      }

      // Function to toggle between units
      function toggleUnits() {
        useMph = !useMph;
        fetchData();  // Fetch data to update displayed values with the new unit
      }
    </script>
