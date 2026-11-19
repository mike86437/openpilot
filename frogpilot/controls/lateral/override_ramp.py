"""Driver-override assist ramp, ported from dev-111826.

Source: `opendbc_repo/opendbc/sunnypilot/car/honda/controller_features.py:114-140` (`update_steering_torque`),
whose state is `self.override_ramp` and whose numbers come from `HondaLiveTuning`
(`opendbc_repo/opendbc/sunnypilot/car/runtime_config.py:8-13`) — the source's per-brand live-tuning carrier.
The arithmetic is carried unchanged: the `DT_CTRL / fade_seconds` step, the `max(floor, …)` on the way out, the
`min(1.0, …)` on the way back, the `fade_seconds <= 0.0` shortcut that makes a fade instantaneous, and the reset
to 0.0 both when lateral deactivates and on the first frame a new activation begins.

What it *is*: a multiplier applied to the torque command **after** the controller has produced it, in the car
controller, on the way to the CAN message. It does not touch the controller's P, I, feedforward or any of its
state — the source keeps the two apart for the same reason this file does: what is being faded is what the EPS
is told, not what the loop believes.

Three things this port does not carry, each checked rather than assumed:

  * **the filtered press for the ramp.** The source swaps in its own filtered detector when
    `live.increase_override_tolerance` is set (`controller_features.py:116-119`), and that key is registered
    `ParamLifecycle.TOMBSTONE` with default `"0"` (`nrdr/params/specs.py:192`) — off, and on its way out.
    This ramp reads the car state's own `steeringPressed`, which is what the source's default path reads.
    The port's *controller* has its own filtered press (`selfdrive/controls/lib/latcontrol_fw.py`, header 3);
    those two are deliberately not shared. One answers "is the driver in the wheel" to the EPS, the other
    decides whether the core's feedforward and integrator hold.
  * **`increase_override_tolerance` itself**, for the reason above.
  * **the source's own steer delta limiter** (`controller_features.py:137-143`), which the source disables
    whenever `NrdrLateralController` is 1 (`nrdr/car/opendbc.py:244-245`). This tree's Honda car controller
    rate-limits with its own `STEER_DELTA_UP/DOWN` regardless; this file does not change that.

Units, kept the source's: the two fades are seconds clamped to [0, 10] by the source
(`nrdr/car/opendbc.py:238-240`); `override_torque_scale` is stored as a percent 0-100 and divided by 100 there
(`:240`), so the floor this ramp fades to is a fraction of the command, 0 meaning "assist fully out".
"""
from __future__ import annotations

from opendbc.car import DT_CTRL

# The source's clamp on both fade values (nrdr/car/opendbc.py:238-240). A fade longer than this is a typo,
# not a setting: at 10 s the assist is coming back at 10 %/s.
FADE_SECONDS_LIMIT = 10.0


def fade_seconds(value: float) -> float:
  return max(0.0, min(float(value), FADE_SECONDS_LIMIT))


def torque_floor(percent: float) -> float:
  """The source's unit: a 0-100 percent becomes the fraction of the command that survives the fade-out."""
  return max(0.0, min(float(percent) / 100.0, 1.0))


class HondaOverrideRamp:
  """`override_ramp` from `controller_features.py`, on this tree's carrier.

  Scale starts and stays 0.0 while lateral is inactive; the first active frame resets it to 0.0 and it climbs
  to 1.0 over `fade_up_s`, exactly as the source's `if not self.lat_active_previous: self.override_ramp = 0.0`
  followed by the ramp does. With `fade_up_s <= 0` it is 1.0 on that frame; with `fade_down_s <= 0` and a floor
  of 0 the command is gone on the frame the press is seen.
  """

  def __init__(self) -> None:
    self.scale = 0.0
    self.active = False

  def update(self, lat_active: bool, steering_pressed: bool, fade_down_s: float, fade_up_s: float,
             floor_percent: float) -> float:
    if not lat_active:
      self.scale = 0.0
      self.active = False
      return 0.0
    if not self.active:
      self.scale = 0.0
    self.active = True

    floor = torque_floor(floor_percent)
    down = fade_seconds(fade_down_s)
    up = fade_seconds(fade_up_s)
    if steering_pressed:
      self.scale = floor if down <= 0.0 else max(floor, self.scale - DT_CTRL / down)
    else:
      self.scale = 1.0 if up <= 0.0 else min(1.0, self.scale + DT_CTRL / up)
    return self.scale

  def reset(self) -> None:
    self.scale = 0.0
    self.active = False


def assist_stays_on(pass_through: bool, steering_pressed: bool) -> bool:
  """The source's `lkas_active` term (`controller_features.py:148-150`), split out so the decision is testable.

  `HondaDriverAssistDuringOverride` is presented in the source as "Assist Pass-Through": on, the assist hands
  the wheel over while the driver is in it; off, "the normal override response" — assist continues. Whatever
  the name, the term is the source's: pass-through on plus a press is what takes the assist out.
  """
  return not pass_through or not steering_pressed
