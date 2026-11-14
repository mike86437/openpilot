import numpy as np
from numbers import Number

class PIDController:
  def __init__(self, k_p, k_i, k_d=0., pos_limit=1e308, neg_limit=-1e308, rate=100):
    self._k_p = k_p
    self._k_i = k_i
    self._k_d = k_d
    if isinstance(self._k_p, Number):
      self._k_p = [[0], [self._k_p]]
    if isinstance(self._k_i, Number):
      self._k_i = [[0], [self._k_i]]
    if isinstance(self._k_d, Number):
      self._k_d = [[0], [self._k_d]]

    self.set_limits(pos_limit, neg_limit)

    self.i_dt = 1.0 / rate
    self.speed = 0.0

    # FrogPilot variables: an optional rate-damping term, off unless a caller sets the strength. A
    # torque-commanded EPS (Honda Nidec) closes the loop torque -> angle, which is a double integrator, and
    # proportional feedback on a double integrator is an undamped oscillator. p, i and f are all gain knobs;
    # only a term that reacts to how fast the wheel is moving can damp it. NRDR's verified form, kept
    # identical so the two tunings are comparable. With strength 0 the term is exactly 0.0 and this
    # controller is unchanged, term for term.
    self.damping_strength = 0.0      # 100 applies the full output range at 10 deg/s of wheel movement
    self.damping_fade_speed = 30.0   # m/s; at or above this speed the term is zero

    self.reset()

  def damping(self, steering_rate_deg: float, v_ego: float) -> float:
    if self.damping_strength <= 0.0 or v_ego >= self.damping_fade_speed:
      return 0.0
    fade = (self.damping_fade_speed - v_ego) / self.damping_fade_speed
    return -(self.damping_strength * 0.001) * float(steering_rate_deg) * fade

  @property
  def k_p(self):
    return np.interp(self.speed, self._k_p[0], self._k_p[1])

  @property
  def k_i(self):
    return np.interp(self.speed, self._k_i[0], self._k_i[1])

  @property
  def k_d(self):
    return np.interp(self.speed, self._k_d[0], self._k_d[1])

  def reset(self):
    self.p = 0.0
    self.i = 0.0
    self.d = 0.0
    self.f = 0.0
    self.control = 0

  def set_limits(self, pos_limit, neg_limit):
    self.pos_limit = pos_limit
    self.neg_limit = neg_limit

  def update(self, error, error_rate=0.0, speed=0.0, feedforward=0., freeze_integrator=False, steering_rate_deg=None):
    self.speed = speed
    self.p = self.k_p * float(error)
    self.d = self.k_d * error_rate
    self.f = feedforward

    if not freeze_integrator:
      i = self.i + self.k_i * self.i_dt * error

      # Don't allow windup if already clipping
      test_control = self.p + i + self.d + self.f
      i_upperbound = self.i if test_control > self.pos_limit else self.pos_limit
      i_lowerbound = self.i if test_control < self.neg_limit else self.neg_limit
      self.i = np.clip(i, i_lowerbound, i_upperbound)

    control = self.p + self.i + self.d + self.f

    # FrogPilot variables: applied after the terms are summed and before the clamp, so damping can only take
    # output away from a wheel that is arriving fast; it never asks for authority the car does not already
    # have, and it is never integrated, so it cannot wind up. It is deliberately left out of the i bound
    # above: with strength 0 nothing here runs, and the integral evolves exactly as it does today.
    if steering_rate_deg is not None:
      control += self.damping(float(steering_rate_deg), speed)

    self.control = np.clip(control, self.neg_limit, self.pos_limit)
    return self.control
