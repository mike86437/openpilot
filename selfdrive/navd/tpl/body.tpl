<!DOCTYPE html>
<html lang="en" id="htmlElement">
<head>
  <meta charset="utf-8">
  <title>openpilot Navigation</title>
  <meta name="viewport" content="initial-scale=1, maximum-scale=1, user-scalable=no">
  <!-- UIkit CSS -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uikit@3.9.2/dist/css/uikit.min.css" />

  <!-- UIkit JS -->
  <script src="https://cdn.jsdelivr.net/npm/uikit@3.9.2/dist/js/uikit.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/uikit@3.9.2/dist/js/uikit-icons.min.js"></script>

  <!-- Custom Styles for Dark Mode -->
  <style>
    #htmlElement.dark-mode {
      background-color: #121212; /* Dark background color */
      color: #ffffff; /* Light text color */
    }

    #htmlElement.dark-mode input, #htmlElement.dark-mode select {
      background-color: #333; /* Dark input/select background color */
      color: #ffffff; /* Light input/select text color */
    }

    /* Add more custom styles as needed for other elements */
  </style>

  <!-- Script to set default dark mode -->
  <script>
    document.addEventListener('DOMContentLoaded', function () {
      document.getElementById('htmlElement').classList.add('dark-mode');
    });
  </script>
</head>
<body style="margin: 0; padding: 0;">


  <div style="display: grid; place-items: center;">
    {{content}}
  </div>
  <!-- Dark Mode Toggle Button -->
  <button class="uk-button uk-button-default uk-margin-small-right" onclick="toggleDarkMode()">Toggle Dark Mode</button>

  <script>
    function toggleDarkMode() {
      document.getElementById('htmlElement').classList.toggle('dark-mode');
    }
  </script>
</body>
</html>
