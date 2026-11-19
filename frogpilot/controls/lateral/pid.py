"""Feedforward-scaled PID, carried from dev-111826 `nrdr/features/lateral/pid.py` (15 L).

One deliberate difference from the source, and it is not cosmetic: the source's signature annotates the gains as
`Gain`, an alias its `common/pid.py:2` exports. This tree's `common/pid.py` has no such name — it imports
`numbers.Number` and wraps a scalar gain as `[[0], [k]]` where the source wraps it as `([0], [k])`
(`common/pid.py:5-14` against dev-111826's `:7-10`). `PIDController.update`, its anti-windup and its `k_i`
property are otherwise identical in the two trees, which is why the class body below is unchanged: the same
gains, the same limits, the same `rate`, `feedforward` multiplied by `k_f` on the way to `super().update`.
The annotations are dropped rather than replaced by a local alias, because inventing a type name this tree does
not have would make the port look like it was written against a different library than the one it runs on.

Nothing here is used yet: the consumer is `vfn_eps_core` (Task 17) and, behind it, the controller Task 19 ports.
"""
from openpilot.common.pid import PIDController


__all__ = ("FeedforwardPIDController",)


class FeedforwardPIDController(PIDController):
  def __init__(self, k_p, k_i, k_d=0.0, k_f: float = 1.0, pos_limit: float = 1e308, neg_limit: float = -1e308,
               rate: float = 100):
    super().__init__(k_p, k_i, k_d, pos_limit=pos_limit, neg_limit=neg_limit, rate=rate)
    self.k_f = k_f

  def update(self, error, error_rate=0.0, speed=0.0, feedforward=0.0, freeze_integrator=False):
    return super().update(error, error_rate=error_rate, speed=speed, feedforward=feedforward * self.k_f,
                          freeze_integrator=freeze_integrator)
