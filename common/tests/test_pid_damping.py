"""The rate-damping term in common/pid.py on its own: what it does to a torque-commanded steering loop.

No CarInterface, no controlsd, no cereal here on purpose - common/pid.py imports numpy and nothing else, so the
thing under test is the term, and it runs anywhere the repository can be imported. The Clarity wiring
(latcontrol_pid.py gating it on clarity_mod_eps, on not-steeringPressed, on not-steer-limited-by-safety) is the
other half and is checked on the car.

The reason a term like this is needed at all: the Honda Nidec EPS is torque-commanded, so the lateral loop
closes as torque -> force -> wheel angle. That is a double integrator, proportional feedback on a double
integrator is an undamped oscillator, and p, i and f are all just gain knobs. The only term that can damp it
reacts to how fast the wheel is moving. The plant below is that double integrator, deliberately with almost no
natural damping in it - at the speeds where the Clarity rings, tyre self-aligning torque is small and the
kf * angle * v^2 feed-forward has faded out, which is the same thing stated the other way round.

What is asserted:
  - strength 0 leaves the controller bit-for-bit alone, with the kwarg present or absent;
  - the term always acts against the wheel's motion, never with it, in either direction;
  - it fades to exactly zero at or above damping_fade_speed;
  - it is not integrated, so holding a wheel rate does not wind it up the way an error integral would;
  - on the plant, the same gains that ring produce a smaller overshoot with the term on.
"""

import pytest

from openpilot.common.pid import PIDController

DT = 0.01                    # DT_CTRL
FADE = 30.0                  # the committed damping_fade_speed, m/s

# The plant is a stated construction, not this car: the torque -> force -> wheel-angle chain with the tyre's
# own damping removed, which is the case the term exists for. The Clarity's real wheel inertia is not recoverable
# from these logs (analysis/plant_identification.py fits it at R2 0.02 and gets nonsense back), but the corner
# entries are: at 18-30 kph the loop holds full authority for 1.0-1.5 s and the wheel arrives at 130-450 deg/s,
# which bounds the net acceleration a saturated command produces at roughly 100-450 deg/s^2. 120 is the low end
# of that measured range. Only the comparison between the same plant with and without the term is asserted.
PLANT_ACCEL_PER_UNIT_TORQUE = 120.0
PLANT_NATURAL_DAMPING = 0.0


def gains():
  # The Clarity's own: opendbc/car/interfaces.py clarity_mod_eps() gives kp 0.1575 / ki 0.05175 at 0 m/s.
  return [0.0], [0.1575], [0.0], [0.05175]


def make_pid(strength, v_ego):
  kp_bp, kp_v, ki_bp, ki_v = gains()
  pid = PIDController((kp_bp, kp_v), (ki_bp, ki_v), pos_limit=1.0, neg_limit=-1.0)
  pid.damping_strength = strength
  pid.damping_fade_speed = FADE
  return pid


def command_profile():
  """A corner entry hard enough to peg the command, which is what the pulled drives show at 18-30 kph: 12 degrees
  demanded inside 0.5 s. A gentler ramp never saturates and therefore cannot show what this term changes."""
  frames = []
  t = 0.0
  target, ramp = 12.0, 0.5
  while t < 8.0:
    frames.append((t, target * min(1.0, t / ramp)))
    t += DT
  return frames


def run(strength, v_ego, profile=None):
  """Close the loop around the plant and return (time, commanded angle, wheel angle, torque command) per frame."""
  pid = make_pid(strength, v_ego)
  angle, rate = 0.0, 0.0
  out = []
  for t, desired in (profile or command_profile()):
    torque = pid.update(desired - angle, speed=v_ego, freeze_integrator=False,
                       steering_rate_deg=rate if strength > 0 else None)
    rate_next = rate + DT * (PLANT_ACCEL_PER_UNIT_TORQUE * torque - PLANT_NATURAL_DAMPING * rate)
    angle += DT * 0.5 * (rate + rate_next)
    rate = rate_next
    out.append((t, desired, angle, torque))
  return out


def overshoot(run_frames):
  """How far past the commanded angle the wheel goes, how many times it crosses it by more than a degree after
  the command has stopped moving, and how long the command spends pegged at +-1.0. The deadband matters: a
  settled loop jitters about its target and every micro-crossing counted as a re-crossing makes every strength
  look the same."""
  peak, crossings, pegged, prev = 0.0, 0, 0, 0.0
  settled = run_frames[-1][1]
  started = next(i for i, (_, d, _, _) in enumerate(run_frames) if d >= settled)
  for _, _, angle, torque in run_frames[started:]:
    peak = max(peak, angle - settled)
    pegged += 1 if abs(torque) >= 0.999 else 0
    if abs(angle - settled) > 1.0:
      sign = 1.0 if angle > settled else -1.0
      if prev != 0.0 and sign != prev:
        crossings += 1
      prev = sign
  return peak, crossings, pegged


def test_strength_zero_is_this_controller_exactly_as_it_is_today():
  """The whole safety argument for shipping the term off: with strength 0, update() is bit-identical whether the
  caller passes a steering rate or not, and identical to a controller that has never seen the attribute. A fresh
  pair per error on purpose - the integral accumulates, so one controller called twice is not the same
  controller as one called once."""
  kp_bp, kp_v, ki_bp, ki_v = gains()
  for error in (0.5, -1.2, 3.0, 0.0, -0.25, 7.5, 1.0, -4.0, 0.75, -0.1):
    for speed in (0.0, 10.0, 29.9, 30.0):
      plain = PIDController((kp_bp, kp_v), (ki_bp, ki_v), pos_limit=1.0, neg_limit=-1.0)
      damped = make_pid(0.0, speed)
      inert = make_pid(0.0, speed)
      a = plain.update(error, speed=speed)
      b = damped.update(error, speed=speed, steering_rate_deg=None)
      c = inert.update(error, speed=speed, steering_rate_deg=250.0)
      assert a == b == c, f"strength 0 must be inert at {speed} m/s, got {a} {b} {c}"
      assert plain.i == damped.i == inert.i, f"the integral must evolve the same way in all three: {plain.i} {damped.i} {inert.i}"


def test_the_term_always_acts_against_the_wheel():
  """The sign, which is the whole question when the car's CAN factors are negative: a wheel moving one way gets
  its command reduced in that direction whichever way the command itself is pointed. Nothing in the lateral path
  between here and the CAN message flips one term and not the other - honda/carcontroller.py negates the whole
  command together when it builds apply_torque."""
  for rate in (30.0, 120.0, -30.0, -120.0):
    # an error small enough that the clip is not what is being measured here
    pos = make_pid(5.0, 8.0).update(1.0, speed=8.0, steering_rate_deg=rate)
    pos_off = make_pid(0.0, 8.0).update(1.0, speed=8.0)
    assert pos < pos_off if rate > 0 else pos > pos_off, \
      f"rate {rate} must be opposed: without {pos_off}, with {pos}"
    expected = 5.0 * 0.001 * abs(rate) * (FADE - 8.0) / FADE
    assert abs(pos - pos_off) == pytest.approx(expected), f"rate {rate}: {pos_off} -> {pos}, expected {expected}"


def test_the_documented_arithmetic():
  """strength * 0.001 per deg/s: 100 applies the full range at 10 deg/s, and the todo's own worked example -
  strength 100 with the wheel at -20 deg/s adds 2.0, which the clip then decides what to do with."""
  pid = make_pid(100.0, 0.0)
  assert pid.damping(-20.0, 0.0) == 2.0
  assert pid.damping(10.0, 0.0) == -1.0
  assert pid.damping(0.0, 0.0) == 0.0
  assert pid.damping(1000.0, FADE) == 0.0 and pid.damping(1000.0, FADE + 5) == 0.0
  # the term is added after the sum and before the clip, so a term larger than the range cannot hide
  over = pid.update(1.0, speed=0.0, steering_rate_deg=-20.0)
  assert over == 1.0 and pid.p < 1.0


def test_nothing_above_the_fade_speed():
  """At or above damping_fade_speed the term is gone, so a lane change at 110 kph is the controller it has always
  been. The ramp is the point: at a stop the term is the full value, at 29.9 m/s it is a thousandth of it, and
  at 30.0 m/s it is not there at all."""
  stopped, near, at, above = (make_pid(5.0, 0.0).damping(100.0, 0.0), make_pid(5.0, 29.9).damping(100.0, 29.9),
                              make_pid(5.0, FADE).damping(100.0, FADE), make_pid(5.0, FADE + 1).damping(100.0, FADE + 1))
  assert stopped == -0.5
  assert near == pytest.approx(-0.5 * 0.1 / 30.0, abs=1e-4)
  assert at == 0.0 and above == 0.0
  assert stopped < near < at == above == 0.0


def test_it_does_not_wind_up():
  """An error integral and a rate term look alike for one frame and behave nothing alike over a minute: held
  against a wall the integral grows without bound and this does not, which is why it is added after the terms
  are summed and left out of the integral bound."""
  pid = make_pid(20.0, 5.0)
  held = [pid.update(2.0, speed=5.0, steering_rate_deg=40.0) for _ in range(2000)]
  assert pid.i > 0.5, "the integral should still be doing what an integral does"
  assert abs(pid.damping(40.0, 5.0)) < 1.0, "the rate term must stay bounded by the rate, not by time"
  assert max(abs(h) for h in held) <= 1.0
  unwound = make_pid(20.0, 5.0).update(2.0, speed=5.0, steering_rate_deg=40.0)
  assert held[0] == unwound


def test_the_same_gains_that_ring_stop_ringing():
  """The mechanism, on the constructed plant above and with the Clarity's own gains: the same command profile,
  the same controller, only the strength changing. It says two things worth saying - the overshoot falls, and
  what really goes away is the command sitting pegged at full authority, which is the measured shape of the
  18-30 kph corner entries."""
  results = {s: overshoot(run(s, 8.0)) for s in (0.0, 3.0, 5.0, 10.0, 20.0)}
  peaks = [results[s][0] for s in sorted(results)]
  pegged = [results[s][2] for s in sorted(results)]
  assert peaks[0] > 5.0, f"the undamped case must actually overshoot, got {peaks[0]:.2f}"
  assert all(b < a for a, b in zip(peaks, peaks[1:])), f"overshoot must fall monotonically: {peaks}"
  assert peaks[1] < peaks[0] * 0.8, f"strength 3 must move it, {peaks[0]:.2f} -> {peaks[1]:.2f}"
  assert pegged[-1] < pegged[0] * 0.25, f"the command must stop pegging, {pegged[0]} -> {pegged[-1]} frames"
  # it is the undamped loop that loses the commanded angle, not the damped one: left alone on this plant the
  # wheel is on the far side of 12 degrees four seconds after the command stopped moving
  held = {s: abs(run(s, 8.0)[-1][2] - 12.0) for s in (0.0, 20.0)}
  assert held[20.0] < 0.5, f"the damped loop must hold the command, off by {held[20.0]:.2f} deg"
  assert held[20.0] < held[0.0], f"damping must not be what costs the car the angle: {held}"
