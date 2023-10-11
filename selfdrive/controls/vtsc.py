# PFEIFER - VTSC

# Acknowledgements:
# Past versions of this code were based on the move-fast teams vtsc
# implementation. (https://github.com/move-fast/openpilot) Huge thanks to them
# for their initial implementation. I also used sunnypilot as a reference.
# (https://github.com/sunnyhaibin/sunnypilot) Big thanks for sunny's amazing work

import numpy as np
from time import time

TARGET_LAT_A = 1.9  # m/s^2
MIN_TARGET_V = 5    # m/s

class VisionTurnController():
  def __init__(self):
    self.op_enabled = False
    self.gas_pressed = False
    self.v_offset = 0
    self.v_target = MIN_TARGET_V

  @property
  def active(self):
    return self.op_enabled and not self.gas_pressed

  def update(self, op_enabled, v_ego, sm, curve_sensitivity, turn_aggressiveness, v_cruise):
    self.op_enabled = op_enabled
    self.gas_pressed = sm['carState'].gasPressed

    # Adjust the rate plan with curve sensitivity
    rate_plan = np.array(np.abs(sm['modelV2'].orientationRate.z)) * curve_sensitivity
    vel_plan = np.array(sm['modelV2'].velocity.x)

    # Get the maximum lat accel from the model
    predicted_lat_accels = rate_plan * vel_plan
    self.max_pred_lat_acc = np.amax(predicted_lat_accels)

    # Get the maximum curve based on the current velocity
    v_ego = max(v_ego, 0.1)  # Ensure a value greater than 0 for calculations
    max_curve = self.max_pred_lat_acc / (v_ego**2)

    # Adjust the target lateral acceleration with turn aggressiveness
    adjusted_target_lat_a = TARGET_LAT_A * turn_aggressiveness

    # Get the target velocity for the maximum curve
    self.v_target = (adjusted_target_lat_a / max_curve) ** 0.5
    self.v_target = max(self.v_target, MIN_TARGET_V)

    # Configure the offset value for the UI
    self.v_offset = 0 if np.isnan(v_cruise - self.v_target) else max(0, int(v_cruise - self.v_target))

vtsc = VisionTurnController()
