"""PTM Controller timing: the model-side prediction delay and the controller's command-delay line.

Carried from dev-111826 `nrdr/features/lateral/yaw_control_timing.py` (66 L). The source's own module
docstring is kept verbatim below, because it is the rule this port has to honour:

Prediction schedules and command delays are firmware-calibration data, not user tuning.
Legacy NrdrYawCommandDelayLow/High values remain stored but are no longer consumed.

Copied first, then narrowed to one car, which is why every name and signature is the source's and only the
*contents* of the two lookup tables moved (ledger §1a, same order as `vfn_eps_core.py`):

* `DELAY_SCHEDULE_BP` / `DELAY_SCHEDULE_V` are the Clarity's measured row, verbatim. The source's five other
  rows are dropped together with the constants that held them (`TEG_A010_DELAY_SCHEDULE_V`,
  `CIVIC_C020_DELAY_SCHEDULE_V`, and the inline RDX row at `:19`), so `_PREDICTION_SCHEDULE_V` is empty
  here: in both trees the Clarity *is* the default table, and the lookup only ever answered for another car.
* `COMMAND_DELAY_ENDPOINTS` keeps its name and keeps the Clarity's row `(0.20, 0.10)`; the eleven other
  images' rows are dropped. A calibration this port does not have raises `KeyError` here on purpose — this
  port has one measured row, and inventing a nearby car's is how a port silently changes a car's handling.
* `command_delay`'s first argument is accepted and ignored exactly as the source wrote it. The retired
  `NrdrYawCommandDelayLow/High` (this car stores 0.145 / 0.125) must not reach the calibration, and
  `analysis/lateral_timing_probe.py` replays the source's test that proves settings cannot move it.

Nothing here is wired: the prediction schedule sets `modeld`'s `lat_delay` only for an admitted profile
(Task 10), and the delay line belongs to `latcontrol_fw` (Task 19). Until those exist this file changes no
number on the road (ISC-3). Note what the source does with the delay line once it *is* wired:
`latcontrol_fw._command_delay` ramps its scale to zero whenever the model's source is `plan`
(`latcontrol_fw.py:86-92`, `model_source.PLAN`), and this tree's models all read the plan — so the scale
lands at zero here. `ModelActionRamp` and `lateral_source` exist to make that decision visible in a log
rather than guessed at; the source's own test of the rule is replayed in both trees by
`analysis/lateral_timing_probe.py`.
"""
from collections import deque
import math

import numpy as np

DELAY_SCHEDULE_BP = (3.5, 7.0, 12.0, 20.0, 30.0)
DELAY_SCHEDULE_V = (0.15, 0.08, 0.10, 0.20, 0.30)
_PREDICTION_SCHEDULE_V = {}
COMMAND_DELAY_BP = (10.0, 15.0)
COMMAND_DELAY_ENDPOINTS = {
  "clarity_a020": (0.20, 0.10),
}
MAX_COMMAND_DELAY = 0.30  # buffer capacity; not an adjustable timing limit


def clarity_lateral_delay(speed: float) -> float:
  return float(np.interp(speed, DELAY_SCHEDULE_BP, DELAY_SCHEDULE_V))


def prediction_delay_schedule(profile):
  if profile is None or not profile.prediction_schedule:
    return None
  return DELAY_SCHEDULE_BP, _PREDICTION_SCHEDULE_V.get(profile.calibration, DELAY_SCHEDULE_V)


def command_delay(settings, speed: float, *, calibration: str = "clarity_a020") -> float:
  """Donor's fixed per-car speed interpolation; saved settings cannot alter the calibration."""
  return float(np.interp(speed, COMMAND_DELAY_BP, COMMAND_DELAY_ENDPOINTS[calibration]))


class CommandDelay:
  """Fixed-rate delay line, linearly interpolated between samples. Fills while inactive so
  engagement starts from the delayed history rather than a step."""

  def __init__(self, dt: float, max_delay: float = MAX_COMMAND_DELAY):
    self.dt = dt
    self.buf: deque[float] = deque(maxlen=int(math.ceil(max_delay / dt)) + 2)

  def update(self, value: float, delay: float) -> float:
    self.buf.append(float(value))
    if delay <= 0.0:
      return float(value)
    steps = delay / self.dt
    i = int(steps)
    frac = steps - i
    n = len(self.buf)
    newer = self.buf[max(n - 1 - i, 0)]
    older = self.buf[max(n - 2 - i, 0)]
    return newer + frac * (older - newer)
