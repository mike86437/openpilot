<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>openpilot Navigation</title>
  <meta name="viewport" content="initial-scale=1,maximum-scale=1,user-scalable=no">
  <!-- UIkit CSS -->
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/uikit@3.9.2/dist/css/uikit.min.css" />

  <!-- UIkit JS -->
  <script src="https://cdn.jsdelivr.net/npm/uikit@3.9.2/dist/js/uikit.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/uikit@3.9.2/dist/js/uikit-icons.min.js"></script>
  <style>
        body {
            padding: 25px;
            background-color: white;
            color: black;
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
  </style>
</head>
<body style="margin: 0; padding: 0;">
  <div style="display: grid; place-items: center;">
  <button onclick="darkMode()">Darkmode</button>
    <button onclick="lightMode()">LightMode</button>
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
    </script>
  {{content}}
  </div>
</body>
</html>
