import numpy as np

import cereal.messaging as messaging

from cereal import car

from openpilot.common.conversions import Conversions as CV
from openpilot.common.numpy_fast import interp
from openpilot.common.params import Params

from openpilot.selfdrive.car.interfaces import ACCEL_MIN, ACCEL_MAX
from openpilot.selfdrive.controls.lib.drive_helpers import V_CRUISE_UNSET
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import A_CHANGE_COST, COMFORT_BRAKE, J_EGO_COST, STOP_DISTANCE, get_jerk_factor, \
                                                                           get_safe_obstacle_distance, get_stopped_equivalence_factor, get_T_FOLLOW
from openpilot.selfdrive.controls.lib.longitudinal_planner import A_CRUISE_MIN, Lead, get_max_accel

from openpilot.selfdrive.frogpilot.controls.lib.conditional_experimental_mode import ConditionalExperimentalMode
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_functions import calculate_lane_width, calculate_road_curvature
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_variables import CITY_SPEED_LIMIT, CRUISING_SPEED
from openpilot.selfdrive.frogpilot.controls.lib.map_turn_speed_controller import MapTurnSpeedController
from openpilot.selfdrive.frogpilot.controls.lib.speed_limit_controller import SpeedLimitController

GearShifter = car.CarState.GearShifter

A_CRUISE_MIN_ECO = A_CRUISE_MIN / 5
A_CRUISE_MIN_SPORT = A_CRUISE_MIN / 2
                  # MPH = [ 0.,  11,  22,  34,  45,  56,  89]
A_CRUISE_MAX_BP_CUSTOM =  [ 0.,  5., 10., 15., 20., 25., 40.]
A_CRUISE_MAX_VALS_ECO =   [1.4, 1.2, 1.0, 0.8, 0.6, 0.4, 0.2]
A_CRUISE_MAX_VALS_SPORT = [4.0, 3.0, 2.0, 1.0, 0.9, 0.8, 0.7]

TRAFFIC_MODE_BP = [0., CITY_SPEED_LIMIT]

def get_max_accel_eco(v_ego):
  return interp(v_ego, A_CRUISE_MAX_BP_CUSTOM, A_CRUISE_MAX_VALS_ECO)

def get_max_accel_sport(v_ego):
  return interp(v_ego, A_CRUISE_MAX_BP_CUSTOM, A_CRUISE_MAX_VALS_SPORT)

class FrogPilotPlanner:
  def __init__(self):
    self.params_memory = Params("/dev/shm/params")

    self.cem = ConditionalExperimentalMode()
    self.lead_one = Lead()
    self.mtsc = MapTurnSpeedController()

    self.slower_lead = False
    self.tracking_lead = False

    self.acceleration_jerk = 0
    self.mtsc_target = 0
    self.road_curvature = 0
    self.slc_target = 0
    self.speed_jerk = 0

  def update(self, carState, controlsState, frogpilotCarControl, frogpilotCarState, frogpilotNavigation, modelData, radarState, frogpilot_toggles):
    if frogpilot_toggles.radarless_model:
      model_leads = list(modelData.leadsV3)
      if len(model_leads) > 0:
        model_lead = model_leads[0]
        self.lead_one.update(model_lead.x[0], model_lead.y[0], model_lead.v[0], model_lead.a[0], model_lead.prob)
      else:
        self.lead_one.reset()
    else:
      self.lead_one = radarState.leadOne

    driving_gear = carState.gearShifter not in (GearShifter.neutral, GearShifter.park, GearShifter.reverse, GearShifter.unknown)

    v_cruise_kph = min(controlsState.vCruise, V_CRUISE_UNSET)
    v_cruise = v_cruise_kph * CV.KPH_TO_MS
    v_cruise_changed = self.mtsc_target < v_cruise

    v_ego = max(carState.vEgo, 0)
    v_lead = self.lead_one.vLead

    distance_offset = max(frogpilot_toggles.increased_stopping_distance + min(CITY_SPEED_LIMIT - v_ego, 0), 0) if not frogpilotCarState.trafficModeActive else 0
    lead_distance = self.lead_one.dRel - distance_offset
    stopping_distance = STOP_DISTANCE + distance_offset

    eco_gear = carState.gearShifter == GearShifter.eco or frogpilotCarState.ecoGear
    sport_gear = carState.gearShifter == GearShifter.sport or frogpilotCarState.sportGear

    if self.lead_one.status and frogpilot_toggles.aggressive_acceleration:
      self.max_accel = float(np.clip(self.lead_one.aLeadK, get_max_accel_sport(v_ego), 2.0 if v_ego >= 20 else 4.0))
    elif frogpilot_toggles.map_acceleration and (eco_gear or sport_gear):
      if eco_gear:
        self.max_accel = get_max_accel_eco(v_ego)
      else:
        self.max_accel = get_max_accel_sport(v_ego)
    else:
      if frogpilot_toggles.acceleration_profile == 1:
        self.max_accel = get_max_accel_eco(v_ego)
      elif frogpilot_toggles.acceleration_profile in (2, 3):
        self.max_accel = get_max_accel_sport(v_ego)
      elif controlsState.experimentalMode:
        self.max_accel = ACCEL_MAX
      else:
        self.max_accel = get_max_accel(v_ego)

    if controlsState.experimentalMode:
      self.min_accel = ACCEL_MIN
    elif v_cruise_changed:
      self.min_accel = A_CRUISE_MIN
    elif frogpilot_toggles.map_deceleration and (eco_gear or sport_gear):
      if eco_gear:
        self.min_accel = A_CRUISE_MIN_ECO
      else:
        self.min_accel = A_CRUISE_MIN_SPORT
    else:
      if frogpilot_toggles.deceleration_profile == 1:
        self.min_accel = A_CRUISE_MIN_ECO
      elif frogpilot_toggles.deceleration_profile == 2:
        self.min_accel = A_CRUISE_MIN_SPORT
      else:
        self.min_accel = A_CRUISE_MIN

    if frogpilotCarState.trafficModeActive:
      self.base_acceleration_jerk = interp(v_ego, TRAFFIC_MODE_BP, frogpilot_toggles.traffic_mode_jerk_acceleration)
      self.base_speed_jerk = interp(v_ego, TRAFFIC_MODE_BP, frogpilot_toggles.traffic_mode_jerk_speed)
      self.t_follow = interp(v_ego, TRAFFIC_MODE_BP, frogpilot_toggles.traffic_mode_t_follow)
    else:
      self.base_acceleration_jerk, self.base_speed_jerk = get_jerk_factor(
        frogpilot_toggles.custom_personalities, frogpilot_toggles.aggressive_jerk_acceleration, frogpilot_toggles.aggressive_jerk_speed,
        frogpilot_toggles.standard_jerk_acceleration, frogpilot_toggles.standard_jerk_speed, frogpilot_toggles.relaxed_jerk_acceleration,
        frogpilot_toggles.relaxed_jerk_speed, controlsState.personality)
      self.t_follow = get_T_FOLLOW(
        frogpilot_toggles.custom_personalities, frogpilot_toggles.aggressive_follow, frogpilot_toggles.standard_follow,
        frogpilot_toggles.relaxed_follow, controlsState.personality)

    if self.tracking_lead and driving_gear:
      self.update_follow_values(lead_distance, stopping_distance, v_ego, v_lead, frogpilot_toggles)
    else:
      self.acceleration_jerk = self.base_acceleration_jerk
      self.speed_jerk = self.base_speed_jerk

    check_lane_width = frogpilot_toggles.lane_detection
    if check_lane_width and v_ego >= frogpilot_toggles.minimum_lane_change_speed:
      self.lane_width_left = float(calculate_lane_width(modelData.laneLines[0], modelData.laneLines[1], modelData.roadEdges[0]))
      self.lane_width_right = float(calculate_lane_width(modelData.laneLines[3], modelData.laneLines[2], modelData.roadEdges[1]))
    else:
      self.lane_width_left = 0
      self.lane_width_right = 0

    self.road_curvature = calculate_road_curvature(modelData, v_ego)
    self.v_cruise = self.update_v_cruise(carState, controlsState, frogpilotCarState, frogpilotNavigation, modelData, v_cruise, v_ego, frogpilot_toggles)

    if frogpilot_toggles.conditional_experimental_mode:
      self.cem.update(carState, controlsState.enabled, frogpilotNavigation, self.lead_one, modelData, self.road_curvature, self.slower_lead, v_ego, v_lead, frogpilot_toggles)

    if v_ego > CRUISING_SPEED:
      self.tracking_lead = self.lead_one.status

  def update_follow_values(self, lead_distance, stopping_distance, v_ego, v_lead, frogpilot_toggles):
    # Offset by FrogAi for FrogPilot for a more natural approach to a faster lead
    if frogpilot_toggles.aggressive_acceleration and v_lead > v_ego:
      distance_factor = max(lead_distance - (v_ego * self.t_follow), 1)
      standstill_offset = max(stopping_distance - v_ego, 0) * max(v_lead - v_ego, 0)
      acceleration_offset = np.clip((v_lead - v_ego) + standstill_offset - COMFORT_BRAKE, 1, distance_factor)
      self.acceleration_jerk = self.base_acceleration_jerk / acceleration_offset
      self.speed_jerk = self.base_speed_jerk / acceleration_offset
      self.t_follow /= acceleration_offset

    # Offset by FrogAi for FrogPilot for a more natural approach to a slower lead
    if (frogpilot_toggles.conditional_experimental_mode or frogpilot_toggles.smoother_braking) and v_lead < v_ego:
      distance_factor = max(lead_distance - (v_lead * self.t_follow), 1)
      far_lead_offset = max(lead_distance - (v_ego * self.t_follow) - stopping_distance + (v_lead - CITY_SPEED_LIMIT), 0)
      braking_offset = np.clip((v_ego - v_lead) + far_lead_offset - COMFORT_BRAKE, 1, distance_factor)
      if frogpilot_toggles.smoother_braking:
        self.acceleration_jerk = self.base_acceleration_jerk * min(braking_offset, COMFORT_BRAKE / 2)
        self.speed_jerk = self.base_speed_jerk * min(braking_offset, COMFORT_BRAKE * 2)
        self.t_follow /= braking_offset
      self.slower_lead = max(braking_offset - far_lead_offset, 1) > 1

  def update_v_cruise(self, carState, controlsState, frogpilotCarState, frogpilotNavigation, modelData, v_cruise, v_ego, frogpilot_toggles):
    v_cruise_cluster = max(controlsState.vCruiseCluster, v_cruise) * CV.KPH_TO_MS
    v_cruise_diff = v_cruise_cluster - v_cruise

    v_ego_cluster = max(carState.vEgoCluster, v_ego)
    v_ego_diff = v_ego_cluster - v_ego

    # Pfeiferj's Map Turn Speed Controller
    if frogpilot_toggles.map_turn_speed_controller and v_ego > CRUISING_SPEED and controlsState.enabled:
      mtsc_active = self.mtsc_target < v_cruise
      self.mtsc_target = np.clip(self.mtsc.target_speed(v_ego, carState.aEgo), CRUISING_SPEED, v_cruise)

      if frogpilot_toggles.mtsc_curvature_check and self.road_curvature < 1.0 and not mtsc_active:
        self.mtsc_target = v_cruise
      if self.mtsc_target == CRUISING_SPEED:
        self.mtsc_target = v_cruise
    else:
      self.mtsc_target = v_cruise if v_cruise != V_CRUISE_UNSET else 0

    # Pfeiferj's Speed Limit Controller
    if frogpilot_toggles.speed_limit_controller:
      SpeedLimitController.update(frogpilotNavigation.navigationSpeedLimit, v_ego, frogpilot_toggles)
      unconfirmed_slc_target = SpeedLimitController.desired_speed_limit

      if frogpilot_toggles.speed_limit_confirmation and self.slc_target != 0:
        if self.params_memory.get_bool("SLCConfirmed"):
          self.slc_target = unconfirmed_slc_target
          self.params_memory.put_bool("SLCConfirmed", False)
      else:
        self.slc_target = unconfirmed_slc_target
    else:
      self.slc_target = 0

    targets = [self.mtsc_target, self.slc_target - v_ego_diff]
    filtered_targets = [target if target > CRUISING_SPEED else v_cruise for target in targets]

    return min(filtered_targets)

  def publish(self, sm, pm, frogpilot_toggles):
    frogpilot_plan_send = messaging.new_message('frogpilotPlan')
    frogpilot_plan_send.valid = sm.all_checks(service_list=['carState', 'controlsState'])
    frogpilotPlan = frogpilot_plan_send.frogpilotPlan

    frogpilotPlan.accelerationJerk = A_CHANGE_COST * float(self.acceleration_jerk)
    frogpilotPlan.accelerationJerkStock = A_CHANGE_COST * float(self.base_acceleration_jerk)
    frogpilotPlan.speedJerk = J_EGO_COST * float(self.speed_jerk)
    frogpilotPlan.speedJerkStock = J_EGO_COST * float(self.base_speed_jerk)
    frogpilotPlan.tFollow = float(self.t_follow)

    frogpilotPlan.adjustedCruise = float(self.mtsc_target * (CV.MS_TO_KPH if frogpilot_toggles.is_metric else CV.MS_TO_MPH))

    frogpilotPlan.conditionalExperimentalActive = self.cem.experimental_mode

    frogpilotPlan.laneWidthLeft = self.lane_width_left
    frogpilotPlan.laneWidthRight = self.lane_width_right

    frogpilotPlan.maxAcceleration = self.max_accel
    frogpilotPlan.minAcceleration = self.min_accel

    frogpilotPlan.slcSpeedLimit = self.slc_target
    frogpilotPlan.slcSpeedLimitOffset = SpeedLimitController.offset
    frogpilotPlan.unconfirmedSlcSpeedLimit = SpeedLimitController.desired_speed_limit

    frogpilotPlan.vCruise = float(self.v_cruise)

    pm.send('frogpilotPlan', frogpilot_plan_send)
