"""Honda comfort LPF, applied before publishing the steering torque request.

Carried from dev-111826 `nrdr/features/lateral/torque_output_filter.py` (byte-identical; it imports nothing from
either fork, only `dataclasses` and `math`).

VFN (JamesL787/openpilot 662933847fcad19625dcfb8a6549331222087155) moved
this filter upstream of carControl so its lag is not reported as safety limiting.
NRDR applies it after the PID/blend and live-edit transition for all Honda torque
controllers. Driver override and the optional car-side rate limiter remain later.

Two things to know before wiring this in this tree (Task 10/19, not this file): the `live` argument is
duck-typed on the source's live-torque-edit parameters (`live.torque_lpf_enabled`, `live.lpf_tau_low /
…_standard / …_highway`), and none of those keys is registered in this port (ledger §8). The parameter is kept
as the source wrote it rather than being replaced by three numbers, so the day a live-tuning snapshot exists it
can be passed straight in; until then a caller has to supply an object with those attributes or not call this.
"""

from dataclasses import dataclass
import math


MPH_TO_MS = 0.44704


def torque_lpf_tau(v_ego: float, low_tau: float, standard_tau: float, highway_tau: float) -> float:
  if v_ego < 25.0 * MPH_TO_MS:
    return low_tau
  if v_ego < 50.0 * MPH_TO_MS:
    return standard_tau
  return highway_tau


@dataclass
class HondaTorqueOutputFilter:
  output: float = 0.0

  def update(self, torque: float, active: bool, v_ego: float, live, dt: float) -> float:
    if not active or not math.isfinite(torque):
      self.output = 0.0
      return 0.0
    if live.torque_lpf_enabled:
      tau = torque_lpf_tau(v_ego, live.lpf_tau_low, live.lpf_tau_standard, live.lpf_tau_highway)
      alpha = dt / (tau + dt)
      self.output = alpha * torque + (1.0 - alpha) * self.output
    else:
      # Track the unfiltered command so re-enabling does not revive stale state.
      self.output = torque
    return self.output
