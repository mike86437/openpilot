import os
import shutil
from openpilot.common.params import Params

# Define the mapping of Model values to supercombo variant names
MODEL_NAME = {
  0: "optimus-prime",
  1: "B4+B0",
  2: "farmville",
  3: "new-lateral-planner",
  4: "non-inflatable",
  5: "night-strike",
}

# Path to the source models directories
SOURCE_THNEED_MODELS_PATH = "/data/openpilot/selfdrive/modeld/models/thneed_models"
# Path to the models directory
DESTINATION_MODELS_PATH = "/data/openpilot/selfdrive/modeld/models"
THNEED_PATH = os.path.join(DESTINATION_MODELS_PATH, "supercombo.thneed")
# Path to the prebuilt file
PREBUILT_PATH = "/data/openpilot/prebuilt"

def main():
  # Get the corresponding supercombo variant name
  params = Params()
  variant = MODEL_NAME.get(params.get_int("Model"), MODEL_NAME[0])

  # Copy the variant .thneed file to supercombo.thneed in the destination models folder
  source = os.path.join(SOURCE_THNEED_MODELS_PATH, f"{variant}.thneed")
  destination = os.path.join(DESTINATION_MODELS_PATH, "supercombo.thneed")
  shutil.copy(source, destination) 

  # Remove the prebuilt file so the models can compile
  if os.path.exists(PREBUILT_PATH):
    os.remove(PREBUILT_PATH)

  # Reset the calibration
  params.remove("CalibrationParams")
  params.remove("LiveTorqueParameters")

if __name__ == "__main__":
  main()
