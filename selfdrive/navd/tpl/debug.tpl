<div id="debug-container" style="font-size: 20px;">
    <!-- JSON data will be displayed here -->
</div>

<script>
function fetchData() {
    fetch('debug_output.json')
        .then(response => response.json())
        .then(data => {
            // Convert m/s to mph
            data.override_slc = data.override_slc ? "True" : "False";  // Convert boolean to string

            data.overridden_speed = (data.overridden_speed * 2.23694).toFixed(2);
            data.v_slc_target = (data.v_slc_target * 2.23694).toFixed(2);
            data.v_target = (data.v_target * 2.23694).toFixed(2);
            data.v_cruise = (data.v_cruise * 2.23694).toFixed(2);
            data.v_cruise1 = (data.v_cruise1 * 2.23694).toFixed(2);

            // Create an HTML string for each key-value pair
            const htmlString = Object.entries(data)
                .map(([key, value]) => `<strong>${key}:</strong> ${value}<br>`)
                .join('');

            // Update the content in the 'debug-container' div
            document.getElementById('debug-container').innerHTML = htmlString;
        })
        .catch(error => console.error('Error fetching data:', error));
}

// Initial fetch
fetchData();

// Set up a timer to fetch data every 5 seconds
setInterval(fetchData, 5000);
</script>
