"""The Honda driver-override ladder: what the press test must do, and what it must not do.

These cases exist because the whole feature is a *default-off* change to a safety-relevant flag:
opendbc/car/honda/carstate.py decides `steeringPressed`, which decides whether openpilot thinks the steering is
yours. So the first thing proved here is the unchanged case - no parameters, every car gets exactly the number
`STEER_THRESHOLD` gives it, including the cars whose stock value is not 1200. The centre window is NRDR's
(NRDR's own profile on the Clarity: 2000 units off-centre, the stock 1200 within 3.0 degrees of straight), and
the doubling is the part NRDR limits to the three touchy EPS families.

Run: python -m pytest opendbc_repo/opendbc/car/honda/tests/test_honda_override.py -q
"""
from cereal import custom
from opendbc.car.honda.carstate import OVERRIDE_TOLERANCE_SENSITIVE_EPS, CarState
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.values import CAR, STEER_THRESHOLD

STOCK = 1200


def car_state(fingerprint, **fpcp_fields):
  """A real CarState for a real CarParams, with FrogPilotCarParams as card would hand it over: a message with
  the requested fields set and everything else left at its default, which is 0."""
  cs = CarState(CarInterface.get_non_essential_params(fingerprint))
  FPCP = custom.FrogPilotCarParams.new_message()
  for key, value in fpcp_fields.items():
    setattr(FPCP, key, value)
  cs.FPCP = FPCP
  cs.init_frogpilot_params()
  return cs


class TestHondaDriverOverrideLadder:
  def test_nothing_configured_is_the_old_behaviour(self):
    # A Clarity with no Pond values: the number the flat STEER_THRESHOLD test produced, at every angle.
    cs = car_state(CAR.HONDA_CLARITY)
    expected = STEER_THRESHOLD.get(CAR.HONDA_CLARITY, STOCK)
    for angle in (0.0, 1.0, 3.0, 12.0, -430.0):
      assert cs.override_press_threshold(angle) == expected

  def test_zero_means_this_car_stock_not_the_default_1200(self):
    # The RDX's stock threshold is 400, not 1200. A car that sets nothing must get its own value.
    cs = car_state(CAR.ACURA_RDX)
    assert cs.override_press_threshold(0.0) == STEER_THRESHOLD[CAR.ACURA_RDX] == 400
    # Including when only the centre window is configured: both thresholds fall back, independently.
    cs = car_state(CAR.ACURA_RDX, hondaOverrideCenterAngle=5.0)
    assert cs.override_press_threshold(2.0) == 400 and cs.override_press_threshold(20.0) == 400

  def test_the_nrdr_profile_on_the_clarity(self):
    # 2000 off-centre, the stock 1200 within 3.0 degrees of straight - NRDR's shape, with the centre threshold
    # left unset so it falls back to stock rather than becoming "zero torque".
    cs = car_state(CAR.HONDA_CLARITY, hondaOverrideThreshold=2000, hondaOverrideCenterAngle=3.0)
    assert cs.override_press_threshold(0.0) == 1200
    assert cs.override_press_threshold(2.9) == 1200
    assert cs.override_press_threshold(-3.0) == 1200      # the window is symmetric, and its edge is inside
    assert cs.override_press_threshold(3.1) == 2000
    assert cs.override_press_threshold(-40.0) == 2000

  def test_a_set_centre_threshold_is_honoured(self):
    cs = car_state(CAR.HONDA_CLARITY, hondaOverrideThreshold=2000,
                   hondaOverrideCenterThreshold=1500, hondaOverrideCenterAngle=8.0)
    assert cs.override_press_threshold(0.0) == 1500 and cs.override_press_threshold(8.0) == 1500
    assert cs.override_press_threshold(8.5) == 2000

  def test_an_angle_window_without_a_driver_threshold_is_inert(self):
    # Raising the window alone must not move anything: both sides are still stock.
    cs = car_state(CAR.HONDA_CLARITY, hondaOverrideCenterAngle=10.0)
    assert cs.override_press_threshold(0.0) == cs.override_press_threshold(90.0) == STOCK

  def test_the_tolerance_doubling_follows_nrdr_s_membership(self):
    for fingerprint in OVERRIDE_TOLERANCE_SENSITIVE_EPS:
      cs = car_state(fingerprint, hondaRaiseOverrideTolerance=True)
      stock = STEER_THRESHOLD.get(fingerprint, STOCK)
      assert cs.override_press_threshold(0.0) == stock * 2, fingerprint
      cs = car_state(fingerprint, hondaOverrideThreshold=2000,
                     hondaOverrideCenterAngle=3.0, hondaRaiseOverrideTolerance=True)
      assert cs.override_press_threshold(0.0) == stock * 2 and cs.override_press_threshold(20.0) == 4000, fingerprint

    # A Honda outside that list keeps its own threshold, doubled or not asked for.
    cs = car_state(CAR.HONDA_PILOT, hondaOverrideThreshold=2000,
                   hondaRaiseOverrideTolerance=True)
    assert cs.override_press_threshold(0.0) == 2000

  def test_carstate_without_frogpilotcarparams_still_presses_like_stock(self):
    # CarState is constructed outside CarInterface in replay and in unit tests, where init_frogpilot_params is
    # never called. __init__ has to leave the stock numbers in place on its own.
    cs = CarState(CarInterface.get_non_essential_params(CAR.HONDA_CLARITY))
    assert not hasattr(cs, "FPCP")
    assert cs.override_press_threshold(0.0) == STOCK
