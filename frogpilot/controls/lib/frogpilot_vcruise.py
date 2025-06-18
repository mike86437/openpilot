#!/usr/bin/env python3
import collections
import numpy as np
from openpilot.common.realtime import DT_MDL
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import COMFORT_BRAKE

from openpilot.frogpilot.common.frogpilot_variables import CRUISING_SPEED, PLANNER_TIME
from openpilot.frogpilot.controls.lib.map_turn_speed_controller import MapTurnSpeedController
from openpilot.frogpilot.controls.lib.speed_limit_controller import SpeedLimitController

TARGET_LAT_A = 2.0

class FrogPilotVCruise:
  def __init__(self, FrogPilotPlanner):
    self.frogpilot_planner = FrogPilotPlanner

    self.mtsc = MapTurnSpeedController()
    self.slc = SpeedLimitController()

    self.forcing_stop = False
    self.override_force_stop = False

    self.mtsc_target = 0
    self.override_force_stop_timer = 0

    self.dRel_hist = collections.deque(maxlen=10)

  def update(self, gps_position, v_cruise, v_ego, sm, frogpilot_toggles):
    force_stop = self.frogpilot_planner.cem.stop_light_detected and sm["controlsState"].enabled and frogpilot_toggles.force_stops
    force_stop &= self.frogpilot_planner.model_stopped
    force_stop &= self.override_force_stop_timer <= 0

    self.force_stop_timer = self.force_stop_timer + DT_MDL if force_stop else 0

    force_stop_enabled = self.force_stop_timer >= 1

    self.override_force_stop |= sm["carState"].gasPressed
    self.override_force_stop |= sm["frogpilotCarState"].accelPressed
    self.override_force_stop &= force_stop_enabled

    if self.override_force_stop:
      self.override_force_stop_timer = 10
    elif self.override_force_stop_timer > 0:
      self.override_force_stop_timer -= DT_MDL

    # Mike's extended lead linear braking
    if self.frogpilot_planner.lead_one.vLead < v_ego > CRUISING_SPEED and sm["controlsState"].enabled and self.frogpilot_planner.tracking_lead and frogpilot_toggles.human_following:
      self.linear_braking_active |= self.frogpilot_planner.v_cruise - v_ego < 1

      if not self.frogpilot_planner.frogpilot_following.following_lead and self.linear_braking_active:
        decel_rate = (v_ego - self.frogpilot_planner.lead_one.vLead)**2 / self.frogpilot_planner.lead_one.dRel
        self.braking_target = max(v_ego - (decel_rate * DT_MDL), self.frogpilot_planner.lead_one.vLead + CRUISING_SPEED)
      else:
        self.braking_target = v_cruise
    else:
      self.linear_braking_active = False

      self.braking_target = v_cruise

    # Extended lead linear braking
    self.mtsc_target = v_cruise + 1
    mtsc_active = False
    if v_ego > CRUISING_SPEED and sm["controlsState"].enabled and frogpilot_toggles.map_turn_speed_controller and self.frogpilot_planner.tracking_lead:
      lead = self.frogpilot_planner.lead_one
      v_rel = lead.vRel
      v_lead = lead.vLead
      tFollow = self.frogpilot_planner.frogpilot_following.t_follow
      self.dRel_hist.append(lead.dRel)
      if len(self.dRel_hist) == self.dRel_hist.maxlen and lead.dRel < 100 and False:
        y = np.array(self.dRel_hist)
        x = np.arange(len(y)) * DT_MDL
        try:
          drel_slope = np.polyfit(x, y, 1)[0]
          vRel_calc = -drel_slope
          vLead_calc = max(v_ego - vRel_calc, 0)
          if vLead_calc < v_lead:
            v_rel = vRel_calc
            v_lead = vLead_calc
        except Exception as e:
          print(f"Error during polyfit calculation: {e}")
      dFollow = max(lead.dRel - v_lead * (tFollow + 0.5), 1e-6)
      if (v_lead + dFollow / v_ego) < v_ego:
        mtsc_active = True
        decelRate = (v_rel ** 2) / (2 * dFollow)
        mtsc_speed = v_ego - (decelRate - lead.aLeadK)
        self.mtsc_target = float(max(CRUISING_SPEED, mtsc_speed, v_lead))
    else:
      self.dRel_hist.clear()

    # Pfeiferj's Speed Limit Controller
    self.slc.frogpilot_toggles = frogpilot_toggles

    if frogpilot_toggles.speed_limit_controller:
      self.slc.update_limits(sm["frogpilotCarState"].dashboardSpeedLimit, gps_position, sm["frogpilotNavigation"].navigationSpeedLimit, v_cruise, v_ego, sm)
      self.slc.update_override(v_cruise, v_ego, sm)

      self.slc_offset = self.slc.offset
      self.slc_target = self.slc.target
    elif frogpilot_toggles.show_speed_limits:
      self.slc.update_limits(sm["frogpilotCarState"].dashboardSpeedLimit, gps_position, sm["frogpilotNavigation"].navigationSpeedLimit, v_cruise, v_ego, sm)

      self.slc_offset = 0
      self.slc_target = self.slc.target
    else:
      self.slc_offset = 0
      self.slc_target = 0

    # Pfeiferj's Vision Turn Controller
    if v_ego > CRUISING_SPEED and sm["controlsState"].enabled and self.frogpilot_planner.road_curvature_detected and frogpilot_toggles.vision_turn_speed_controller:
      vtsc_speed = ((TARGET_LAT_A * frogpilot_toggles.turn_aggressiveness) / (abs(self.frogpilot_planner.road_curvature) * frogpilot_toggles.curve_sensitivity))**0.5
      self.vtsc_target = max(CRUISING_SPEED, vtsc_speed)
    else:
      self.vtsc_target = v_cruise + 1

    # Float 10 mph over vcruise
    actuators = sm["carControl"].actuators
    if self.vtsc_target >= v_cruise and self.mtsc_target >= v_cruise and v_ego > (v_cruise + 0.25):
      buffer = 0.0 if actuators.accel < 0.1 else 0.25
      v_cruise = min(v_ego - buffer, v_cruise + 4.4704)

    # Float 5 mph under vcruise
    # if self.vtsc_target >= v_cruise and self.mtsc_target >= v_cruise and v_ego < (v_cruise - 0.5):
    #   v_cruise = max(v_ego + 0.5, v_cruise - 2.2352)

    if sm["carState"].standstill and not self.override_force_stop and sm["controlsState"].enabled and frogpilot_toggles.force_standstill and not (self.frogpilot_planner.tracking_lead and 1 < getattr(self.frogpilot_planner.lead_one, "dRel", float("inf")) < 15):
      self.forcing_stop = True

      v_cruise = -1

    elif force_stop_enabled and not self.override_force_stop:
      self.forcing_stop |= not sm["carState"].standstill

      self.tracked_model_length = max(self.tracked_model_length - (v_ego * DT_MDL), 0)
      v_cruise = min((self.tracked_model_length // PLANNER_TIME), v_cruise)

    else:
      self.forcing_stop = False

      self.tracked_model_length = self.frogpilot_planner.model_length

      targets = [self.braking_target, self.mtsc_target, self.vtsc_target, v_cruise]
      if frogpilot_toggles.speed_limit_controller:
        targets.append(max(self.slc.overridden_speed, self.slc_target + self.slc_offset))

      v_cruise = min([target if target > CRUISING_SPEED else v_cruise for target in targets])

    return v_cruise
