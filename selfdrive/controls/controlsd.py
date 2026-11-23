#!/usr/bin/env python3
import math
from numbers import Number

from cereal import car, custom, log
import cereal.messaging as messaging
from openpilot.common.constants import CV
from openpilot.common.params import Params
from openpilot.common.realtime import config_realtime_process, DT_CTRL, Priority, Ratekeeper
from openpilot.common.swaglog import cloudlog

from opendbc.car.car_helpers import interfaces
from opendbc.car.vehicle_model import VehicleModel
from opendbc.safety import ALTERNATIVE_EXPERIENCE
from openpilot.selfdrive.controls.lib.drive_helpers import clip_curvature
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.selfdrive.controls.lib.latcontrol_pid import LatControlPID
from openpilot.selfdrive.controls.lib.latcontrol_angle import LatControlAngle, STEER_ANGLE_SATURATION_THRESHOLD
from openpilot.selfdrive.controls.lib.latcontrol_torque import LatControlTorque
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
from openpilot.selfdrive.modeld.modeld import LAT_SMOOTH_SECONDS
from openpilot.selfdrive.locationd.helpers import PoseCalibrator, Pose

from openpilot.frogpilot.common import frogpilot_utilities, frogpilot_variables
from openpilot.frogpilot.common.lateral_settings import LateralSettingsSource
from openpilot.frogpilot.controls.lateral.controller_selection import firmware_controller_selected
from openpilot.frogpilot.controls.lateral.steer_ratio_tuning import SteerRatioModeLatch, resolve_steer_ratio_selection
from openpilot.frogpilot.controls.lib.neural_network_feedforward import LatControlNNFF

State = log.SelfdriveState.OpenpilotState
LaneChangeState = log.LaneChangeState
LaneChangeDirection = log.LaneChangeDirection

ACTUATOR_FIELDS = tuple(car.CarControl.Actuators.schema.fields.keys())


class Controls:
  def __init__(self) -> None:
    self.params = Params()
    cloudlog.info("controlsd is waiting for CarParams")
    self.CP = messaging.log_from_bytes(self.params.get("CarParams", block=True), car.CarParams)

    # FrogPilot variables
    self.FPCP = messaging.log_from_bytes(self.params.get("FrogPilotCarParams", block=True), custom.FrogPilotCarParams)

    cloudlog.info("controlsd got CarParams")

    self.CI = interfaces[self.CP.carFingerprint](self.CP, self.FPCP)

    self.sm = messaging.SubMaster(['liveDelay', 'liveParameters', 'liveTorqueParameters', 'modelV2', 'selfdriveState',
                                   'liveCalibration', 'livePose', 'longitudinalPlan', 'carState', 'carOutput',
                                   'driverMonitoringState', 'onroadEvents', 'driverAssistance'], poll='selfdriveState')
    self.pm = messaging.PubMaster(['carControl', 'controlsState'])

    self.steer_limited_by_safety = False
    self.curvature = 0.0
    self.desired_curvature = 0.0

    self.pose_calibrator = PoseCalibrator()
    self.calibrated_pose: Pose | None = None

    self.LoC = LongControl(self.CP)
    self.VM = VehicleModel(self.CP)
    self.LaC: LatControl
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      self.LaC = LatControlAngle(self.CP, self.CI, DT_CTRL)
    elif self.CP.lateralTuning.which() == 'pid':
      self.LaC = LatControlPID(self.CP, self.CI, DT_CTRL)
    elif self.CP.lateralTuning.which() == 'torque':
      self.LaC = LatControlTorque(self.CP, self.CI, DT_CTRL)

    # FrogPilot variables
    self.sm = self.sm.extend(['frogpilotCarState', 'frogpilotPlan', 'frogpilotProcessState'])

    self.frogpilot_toggles = frogpilot_variables.get_frogpilot_toggles()
    self.lat_smooth_seconds = frogpilot_utilities.get_model_lat_smooth_seconds(self.frogpilot_toggles.model)
    self.using_custom_torque_params = False

    if self.CP.lateralTuning.which() == "torque" and (self.frogpilot_toggles.nnff or self.frogpilot_toggles.nnff_lite):
      self.LaC = LatControlNNFF(self.CP, self.CI, DT_CTRL)

    # PTM lateral, S3 (`analysis/PORT-LATERAL-LEDGER.md` §1a, Task 31). The admission is read once, at startup,
    # where the source reads it once (`sunnypilot/selfdrive/controls/controlsd_ext.py:57-63`), and the key is read
    # through this tree's own settings reader rather than from Params directly (D3). `NrdrLateralController` absent
    # or 0 selects nothing here: the four branches above stand, unchanged (ISC-3). The override sits where the
    # source's own override sits, after the branch the CarParams asked for, and `firmware_controller_selected`
    # already contains the four-condition admission, `lateralTuning.which() == 'pid'` included.
    self.lateral_settings = LateralSettingsSource(self.params)
    self.firmware_lateral_selected = firmware_controller_selected(self.lateral_settings.current(), self.CP, self.FPCP)
    if self.firmware_lateral_selected:
      # Deferred, as the source defers it (`controlsd_ext.py:58-63`): a car this admission does not accept does
      # not import the controller, its core or the measured tables.
      from openpilot.selfdrive.controls.lib.latcontrol_fw import LatControlFirmware
      self.LaC = LatControlFirmware(self.CP, self.CI, DT_CTRL)
      # The geometry the controller starts on, resolved from the same snapshot the admission was read from. Every
      # frame after this replaces it through the latch below, which is what `ptm_baseline=True` means: the measured
      # rack map is Table A only for a car the admission has accepted (D8). The source reaches the same value
      # through `ptm_baseline=getattr(controls.LaC, "firmware_profile", None) is not None`.
      self.steer_ratio_latch = SteerRatioModeLatch(
        resolve_steer_ratio_selection(self.CP, self.lateral_settings.current(), ptm_baseline=True))

    if hasattr(self.LaC, "pid"):
      self.base_k_p = self.LaC.pid._k_p

  def update(self):
    self.sm.update(15)
    if self.sm.updated["liveCalibration"]:
      self.pose_calibrator.feed_live_calib(self.sm['liveCalibration'])
    if self.sm.updated["livePose"]:
      device_pose = Pose.from_live_pose(self.sm['livePose'])
      self.calibrated_pose = self.pose_calibrator.build_calibrated_pose(device_pose)

    # FrogPilot variables
    if hasattr(self.LaC, "pid") and self.CP.lateralTuning.which() != "pid":
      self.LaC.pid._k_p = [self.base_k_p[0], [k_p * self.frogpilot_toggles.steerKp for k_p in self.base_k_p[1]]]

    if self.sm.updated['liveDelay'] and hasattr(self.LaC, "update_live_delay"):
      self.LaC.update_live_delay(self.sm['liveDelay'].lateralDelay)

    self.frogpilot_toggles = frogpilot_variables.get_frogpilot_toggles(self.sm)

  def state_control(self):
    CS = self.sm['carState']

    # Check which actuators can be enabled, resolved before the geometry as the source's controlsd resolves it
    # (`controlsd.py:103-106`): the steer-ratio latch is told whether the controller is engaged. `lat_active` is
    # the source's own quantity; this tree's FrogPilot-only term stays on the `CC.latActive` line below.
    standstill = abs(CS.vEgo) <= max(self.CP.minSteerSpeed, 0.3) or CS.standstill

    # FrogPilot variables
    lateral_allowed = not self.CP.alternativeExperience & ALTERNATIVE_EXPERIENCE.ALWAYS_ON_LATERAL or self.sm["frogpilotCarState"].alwaysOnLateralAllowed
    lateral_active = (lateral_allowed and self.sm["selfdriveState"].active) or self.sm["frogpilotCarState"].alwaysOnLateralEnabled
    lat_active = lateral_active and not CS.steerFaultTemporary and not CS.steerFaultPermanent and \
                 (not standstill or self.CP.steerAtStandstill)

    # Update VehicleModel
    lp = self.sm['liveParameters']
    x = max(lp.stiffnessFactor, 0.1)
    sr = max(lp.steerRatio, 0.1)
    if self.firmware_lateral_selected:
      # One settings snapshot for this frame (S1's reader refreshes on its own clock, so the control path does no
      # Params read, D3), the latch, and the latched geometry in both directions. The same snapshot is what the
      # controller's own lane gate reads (S6), which is the live half Task 11 left for this call site.
      settings = self.lateral_settings.current()
      self.LaC.set_live_tuning_snapshot(settings)
      selection = self.steer_ratio_latch.update(
        resolve_steer_ratio_selection(self.CP, settings, ptm_baseline=True), lat_active)
      self.LaC.set_steer_ratio_selection(selection)
      # The ratio the VehicleModel runs on and the curvature the car's measured angle means both come from the
      # accepted selection, as the source runs them: a controller that commanded through the measured map while
      # openpilot's own curvature still came from the learned ratio is the mixed state the plan forbids. Outside
      # mode 1 `ratio_at` answers the car's own ratio; mode 1's live learner ratio is the same
      # `liveParameters.steerRatio` this tree already runs on, with no held-ratio guard (see the README).
      sr = max(selection.ratio_at(0.0, sr), 0.1)
      self.VM.update_params(x, sr)
      self.curvature = selection.measured_curvature(self.VM, CS.steeringAngleDeg, CS.vEgo, lp.roll,
                                                    angle_offset_deg=lp.angleOffsetDeg)
    else:
      self.VM.update_params(x, sr)
      steer_angle_without_offset = math.radians(CS.steeringAngleDeg - lp.angleOffsetDeg)
      self.curvature = -self.VM.calc_curvature(steer_angle_without_offset, CS.vEgo, lp.roll)

    # Update Torque Params
    if self.CP.lateralTuning.which() == 'torque':
      torque_params = self.sm['liveTorqueParameters']
      if self.sm.all_checks(['liveTorqueParameters']) and \
         ((torque_params.useParams and not self.frogpilot_toggles.force_auto_tune_off) or self.frogpilot_toggles.force_auto_tune):
        self.LaC.update_live_torque_params(torque_params.latAccelFactorFiltered, torque_params.latAccelOffsetFiltered,
                                           torque_params.frictionCoefficientFiltered)

        # FrogPilot variables
        self.using_custom_torque_params = True
      elif (not torque_params.useParams and self.using_custom_torque_params and not self.frogpilot_toggles.force_auto_tune) or \
           self.frogpilot_toggles.use_custom_friction or self.frogpilot_toggles.use_custom_latAccelFactor:
        self.LaC.update_live_torque_params(self.frogpilot_toggles.latAccelFactor, self.CP.lateralTuning.torque.latAccelOffset, self.frogpilot_toggles.friction)
        self.using_custom_torque_params = self.frogpilot_toggles.use_custom_friction or self.frogpilot_toggles.use_custom_latAccelFactor

    long_plan = self.sm['longitudinalPlan']
    model_v2 = self.sm['modelV2']

    CC = car.CarControl.new_message()
    CC.enabled = self.sm['selfdriveState'].enabled

    # FrogPilot variables
    # The base's own longitudinal term, left where the base computes it. The port's recorded delta is the lateral
    # activity gate moving above the geometry and nothing else: `analysis/lateral_controlsd_probe.py` compares the
    # wired file against the file it replaced statement for statement, and a base term moved out of the base's own
    # block shows up there as an unrecorded change to a car that never asks for the port. `12aec8d34` had no
    # force_decel at all; this base does, and it stays the base's.
    force_decel = bool((self.sm["driverMonitoringState"].awarenessStatus < 0.) or
                       (self.sm["selfdriveState"].state == State.softDisabling))
    # The gate above is the only place the lateral activity is computed. `lat_active` is the source's quantity, the
    # same one the steer-ratio latch is told; this tree's FrogPilot-only term stays on the `CC.latActive` line.
    CC.latActive = lat_active and self.sm['frogpilotPlan'].lateralCheck
    CC.longActive = CC.enabled and not any(e.overrideLongitudinal for e in self.sm['onroadEvents']) and \
                    (force_decel or not self.sm['frogpilotCarState'].pauseLongitudinal) and self.CP.openpilotLongitudinalControl

    actuators = CC.actuators
    actuators.longControlState = self.LoC.long_control_state

    # Enable blinkers while lane changing
    if model_v2.meta.laneChangeState != LaneChangeState.off:
      CC.leftBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.left
      CC.rightBlinker = model_v2.meta.laneChangeDirection == LaneChangeDirection.right

    if not CC.latActive:
      self.LaC.reset()
    if not CC.longActive:
      self.LoC.reset()

    # accel PID loop
    pid_accel_limits = self.CI.get_pid_accel_limits(self.CP, CS.vEgo, CS.vCruise * CV.KPH_TO_MS)

    # FrogPilot variables
    pid_accel_limits = (pid_accel_limits[0], min(pid_accel_limits[1], self.frogpilot_toggles.max_desired_acceleration))

    actuators.accel = float(self.LoC.update(CC.longActive, CS, long_plan.aTarget, long_plan.shouldStop, pid_accel_limits, self.frogpilot_toggles))

    # Steering PID loop and lateral MPC
    # Reset desired curvature to current to avoid violating the limits on engage
    new_desired_curvature = model_v2.action.desiredCurvature if CC.latActive else self.curvature
    self.desired_curvature, curvature_limited = clip_curvature(CS.vEgo, self.desired_curvature, new_desired_curvature, lp.roll)
    lat_delay = self.sm["liveDelay"].lateralDelay + self.lat_smooth_seconds

    actuators.curvature = self.desired_curvature
    steer, steeringAngleDeg, lac_log = self.LaC.update(CC.latActive, CS, self.VM, lp,
                                                       self.steer_limited_by_safety, self.desired_curvature,
                                                       curvature_limited, lat_delay,
                                                       self.calibrated_pose,
                                                       self.sm['modelV2'],
                                                       self.frogpilot_toggles)
    actuators.torque = float(steer)
    actuators.steeringAngleDeg = float(steeringAngleDeg)
    # Ensure no NaNs/Infs
    for p in ACTUATOR_FIELDS:
      attr = getattr(actuators, p)
      if not isinstance(attr, Number):
        continue

      if not math.isfinite(attr):
        cloudlog.error(f"actuators.{p} not finite {actuators.to_dict()}")
        setattr(actuators, p, 0.0)

    return CC, lac_log

  def publish(self, CC, lac_log):
    CS = self.sm['carState']

    # Orientation and angle rates can be useful for carcontroller
    # Only calibrated (car) frame is relevant for the carcontroller
    CC.currentCurvature = self.curvature
    if self.calibrated_pose is not None:
      CC.orientationNED = self.calibrated_pose.orientation.xyz.tolist()
      CC.angularVelocity = self.calibrated_pose.angular_velocity.xyz.tolist()

    CC.cruiseControl.override = CC.enabled and not CC.longActive and self.CP.openpilotLongitudinalControl
    CC.cruiseControl.cancel = CS.cruiseState.enabled and (not CC.enabled or not self.CP.pcmCruise)
    CC.cruiseControl.resume = CC.enabled and CS.cruiseState.standstill and not self.sm['longitudinalPlan'].shouldStop

    # FrogPilot variables
    CC.cruiseControl.resume &= not self.sm['frogpilotPlan'].forcingStop

    hudControl = CC.hudControl
    hudControl.setSpeed = float(CS.vCruiseCluster * CV.KPH_TO_MS)
    hudControl.speedVisible = CC.enabled
    hudControl.lanesVisible = CC.enabled
    hudControl.leadVisible = self.sm['longitudinalPlan'].hasLead
    hudControl.leadDistanceBars = self.sm['selfdriveState'].personality.raw + 1
    hudControl.visualAlert = self.sm['selfdriveState'].alertHudVisual

    hudControl.rightLaneVisible = True
    hudControl.leftLaneVisible = True
    if self.sm.valid['driverAssistance']:
      hudControl.leftLaneDepart = self.sm['driverAssistance'].leftLaneDeparture
      hudControl.rightLaneDepart = self.sm['driverAssistance'].rightLaneDeparture

    if self.sm['selfdriveState'].active or self.sm['frogpilotCarState'].alwaysOnLateralEnabled:
      CO = self.sm['carOutput']
      if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
        self.steer_limited_by_safety = abs(CC.actuators.steeringAngleDeg - CO.actuatorsOutput.steeringAngleDeg) > \
                                              STEER_ANGLE_SATURATION_THRESHOLD
      else:
        self.steer_limited_by_safety = abs(CC.actuators.torque - CO.actuatorsOutput.torque) > 1e-2

    # TODO: both controlsState and carControl valids should be set by
    #       sm.all_checks(), but this creates a circular dependency

    # controlsState
    dat = messaging.new_message('controlsState')
    dat.valid = CS.canValid
    cs = dat.controlsState

    cs.curvature = self.curvature
    cs.longitudinalPlanMonoTime = self.sm.logMonoTime['longitudinalPlan']
    cs.lateralPlanMonoTime = self.sm.logMonoTime['modelV2']
    cs.desiredCurvature = self.desired_curvature
    cs.longControlState = self.LoC.long_control_state
    cs.upAccelCmd = float(self.LoC.pid.p)
    cs.uiAccelCmd = float(self.LoC.pid.i)
    cs.ufAccelCmd = float(self.LoC.pid.f)
    cs.forceDecel = bool((self.sm['driverMonitoringState'].awarenessStatus < 0.) or
                         (self.sm['selfdriveState'].state == State.softDisabling))

    lat_tuning = self.CP.lateralTuning.which()
    if self.CP.steerControlType == car.CarParams.SteerControlType.angle:
      cs.lateralControlState.angleState = lac_log
    elif lat_tuning == 'pid':
      cs.lateralControlState.pidState = lac_log
    elif lat_tuning == 'torque':
      cs.lateralControlState.torqueState = lac_log

    self.pm.send('controlsState', dat)

    # carControl
    cc_send = messaging.new_message('carControl')
    cc_send.valid = CS.canValid
    cc_send.carControl = CC
    self.pm.send('carControl', cc_send)

  def run(self):
    rk = Ratekeeper(100, print_delay_threshold=None)
    while True:
      self.update()
      CC, lac_log = self.state_control()
      self.publish(CC, lac_log)
      rk.monitor_time()


def main():
  config_realtime_process(4, Priority.CTRL_HIGH)
  controls = Controls()
  controls.run()


if __name__ == "__main__":
  main()
