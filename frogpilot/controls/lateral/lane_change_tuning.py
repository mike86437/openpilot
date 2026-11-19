"""Lane-change request shaping, not a change to measured steering geometry.

Ported from dev-111826 `nrdr/features/lateral/lane_change_tuning.py` (199 L). `ENTRY_RAMP_SECONDS`,
`CANCEL_RETURN_SECONDS`, `MIN_EFFECTIVE_RATIO`, the two fixed value tables, `bounded_setting`, `_smoothstep`,
`LaneChangeEntry`, `shape_lane_change_curvature` and `optimized_lane_change_active` are the source's code, def
for def and constant for constant (the AST comparison is `analysis/lateral_lane_change_probe.py` §A). What is
not carried is the model-eligibility half, listed below with the reason. Read `steer_ratio_tuning.py` first:
the only geometry this shaping may reshape is that module's `SteerRatioSelection`, and going through
`selection.ratio_at` / `desired_angle_no_offset` / `measured_curvature` instead of `CP.steerRatio` is the whole
difference between this and a stock lane-change nudge.

**What the source tree actually runs on this car (measured 2026-11-19, not carried from the plan).** The car has
`NrdrOptimizedLaneChanges=1`, `LaneGuidanceMode=0`, `LaneCentering=0` (`/data/params/d/`, read directly). And
the entry reduction is **fixed at 0.0** — in both tables (`:15-21`, the comment is the source's own: "Keep the
selected geometry/request unchanged, including with legacy saved values"), the key is a tombstone in its registry
(`nrdr/params/specs.py:168` for the sibling key), and no saved value can raise it. So `onset` never fires,
`applied` is 0.0 on every frame, and `shape_lane_change_curvature` returns `desired_curvature` unchanged at its
first line. The source's own tests say the same thing (`test_lane_change_tuning.py`: `test_optimized_entry_keeps_
the_current_steering_ratio` asserts 200 frames of `0.0`; `test_retired_edits_cannot_restore_ratio_reduction`
asserts `entry.reduction == 0 and entry.return_seconds == 1`), and one of them has drifted from its own code —
`test_cleanup_policy.py::test_lane_change_retired_sliders_cannot_change_fixed_settings` expects
`NrdrLaneChangeEntrySrReduction → 5` and fails at `4a806bf` with `assert 0.0 == 5`. This port reproduces the
code, not the stale test; the tables and the source's own suite are both run (§B and §C of the gate) rather than
asserted here.

**What is therefore not inert about this module.** One thing, and it is the reason the file is ported at all:
`optimized_lane_change_active`. The source's controller computes it per frame (`latcontrol_fw.py:135`) and hands
it to the core (`:140`), which drops the feedforward — including the modeled EPS damping — and resets its rejoin
ramp for the duration of a starting or finishing maneuver (`vfn_eps_core.py:579-582`, "Owner-requested adaptation:
no feedforward … during optimized lane changes. Reset its rejoin ramp to prevent a jump on exit."). That branch
is already in this tree's core (`vfn_eps_core.py`, its `optimized_lane_change` argument, exercised for a
five-frame block inside V20's 86 863 frames); what is missing is the caller, and that is Task 19, which is where
this gate is reached — with the `LateralSettings` snapshot this module reads and the `modelV2` this tree's
`controlsd.py:171-176` already passes to `LaC.update`.

**The model gate: not carried, because this tree cannot evaluate it.** The source admits the optimized values
only for a model it can identify — a catalog family (`OPTIMIZED_MODEL_FAMILIES`), one of sixteen model refs
(`OPTIMIZED_MODEL_REFS`), and never for `is_big` or a chestnut bundle (`lane_change_tuning.py:24-62`). This
tree's knowledge of a model is an id, a display name and `lat_smooth_seconds`: the catalog file is rebuilt from
the remote list keeping exactly those three keys (`frogpilot/system/model_manager.py:116-121`, the only model row
the tree writes), and
`frogpilot_variables.get_models()` reads nothing else (`:1243-1244`). There is no family folder, no ref hash, no
big/small distinction and no chestnut anywhere in the tree — §E of the gate searches this tree for every family
name, every model ref, `is_big`, `chestnut` and `ActiveBundle` the source's gate could test, and finds none. If
that ever stops being true the refusal is wrong, and the gate says so. Refusing that half
cannot disagree with the source on this car today: the car has no `ModelManager_ActiveBundle` parameter at all,
so the source's own answer for it is its `None` branch, whose default ref
(`sunnypilot/models/model_name.py:2`, `5b6436a90cf6902b8aaa71c2b6f3d7164d8ae391` — "CD210 (default small
model)") is itself in `OPTIMIZED_MODEL_REFS`. Both trees admit the model on this car; §E of the gate evaluates
that rather than claiming it. If a drive ever shows a model that must not have the adaptation, this tree's
convention for that is a named model set next to `ACTION_DELAY_MODELS` and `MIN_STABLE_DELAY_MODELS`
(`frogpilot/common/frogpilot_variables.py:107-111`), and it would arrive with the measurement, not before it.

**Three of the five fixed values are dead data here, kept as written.** `bounded_setting` returns the table for
all five keys, and only `NrdrLaneChangeEntrySrReduction` / `…EntryReturnTime` are read by code this tree runs.
`NrdrLaneChangeMinTime` belongs to the source's lane-change state machine (`selfdrive/controls/lib/desire_helper.py:82`),
whose equivalent knob in this tree is FrogPilot's own `LaneChangeTime` → `toggle.lane_change_delay` →
`desire_helper.py:91,94` — so the port registers no second knob for the same thing, and a comparable drive states
both. `NrdrLaneChangeTorqueFactor` belongs to `nrdr/features/driver_policy/lane_change.py`, and
`NrdrLaneChangeFrictionPercent` to the fallback torque controller (`selfdrive/controls/lib/latcontrol_torque.py:100`)
that D5 does not port. The table is kept whole for the same reason `torque_output_filter.py` kept its duck-typed
`live` argument: flattening it would quietly rewrite the source's policy while looking like a copy.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
  from openpilot.frogpilot.common.lateral_settings import LateralSettings

ENTRY_RAMP_SECONDS = 0.15
CANCEL_RETURN_SECONDS = 0.20
MIN_EFFECTIVE_RATIO = 8.0
OPTIMIZED_VALUES = {
  "NrdrLaneChangeMinTime": 0.5,
  # Keep the selected geometry/request unchanged, including with legacy saved values.
  "NrdrLaneChangeEntrySrReduction": 0.0,
  "NrdrLaneChangeEntryReturnTime": 1.0,
  "NrdrLaneChangeTorqueFactor": 2.0,
  "NrdrLaneChangeFrictionPercent": 0.0,
}
BASELINE_VALUES = {**OPTIMIZED_VALUES, "NrdrLaneChangeMinTime": 1.0,
                   "NrdrLaneChangeEntrySrReduction": 0.0, "NrdrLaneChangeTorqueFactor": 1.0,
                   "NrdrLaneChangeFrictionPercent": 100.0}


def optimized_lane_changes_enabled(settings: LateralSettings | Any) -> bool:
  """The one parameter this module reads, read the way this tree reads parameters.

  Two differences from the source, both deliberate and both recorded rather than left to be noticed in a drive:

  * the source's answer is `setting AND model`, this tree's is the setting alone - the model half has no carrier
    here, and the reason and the car-side measurement are in the header above;
  * the source treats an unset `NrdrOptimizedLaneChanges` as on (`requested = value is None or …`, `:68`)
    because its profile default is `True` (`nrdr/params/profiles.py:252`, which is also what this car has saved).
    Here the key is registered with default `0` and an unset key is this tree's stock behaviour (ISC-3), so a
    car that was never asked runs its own lateral controller unchanged. A comparable drive therefore states the
    key explicitly in both trees - the same rule this tree already follows for `NrdrSteerRatioMode` (D8).

  Anything that is not a settings snapshot - a missing key, a reader that is not this tree's - is off. The source
  caches a Params read to keep storage out of its control loop (`@cache`, "never poll Params/USB in the control
  loop"); here there is nothing to cache, because the caller hands in a snapshot that already read it once.
  """
  try:
    return bool(settings.bool_of("NrdrOptimizedLaneChanges"))
  except (AttributeError, TypeError, ValueError):
    return False


def optimized_lane_change_active(settings, state) -> bool:
  # Waiting for a nudge is not yet a lane change. Keep normal steering then.
  return optimized_lane_changes_enabled(settings) and int(getattr(state, "raw", state)) in (2, 3)


def bounded_setting(settings, key: str, default: float, minimum: float, maximum: float) -> float:
  if key in OPTIMIZED_VALUES:
    return (OPTIMIZED_VALUES if optimized_lane_changes_enabled(settings) else BASELINE_VALUES)[key]
  try:
    value = float(settings.get(key)) if settings is not None else default
  except (TypeError, ValueError, OverflowError):
    value = default
  return min(max(value, minimum), maximum) if math.isfinite(value) else default


def _smoothstep(value: float) -> float:
  value = min(max(value, 0.0), 1.0)
  return value * value * (3.0 - 2.0 * value)


@dataclass
class LaneChangeEntry:
  """One bounded envelope per starting edge; edits take effect next maneuver.

  LaneChangeState: off=0, pre=1, starting=2, finishing=3. Waiting for a nudge
  must not shape steering. A signal held after completion must not retrigger.
  """

  was_starting: bool = False
  elapsed: float | None = None
  reduction: float = 0.0
  return_seconds: float = 1.0
  direction: int = 0
  applied: float = 0.0
  cancel_elapsed: float | None = None
  cancel_from: float = 0.0

  def update(self, *, active: bool, valid: bool, state: int, direction: int,
             driver_override: bool, settings, dt: float) -> float:
    starting = state == 2
    requested = bounded_setting(settings, "NrdrLaneChangeEntrySrReduction", 0.0, 0.0, 5.0)
    onset = starting and not self.was_starting
    self.was_starting = starting
    if not active or not valid:
      self.elapsed = self.cancel_elapsed = None
      self.applied = 0.0
      return 0.0

    dt = min(max(dt, 0.0), 0.1) if math.isfinite(dt) else 0.0
    if onset and direction in (1, 2) and not driver_override and requested > 0.0:
      self.elapsed = 0.0
      self.cancel_elapsed = None
      self.reduction = requested
      self.return_seconds = bounded_setting(settings, "NrdrLaneChangeEntryReturnTime", 1.0, 0.2, 3.0)
      self.direction = direction

    cancelled = not starting or direction != self.direction or driver_override or requested == 0.0
    if self.elapsed is not None and cancelled:
      self.elapsed = None
      self.cancel_elapsed = 0.0
      self.cancel_from = self.applied

    if self.cancel_elapsed is not None:
      self.cancel_elapsed += dt
      self.applied = self.cancel_from * (1.0 - _smoothstep(self.cancel_elapsed / CANCEL_RETURN_SECONDS))
      if self.cancel_elapsed >= CANCEL_RETURN_SECONDS:
        self.cancel_elapsed = None
        self.applied = 0.0
    elif self.elapsed is not None:
      self.elapsed += dt
      if self.elapsed <= ENTRY_RAMP_SECONDS:
        weight = _smoothstep(self.elapsed / ENTRY_RAMP_SECONDS)
      else:
        weight = 1.0 - _smoothstep((self.elapsed - ENTRY_RAMP_SECONDS) / self.return_seconds)
      self.applied = self.reduction * weight
      if self.elapsed >= ENTRY_RAMP_SECONDS + self.return_seconds:
        self.elapsed = None
        self.applied = 0.0
    return self.applied


def shape_lane_change_curvature(selection, VM, measured_angle: float, speed: float, roll: float,
                                desired_curvature: float, reduction: float) -> float:
  """Reduce the request using the resolved source, including Hybrid/Firmware.

  The current effective SR is the selected physical-to-linear mapping at the
  current wheel angle. Apply its fractional reduction to the requested physical
  angle relative to the zero-curvature angle, preserving road-roll compensation.
  Convert back using the SAME geometry. Feedback and learners remain unchanged.
  The caller must still run normal curvature/actuator safety limits afterward.
  """
  if reduction <= 0.0 or desired_curvature == 0.0:
    return desired_curvature
  if not all(math.isfinite(v) for v in (measured_angle, speed, roll, desired_curvature, reduction)):
    return desired_curvature

  previous_ratio = VM.sR
  try:
    ratio = selection.ratio_at(measured_angle, previous_ratio)
    reference = max(abs(measured_angle), 1e-3)
    linear_reference = selection.linearize_measured_angle(reference)
    if linear_reference <= 0.0:
      return desired_curvature
    effective_ratio = ratio * reference / linear_reference
    if not math.isfinite(effective_ratio) or effective_ratio <= MIN_EFFECTIVE_RATIO:
      return desired_curvature
    reduction = min(reduction, 5.0, effective_ratio - MIN_EFFECTIVE_RATIO)
    scale = 1.0 - reduction / effective_ratio
    zero_angle = selection.desired_angle_no_offset(VM, measured_angle, speed, roll, 0.0)
    target_angle = selection.desired_angle_no_offset(VM, measured_angle, speed, roll, desired_curvature)
    shaped_angle = zero_angle + scale * (target_angle - zero_angle)
    if getattr(selection, "model_blend", None) is not None:
      shaped = selection.measured_curvature(VM, shaped_angle, speed, roll)
    elif (rack_map := getattr(selection, "rack_map", None)) is not None:
      # The rack map carries its own slip factor; convert back through it, as the angles above were.
      shaped = -rack_map.curvature_from_angle(shaped_angle, speed, roll)
    else:
      linear_angle = selection.linearize_measured_angle(shaped_angle)
      shaped = -VM.calc_curvature(math.radians(linear_angle), speed, roll)
    if not math.isfinite(shaped):
      return desired_curvature
    # A reduction must never amplify or reverse the requested curvature.
    return min(max(shaped, min(0.0, desired_curvature)), max(0.0, desired_curvature))
  finally:
    VM.sR = previous_ratio


__all__ = (
  "BASELINE_VALUES",
  "CANCEL_RETURN_SECONDS",
  "ENTRY_RAMP_SECONDS",
  "LaneChangeEntry",
  "MIN_EFFECTIVE_RATIO",
  "OPTIMIZED_VALUES",
  "bounded_setting",
  "optimized_lane_change_active",
  "optimized_lane_changes_enabled",
  "shape_lane_change_curvature",
)
