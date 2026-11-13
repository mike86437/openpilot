"""The corner-phase detector on its own: what it reports while a car turns in and unwinds.

No control loop and no CarInterface here on purpose - latcontrol_phase imports nothing, so this runs anywhere
the repository can be imported, and the thing under test is the sign of a lane change, not a controller.

The controller side (latcontrol_pid.py freezing on phase < 0 while pid.i and the error agree) was checked by
running LatControlPID against an under-damped steering plant through a 5 degree curve and its exit: the
integrator's excursion through the coming-out-of-the-corner phase is 0.0111 with the freeze and 0.0192 without
it, on the same plant and the same commanded angle profile.
"""

from openpilot.selfdrive.controls.lib.latcontrol_phase import PHASE_SWITCH_MIN_SPEED, phase_with_latch

TURN_IN = [0.0, 1.0, 3.0, 6.0, 9.0, 12.0, 15.0, 18.0, 20.0, 20.0]
UNWIND = [18.0, 15.0, 11.0, 7.0, 4.0, 2.0, 1.0, 0.5, 0.2, 0.0]


def profile(desired, previous=0.0):
  """(angle, angle_delta) pairs as the control loop would compute them from a commanded angle. The caller's
  `previous` matters: a corner exit continues from where the corner entry left the wheel, it does not restart
  at zero."""
  out = []
  for angle in desired:
    out.append((angle, angle - previous))
    previous = angle
  return out


def test_turn_in_is_positive_and_unwind_is_negative():
  direction = 0.0
  turn_in, unwind = profile(TURN_IN), None
  previous = TURN_IN[-1]
  unwind = profile(UNWIND, previous)
  for angle, delta in turn_in:
    phase, direction = phase_with_latch(angle, delta, 20.0, direction)
    if angle and delta:
      assert phase > 0.0, f"turning in must read positive, got {phase} at angle {angle}"
  assert direction > 0.0
  for angle, delta in unwind:
    phase, direction = phase_with_latch(angle, delta, 20.0, direction)
    if angle and delta:
      assert phase < 0.0, f"unwinding must read negative, got {phase} at angle {angle}"
  assert direction < 0.0


def test_the_latch_survives_the_peak_where_the_unlatched_sign_is_zero():
  # angle * angle_delta is exactly 0.0 on the frame the commanded angle peaks, and flickers for the frames
  # around it. Without the latch the "we are unwinding" decision would start and stop at the peak, which is
  # the one moment the decision has to be continuous.
  _, direction = phase_with_latch(20.0, 1.0, 20.0, 0.0)
  phase_at_peak, held = phase_with_latch(20.0, 0.0, 20.0, direction)
  assert phase_at_peak == 0.0
  assert held == direction, "the peak frame must keep the direction from before it"
  phase_after, _ = phase_with_latch(19.0, -1.0, 20.0, held)
  assert phase_after < 0.0


def test_below_the_speed_floor_the_direction_is_held_not_reversed():
  # At a crawl the commanded angle jitters by degrees and the sign of angle * angle_delta is sensor noise;
  # latching keeps whatever the last real decision was instead of alternating it every frame.
  for angle, delta in ((5.0, -1.0), (4.0, 1.0), (5.0, -1.0), (4.0, 1.0)):
    _, direction = phase_with_latch(angle, delta, PHASE_SWITCH_MIN_SPEED * 0.5, 1.0)
    assert direction > 0.0, "a stopped car must not be told it is unwinding"
