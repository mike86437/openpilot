<div id="debug-container">
    <!-- JSON data will be displayed here -->
</div>

<script>
function fetchData() {
    fetch('debug_output.json')
        .then(response => response.json())
        .then(data => {
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
