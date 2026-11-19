import math
from enum import StrEnum, auto

from cereal import car, messaging
from openpilot.common.params import UnknownKeyName
from openpilot.common.realtime import DT_CTRL
from openpilot.selfdrive.locationd.helpers import Pose
from opendbc.car import ACCELERATION_DUE_TO_GRAVITY
from opendbc.car.lateral import ISO_LATERAL_ACCEL
from opendbc.car.interfaces import ACCEL_MIN, ACCEL_MAX

MIN_EXCESSIVE_ACTUATION_COUNT = int(0.25 / DT_CTRL)
MIN_LATERAL_ENGAGE_BUFFER = int(1 / DT_CTRL)


# FrogPilot variables (NRDR): the switch that turns the check below off, and with it the alert and everything
# that makes the alert sticky. Registered in common/params_keys.h as a PERSISTENT BOOL defaulting to "0", so a
# car that never asks for it runs upstream's behaviour unchanged. Disabled means all three parts:
#   * ExcessiveActuationCheck is never updated, so no new Offroad_ExcessiveActuation is written;
#   * selfdrived does not consult a stale one at startup, so it stops adding EventName.excessiveActuation
#     (SOFT_DISABLE + NO_ENTRY) every frame - that event is what refuses lateral control after an alert;
#   * hardwared's no_excessive_actuation startup condition passes, so a stale alert cannot block startup.
# What it deliberately does NOT do is clear the parameter: a stale alert stays on disk, and re-enabling the check
# (or the UI's Acknowledge button) restores it.
EXCESSIVE_ACTUATION_DISABLE_KEY = "DisableExcessiveActuationCheck"


def excessive_actuation_disabled(params) -> bool:
  # Read the switch without assuming this tree's compiled parameter registry knows it: params_pyx.so is built
  # from common/params_keys.h, so a checkout newer than the .so it runs with answers UnknownKeyName. That is
  # answered as "not disabled", which is what an unregistered key means here.
  try:
    return bool(params.get_bool(EXCESSIVE_ACTUATION_DISABLE_KEY))
  except UnknownKeyName:
    return False


class ExcessiveActuationType(StrEnum):
  LONGITUDINAL = auto()
  LATERAL = auto()


class ExcessiveActuationCheck:
  def __init__(self):
    self._excessive_counter = 0
    self._engaged_counter = 0

  def update(self, sm: messaging.SubMaster, CS: car.CarState, calibrated_pose: Pose) -> ExcessiveActuationType | None:
    # CS.aEgo can be noisy to bumps in the road, transitioning from standstill, losing traction, etc.
    # longitudinal
    accel_calibrated = calibrated_pose.acceleration.x
    excessive_long_actuation = sm['carControl'].longActive and (accel_calibrated > ACCEL_MAX * 2 or accel_calibrated < ACCEL_MIN * 2)

    # lateral
    yaw_rate = calibrated_pose.angular_velocity.yaw
    roll = sm['liveParameters'].roll
    roll_compensated_lateral_accel = (CS.vEgo * yaw_rate) - (math.sin(roll) * ACCELERATION_DUE_TO_GRAVITY)

    # Prevent false positives after overriding
    excessive_lat_actuation = False
    self._engaged_counter = self._engaged_counter + 1 if sm['carControl'].latActive and not CS.steeringPressed else 0
    if self._engaged_counter > MIN_LATERAL_ENGAGE_BUFFER:
      if abs(roll_compensated_lateral_accel) > ISO_LATERAL_ACCEL * 2:
        excessive_lat_actuation = True

    # livePose acceleration can be noisy due to bad mounting or aliased livePose measurements
    livepose_valid = abs(CS.aEgo - accel_calibrated) < 2
    self._excessive_counter = self._excessive_counter + 1 if livepose_valid and (excessive_long_actuation or excessive_lat_actuation) else 0

    excessive_type = None
    if self._excessive_counter > MIN_EXCESSIVE_ACTUATION_COUNT:
      if excessive_long_actuation:
        excessive_type = ExcessiveActuationType.LONGITUDINAL
      else:
        excessive_type = ExcessiveActuationType.LATERAL

    return excessive_type
