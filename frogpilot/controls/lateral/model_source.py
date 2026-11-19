"""Model-source metadata and PTM timing shared by the model runner and controlsd.

Carried from dev-111826 `nrdr/features/lateral/model_source.py` (55 L) — the code is the source's, def for
def; only this docstring differs. Its single import is `openpilot.common.realtime`, which is the same file in
both trees (`DT_CTRL = 0.01`, `DT_MDL = 0.05`).

What the three names mean in **this** tree, which is the reason the stamps exist (ledger §2 D2, D4):

* `PLAN` — every model this tree runs is read off the plan at `lat_action_t`
  (`selfdrive/modeld/modeld.py:get_action_from_model` → `get_curvature_from_plan`). A dev-111826 drive with a
  plan-output model stamps `plan` too: the real drive `0000003e--366234e97b` stamps `plan` on 48 325 of
  48 325 model frames, which is what makes the two trees comparable frame for frame.
* `CURVATURE_HEAD` — the legacy-model path here is `frogpilot_model_utilities.LegacyModelState.update_action`,
  which takes `model_output["desired_curvature"]` when its `curvature_source` is not `plan`/`legacy_plan`. The
  source's `lateral_source` classifies exactly that shape (`desired_curvature` non-zero, not mlsim), so the
  classification is replayed as written rather than rewritten against a function this tree does not have.
* `ACTION_HEAD` — no model in this tree produces an `action` output: `grep` over the whole tree finds no
  `actionHead`, no `model_output['action']`, and `ModelConstants` has no action head. The member is kept
  because the *field ids* must match the source's schema byte for byte, not because this tree can write it.

`ModelActionRamp` is the source's interpolation of the 20 Hz model action across each 100 Hz control frame
(`controlsd.py:79,176-177` there). It is not wired here yet — controlsd wiring is Task 10/19 — and both
directions of the related command-delay ramp are tested from the ramp itself for the same reason
(`analysis/lateral_timing_probe.py`).
"""
from openpilot.common.realtime import DT_CTRL, DT_MDL

PTM_LAT_SMOOTH_SECONDS = 0.1
CMD_DELAY_RAMP_S = 1.0

ACTION_HEAD = "actionHead"
CURVATURE_HEAD = "curvatureHead"
PLAN = "plan"
UNKNOWN = "unknown"


def lateral_source(model_output, mlsim: bool) -> str:
  """The source, exactly as get_action_from_model / get_curvature_from_output choose it."""
  if "action" in model_output:
    return ACTION_HEAD
  # Match get_curvature_from_output, including its zero-output plan fallback.
  if not mlsim and model_output.get("desired_curvature"):
    return CURVATURE_HEAD
  return PLAN


def delay_input(numpy_inputs) -> str:
  if "action_t" in numpy_inputs:
    return "actionT"
  if "lateral_control_params" in numpy_inputs:
    return "lateralControlParams"
  return "none"


def model_uses_plan(output_names, mlsim: bool) -> bool:
  """Select the prediction horizon from declared outputs before inference."""
  return "action" not in output_names and (mlsim or "desired_curvature" not in output_names)


class ModelActionRamp:
  """Biscuit-Labs 45e5b91fae: interpolate the 20 Hz model action across each control frame."""

  def __init__(self):
    self.reset(0.0)

  def reset(self, curvature: float) -> None:
    self.output = self.start = self.target = float(curvature)
    self.elapsed = 0.0

  def update(self, curvature: float, new_frame: bool, active: bool) -> float:
    if not active:
      self.reset(curvature)
      return self.output
    if new_frame:
      self.start, self.target, self.elapsed = self.output, float(curvature), 0.0
    else:
      self.elapsed += DT_CTRL
    self.output = self.start + min(self.elapsed / DT_MDL, 1.0) * (self.target - self.start)
    return self.output
