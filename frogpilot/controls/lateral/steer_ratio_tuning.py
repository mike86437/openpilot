"""Which steer-ratio geometry this car's lateral controller runs on, and the record of what was asked for.

Ported from dev-111826 `nrdr/features/lateral/steer_ratio_tuning.py` (476 L) as the decision layer on top of
Task 14's tables (`honda_vgr.py`, `honda_rack_map.py`). What carries across is the part this car's controller
uses: the mode enum and its labels, `SteerRatioSelection` with both directions (angle → curvature,
curvature → angle) and its per-frame `VM.sR`, and `SteerRatioModeLatch` with `rejected_reason`. What does not
is everything that belongs to a second car, a second geometry source, or an editing UI. See README.md.

Modes, and what selecting each one does in THIS tree (the numbers are the source's, unchanged):

  0  MANUAL    Stock. Nothing here touches a number the target's own controller uses: `effective_mode` is None,
               `ratio_at` answers `CP.steerRatio`, and `VehicleModel` behaves exactly as `controlsd.py` runs it
               today. 0 is this tree's registered default (`common/params_keys.h`, `STOCK_DEFAULTS`), so a car
               that never enables the port is unchanged. **This is where this port deliberately differs from the
               source:** `resolve_steer_ratio_selection` there (`:367-368`) turns 0 and 2 into FIRMWARE whenever
               a firmware profile exists, because that fork's default is 3. Here the default is 0 and 0 means
               stock (ISC-3, plan §1 rule 1). A comparable drive states mode 3 explicitly, in both trees.
  1  COMMA     `CP.steerRatio` only, with no measured map, and the label the report prints. Numerically the
               same geometry as 0 for this car - that is the point: it is how a drive is shown against stock.
  2  NRDR_RAW  Not ported. The measured-angle curve (`RawSteerRatioProfile`, `CLARITY_RAW_STEER_RATIO`) is a
               second geometry source and its parameter is not registered here; selecting 2 records
               `unavailable_reason` and keeps the car's own ratio.
  3  FIRMWARE  The measured path: `CLARITY_TRW_A020_RACK` through `RackMapGeometry`, i.e. Table A (the EPS's
               own angle map) on the rack map measured against this car's VSA yaw - used in both directions,
               and its slip factor used by the two paths that know the speed. Matched on the car's fingerprint
               plus its reported EPS firmware, so it needs no car-specific helper: a Clarity reporting a rack
               nobody measured answers `effective_mode = None` and keeps stock geometry.

Config is read through `frogpilot/common/lateral_settings.py` and nowhere else: `settings.int_of(
"NrdrSteerRatioMode")`. The `LateralSettings` import below is typing-only, so the geometry can be exercised by
an offline probe without `params_pyx`; passing anything else in yields mode 0, i.e. stock, never a wrong
geometry. `NrdrLateralController` - which controller consumes this selection - is not read here (Task 10).

The EPS-modified fact of this car is `FrogPilotCarParams.flags & HondaFrogPilotFlags.EPS_MODIFIED`, not a
helper: no `clarity_mod_eps` exists in this tree and none is added.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import math
from typing import TYPE_CHECKING, Any

from openpilot.frogpilot.controls.lateral.honda_rack_map import RackMapGeometry, rack_map_geometry
from openpilot.frogpilot.controls.lateral.honda_vgr import HondaVgrProfile, get_honda_vgr_profile

if TYPE_CHECKING:
  from openpilot.frogpilot.common.lateral_settings import LateralSettings

# Fallback ratio when a CarParams carries none, kept as the source's own number (`MANUAL_CENTER_DEFAULT`,
# `steer_ratio_tuning.py:16`) so a degenerate CarParams cannot make this tree answer something the source
# would not have answered. The manual mode that number belonged to is not ported.
CP_RATIO_FALLBACK = 15.38


class SteerRatioMode(IntEnum):
  MANUAL = 0
  COMMA = 1
  NRDR_RAW = 2
  FIRMWARE = 3


def steer_ratio_mode_label(mode: SteerRatioMode) -> str:
  return {
    SteerRatioMode.MANUAL: "Manual override",
    SteerRatioMode.COMMA: "Comma’s Learner (Legacy)",
    SteerRatioMode.NRDR_RAW: "NRDR measured-angle curve",
    SteerRatioMode.FIRMWARE: "PTM (Auto)",
  }[mode]


@dataclass(frozen=True)
class SteerRatioSelection:
  """One resolved geometry for one control frame. Immutable: the control loop builds a new one instead of
  mutating this, which is what makes a frame's geometry reproducible from the log that describes it."""
  requested_mode: SteerRatioMode
  effective_mode: SteerRatioMode | None
  fingerprint: str
  cp_ratio: float
  # Never True in this tree: the hybrid composition of two geometry sources (`NrdrSteerRatioHybrid`,
  # `hybrid_steer_ratio.py`) is not ported. Kept as the field the source's latch keys its refusal on, so the
  # latch below is the source's code rather than an approximation of it.
  hybrid_requested: bool = False
  # Table A on this car's measured rack map, or Table A alone where nobody has measured the rack.
  firmware_profile: HondaVgrProfile | RackMapGeometry | None = None
  unavailable_reason: str = ""

  @property
  def available(self) -> bool:
    return self.effective_mode is not None

  @property
  def requested_label(self) -> str:
    return "Hybrid steer ratio" if self.hybrid_requested else steer_ratio_mode_label(self.requested_mode)

  @property
  def effective_label(self) -> str:
    return "Stock car ratio (safe fallback)" if self.effective_mode is None else steer_ratio_mode_label(self.effective_mode)

  @property
  def firmware_vgr_selected(self) -> bool:
    return self.effective_mode is SteerRatioMode.FIRMWARE and self.firmware_profile is not None

  @property
  def rack_map(self) -> RackMapGeometry | None:
    """The car's rack map, when Firmware alone is the geometry: then the control paths use its slip factor too."""
    if self.firmware_vgr_selected and isinstance(self.firmware_profile, RackMapGeometry):
      return self.firmware_profile
    return None

  def ratio_at(self, measured_angle_deg: float, live_comma_ratio: float | None = None) -> float:
    if self.effective_mode is SteerRatioMode.COMMA:
      return _safe_positive_ratio(live_comma_ratio, self.cp_ratio)
    if self.effective_mode is SteerRatioMode.FIRMWARE and isinstance(self.firmware_profile, RackMapGeometry):
      # The rack map's ratio is by angle, and it is only meaningful together with the wheelbase the fit used;
      # it is applied through the map itself (`measured_curvature` / `desired_angle_no_offset`), never folded
      # into a single number here.
      return self.cp_ratio
    return self.cp_ratio

  def linearize_measured_angle(self, measured_angle_deg: float) -> float:
    """Physical wheel angle → the linear angle at `cp_ratio` that VehicleModel runs."""
    if self.firmware_vgr_selected:
      return self.firmware_profile.physical_to_linear(measured_angle_deg)
    return measured_angle_deg

  def physicalize_desired_angle(self, linear_angle_deg: float) -> float:
    if self.firmware_vgr_selected:
      return self.firmware_profile.linear_to_physical(linear_angle_deg)
    return linear_angle_deg

  def configure_vehicle_model(self, VM, measured_angle_deg: float) -> float:
    """Set `VM.sR` for the angle this frame is actually at, as the source does per frame."""
    live_comma_ratio = VM.sR if self.effective_mode is SteerRatioMode.COMMA else None
    VM.sR = self.ratio_at(measured_angle_deg, live_comma_ratio)
    return VM.sR

  def measured_curvature(self, VM, measured_angle_deg: float, speed: float, roll: float,
                         angle_offset_deg: float = 0.0) -> float:
    """What the measured wheel angle means as curvature, in VehicleModel.calc_curvature's sign."""
    self.configure_vehicle_model(VM, measured_angle_deg)
    if (rack_map := self.rack_map) is not None:
      return -rack_map.curvature_from_angle(measured_angle_deg - angle_offset_deg, speed, roll)
    linear_angle = self.linearize_measured_angle(measured_angle_deg - angle_offset_deg)
    return -VM.calc_curvature(math.radians(linear_angle), speed, roll)

  def desired_angle_no_offset(self, VM, measured_angle_deg: float, speed: float, roll: float,
                              desired_curvature: float) -> float:
    """The physical wheel angle that produces `desired_curvature`, i.e. what the actuator is commanded to."""
    self.configure_vehicle_model(VM, measured_angle_deg)
    if (rack_map := self.rack_map) is not None:
      return rack_map.angle_from_curvature(-desired_curvature, speed, roll)
    linear_angle = math.degrees(VM.get_steer_from_curvature(-desired_curvature, speed, roll))
    return self.physicalize_desired_angle(linear_angle)


@dataclass
class SteerRatioModeLatch:
  """Capture one complete geometry selection for the current control frame.

  The candidate is resolved from the parameter as it is now; `update` decides whether it replaces what is
  running. `rejected_reason` is the printable record of a refusal - the same tuple the source's controlsd hook
  records outside the realtime loop (`nrdr/hooks/controlsd.py:104-119`) - so a port drive can be audited
  against the source drive. In this tree no candidate can request a composed geometry (`hybrid_requested` is
  always False), so a refusal instead shows up as `effective_mode = None` plus `unavailable_reason`, which the
  report carries as `effective_label`. The line below is the source's, unchanged."""
  selection: SteerRatioSelection
  pending: SteerRatioSelection | None = field(init=False, default=None)
  rejected_reason: str = field(init=False, default="")

  def update(self, candidate: SteerRatioSelection, active: bool) -> SteerRatioSelection:
    self.rejected_reason = candidate.unavailable_reason if candidate.hybrid_requested and not candidate.available else ""
    if self.rejected_reason and active:
      # Invalid live edits must not switch an engaged controller to an unrelated
      # geometry. Startup's existing stock selection remains the safe baseline.
      return self.selection
    self.selection = candidate
    self.pending = None
    return self.selection


def _safe_positive_ratio(value: Any, default: float) -> float:
  try:
    result = float(value)
  except (TypeError, ValueError):
    result = float(default)
  return result if math.isfinite(result) and result >= 0.1 else max(float(default), 0.1)


def _mode_value(settings: LateralSettings | Any) -> SteerRatioMode:
  """The one parameter this module reads, read the way this tree reads parameters. Anything that is not the
  settings snapshot - a missing key, a value outside the enum - resolves to MANUAL, i.e. stock geometry."""
  try:
    return SteerRatioMode(int(settings.int_of("NrdrSteerRatioMode")))
  except (AttributeError, TypeError, ValueError):
    return SteerRatioMode.MANUAL


def resolve_steer_ratio_selection(CP, settings: LateralSettings | Any, *, ptm_baseline: bool = False) -> SteerRatioSelection:
  """Resolve the geometry for one frame. No storage access, no state: the same CarParams and settings snapshot
  give the same selection, which is what lets a probe compare this tree against the source one."""
  fingerprint = str(getattr(CP, "carFingerprint", ""))
  cp_ratio = _safe_positive_ratio(getattr(CP, "steerRatio", CP_RATIO_FALLBACK), CP_RATIO_FALLBACK)
  mode = _mode_value(settings)

  # A car with a rack map anchors Table A to it instead of to CP's ratio. In this tree the only map is the
  # Clarity's measured one, so both lookups answer together or not at all.
  firmware_profile = get_honda_vgr_profile(CP)
  firmware_profile = rack_map_geometry(CP, firmware_profile, cp_ratio, ptm_baseline=ptm_baseline) or firmware_profile

  # Accepted modes keep the parameter's own number; a refused one sets effective_mode to None and says why.
  # COMMA is accepted without a live learner ratio: for this car that is CP.steerRatio, which is what the
  # target's controller already uses - the mode exists to be *reported*, not to change a number.
  effective_mode: SteerRatioMode | None = mode
  unavailable_reason = ""
  if mode is SteerRatioMode.MANUAL:
    effective_mode = None                                  # unset parameter = this tree's stock behaviour
  elif mode is SteerRatioMode.NRDR_RAW:
    effective_mode, unavailable_reason = None, ("NRDR_RAW measured-angle curve is not ported in this tree, "
                                                "keeping the car's own ratio")
  elif mode is SteerRatioMode.FIRMWARE and firmware_profile is None:
    effective_mode = None
    unavailable_reason = f"No exact recognized EPS firmware profile exists for {fingerprint or 'this car'}"

  return SteerRatioSelection(
    requested_mode=mode,
    effective_mode=effective_mode,
    fingerprint=fingerprint,
    cp_ratio=cp_ratio,
    firmware_profile=firmware_profile,
    unavailable_reason=unavailable_reason,
  )


def stock_steer_ratio_selection(CP) -> SteerRatioSelection:
  """Safe controller-construction default until controlsd supplies its latched selection. Identical to what
  this tree's own controller does today, so a half-initialised controller cannot steer on a geometry nobody
  asked for."""
  resolved = resolve_steer_ratio_selection(CP, None)
  return SteerRatioSelection(
    requested_mode=SteerRatioMode.MANUAL,
    effective_mode=None,
    fingerprint=resolved.fingerprint,
    cp_ratio=resolved.cp_ratio,
    firmware_profile=resolved.firmware_profile,
    unavailable_reason="controlsd has not supplied a steer-ratio selection yet",
  )


__all__ = (
  "CP_RATIO_FALLBACK",
  "SteerRatioMode",
  "SteerRatioModeLatch",
  "SteerRatioSelection",
  "resolve_steer_ratio_selection",
  "stock_steer_ratio_selection",
  "steer_ratio_mode_label",
)
