"""Honda EPS position maps (Table A), Clarity only.

Ported verbatim from dev-111826 `nrdr/features/lateral/honda_vgr.py` as the geometry data layer of the lateral
port (analysis/PORT-LATERAL-LEDGER.md §1a, plan §1 rule 3). Two deliberate narrowings:

  * the only profile here is the car this branch is for - "Clarity TRW-A020", the measured Table A of its
    39990-TRW,A020 EPS. Civic / Insight / CR-V / Ridgeline / Odyssey profiles and the RDX identity path are
    dropped (plan §4), so nothing in this tree can reach a rack that has not been measured on this car;
  * imports are this tree's own. There is no `sunnypilot`, no `CarParamsSP`, no `rdx_identity`.

Nothing here reads Params or decides behaviour: it is tables plus the interpolation on them. The consumer, and the
parameter that decides whether any of it is used, is `frogpilot/controls/lateral/steer_ratio_tuning.py`.
"""
from bisect import bisect_right
from dataclasses import dataclass, field
from functools import lru_cache
import math

import numpy as np


__all__ = (
  "HONDA_VGR_PROFILES",
  "Q14",
  "RAW_UNITS_PER_DEGREE",
  "HondaVgrProfile",
  "get_honda_vgr_profile",
  "normalize_honda_eps_firmware",
)


Q14 = 1 << 14
RAW_UNITS_PER_DEGREE = 10.0


@lru_cache(maxsize=16)
def ptm_inverse(profile):
  """Biscuit-Labs 45e5b91fae sampled angle inverse for matched PTM calibration/output."""
  if profile.position_y == (Q14, Q14):
    return profile.physical_knots, profile.physical_knots
  linear_bp, angle_bp = [], []
  for x0, x1, y0, y1 in zip(profile.position_x, profile.position_x[1:],
                            profile.position_y, profile.position_y[1:], strict=False):
    steps = max(1, math.ceil((x1 - x0) / 20))
    for step in range(steps):
      fraction = step / steps
      raw, divisor = x0 + (x1 - x0) * fraction, y0 + (y1 - y0) * fraction
      linear_bp.append(raw * Q14 / profile.center_divisor / RAW_UNITS_PER_DEGREE)
      angle_bp.append(raw * Q14 / divisor / RAW_UNITS_PER_DEGREE)
  linear_bp.append(profile.position_x[-1] * Q14 / profile.center_divisor / RAW_UNITS_PER_DEGREE)
  angle_bp.append(profile.position_x[-1] * Q14 / profile.position_y[-1] / RAW_UNITS_PER_DEGREE)
  return tuple(linear_bp), tuple(angle_bp)


@dataclass(frozen=True)
class HondaVgrProfile:
  name: str
  fingerprints: tuple[str, ...]
  firmware: tuple[str, ...]
  position_x: tuple[int, ...]
  position_y: tuple[int, ...]
  physical_knots: tuple[float, ...] = field(init=False)

  def __post_init__(self) -> None:
    if len(self.position_x) != len(self.position_y) or len(self.position_x) < 2:
      raise ValueError("Honda VGR position tables must contain matching X/Y values")
    if self.position_x[0] != 0 or any(b <= a for a, b in zip(self.position_x, self.position_x[1:], strict=False)):
      raise ValueError("Honda VGR position breakpoints must start at zero and increase")
    if any(value <= 0 for value in self.position_y):
      raise ValueError("Honda VGR position divisors must be positive")

    physical = tuple(raw * Q14 / (divisor * RAW_UNITS_PER_DEGREE)
                     for raw, divisor in zip(self.position_x, self.position_y, strict=True))
    if any(b <= a for a, b in zip(physical, physical[1:], strict=False)):
      raise ValueError("Honda VGR physical-angle map must increase")
    object.__setattr__(self, "physical_knots", physical)

  @property
  def center_divisor(self) -> int:
    return self.position_y[0]

  @property
  def tail_scale(self) -> float:
    return self.center_divisor / self.position_y[-1]

  def linear_to_physical(self, angle_deg: float) -> float:
    raw = abs(angle_deg) * self.center_divisor * RAW_UNITS_PER_DEGREE / Q14
    divisor = float(np.interp(raw, self.position_x, self.position_y))
    physical = raw * Q14 / (divisor * RAW_UNITS_PER_DEGREE)
    return math.copysign(physical, angle_deg)

  def linear_to_physical_slope(self, angle_deg: float) -> float:
    """Return d(physical angle) / d(linear angle) for the active table segment."""
    raw = abs(angle_deg) * self.center_divisor * RAW_UNITS_PER_DEGREE / Q14
    if raw >= self.position_x[-1]:
      return self.tail_scale

    index = min(bisect_right(self.position_x, raw) - 1, len(self.position_x) - 2)
    x0, x1 = self.position_x[index:index + 2]
    y0, y1 = self.position_y[index:index + 2]
    divisor_slope = (y1 - y0) / (x1 - x0)
    divisor = y0 + divisor_slope * (raw - x0)
    divisor_intercept = y0 - divisor_slope * x0
    return self.center_divisor * divisor_intercept / divisor ** 2

  def physical_to_linear(self, angle_deg: float) -> float:
    physical = abs(angle_deg)
    if physical == 0.0:
      return 0.0

    if physical >= self.physical_knots[-1]:
      raw = physical * self.position_y[-1] * RAW_UNITS_PER_DEGREE / Q14
    else:
      index = min(bisect_right(self.physical_knots, physical) - 1, len(self.position_x) - 2)
      x0, x1 = self.position_x[index:index + 2]
      y0, y1 = self.position_y[index:index + 2]
      slope = (y1 - y0) / (x1 - x0)
      intercept = y0 - slope * x0
      raw = physical * RAW_UNITS_PER_DEGREE * intercept / (Q14 - physical * RAW_UNITS_PER_DEGREE * slope)

    linear = raw * Q14 / (self.center_divisor * RAW_UNITS_PER_DEGREE)
    return math.copysign(linear, angle_deg)

# Table-A position maps extracted and traced by vote_for_nobody; Table B is the independent EPS rate path.
_TRW_A020_X = (0, 40, 80, 119, 158, 198, 237, 277, 317, 398, 604, 820, 1047, 1164, 1210,
               1257, 1305, 1352, 1398, 1447, 1493, 1540, 1588, 1634, 1989, 2344, 2700, 3056, 3413, 5020)
_TRW_A020_Y = (16384, 16174, 16173, 16247, 16179, 16220, 16180, 16209, 16231, 16303, 16506, 16812,
               17177, 17352, 17411, 17473, 17538, 17600, 17644, 17705, 17749, 17792, 17843, 17885,
               18130, 18303, 18439, 18547, 18645, 18952)

HONDA_VGR_PROFILES = (
  HondaVgrProfile("Clarity TRW-A020", ("HONDA_CLARITY",), ("39990-TRW-A020",), _TRW_A020_X, _TRW_A020_Y),
)

_PROFILE_BY_CAR_FIRMWARE = {
  ("HONDA_CLARITY", "39990-TRW-A020"): HONDA_VGR_PROFILES[0],
}


def normalize_honda_eps_firmware(version) -> str:
  if not isinstance(version, (bytes, str)):
    try:
      version = bytes(version)
    except (TypeError, ValueError):
      pass
  if isinstance(version, bytes):
    version = version.split(b"\0", 1)[0].decode("ascii", errors="ignore")
  return str(version).split("\0", 1)[0].strip().replace(",", "-")


def get_honda_vgr_profile(CP) -> HondaVgrProfile | None:
  """The measured Table A of this car's EPS, or None. Matched on the car's own fingerprint plus its reported
  EPS firmware - `normalize_honda_eps_firmware` is what makes the car's `39990-TRW,A020` answer the table
  registered as `39990-TRW-A020`. No parameter is involved: a car that does not report this EPS gets None, and
  the caller keeps the geometry it already had."""
  if str(getattr(CP, "brand", "")).lower() != "honda":
    return None
  fingerprint = str(getattr(CP, "carFingerprint", ""))
  for firmware in getattr(CP, "carFw", ()):
    if firmware.ecu != "eps":
      continue
    profile = _PROFILE_BY_CAR_FIRMWARE.get((fingerprint, normalize_honda_eps_firmware(firmware.fwVersion)))
    if profile is not None:
      return profile
  return None
