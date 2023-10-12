<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>openpilot Navigation</title>
  <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no">
  <!-- UIkit CSS -->
  

  <!-- UIkit JS -->
  <script src="https://cdn.jsdelivr.net/npm/uikit@3.9.2/dist/js/uikit.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/uikit@3.9.2/dist/js/uikit-icons.min.js"></script>
  <style>
        body {
            padding: 25px;
            background-color: #121212;
            color: white;
            font-size: 25px;
        }
 
        .dark-mode {
            background-color: black;
            color: white;
        }
 
        .light-mode {
            background-color: white;
            color: black;
        }
        .button-container {
            display: flex;
            justify-content: center;
            align-items: center;
        }
        button {
            margin: 5px; /* Add some spacing between the buttons */
        }
  </style>
</head>
<body style="margin: 0; padding: 0;">
    <div class="button-container">
        <button onclick="darkMode()">Dark Mode</button>
        <button onclick="lightMode()">Light Mode</button>
        <button id="unitToggle">Toggle Units</button>
    </div>
    <script>
        function darkMode() {
            let element = document.body;
            let content = document.getElementById("DarkModetext");
            element.className = "dark-mode";
            content.innerText = "Dark Mode is ON";
        }
        function lightMode() {
            let element = document.body;
            let content = document.getElementById("DarkModetext");
            element.className = "light-mode";
            content.innerText = "Dark Mode is OFF";
        }
    </script>  {{content}}
  </div>
</body>
</html>
