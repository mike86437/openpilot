import numpy as np
from openpilot.common.constants import ACCELERATION_DUE_TO_GRAVITY
from openpilot.common.realtime import DT_CTRL, DT_MDL

MIN_SPEED = 1.0
CONTROL_N = 17
CAR_ROTATION_RADIUS = 0.0
# This is a turn radius smaller than most cars can achieve
MAX_CURVATURE = 0.2
MAX_VEL_ERR = 5.0  # m/s

# The two limits clip_curvature enforces, matched to dev-111826 (`selfdrive/controls/lib/drive_helpers.py:13-14`,
# which carries 10.0 / 10.0 under the same "EU guidelines" comment). Upstream is 5.0 / 3.0. This is not a
# cosmetic change: at 3.0 the acceleration clamp is what binds first on this car at any road speed - 3.0 m/s^2 is
# 0.0155 1/m at 50 km/h and 0.0061 1/m at 80 - while `LatControl._check_saturation` counts `curvature_limited`
# alongside the actuator ceiling (`selfdrive/controls/lib/latcontrol.py:29`), so `EventName.steerSaturated` can
# say "turn exceeds limit" with torque still available in the EPS. At 10.0 those clamps stop being the limit on
# anything a road offers: 10.0 m/s^2 is 0.0518 1/m at 50 km/h (49 deg of wheel angle at this car's 16.5 ratio),
# and only MAX_CURVATURE below can answer no. Same reason dev-111826 raises the jerk figure: 5.0 m/s^3 is 33 deg/s
# of wheel-angle ramp at 12 m/s, which is tighter than the lateral controllers' own angle-rate limits.
MAX_LATERAL_JERK = 10.0  # m/s^3   # read by clip_curvature and nothing else in this tree
MAX_LATERAL_ACCEL_NO_ROLL_DEMAND = 10.0  # m/s^2   # likewise

# Kept at upstream 3.0 on purpose. Despite the name this is not the demand clamp: four FrogPilot call sites are
# capped by it - frogpilot/common/frogpilot_variables.py:1442 (the cap on toggle.maxLateralAccel),
# frogpilot/controls/lib/curve_speed_controller.py:51, frogpilot/controls/lib/curve_speed_profile_learner.py:53
# (the clamp on the lateral acceleration a learned curve profile may record) and
# frogpilot/controls/lib/max_lateral_acceleration_learner.py:21 through the toggle. Those decide how hard the car
# is allowed to slow for a curve, which is a longitudinal feature this change does not touch; matching the source's
# number there would have quietly made curve speed profiles from drives up to 10 m/s^2.
MAX_LATERAL_ACCEL_NO_ROLL = 3.0  # m/s^2


def clamp(val, min_val, max_val):
  clamped_val = float(np.clip(val, min_val, max_val))
  return clamped_val, clamped_val != val

def smooth_value(val, prev_val, tau, dt=DT_MDL):
  alpha = 1 - np.exp(-dt/tau) if tau > 0 else 1
  return alpha * val + (1 - alpha) * prev_val

def clip_curvature(v_ego, prev_curvature, new_curvature, roll) -> tuple[float, bool]:
  # This function respects ISO lateral jerk and acceleration limits + a max curvature
  v_ego = max(v_ego, MIN_SPEED)
  max_curvature_rate = MAX_LATERAL_JERK / (v_ego ** 2)  # inexact calculation, check https://github.com/commaai/openpilot/pull/24755
  new_curvature = np.clip(new_curvature,
                          prev_curvature - max_curvature_rate * DT_CTRL,
                          prev_curvature + max_curvature_rate * DT_CTRL)

  roll_compensation = roll * ACCELERATION_DUE_TO_GRAVITY
  max_lat_accel = MAX_LATERAL_ACCEL_NO_ROLL_DEMAND + roll_compensation
  min_lat_accel = -MAX_LATERAL_ACCEL_NO_ROLL_DEMAND + roll_compensation
  new_curvature, limited_accel = clamp(new_curvature, min_lat_accel / v_ego ** 2, max_lat_accel / v_ego ** 2)

  new_curvature, limited_max_curv = clamp(new_curvature, -MAX_CURVATURE, MAX_CURVATURE)
  return float(new_curvature), limited_accel or limited_max_curv


def get_accel_from_plan(speeds, accels, t_idxs, action_t=DT_MDL, vEgoStopping=0.05):
  if len(speeds) == len(t_idxs):
    v_now = speeds[0]
    a_now = accels[0]
    v_target = np.interp(action_t, t_idxs, speeds)
    a_target = 2 * (v_target - v_now) / (action_t) - a_now
    v_target_1sec = np.interp(action_t + 1.0, t_idxs, speeds)
  else:
    v_target = 0.0
    v_target_1sec = 0.0
    a_target = 0.0
  should_stop = (v_target < vEgoStopping and
                 v_target_1sec < vEgoStopping)
  return a_target, should_stop

def curv_from_psis(psi_target, psi_rate, vego, action_t):
  vego = np.clip(vego, MIN_SPEED, np.inf)
  curv_from_psi = psi_target / (vego * action_t)
  return 2*curv_from_psi - psi_rate / vego

def get_curvature_from_plan(yaws, yaw_rates, t_idxs, vego, action_t):
  psi_target = np.interp(action_t, t_idxs, yaws)
  psi_rate = yaw_rates[0]
  return curv_from_psis(psi_target, psi_rate, vego, action_t)
