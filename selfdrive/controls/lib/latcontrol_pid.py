import math

from cereal import log
from opendbc.car.honda.values import clarity_mod_eps
from openpilot.common.pid import PIDController
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.selfdrive.controls.lib.latcontrol_phase import phase_with_latch


class LatControlPID(LatControl):
  def __init__(self, CP, CI, dt):
    super().__init__(CP, CI, dt)
    self.pid = PIDController((CP.lateralTuning.pid.kpBP, CP.lateralTuning.pid.kpV),
                             (CP.lateralTuning.pid.kiBP, CP.lateralTuning.pid.kiV),
                             pos_limit=self.steer_max, neg_limit=-self.steer_max)
    self.ff_factor = CP.lateralTuning.pid.kf
    self.get_steer_feedforward = CI.get_steer_feedforward_function()

    # FrogPilot variables: the modified-EPS Clarity only - clarity_mod_eps() is the same firmware gate that
    # selects its torque map and its actuator smoothing, so every other car keeps this controller unchanged.
    #
    # NRDR freezes the integrator while the commanded angle is unwinding and the integrator is wound up in the
    # direction the unwind is fighting (nrdr/latcontrol_pid.py:287-295). FrogPilot's condition below has no
    # notion of which half of a corner the car is in, so an integrator wound up through a turn keeps being
    # fed while the car is already trying to come back out of it. Route 0000001d is the measurement: with the
    # actuator smoothing live, hands-off straight driving is calm (393 windows with the wheel wandering a
    # median 1.2 degrees), but in the 15-30 kph band the actuator still reverses direction 192 times a minute
    # - and the drive was described as "oversteers, then twitches getting back in line". That is the unwind,
    # and the integrator is the thing still pushing there. It is not the low-speed problem: below 5 m/s this
    # controller already freezes the integrator, which is why the measured integral share below 20 kph is
    # under 1 %.
    self.phase_latched = clarity_mod_eps(CP.carFingerprint, CP.carFw)
    self.previous_desired_angle = 0.0
    self.phase_direction = 0.0

  def reset(self):
    super().reset()
    self.previous_desired_angle = 0.0
    self.phase_direction = 0.0

  def update(self, active, CS, VM, params, steer_limited_by_safety, desired_curvature, curvature_limited, lat_delay, calibrated_pose, model_data, frogpilot_toggles):
    pid_log = log.ControlsState.LateralPIDState.new_message()
    pid_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    pid_log.steeringRateDeg = float(CS.steeringRateDeg)

    angle_steers_des_no_offset = math.degrees(VM.get_steer_from_curvature(-desired_curvature, CS.vEgo, params.roll))
    angle_steers_des = angle_steers_des_no_offset + params.angleOffsetDeg
    error = angle_steers_des - CS.steeringAngleDeg

    pid_log.steeringAngleDesiredDeg = angle_steers_des
    pid_log.angleError = error
    if not active:
      output_torque = 0.0
      pid_log.active = False
      # not zero: the first frame after a re-engage must not read the whole disengagement as one angle delta
      self.previous_desired_angle = angle_steers_des_no_offset
      self.phase_direction = 0.0

    else:
      # offset does not contribute to resistive torque
      ff = self.ff_factor * self.get_steer_feedforward(angle_steers_des_no_offset, CS.vEgo)
      angle_delta = angle_steers_des_no_offset - self.previous_desired_angle
      self.previous_desired_angle = angle_steers_des_no_offset
      phase, self.phase_direction = phase_with_latch(angle_steers_des_no_offset, angle_delta, CS.vEgo,
                                                     self.phase_direction)
      freeze_integrator = steer_limited_by_safety or CS.steeringPressed or CS.vEgo < 5
      # phase < 0 means the commanded angle's magnitude is falling; pid.i is the integral from the previous
      # frame, so i * error > 0 means it is still signed the way the turn was going, not the way back
      if self.phase_latched and phase < 0.0 and self.pid.i * error > 0.0:
        freeze_integrator = True

      output_torque = self.pid.update(error,
                                feedforward=ff,
                                speed=CS.vEgo,
                                freeze_integrator=freeze_integrator)

      pid_log.active = True
      pid_log.p = float(self.pid.p)
      pid_log.i = float(self.pid.i)
      pid_log.f = float(self.pid.f)
      pid_log.output = float(output_torque)
      pid_log.saturated = bool(self._check_saturation(self.steer_max - abs(output_torque) < 1e-3, CS, steer_limited_by_safety, curvature_limited))

    return output_torque, angle_steers_des, pid_log
