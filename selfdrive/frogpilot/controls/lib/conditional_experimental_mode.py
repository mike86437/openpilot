from openpilot.common.params import Params

from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_functions import MovingAverageCalculator
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_variables import CITY_SPEED_LIMIT, PROBABILITY

class ConditionalExperimentalMode:
  def __init__(self):
    self.params_memory = Params("/dev/shm/params")

    self.experimental_mode = False

  def update(self, carState, enabled, frogpilotNavigation, lead, modelData, road_curvature, slower_lead, v_ego, v_lead, frogpilot_toggles):
    self.update_conditions(lead.dRel, lead.status, modelData, road_curvature, slower_lead, v_ego, v_lead, frogpilot_toggles)
    self.experimental_mode = self.check_conditions(carState, frogpilotNavigation, lead.status, modelData, v_ego, v_lead, frogpilot_toggles)
    self.params_memory.put_int("CEStatus", self.status_value if self.experimental_mode else 0)

  def check_conditions(self, carState, frogpilotNavigation, lead_status, modelData, v_ego, v_lead, frogpilot_toggles):
    if carState.standstill:
      return self.experimental_mode

    if (not lead_status and v_ego <= frogpilot_toggles.conditional_limit) or (lead_status and v_ego <= frogpilot_toggles.conditional_limit_lead):
      self.status_value = 7 if lead_status else 8
      return True

    return False

  def update_conditions(self, lead_distance, lead_status, modelData, road_curvature, slower_lead, v_ego, v_lead, frogpilot_toggles):
