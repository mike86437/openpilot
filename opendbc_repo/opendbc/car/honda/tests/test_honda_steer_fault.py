"""Which EPS steering states are a steering fault, for whom, and what the switch does.

honda/carstate.py decides two of the flags openpilot treats as "the car cannot steer": carState.steerFaultTemporary
and steerFaultPermanent. Both come from one enum on the car's own CAN - STEER_STATUS - and the temporary one is
what controlsd.py:133 uses to turn lateral off (car_specific.py:208 turns it into an alert). On this branch's
Clarity the state that fires constantly is NO_TORQUE_ALERT_1, and it fires when the driver is steering: measured
over the seven pulled drives, 101 onsets, none of them without carState.steerPressed, driver torque median 3144
CAN units against a stock override threshold of 1200, with openpilot commanding 500 units or less in 94 of them
(analysis/dropout_check.py; the state itself read off the bus in analysis/steer_status_timeline.py).

The exception is a2fac39, and this makes it a switch. Two things have to be true for NO_TORQUE_ALERT_1 to stop
being a fault, and the tests below take each one apart on its own: the car's EPS firmware has to be the modified
one (clarity_mod_eps, the same predicate that picks this car's gains, its torque map and its actuator smoothing),
and FrogHondaOverrideNotAFault - the Pond row "Keep Steering When You Take Over" - has to be on. Firmware decides
who may have it, the parameter decides whether it is on, and the parameter is read per frame, so it can be flipped
while card is running. Off is what every Honda does today, including this one.

What is proved here is the width of it: with the switch on, the modified-EPS Clarity stops reading that state as a
fault; every other Honda - a Clarity with unmodified EPS firmware included - reads it exactly as upstream does with
the switch on or off; and no state upstream calls a fault has become anything but a fault for anybody.

Run: python -m pytest opendbc_repo/opendbc/car/honda/tests/test_honda_steer_fault.py -q
(This tree is unbuilt on a development host, so cereal.custom does not import there. On the device:
cd /data/openpilot && /usr/local/venv/bin/python -m pytest --noconftest -o addopts="" \
  opendbc_repo/opendbc/car/honda/tests/test_honda_steer_fault.py -q)
"""

from collections import defaultdict
from types import SimpleNamespace

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

# Upstream's set, verbatim (carstate.py's steerFaultTemporary line, the else branch that every Nidec Honda takes),
# and its permanent-fault rule, which this branch leaves exactly as it is. carstate compares the decoded enum by
# name, so the expectations below are computed in names too - the int above is only what gets fed to the CAN.
UPSTREAM_EXCUSED = ("NORMAL", "LOW_SPEED_LOCKOUT", "NO_TORQUE_ALERT_2")
UPSTREAM_PERMANENT_EXCUSED = ("NORMAL", "NO_TORQUE_ALERT_1", "NO_TORQUE_ALERT_2", "LOW_SPEED_LOCKOUT", "TMP_FAULT")
STATE_NAMES = {NORMAL: "NORMAL", DRIVER_STEERING: "DRIVER_STEERING", NO_TORQUE_ALERT_1: "NO_TORQUE_ALERT_1",
               LOW_SPEED_LOCKOUT: "LOW_SPEED_LOCKOUT", NO_TORQUE_ALERT_2: "NO_TORQUE_ALERT_2",
               FAULT_1: "FAULT_1", TMP_FAULT: "TMP_FAULT", PERMANENT_FAULT: "PERMANENT_FAULT"}

MOD_EPS_FW = b"39990-TRW,A020"     # what this car answers: NRDR's modified EPS, dash and comma both present
STOCK_EPS_FW = b"39990-TYF-A020"   # no dash: the unmodified EPS, which is every other Clarity

SWITCH_ON, SWITCH_OFF, SWITCH_ABSENT = True, False, None


class FakeCAN:
  """Enough of a CANParser for carstate to run: every signal it asks for answers 0, and the one signal under
  test answers what the test says. carState reads about forty signals on this car and none of the others can
  change a steering-fault flag."""

  def __init__(self, steer_status=NORMAL):
    self.vl = defaultdict(lambda: defaultdict(float))
    self.vl_all = defaultdict(lambda: defaultdict(list))
    self.vl["STEER_STATUS"]["STEER_STATUS"] = float(steer_status)


def faults(fingerprint, fw=None, status=NORMAL, switch=SWITCH_ON):
  cs = car_state(fingerprint, fw, switch)
  parsers = {Bus.pt: FakeCAN(status), Bus.cam: FakeCAN(status)}
  ret = cs.update(parsers)
  return bool(ret.steerFaultTemporary), bool(ret.steerFaultPermanent)


def car_state(fingerprint, fw=None, switch=SWITCH_ON):
  """A real CarState for a real CarParams, initialised the way CarInterface initialises one: FPCP and
  init_frogpilot_params() at construction (interfaces.py:124-126), plus the two things CarInterface.update hangs
  off the CarState on every frame before calling carstate.update (interfaces.py:379-380) - the FrogPilotCarState
  Honda's carstate writes fp_ret.brakeLights into, and the toggles namespace the fault decision reads. SWITCH_ABSENT hands over a namespace with no such attribute, which is what
  getattr's default is for (CarInterface.update always installs one, interfaces.py:380). A CarState without these
  is a car that never started."""
  CP = CarInterface.get_non_essential_params(fingerprint)
  if fw is not None:
    CP.carFw = [] if not fw else [{"ecu": "eps", "fwVersion": fw}]
  cs = CarState(CP)
  cs.FPCP = custom.FrogPilotCarParams.new_message()
  cs.init_frogpilot_params()
  cs.fp_ret = custom.FrogPilotCarState.new_message()
  if switch is SWITCH_ABSENT:
    cs.frogpilot_toggles = SimpleNamespace()          # the namespace exists, the attribute does not
  else:
    cs.frogpilot_toggles = SimpleNamespace(frog_honda_override_not_a_fault=switch)
  return cs


class TestHondaSteerFaultStates:
  def test_off_is_upstream_for_every_honda_including_this_one(self):
    # The parameter's other position, and the one ISC-3 requires: unwritten or off is what every Honda does today.
    for fingerprint in (CAR.HONDA_CIVIC, CAR.HONDA_ACCORD, CAR.HONDA_PILOT, CAR.ACURA_RDX, CAR.HONDA_CLARITY):
      for fw in (MOD_EPS_FW, STOCK_EPS_FW, None):
        temporary, permanent = faults(fingerprint, fw=fw, status=NO_TORQUE_ALERT_1, switch=SWITCH_OFF)
        assert temporary is True and permanent is False, f"{fingerprint} {fw}"

  def test_on_changes_it_for_the_modified_eps_clarity_alone(self):
    temporary, permanent = faults(CAR.HONDA_CLARITY, fw=MOD_EPS_FW, status=NO_TORQUE_ALERT_1, switch=SWITCH_ON)
    assert temporary is False and permanent is False

    # Same switch, same value, every other Honda: the firmware half is what does the scoping, not the parameter.
    for fingerprint in (CAR.HONDA_CIVIC, CAR.HONDA_ACCORD, CAR.HONDA_PILOT, CAR.ACURA_RDX):
      temporary, _ = faults(fingerprint, fw=STOCK_EPS_FW, status=NO_TORQUE_ALERT_1, switch=SWITCH_ON)
      assert temporary is True, fingerprint
    temporary, _ = faults(CAR.HONDA_CLARITY, fw=STOCK_EPS_FW, status=NO_TORQUE_ALERT_1, switch=SWITCH_ON)
    assert temporary is True, "a Clarity whose EPS was not modified keeps the upstream reading with the switch on"

  def test_the_firmware_half_is_the_cars_own_and_not_the_fingerprint_alone(self):
    # Two Claritys one firmware string apart. clarity_mod_eps() is the same predicate that picks this car's gains,
    # its torque map and its actuator smoothing (car/interfaces.py:228, carcontroller.py:136, latcontrol_pid.py:32),
    # and it is a firmware test, not a model test.
    def available(fw):
      return car_state(CAR.HONDA_CLARITY, fw).override_not_a_fault_available

    assert available(None) is False       # no firmware answered at all
    assert available([]) is False
    assert available(STOCK_EPS_FW) is False
    assert available(MOD_EPS_FW) is True
    # the tuple built in __init__ is upstream's either way; the exception is added per frame in update()
    for fw in (MOD_EPS_FW, STOCK_EPS_FW, None):
      assert car_state(CAR.HONDA_CLARITY, fw).steer_fault_states == UPSTREAM_EXCUSED

  def test_a_missing_toggle_is_stock_behaviour(self):
    # getattr(..., False) in carstate.py: a FrogPilotVariables that never sets the attribute is the off position,
    # not a crash and not an exception.
    temporary, permanent = faults(CAR.HONDA_CLARITY, fw=MOD_EPS_FW, status=NO_TORQUE_ALERT_1, switch=SWITCH_ABSENT)
    assert temporary is True and permanent is False

  def test_everything_upstream_calls_a_fault_is_still_a_fault_in_both_positions(self):
    # Not one state got quieter, and not one car did: the change is one name, and the states upstream treats as
    # permanent faults stay permanent faults on the car that can be switched.
    for switch in (SWITCH_ON, SWITCH_OFF):
      excused = UPSTREAM_EXCUSED + (("NO_TORQUE_ALERT_1",) if switch is SWITCH_ON else ())
      for status in ALL_STATES:
        name = STATE_NAMES[status]
        expected_temporary = name not in excused
        expected_permanent = name not in UPSTREAM_PERMANENT_EXCUSED
        temporary, permanent = faults(CAR.HONDA_CLARITY, fw=MOD_EPS_FW, status=status, switch=switch)
        assert temporary == expected_temporary, f"state {name}: got temporary={temporary}"
        assert permanent == expected_permanent, f"state {name}: got permanent={permanent}"

      # On the unmodified car the unchanged rule holds, state for state - including DRIVER_STEERING, which upstream
      # does treat as a temporary fault, and which neither the switch nor this branch changes.
      for status in ALL_STATES:
        name = STATE_NAMES[status]
        temporary, _ = faults(CAR.HONDA_CLARITY, fw=STOCK_EPS_FW, status=status, switch=switch)
        assert temporary == (name not in UPSTREAM_EXCUSED), f"stock state {name}: got temporary={temporary}"
