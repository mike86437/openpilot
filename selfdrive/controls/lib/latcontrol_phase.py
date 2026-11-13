"""Which half of a lane change the car is in: turning into it, or unwinding out of it.

A copy of the NRDR fork's `openpilot/sunnypilot/nrdr/phase_detector.py`, which is one of the three things
that make that fork's Honda Clarity quiet (the other two are the torque low-pass in the carcontroller and the
modified override threshold). The sign of `angle * angle_delta` says whether the commanded angle's magnitude
is growing or falling: positive while the car is turning in, negative while it is coming back. The latch is
the point of it - `angle * angle_delta` passes through zero exactly when the commanded angle peaks, which is
the instant the overshoot begins, and an un-latched sign flickers for the few frames around it.

Kept free of imports, including from openpilot, so the control loop is not needed to test it.
"""

PHASE_SWITCH_MIN_SPEED = 0.5 * 0.44704  # 0.5 mph, in m/s: below this the angle signal is mostly sensor noise


def phase_with_latch(angle: float, angle_delta: float, v_ego: float, direction: float) -> tuple[float, float]:
  """Returns (signed phase, latched direction). Negative phase means the commanded angle's magnitude is
  falling - the car is unwinding from a turn, which is when an integrator wound up during the turn keeps
  pushing in the direction it was wound up, against the direction the car now needs."""
  phase = angle * angle_delta
  if phase != 0.0 and (v_ego > PHASE_SWITCH_MIN_SPEED or direction == 0.0):
    direction = 1.0 if phase > 0.0 else -1.0
  return abs(phase) * direction, direction
