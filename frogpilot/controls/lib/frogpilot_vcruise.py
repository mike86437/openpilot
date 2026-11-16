#!/usr/bin/env python3
import numpy as np

from openpilot.common.constants import CV
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import CRUISE_MIN_ACCEL

from openpilot.frogpilot.common import frogpilot_utilities, frogpilot_variables
from openpilot.frogpilot.controls.lib.curve_speed_controller import CurveSpeedController
from openpilot.frogpilot.controls.lib.speed_limit_controller import SpeedLimitController

# Speed float (SpeedFloatAboveSetSpeed). How far below our own speed the aim sits comes from the Pond's
# ForceCoastTargetOffset - the same key force coast already uses for the identical question - floored at these two
# values so the aim is never exactly at v_ego, and capped so the float can never own more than 10 mph above what the
# driver dialled.
SPEED_FLOAT_MIN_DEPTH_MS = 0.5        # aiming at v_ego itself lets the MPC spend gas holding that speed: always sit below
SPEED_FLOAT_MIN_DEPTH_SLOWING_MS = 0.1  # ...and shallower once a deceleration is already commanded, so it converges
SPEED_FLOAT_CAP_MS = 4.4704           # 10 mph above the dialled speed, the most the float is allowed to aim above it

class FrogPilotVCruise:
  def __init__(self, FrogPilotPlanner):
    self.frogpilot_planner = FrogPilotPlanner

    self.csc = CurveSpeedController(self)
    self.slc = SpeedLimitController(self)

    self.csc_active = False
    self.csc_controlling_speed = False
    self.forcing_stop = False
    self.override_force_stop = False
    self.taco_controlling_speed = False

    self.force_stop_timer = 0
    self.stop_distance = 0
    self.force_coast_target = 0.0

  def update(self, long_control_active, now, time_validated, v_cruise, v_ego, sm, frogpilot_toggles):
    self.update_force_stop(long_control_active, v_ego, sm, frogpilot_toggles)

    v_cruise_cluster = max(sm["carState"].vCruiseCluster * CV.KPH_TO_MS, v_cruise)

    v_ego_cluster = max(sm["carState"].vEgoCluster, v_ego)
    v_ego_diff = v_ego_cluster - v_ego

    # FrogsGoMoo's Curve Speed Controller
    self.csc.profile_learner.update(long_control_active, sm)

    if long_control_active and frogpilot_toggles.curve_speed_controller:
      self.csc_target = self.csc.update_target(v_cruise, v_ego)
    else:
      self.csc.target = None

      self.csc_target = v_cruise

    self.csc_active = self.csc_target < v_cruise

    # Pfeiferj's Speed Limit Controller
    if frogpilot_toggles.speed_limit_controller:
      self.slc.update_limits(self.frogpilot_planner.gps_position, now, time_validated, v_ego, sm)
      self.slc.update_override(v_cruise_cluster, v_ego_cluster, sm)

      self.slc_offset = self.slc.offset
      self.slc_target = self.slc.target
    elif frogpilot_toggles.show_speed_limits:
      self.slc.update_limits(self.frogpilot_planner.gps_position, now, time_validated, v_ego, sm)

      self.slc_offset = 0
      self.slc_target = self.slc.target
    else:
      self.slc.reset()

      self.slc_offset = 0
      self.slc_target = 0

    # Force coast: aim below our own speed so the coast reaches a stop instead of levelling off below the speed
    # where the throttle clamp goes inert. The offset is a negative m/s value from the Pond; the target is floored
    # at zero, it is never a negative set speed. Re-defaulted every frame so it is inert unless the key is armed.
    self.force_coast_target = v_cruise
    if long_control_active and sm["frogpilotCarState"].forceCoast and frogpilot_toggles.force_coast_target_offset < 0:
      self.force_coast_target = max(v_ego + frogpilot_toggles.force_coast_target_offset, 0.0)

    targets = [self.force_coast_target, self.csc_target, v_cruise]
    if frogpilot_toggles.speed_limit_controller and self.slc_target > 0:
      targets.append(max(max(self.slc.overridden_speed, self.slc_target + self.slc_offset) - v_ego_diff, frogpilot_variables.CRUISING_SPEED))

    taco_target = v_cruise
    if long_control_active and frogpilot_toggles.taco_tune and not frogpilot_toggles.curve_speed_controller:
      turn_speeds = np.maximum(frogpilot_utilities.calculate_taco_turn_speeds(sm["modelV2"].orientationRate.z, sm["modelV2"].velocity.x, v_ego), 0.0)
      turn_distances = np.maximum(np.asarray(sm["modelV2"].position.x) - v_ego * frogpilot_variables.TACO_LAG_TIME, 0.0)
      taco_target = np.sqrt(turn_speeds ** 2 - 2 * CRUISE_MIN_ACCEL * turn_distances).min()
      targets.append(taco_target)

    taco_active = taco_target < v_cruise

    dialled = v_cruise
    min_target = min(targets)
    if (long_control_active and frogpilot_toggles.speed_float_above_set_speed and v_ego > dialled and
        all(target >= dialled for target in targets)):
      # Speed float: with nothing but the set speed holding the car and the car above it, aim below our own speed
      # instead of aiming at the dialled speed - so coming back is a coast, not a brake. The guard compared against the
      # dialled speed is what makes this inert whenever curve speed control, Taco, a map limit or force coast is the
      # thing lowering the target (targets contains the dialled speed, so all(t >= dialled) is min(targets) == dialled).
      # How far below v_ego to aim is the driver's own number: frogpilot_toggles.force_coast_target_offset, the
      # ForceCoastTargetOffset Pond value force coast uses one block above for the same question (negative m/s, "Off"
      # at 0). One key, one meaning: how far below my current speed openpilot should aim. At 0 the float uses its own
      # tuned minimum instead, because an aim sitting exactly at v_ego is what makes the MPC pay gas to hold a speed
      # above the dialled one - the behaviour this feature exists to remove.
      # The buffer is still clamped by v_ego - dialled (the upstream "fix float", b562d9b9): with buffer <= that, v_ego -
      # buffer is never below the dialled speed, so the float can only ever raise the aim, and it degrades to a normal
      # return to the dialled speed for the last stretch of any overshoot deeper than the offset.
      offset = frogpilot_toggles.force_coast_target_offset
      actuator_accel = sm["carControl"].actuators.accel
      depth = -offset if offset < 0 else (SPEED_FLOAT_MIN_DEPTH_SLOWING_MS if actuator_accel < 0 else
                                          SPEED_FLOAT_MIN_DEPTH_MS)
      buffer = min(depth, v_ego - dialled)
      v_cruise = min(v_ego - buffer, dialled + SPEED_FLOAT_CAP_MS)
    else:
      v_cruise = min_target

    # Whether a curve/limit feature owns the speed is decided by min(targets), not by the floated aim: that comparison
    # is what selects the braking floor in frogpilot_acceleration.py:77-79, and the float must not change it.
    self.csc_controlling_speed = self.csc_active and self.csc_target == min_target
    self.taco_controlling_speed = taco_active and taco_target == min_target

    return v_cruise

  def update_force_stop(self, long_control_active, v_ego, sm, frogpilot_toggles):
    if not sm["selfdriveState"].enabled or sm["frogpilotCarState"].pauseLongitudinal or sm["frogpilotCarState"].trafficModeEnabled or not frogpilot_toggles.force_stops:
      self.forcing_stop = False
      self.override_force_stop = False

      self.force_stop_timer = 0
      self.stop_distance = 0
      return

    stop_detected = self.frogpilot_planner.frogpilot_cem.stop_light_filter.x >= frogpilot_variables.THRESHOLD and self.frogpilot_planner.model_stopped
    stop_detected &= not self.frogpilot_planner.lead_relevant

    override_pressed = sm["carState"].gasPressed or self.frogpilot_planner.accel_pressed
    if override_pressed or not long_control_active:
      self.override_force_stop |= override_pressed and (self.forcing_stop or stop_detected)

      self.forcing_stop = False

      self.force_stop_timer = 0
      self.stop_distance = 0
      return

    if self.override_force_stop:
      if not sm["carState"].standstill and not self.frogpilot_planner.frogpilot_cem.stop_light_signal:
        self.override_force_stop = self.frogpilot_planner.frogpilot_cem.stop_light_filter.x >= frogpilot_variables.THRESHOLD
      return

    if self.forcing_stop or stop_detected:
      model_stop_distance = next((distance for distance, velocity in zip(sm["modelV2"].position.x, sm["modelV2"].velocity.x) if velocity < 0.05), None)

    if self.forcing_stop:
      self.stop_distance = max(self.stop_distance - v_ego * DT_MDL, 0)

      if model_stop_distance is not None:
        self.stop_distance = model_stop_distance
      return

    if stop_detected and not sm["carState"].standstill:
      self.force_stop_timer += DT_MDL

      if self.force_stop_timer >= 0.5:
        self.forcing_stop = True

        self.force_stop_timer = 0
        self.stop_distance = model_stop_distance
        if model_stop_distance is None:
          self.stop_distance = min(zip(sm["modelV2"].velocity.x, sm["modelV2"].position.x, strict=True))[1]
    else:
      self.force_stop_timer = 0
