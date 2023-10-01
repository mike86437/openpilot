import os
from openpilot.common.params import Params

# Define the mapping of Model values to supercombo variant names
MODEL_NAME = {
  0: "optimus_prime",
  1: "B4+B0",
  2: "farmville",
  3: "new-lateral-planner",
  4: "nicki-minaj",
  5: "non-inflatable",
}

# Path to the source models directory
SOURCE_MODELS_PATH = "/data/openpilot/selfdrive/modeld/models/onnx_models"
# Path to the models directory
DESTINATION_MODELS_PATH = "/data/openpilot/selfdrive/modeld/models"
THNEED_PATH = os.path.join(DESTINATION_MODELS_PATH, "supercombo.thneed")
# Path to the prebuilt file
PREBUILT_PATH = "/data/openpilot/prebuilt"

def main():
  # Get the corresponding supercombo variant name
  params = Params()
  variant = MODEL_NAME.get(params.get_int("Model"), MODEL_NAME[0])
  if variant == MODEL_NAME[0]:
    print(f"Unknown model value: {params.get_int('Model')}")

  # Remove the current thneed file
  if os.path.exists(THNEED_PATH):
    os.remove(THNEED_PATH)

  # Copy the variant .onnx file to supercombo.onnx in the destination models folder
  source = os.path.join(SOURCE_MODELS_PATH, f"{variant}.onnx")
  destination = os.path.join(DESTINATION_MODELS_PATH, "supercombo.onnx")
  os.rename(source, destination)

  # Remove the prebuilt file so the models can compile
  if os.path.exists(PREBUILT_PATH):
    os.remove(PREBUILT_PATH)

  # Reset the calibration
  params.remove("CalibrationParams")
  params.remove("LiveTorqueParameters")

if __name__ == "__main__":
  main()
