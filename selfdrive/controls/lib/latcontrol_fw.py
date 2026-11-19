"""PTM Controller using Biscuit-Labs 45e5b91fae firmware calibrations and fixed timing.

Shared steer-ratio selection, driver override and model-scoped Optimized Lane Changes remain nrdr features.
Plan models ramp command delay to zero over one second; other sources ramp back to the calibration's hardcoded
command delay.

Ported from dev-111826's `nrdr/features/lateral/latcontrol_fw.py` (161 L) with the Clarity path only, i.e. the
branch that car already takes: `GAIN_BP`/`KP`/`KI` (`:28-30`), `ANGLE_RATE_LIMIT` (`:31`), the order in `update`
(delay line → geometry → slew → core → ceiling → pidState, `:104-160`) and the usable-output ceiling shared with
the core (`:144-150`) are verbatim. What follows is every place this copy differs from the source, with the
reason, because each one is a decision a later reader would otherwise have to rediscover (ledger §1a `latcontrol_fw`,
plan D1/D3/D5, todos 19/29):

1. **This tree's base class, this tree's carrier.** `__init__(CP, CI, dt)` is `selfdrive/controls/lib/latcontrol.py:11`
   — there is no second CarParams to pass and none is invented. The EPS-modified fact the source reads out of
   `CarParamsSP` is `CI.FPCP.flags & EPS_MODIFIED` (`opendbc/car/interfaces.py:124` attaches the FrogPilot CarParams
   to the interface, `card.py` writes it), so admission is `firmware_controller_profile(CP, CI.FPCP)` and a `None`
   answer raises, exactly as the source raises.
2. **The model arrives as `model_data`.** The source is handed `model_v2` through an `update_model_v2` call its own
   controlsd makes; this tree's `LatControl.update` already receives `self.sm['modelV2']` as its last argument
   (`controlsd.py:171-176`), so the frame's own argument is what the lane gate reads `meta.laneChangeState` from and
   what `_command_delay` reads `action.lateralSource` from. Same information, no extra injection method.
3. **The press detector is copied here, not borrowed.** `_eps_modified_steering_pressed` lives in the source's
   `latcontrol_pid.py:65-72`, and that file is the *fallback* controller this port refuses (D5). The eight lines the
   core's override handling and its feedforward fade depend on are carried here instead of porting a whole second
   controller to get them. Its numbers — the 0.10 command threshold, the opposite-sign test, the 0.28 s hold — are
   unchanged, and it keeps the same `DT_CTRL` step it adds to the hold.
4. **`override_fade_up_s` is 0.0, and that is a behaviour difference, not a gap.** In the source it is read from the
   Honda interface's live-tuning provider (`HondaLiveTuning`, reached through the Honda entry of the source's
   per-brand interface config, `…honda.provider`); nothing in this tree has such an object, so the read has nowhere
   to come from.
   A literal 0.0 keeps the core's documented condition (`vfn_eps_core.py:420-423`) false, so what changes at drive
   level is: there, a sustained steer limit bleeds the integrator through `OVERRIDE_FADE_I_BLEED_TAU` after a press
   releases; here it freezes. That is the number to look for in a paired drive, and it is the one thing this task
   could not carry without inventing a settings carrier this tree does not have.
5. **No calibration table at all.** The source's table lists the eleven images that have their own image constants,
   column load and residual-PID trims. The Clarity is not one of them — it takes the module-defaults branch, whose
   defaults *are* the Clarity's (`vfn_eps_core.CLARITY_A020` / `CLARITY_EPS_LOAD`, which is why that module was
   copied with one calibration). Dropping the other eleven therefore drops the branch, not a number.
6. **Every dropout is a hard reset.** The source's ride-through dropout is armed only for two calibrations
   (`rdx_tjb_a220`, `odyssey_thr_a220`/`odyssey_thr_a020` in its tuple at `:79`), so for this car `inactive_frames`
   — `math.inf`, then 0 while active — is above its threshold on the first inactive frame in both trees, and the
   "track internally, freeze I, send zero" branch is unreachable. `reset()` is the hard reset, unconditionally.
7. **No class-level core/feedforward indirection and no output-filter flag.** `owns_output_filter`, `core_type` and
   `feedforward_type` exist in the source for a testing variant and for its controlsd hook
   (`nrdr/hooks/controlsd.py:32-35`), which uses the flag to skip the *other* controller's post-processing. This
   tree has no such hook and no post-`LaC` output filter to skip (`torque_output_filter.py` is ported and
   unwired), so the flag would be read by nobody; the core is constructed by name. The testing variant is a separate
   task (decided 2026-11-19).
8. **Nothing here is wired** (ISC-3): no caller constructs this class until the controlsd latch exists (Task 31), and
   with `NrdrLateralController` absent or 0 this file changes no number on the road. The two injection methods below
   exist on this class only — this tree's base and its other controllers are untouched — with
   `stock_steer_ratio_selection(CP)` as the construction-safe default, i.e. the geometry this tree's own controller
   already uses, so a half-initialised controller cannot steer on a geometry nobody asked for.
"""
import numpy as np

from cereal import log
from openpilot.common.realtime import DT_CTRL
from openpilot.common.swaglog import cloudlog
from openpilot.selfdrive.controls.lib.latcontrol import LatControl
from openpilot.frogpilot.controls.lateral.controller_selection import firmware_controller_profile
from openpilot.frogpilot.controls.lateral.lane_change_tuning import optimized_lane_change_active
from openpilot.frogpilot.controls.lateral.model_source import CMD_DELAY_RAMP_S, PLAN
from openpilot.frogpilot.controls.lateral.steer_ratio_tuning import SteerRatioSelection, stock_steer_ratio_selection
from openpilot.frogpilot.controls.lateral.vfn_eps_core import HondaEpsFirmwareFeedforward, HondaEpsLateralCore
from openpilot.frogpilot.controls.lateral.yaw_control_timing import CommandDelay, command_delay, prediction_delay_schedule

VFN_SOURCE_COMMIT = "f837ca86a639b1c20a0ce23bb8acf0ebbc6a05d4"
GAIN_BP = [0.0, 11.175, 11.176, 22.352]
KP = [0.018, 0.024, 0.048, 0.060]
KI = [0.006, 0.008, 0.016, 0.020]
ANGLE_RATE_LIMIT = 300.0


def _eps_modified_steering_pressed(raw_pressed, steering_torque: float, torque_command: float,
                                  filter_seconds: float, previous_pressed: bool) -> tuple[float, bool]:
  """The source's press detector (`latcontrol_pid.py:65-72`), carried verbatim; see header 3."""
  if not raw_pressed:
    return 0.0, False
  if previous_pressed or abs(torque_command) < 0.10 or steering_torque * torque_command < 0.0:
    return 1.0, True
  filter_seconds = min(1.0, filter_seconds + DT_CTRL)
  return filter_seconds, filter_seconds >= 0.28


class LatControlFirmware(LatControl):
  def __init__(self, CP, CI, dt):
    self.firmware_profile = firmware_controller_profile(CP, getattr(CI, "FPCP", None))
    if self.firmware_profile is None:
      raise ValueError("PTM Controller requires a supported modified EPS family with PID CarParams")
    super().__init__(CP, CI, dt)
    # Header 8: this tree's base does not carry the geometry latch, so this class defaults it to the ratio CP
    # already ships with. controlsd replaces both before the first update (Task 31).
    self.steer_ratio_selection = stock_steer_ratio_selection(CP)
    self.live_tuning_snapshot = None
    self.delay_schedule = prediction_delay_schedule(self.firmware_profile)
    # The Clarity: the module defaults this core is built with are its own calibration and its own load model.
    self.core = HondaEpsLateralCore(GAIN_BP, KP, GAIN_BP, KI, dt, ff=HondaEpsFirmwareFeedforward(dt))
    cloudlog.info("PTM Controller profile=%s calibration=%s provisional=%s prediction_schedule=%s required_rwd=%s",
                  self.firmware_profile.name, self.firmware_profile.calibration,
                  self.firmware_profile.provisional, self.delay_schedule, self.firmware_profile.required_rwd or "-")
    self.cmd_delay = CommandDelay(dt)
    self.cmd_delay_scale = 1.0
    self.prev_angle = 0.0
    self.pressed_duration = 0.0
    self.pressed_prev = False
    self.model_data = None

  def set_live_tuning_snapshot(self, snapshot) -> None:
    self.live_tuning_snapshot = snapshot

  def set_steer_ratio_selection(self, selection: SteerRatioSelection) -> None:
    self.steer_ratio_selection = selection

  def _command_delay(self, v_ego: float) -> float:
    delay = command_delay(None, v_ego, calibration=self.firmware_profile.calibration)
    action = getattr(self.model_data, "action", None)
    target = 0.0 if str(getattr(action, "lateralSource", "unknown")) == PLAN else 1.0
    step = self.dt / CMD_DELAY_RAMP_S
    self.cmd_delay_scale += max(min(target - self.cmd_delay_scale, step), -step)
    return self.cmd_delay_scale * delay

  def reset(self):
    self._hard_reset()

  def _hard_reset(self):
    super().reset()
    self.core.reset()
    self.pressed_duration = 0.0
    self.pressed_prev = False

  def update(self, active, CS, VM, params, steer_limited_by_safety, desired_curvature,
             curvature_limited, lat_delay, calibrated_pose, model_data, frogpilot_toggles):
    self.model_data = model_data
    pid_log = log.ControlsState.LateralPIDState.new_message()
    pid_log.steeringAngleDeg = float(CS.steeringAngleDeg)
    pid_log.steeringRateDeg = float(CS.steeringRateDeg)
    delay = self._command_delay(CS.vEgo)
    desired_curvature = self.cmd_delay.update(desired_curvature, delay)
    desired = self.steer_ratio_selection.desired_angle_no_offset(
      VM, CS.steeringAngleDeg, CS.vEgo, params.roll, desired_curvature)
    if active:
      step = ANGLE_RATE_LIMIT * self.dt
      desired = float(np.clip(desired, self.prev_angle - step, self.prev_angle + step))
    self.prev_angle = desired
    angle = desired + params.angleOffsetDeg
    pid_log.steeringAngleDesiredDeg = angle
    pid_log.angleError = angle - CS.steeringAngleDeg
    if not active:
      self._hard_reset()
      output = 0.0
    else:
      self.pressed_duration, pressed = _eps_modified_steering_pressed(
        bool(CS.steeringPressed), float(CS.steeringTorque), self.core.output,
        self.pressed_duration, self.pressed_prev)
      self.pressed_prev = pressed
      state = 0 if model_data is None else model_data.meta.laneChangeState.raw
      optimized = optimized_lane_change_active(self.live_tuning_snapshot, state)
      # See header 4: no Honda live-tuning carrier in this tree, so the core's limiter-feedback bleed stays off.
      output = self.core.update(desired, params.angleOffsetDeg, CS.steeringAngleDeg, CS.vEgo, params.roll,
                                pressed, steer_limited_by_safety, optimized_lane_change=optimized,
                                override_fade_up_s=0.0)
      # A command row may stop adding assist before the host's normalized limit.
      # Saturation reporting must follow the same usable ceiling as the core.
      output_limit = min(self.steer_max, self.core.ff.cal.output_ceiling())
      output = float(np.clip(output, -output_limit, output_limit))
      pid_log.p = float(self.core.pid.p)
      pid_log.i = float(self.core.pid.i)
      pid_log.f = float(self.core.pid.f)
      pid_log.saturated = bool(self._check_saturation(
        output_limit - abs(output) < 1e-3, CS, steer_limited_by_safety, curvature_limited))
    ff = self.core.ff
    pid_log.epsFfActive = bool(active)
    pid_log.epsFfWeight = float(self.core.ff_weight)
    pid_log.epsFfFeedforward = float(ff.output)
    pid_log.epsFfR5 = float(ff.r5)
    pid_log.epsFfLoad = float(ff.load)
    pid_log.epsFfDesiredRate = float(ff.rate)
    pid_log.commandDelay = float(delay)
    pid_log.active = bool(active)
    pid_log.output = output
    return output, angle, pid_log
