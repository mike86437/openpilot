import os
import shutil
from openpilot.common.params import Params

DESTINATION_PATH = "/data/openpilot/selfdrive/modeld/models"
ONNX_MODELS_SOURCE = os.path.join(DESTINATION_PATH, "onnx_models")
SUPERCOMBO_THNEED_PATH = os.path.join(DESTINATION_PATH, "supercombo.thneed")
PREBUILT_PATH = "/data/openpilot/prebuilt"

MODEL_NAME = {
  0: "night-strike",
  1: "B4+B0",
  2: "farmville",
  3: "new-lemon-pie",
  4: "non-inflatable",
  5: "optimus-prime",
}

def remove_file(path):
  """Remove file if it exists."""
  if os.path.exists(path):
    os.remove(path)

def copy_model_variant():
  # Remove the thneed file
  remove_file(SUPERCOMBO_THNEED_PATH)

  # Get the corresponding supercombo variant name
  params = Params()
  variant = MODEL_NAME.get(params.get_int("Model"), MODEL_NAME[0])

  # Copy the variant .onnx file to supercombo.onnx in the destination models folder
  onnx_path = os.path.join(ONNX_MODELS_SOURCE, f"{variant}.onnx")
  destination = os.path.join(DESTINATION_PATH, "supercombo.onnx")
  shutil.copy(onnx_path, destination)

  # Remove the prebuilt file so the model can compile
  remove_file(PREBUILT_PATH)

  # Reset the calibration
  params.remove("CalibrationParams")
  params.remove("LiveTorqueParameters")

if __name__ == "__main__":
  copy_model_variant()
