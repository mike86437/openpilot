"""Admission for the measured-EPS lateral model: which car this controller is for, and what it is calibrated to.

Ported from dev-111826 `nrdr/features/lateral/controller_selection.py` (130 L) as the gate the rest of the lateral
port stands on (plan §S5, ledger §2 D1/D6). Copied first, then narrowed to one car, in the same order as every other
module in this directory: every name, signature and condition the source has is here unchanged except where a target
fact replaces it, and what is missing is listed below with the reason.

What the admission *is*: a `(carFingerprint, normalized EPS firmware)` lookup, and four conditions on top of it —
the car's EPS is a modified one, this tree has a measured Table A for exactly that fingerprint+firmware pair, the
CarParams asks for a PID-shaped lateral tune, and someone has asked for this controller. `required_rwd` is the part
admission cannot prove: the corrected-PTM build a calibration models, named by a RWD SHA-256 prefix. Older builds
report the same EPS version, so it is reported, never checked. **The Clarity's `required_rwd` is empty** — which is
walk §8.2's open question, and the reason `provisional=False` here does not mean "the flashed build is known".

Four things this port does not carry, each checked rather than assumed:

  * the other twelve profiles and `rdx_identity` (`RDX_CARS`, `confirmed_rdx`, `:96-112`, `:84-86`): the Clarity entry
    is the only one this branch is for (plan §4), so `_firmware_family` has no RDX identity branch and no name in this
    file names another car;
  * `PTM_EPS_REVISIONS` (`:87-89`): in the source that map holds `HONDA_RIDGELINE` and `HONDA_ODYSSEY` only
    (`opendbc/sunnypilot/car/honda/values_ext.py:14-17`), so its "reported version must be the revision this
    calibration models" gate has never applied to a Clarity. Not ported — an inert condition is not carried across a
    tree boundary for appearances. `analysis/lateral_admission_probe.py` prints the lookup that proves it;
  * storage and messaging at import time. `cereal` and `lateral_settings` are imported inside
    `firmware_controller_profile_for_model` - the once-per-startup resolver the source's `modeld.py` calls - so a
    probe that only evaluates admission needs neither `capnp` nor `params_pyx`;
  * `CarParamsSP` / `HondaFlagsSP` (D1): this tree's carrier of "this EPS has been modified" is
    `FrogPilotCarParams.flags & HondaFrogPilotFlags.EPS_MODIFIED`, written from the car's own `carFw` in
    `CarInterfaceBase.get_frogpilot_params`'s Honda branch (ledger §2 D1, verified V11). The second argument of
    `firmware_controller_profile` is therefore an `FrogPilotCarParams` where the source's is a `CarParamsSP`, and the
    bit value differs because the two enums are different enums (`2` there, `1` here). What must match is the decision.

The `NrdrLateralController` read goes through `frogpilot/common/lateral_settings.py` like `steer_ratio_tuning.py`'s
does, and the import is typing-only so this module imports without `params_pyx`: unset, out of range or unparseable is
`0`, which is this tree's own stock lateral controller (ISC-3). Nothing in this file enables anything: admission is a
fact a caller acts on, and the only reader that changes a controller is `controlsd` (Task 19). No Params, no capnp and
no cloudlog at import.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from opendbc.car.honda.values import HondaFrogPilotFlags

from openpilot.frogpilot.controls.lateral.honda_vgr import get_honda_vgr_profile, normalize_honda_eps_firmware

if TYPE_CHECKING:
  from openpilot.frogpilot.common.lateral_settings import LateralSettings

# The source's profile record, unchanged. `prediction_schedule` is what lets modeld take `lat_delay` from the
# calibration (ledger §2 D4); `required_rwd` is documentation the control path never reads.
@dataclass(frozen=True)
class FirmwareControllerProfile:
  name: str
  calibration: str
  prediction_schedule: bool = False
  provisional: bool = False
  # The corrected PTM build the calibration models (RWD SHA-256 prefix). Older builds report the same EPS version,
  # so admission cannot check it; it is shown and logged so the owner can. Empty for the Clarity: its family is
  # admitted, its flashed build is not identified by any version string (vfn_eps_core.py's own note).
  required_rwd: str = ""


CLARITY_PROFILE = FirmwareControllerProfile("Clarity A020", "clarity_a020", prediction_schedule=True)
_PROFILES = {
  ("HONDA_CLARITY", "39990-TRW-A020"): CLARITY_PROFILE,
}


def _firmware_family(CP) -> FirmwareControllerProfile | None:
  """The profile this car's own reported EPS firmware selects, or None. `normalize_honda_eps_firmware` is what makes
  the car's `39990-TRW,A020` answer the table registered as `39990-TRW-A020` (honda_vgr.py)."""
  if CP is None or str(getattr(CP, "brand", "")) != "honda":
    return None
  for firmware in getattr(CP, "carFw", ()):
    if firmware.ecu == "eps":
      profile = _PROFILES.get((str(CP.carFingerprint), normalize_honda_eps_firmware(firmware.fwVersion)))
      if profile is not None:
        return profile
  return None


def firmware_controller_profile(CP, FPCP) -> FirmwareControllerProfile | None:
  """The four-condition admission, as the source wrote it, with this tree's carrier for the EPS-modified fact.

  `FPCP` is `cereal.custom.FrogPilotCarParams` where the source takes `CarParamsSP`: this tree has no CarParamsSP
  (D1), and `flags & EPS_MODIFIED` is the same fact from the same `carFw`. A `lateralTuning.which()` other than
  `pid` means the CarParams is not asking for the controller this profile calibrates, so it is a refusal, not a
  fallback.
  """
  profile = _firmware_family(CP)
  if profile is not None and getattr(FPCP, "flags", 0) & int(HondaFrogPilotFlags.EPS_MODIFIED) and \
     get_honda_vgr_profile(CP) is not None and CP.lateralTuning.which() == "pid":
    return profile
  return None


def yaw_controller_available(CP, FPCP) -> bool:
  # Keep the legacy wire/call-site name; this controller is not a live yaw loop.
  return firmware_controller_profile(CP, FPCP) is not None


def _controller_state(settings: LateralSettings | Any) -> int:
  """The one parameter this module reads, read the way this tree reads parameters. Anything that is not the settings
  snapshot - a missing key, a value outside the two states - is 0, i.e. this tree's own lateral controller. The
  source compares strings straight out of Params (`str(params.get(...)) in ("1", "b'1'", ...)`); the keys are
  registered INT here (common/params_keys.h), so the typed read is the equivalent, not a narrowing."""
  try:
    return int(settings.int_of("NrdrLateralController"))
  except (AttributeError, TypeError, ValueError):
    return 0


def firmware_controller_selected(settings, CP, FPCP) -> bool:
  """Use the admitted selection, not a stale selector left over from another car. 1 and 2 are the source's two
  states (it matches them as strings out of Params); this tree registers the key INT, so they compare as ints."""
  return _controller_state(settings) in (1, 2) and yaw_controller_available(CP, FPCP)


def firmware_controller_testing_selected(settings, CP, FPCP) -> bool:
  """Testing is an explicit opt-in with the same firmware admission as PTM."""
  return _controller_state(settings) == 2 and yaw_controller_available(CP, FPCP)


def firmware_controller_profile_for_model(params, CP) -> FirmwareControllerProfile | None:
  """Resolve once per drive, without waiting on Honda-only data for other cars.

  Same shape as the source's model-side resolver, including the deferred imports and the blocking read: the parameter
  it blocks on is this tree's `FrogPilotCarParams` (`card.py:203-204` writes it, `controlsd.py:41` reads it back)
  where the source blocks on `CarParamsSP`. `params` is a `Params` object, as in the source; this is the one place
  here touches storage, and it is the once-per-startup call the source's `modeld.py` makes, not a control frame — the
  per-frame read stays a `LateralSettings` snapshot handed in by the caller (D3).
  """
  from openpilot.cereal import custom, messaging
  from openpilot.frogpilot.common.lateral_settings import LateralSettings
  settings = params if hasattr(params, "int_of") else LateralSettings.snapshot(params)
  if _firmware_family(CP) is None or _controller_state(settings) not in (1, 2):
    return None
  FPCP = messaging.log_from_bytes(params.get("FrogPilotCarParams", block=True), custom.FrogPilotCarParams)
  return firmware_controller_profile(CP, FPCP)


def firmware_controller_for_model(params, CP) -> bool:
  return firmware_controller_profile_for_model(params, CP) is not None


__all__ = (
  "CLARITY_PROFILE",
  "FirmwareControllerProfile",
  "firmware_controller_for_model",
  "firmware_controller_profile",
  "firmware_controller_profile_for_model",
  "firmware_controller_selected",
  "firmware_controller_testing_selected",
  "yaw_controller_available",
)
