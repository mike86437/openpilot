"""Which EPS steering states are a steering fault, and for whom.

honda/carstate.py decides two of the flags openpilot treats as "the car cannot steer": carState.steerFaultTemporary
and steerFaultPermanent. Both come from one enum on the car's own CAN - STEER_STATUS - and the temporary one is
what controlsd.py:133 uses to turn lateral off (car_specific.py:208 turns it into an alert). On this branch's
Clarity the state that fires constantly is NO_TORQUE_ALERT_1, and it fires when the driver is steering: measured
over the seven pulled drives, 101 onsets, none of them without carState.steerPressed, driver torque median 3144
CAN units against a stock override threshold of 1200, with openpilot commanding 500 units or less in 94 of them
(analysis/dropout_check.py; the state itself read off the bus in analysis/steer_status_timeline.py).

So the change here is to one name in one tuple, for one car, gated by the same clarity_mod_eps() firmware
predicate as its lateral tune, its actuator smoothing and its integrator freeze. What is proved below is that
the change is exactly that wide: the modified-EPS Clarity stops reading that state as a fault, every other
Honda - including a Clarity with unmodified EPS firmware - reads it exactly as upstream does, and no state that
upstream calls a fault has become anything but a fault for anybody.

Run: python -m pytest opendbc_repo/opendbc/car/honda/tests/test_honda_steer_fault.py -q
"""

from collections import defaultdict

from cereal import custom
from opendbc.car import Bus
from opendbc.car.honda.carstate import CarState
from opendbc.car.honda.interface import CarInterface
from opendbc.car.honda.values import CAR

# STEER_STATUS as honda_clarity_hybrid_2018_can_generated.dbc:397 defines it
NORMAL, DRIVER_STEERING, NO_TORQUE_ALERT_1, LOW_SPEED_LOCKOUT = 0, 1, 2, 3
NO_TORQUE_ALERT_2, FAULT_1, TMP_FAULT, PERMANENT_FAULT = 4, 5, 6, 7
ALL_STATES = (NORMAL, DRIVER_STEERING, NO_TORQUE_ALERT_1, LOW_SPEED_LOCKOUT,
              NO_TORQUE_ALERT_2, FAULT_1, TMP_FAULT, PERMANENT_FAULT)

MOD_EPS_FW = b"39990-TRW,A020"     # what this car answers: NRDR's modified EPS, dash and comma both present
STOCK_EPS_FW = b"39990-TYF-A020"   # no dash: the unmodified EPS, which is every other Clarity


class FakeCAN:
  """Enough of a CANParser for carstate to run: every signal it asks for answers 0, and the one signal under
  test answers what the test says. carState reads about forty signals on this car and none of the others can
  change a steering-fault flag."""

  def __init__(self, steer_status=NORMAL):
    self.vl = defaultdict(lambda: defaultdict(float))
    self.vl_all = defaultdict(lambda: defaultdict(list))
    self.vl["STEER_STATUS"]["STEER_STATUS"] = float(steer_status)


def faults(fingerprint, fw=None, status=NORMAL):
  cs = car_state(fingerprint, fw)
  parsers = {Bus.pt: FakeCAN(status), Bus.cam: FakeCAN(status)}
  ret = cs.update(parsers)
  return bool(ret.steerFaultTemporary), bool(ret.steerFaultPermanent)


def car_state(fingerprint, fw=None):
  """A real CarState for a real CarParams, initialised the way CarInterface initialises one: FPCP and
  init_frogpilot_params() at construction (interfaces.py:124-126), plus the FrogPilotCarState that
  CarInterface.update hangs off the CarState on every frame before calling carstate.update
  (interfaces.py:379-380). Honda's carstate writes fp_ret.brakeLights on the way out, so a CarState without it
  is a car that never started."""
  CP = CarInterface.get_non_essential_params(fingerprint)
  if fw is not None:
    CP.carFw = [] if not fw else [{"ecu": "eps", "fwVersion": fw}]
  cs = CarState(CP)
  cs.FPCP = custom.FrogPilotCarParams.new_message()
  cs.init_frogpilot_params()
  cs.fp_ret = custom.FrogPilotCarState.new_message()
  return cs


class TestHondaSteerFaultStates:
  def test_upstream_reads_no_torque_alert_1_as_a_fault_and_this_keeps_it_for_every_other_honda(self):
    # The whole reason this test exists: on a stock Clarity, and on every other Honda, nothing changed.
    for fingerprint in (CAR.HONDA_CIVIC, CAR.HONDA_ACCORD, CAR.HONDA_PILOT, CAR.ACURA_RDX):
      temporary, permanent = faults(fingerprint, fw=STOCK_EPS_FW, status=NO_TORQUE_ALERT_1)
      assert temporary is True and permanent is False, fingerprint
    temporary, _ = faults(CAR.HONDA_CLARITY, fw=STOCK_EPS_FW, status=NO_TORQUE_ALERT_1)
    assert temporary is True, "a Clarity whose EPS was not modified keeps the upstream reading"

  def test_the_modified_eps_clarity_does_not_read_it_as_a_fault(self):
    temporary, permanent = faults(CAR.HONDA_CLARITY, fw=MOD_EPS_FW, status=NO_TORQUE_ALERT_1)
    assert temporary is False and permanent is False

  def test_the_predicate_is_the_car_s_own_and_not_the_fingerprint_alone(self):
    # Two Claritys, one firmware string apart: the gate is clarity_mod_eps(), the same one that picks this
    # car's gains, its torque map and its actuator smoothing, and it is a firmware test, not a model test.
    def states(fw):
      return car_state(CAR.HONDA_CLARITY, fw).steer_fault_states

    assert 'NO_TORQUE_ALERT_1' not in states(None)          # no firmware answered: not the modified EPS
    assert 'NO_TORQUE_ALERT_1' not in states([])
    assert 'NO_TORQUE_ALERT_1' not in states(STOCK_EPS_FW)
    assert 'NO_TORQUE_ALERT_1' in states(MOD_EPS_FW)
    # and the four states upstream already excused are still excused, unchanged, on the car that got the new one
    assert states(MOD_EPS_FW) == ("NORMAL", "LOW_SPEED_LOCKOUT", "NO_TORQUE_ALERT_2", "NO_TORQUE_ALERT_1")
    assert states(STOCK_EPS_FW) == ("NORMAL", "LOW_SPEED_LOCKOUT", "NO_TORQUE_ALERT_2")

  def test_everything_upstream_calls_a_fault_is_still_a_fault(self):
    # Not one state got quieter: the change is one name, and the states upstream treats as permanent faults
    # stay permanent faults on the car that got the change.
    for status in ALL_STATES:
      expected_temporary = status not in (NORMAL, LOW_SPEED_LOCKOUT, NO_TORQUE_ALERT_2, NO_TORQUE_ALERT_1)
      expected_permanent = status not in (NORMAL, NO_TORQUE_ALERT_1, NO_TORQUE_ALERT_2, LOW_SPEED_LOCKOUT,
                                          TMP_FAULT)
      temporary, permanent = faults(CAR.HONDA_CLARITY, fw=MOD_EPS_FW, status=status)
      assert temporary == expected_temporary, f"state {status}: got temporary={temporary}"
      assert permanent == expected_permanent, f"state {status}: got permanent={permanent}"

    # On the unmodified car the unchanged rule holds, state for state - including DRIVER_STEERING, which
    # upstream does treat as a temporary fault, and which this change leaves exactly as it was.
    for status in ALL_STATES:
      expected_temporary = status not in (NORMAL, LOW_SPEED_LOCKOUT, NO_TORQUE_ALERT_2)
      temporary, _ = faults(CAR.HONDA_CLARITY, fw=STOCK_EPS_FW, status=status)
      assert temporary == expected_temporary, f"stock state {status}: got temporary={temporary}"
