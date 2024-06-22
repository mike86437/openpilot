from openpilot.common.params import Params

from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_functions import MovingAverageCalculator
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_variables import CITY_SPEED_LIMIT, PROBABILITY

class ConditionalExperimentalMode:
  def __init__(self):
    self.params_memory = Params("/dev/shm/params")

    self.curve_detected = False
    self.experimental_mode = False

    self.curvature_mac = MovingAverageCalculator()
    self.slow_lead_mac = MovingAverageCalculator()

  def update(self, carState, enabled, frogpilotNavigation, lead, modelData, road_curvature, slower_lead, v_ego, v_lead, frogpilot_toggles):
    self.update_conditions(lead.dRel, lead.status, modelData, road_curvature, slower_lead, v_ego, v_lead, frogpilot_toggles)
    self.experimental_mode = self.check_conditions(carState, frogpilotNavigation, lead.status, modelData, v_ego, v_lead, frogpilot_toggles)
    self.params_memory.put_int("CEStatus", self.status_value if self.experimental_mode else 0)

  def check_conditions(self, carState, frogpilotNavigation, lead_status, modelData, v_ego, v_lead, frogpilot_toggles):
    if carState.standstill:
      return self.experimental_mode

    if (lead_status and v_ego <= frogpilot_toggles.conditional_limit_lead) or (not lead_status and v_ego <= frogpilot_toggles.conditional_limit_lead):
      self.status_value = 7 if lead_status else 8
      return True

    approaching_maneuver = modelData.navEnabled and (frogpilotNavigation.approachingIntersection or frogpilotNavigation.approachingTurn)
    if frogpilot_toggles.conditional_navigation and approaching_maneuver and (frogpilot_toggles.conditional_navigation_lead or not lead_status):
      self.status_value = 10 if frogpilotNavigation.approachingIntersection else 11
      return True

    if frogpilot_toggles.conditional_curves and self.curve_detected:
      self.status_value = 12
      return True

    if frogpilot_toggles.conditional_lead and self.slow_lead_detected:
      self.status_value = 13 if v_lead < 1 else 14
      return True

    return False

  def update_conditions(self, lead_distance, lead_status, modelData, road_curvature, slower_lead, v_ego, v_lead, frogpilot_toggles):
    self.road_curvature(lead_status, road_curvature, v_ego, frogpilot_toggles)
    self.slow_lead(lead_status, slower_lead, v_lead, frogpilot_toggles)

  def road_curvature(self, lead_status, road_curvature, v_ego, frogpilot_toggles):
    curve_detected = (1 / road_curvature)**0.5 < v_ego and (frogpilot_toggles.conditional_curves_lead or not lead_status)
    curve_active = (0.9 / road_curvature)**0.5 < v_ego and self.curve_detected

    self.curvature_mac.add_data(curve_detected or curve_active)
    self.curve_detected = self.curvature_mac.get_moving_average() >= PROBABILITY

  def slow_lead(self, lead_status, slower_lead, v_lead, frogpilot_toggles):
    if lead_status:
      slower_lead &= frogpilot_toggles.conditional_slower_lead
      stopped_lead = frogpilot_toggles.conditional_stopped_lead and v_lead < 1

      self.slow_lead_mac.add_data(slower_lead or stopped_lead)
      self.slow_lead_detected = self.slow_lead_mac.get_moving_average() >= PROBABILITY
    else:
      self.slow_lead_mac.reset_data()
      self.slow_lead_detected = False
