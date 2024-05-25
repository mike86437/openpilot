import numpy as np

import cereal.messaging as messaging

from cereal import car, log

from openpilot.common.conversions import Conversions as CV
from openpilot.common.numpy_fast import interp
from openpilot.common.params import Params

from openpilot.selfdrive.car.interfaces import ACCEL_MIN, ACCEL_MAX
from openpilot.selfdrive.controls.lib.desire_helper import LANE_CHANGE_SPEED_MIN
from openpilot.selfdrive.controls.lib.drive_helpers import V_CRUISE_UNSET
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import A_CHANGE_COST, J_EGO_COST, COMFORT_BRAKE, STOP_DISTANCE, get_jerk_factor, \
                                                                           get_safe_obstacle_distance, get_stopped_equivalence_factor, get_T_FOLLOW
from openpilot.selfdrive.controls.lib.longitudinal_planner import A_CRUISE_MIN, Lead, get_max_accel

from openpilot.system.version import get_short_branch

from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_functions import calculate_lane_width, calculate_road_curvature
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_variables import CITY_SPEED_LIMIT, CRUISING_SPEED

GearShifter = car.CarState.GearShifter

class FrogPilotPlanner:
  def __init__(self):
    self.params_memory = Params("/dev/shm/params")

    self.acceleration_jerk = 0
    self.base_acceleration_jerk = 0
    self.base_speed_jerk = 0
    self.road_curvature = 0
    self.speed_jerk = 0
    self.t_follow = 0

  def update(self, carState, controlsState, frogpilotCarControl, frogpilotCarState, frogpilotNavigation, liveLocationKalman, modelData, radarState):
    self.lead_one = radarState.leadOne

    v_cruise_kph = min(controlsState.vCruise, V_CRUISE_UNSET)
    v_cruise = v_cruise_kph * CV.KPH_TO_MS

    v_ego = max(carState.vEgo, 0)
    v_lead = self.lead_one.vLead

    self.base_acceleration_jerk, self.base_speed_jerk = get_jerk_factor(controlsState.personality)
    self.t_follow = get_T_FOLLOW(controlsState.personality)

    if self.lead_one.status:
      self.update_follow_values(v_ego, v_lead)
    else:
      self.acceleration_jerk = self.base_acceleration_jerk
      self.speed_jerk = self.base_speed_jerk

    self.road_curvature = calculate_road_curvature(modelData, v_ego)
    self.v_cruise = self.update_v_cruise(carState, controlsState, controlsState.enabled, frogpilotCarState, frogpilotNavigation, liveLocationKalman, modelData, v_cruise, v_ego)

  def update_follow_values(self, v_ego, v_lead):
    lead_distance = self.lead_one.dRel

  def update_v_cruise(self, carState, controlsState, enabled, frogpilotCarState, frogpilotNavigation, liveLocationKalman, modelData, v_cruise, v_ego):
    v_cruise_cluster = max(controlsState.vCruiseCluster, controlsState.vCruise) * CV.KPH_TO_MS
    v_cruise_diff = v_cruise_cluster - v_cruise

    v_ego_cluster = max(carState.vEgoCluster, v_ego)
    v_ego_diff = v_ego_cluster - v_ego

    targets = []
    filtered_targets = [target if target > CRUISING_SPEED else v_cruise for target in targets]

    return min(filtered_targets)

  def publish(self, sm, pm):
    frogpilot_plan_send = messaging.new_message('frogpilotPlan')
    frogpilot_plan_send.valid = sm.all_checks(service_list=['carState', 'controlsState'])
    frogpilotPlan = frogpilot_plan_send.frogpilotPlan

    frogpilotPlan.accelerationJerk = A_CHANGE_COST * float(self.acceleration_jerk)
    frogpilotPlan.accelerationJerkStock = A_CHANGE_COST * float(self.base_acceleration_jerk)
    frogpilotPlan.speedJerk = J_EGO_COST * float(self.speed_jerk)
    frogpilotPlan.speedJerkStock = J_EGO_COST * float(self.base_speed_jerk)
    frogpilotPlan.tFollow = float(self.t_follow)
    frogpilotPlan.vCruise = float(self.v_cruise)

    pm.send('frogpilotPlan', frogpilot_plan_send)
