#!/usr/bin/env python3
import numpy as np

from openpilot.common.conversions import Conversions as CV
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.drive_helpers import V_CRUISE_MAX
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import COMFORT_BRAKE
from collections import deque
from openpilot.selfdrive.frogpilot.controls.lib.map_turn_speed_controller import MapTurnSpeedController
from openpilot.selfdrive.frogpilot.controls.lib.speed_limit_controller import SpeedLimitController
from openpilot.selfdrive.frogpilot.frogpilot_variables import CRUISING_SPEED, PLANNER_TIME, State, params_memory

TARGET_LAT_A = 2.0

class FrogPilotVCruise:
  def __init__(self, FrogPilotPlanner):
    self.frogpilot_planner = FrogPilotPlanner

    self.mtsc = MapTurnSpeedController()
    self.slc = SpeedLimitController()

    self.forcing_stop = False
    self.override_force_stop = False
    self.override_slc = False

    self.mtsc_target = 0
    self.overridden_speed = 0
    self.override_force_stop_timer = 0
    self.slc_offset = 0
    self.slc_target = 0
    self.speed_limit_timer = 0
    self.dRelk = 0
    self.vRelk = 0
    self.dRelk_hist = deque(maxlen=10)
    self.drelk_stable = False

  def update(self, carState, controlsState, frogpilotCarState, frogpilotNavigation, gps_position, v_cruise, v_ego, frogpilot_toggles):
    force_stop = self.frogpilot_planner.cem.stop_light_detected and controlsState.enabled and frogpilot_toggles.force_stops
    force_stop &= self.frogpilot_planner.model_stopped
    force_stop &= self.override_force_stop_timer <= 0

    self.force_stop_timer = self.force_stop_timer + DT_MDL if force_stop else 0

    force_stop_enabled = self.force_stop_timer >= 1

    self.override_force_stop |= carState.gasPressed
    self.override_force_stop |= frogpilotCarState.accelPressed
    self.override_force_stop &= force_stop_enabled

    if self.override_force_stop:
      self.override_force_stop_timer = 10
    elif self.override_force_stop_timer > 0:
      self.override_force_stop_timer -= DT_MDL

    v_cruise_cluster = max(controlsState.vCruiseCluster * CV.KPH_TO_MS, v_cruise)
    v_cruise_diff = v_cruise_cluster - v_cruise

    v_ego_cluster = max(carState.vEgoCluster, v_ego)
    v_ego_diff = v_ego_cluster - v_ego

    # Mike's extended lead linear braking
    if self.frogpilot_planner.lead_one.vLead < v_ego > CRUISING_SPEED and controlsState.enabled and self.frogpilot_planner.tracking_lead and frogpilot_toggles.human_following:
      self.linear_braking_active |= self.frogpilot_planner.v_cruise - v_ego < 1

      if not self.frogpilot_planner.frogpilot_following.following_lead and self.linear_braking_active:
        decel_rate = (v_ego - self.frogpilot_planner.lead_one.vLead - COMFORT_BRAKE) / self.frogpilot_planner.lead_one.dRel
        self.braking_target = v_ego - (decel_rate * DT_MDL)
      else:
        self.braking_target = v_cruise
    else:
      self.linear_braking_active = False

      self.braking_target = v_cruise
    lead = self.frogpilot_planner.lead_one
    # Pfeiferj's Map Turn Speed Controller
    if frogpilot_toggles.map_turn_speed_controller:
      # Extended lead linear braking
      d_rel = lead.dRel
      v_lead = lead.vLead
      v_rel = v_ego - v_lead
      if (v_lead + 2) < v_ego > CRUISING_SPEED and self.frogpilot_planner.tracking_lead: # 2 m/s under current v_ego activates
        decelRate = (v_rel ** 2) / (2 * max(d_rel, 1e-6)) * 4 # 4x multipler to strengthen. Tune this as needed
        self.mtsc_target = v_ego - decelRate

      if self.frogpilot_planner.tracking_lead: # clear trim variables when no lead
        self.dRelk = 0.8 * float(lead.dRel) + 0.2 * self.dRelk # noisy dRel
        self.vRelk = 0.8 * float(v_rel) + 0.2 * self.vRelk # noisy vRel
        self.dRelk_hist.append(self.dRelk) # store dRelk history for slope calculation
        if len(self.dRelk_hist) >= 5:  # Minimum length to avoid noise from too few points
          y = np.array(self.dRelk_hist)
          x = np.arange(len(y))
          drel_slope = np.polyfit(x, y, 1)[0]  # 1st-degree polyfit returns [slope, intercept]
          self.drelk_stable = drel_slope > -0.1 # consider stable when drelk not decreasing too fast or pulling away
      else:
        self.drelk_stable = False
        self.dRelk_hist.clear() # clear history when no lead
      # trim v_ego to when closer than expected following distance
      expected_dist = (self.frogpilot_planner.frogtfollow - 0.25) * v_ego # 0.25s overlap with following distance for better transition
      distance_error = expected_dist - self.dRelk

      if self.dRelk < expected_dist and v_ego > 2.0 and self.frogpilot_planner.tracking_lead and not self.drelk_stable:
        k_p = 0.1
        k_v = 0.5
        max_trim = 3.0 # 3 m/s max trim ~ 6.7 mph
        trim = k_p * distance_error + k_v * max(0, self.vRelk) # trim based on error and vRelk
        trim = min(trim, max_trim)
        trimmed_vego = v_ego - max(0.0, trim) # current speed - trim
        if self.mtsc_target > trimmed_vego: # extended lead braking could be stronger than trim
          self.mtsc_target = trimmed_vego
      else:
        self.mtsc_target = v_cruise

    # Pfeiferj's Speed Limit Controller
    if frogpilot_toggles.show_speed_limits or frogpilot_toggles.speed_limit_controller:
      self.slc.update(frogpilotCarState.dashboardSpeedLimit, controlsState.enabled, frogpilotNavigation.navigationSpeedLimit, v_cruise_cluster, v_ego, frogpilot_toggles)
      desired_slc_target = self.slc.desired_speed_limit

      if self.slc.speed_limit_changed:
        speed_limit_accepted = frogpilotCarState.accelPressed and controlsState.state == State.enabled or params_memory.get_bool("SpeedLimitAccepted")
        speed_limit_denied = frogpilotCarState.decelPressed and controlsState.state == State.enabled or self.speed_limit_timer >= 30

        if speed_limit_accepted:
          self.slc_target = desired_slc_target
          params_memory.remove("SpeedLimitAccepted")
        elif desired_slc_target < self.slc_target and not frogpilot_toggles.speed_limit_confirmation_lower:
          self.slc_target = desired_slc_target
        elif desired_slc_target > self.slc_target and not frogpilot_toggles.speed_limit_confirmation_higher:
          self.slc_target = desired_slc_target
        else:
          self.speed_limit_timer += DT_MDL

        self.slc.speed_limit_changed = self.slc_target != desired_slc_target and not speed_limit_denied
      elif self.slc_target == 0:
        self.slc_target = desired_slc_target
      else:
        self.speed_limit_timer = 0

      if frogpilot_toggles.speed_limit_controller:
        self.override_slc = self.overridden_speed > self.slc_target + self.slc_offset
        self.override_slc |= carState.gasPressed and v_ego > self.slc_target + self.slc_offset
        self.override_slc &= controlsState.enabled

        if self.override_slc:
          if frogpilot_toggles.speed_limit_controller_override_manual:
            if carState.gasPressed:
              self.overridden_speed = v_ego_cluster
            self.overridden_speed = np.clip(self.overridden_speed, self.slc_target + self.slc_offset, v_cruise_cluster)
          elif frogpilot_toggles.speed_limit_controller_override_set_speed:
            self.overridden_speed = v_cruise_cluster
        else:
          self.overridden_speed = 0
      else:
        self.override_slc = False
        self.overridden_speed = 0

      self.slc_offset = self.slc.get_offset(self.slc_target, frogpilot_toggles)
    else:
      self.slc_offset = 0
      self.slc_target = 0

    # Pfeiferj's Vision Turn Controller
    if v_ego > CRUISING_SPEED and controlsState.enabled and self.frogpilot_planner.road_curvature_detected and frogpilot_toggles.vision_turn_speed_controller and v_ego < 25:
      self.vtsc_target = ((TARGET_LAT_A * frogpilot_toggles.turn_aggressiveness) / (abs(self.frogpilot_planner.road_curvature) * frogpilot_toggles.curve_sensitivity))**0.5
      self.vtsc_target = float(np.clip(self.vtsc_target, CRUISING_SPEED, v_cruise))
    else:
      self.vtsc_target = v_cruise

    # Float 5 mph over vcruise
    if self.vtsc_target >= v_cruise and self.mtsc_target >= v_cruise and v_ego > (v_cruise + 0.5):
      v_cruise = min(v_ego - 0.5, v_cruise + 2.2352)

    # Float 5 mph under vcruise
    if self.vtsc_target >= v_cruise and self.mtsc_target >= v_cruise and v_ego < (v_cruise - 0.5):
      v_cruise = max(v_ego + 0.5, v_cruise - 2.2352)

    if carState.standstill and not self.override_force_stop and controlsState.enabled and frogpilot_toggles. and not (self.frogpilot_planner.tracking_lead and lead.drel < 15):
      self.forcing_stop = True
      v_cruise = -1

    elif force_stop_enabled and not self.override_force_stop:
      self.forcing_stop |= not carState.standstill
      self.tracked_model_length = max(self.tracked_model_length - (v_ego * DT_MDL), 0)
      v_cruise = min((self.tracked_model_length // PLANNER_TIME), v_cruise)

    else:
      self.forcing_stop = False
      self.tracked_model_length = self.frogpilot_planner.model_length

      targets = [self.braking_target, self.mtsc_target, self.vtsc_target]
      if frogpilot_toggles.speed_limit_controller:
        targets.append(max(self.overridden_speed, self.slc_target + self.slc_offset))

      v_cruise = min([target if target > CRUISING_SPEED else v_cruise for target in targets])

    self.mtsc_target += v_cruise_diff
    self.vtsc_target += v_cruise_diff

    return v_cruise
