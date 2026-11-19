"""Clarity A020 modified-EPS firmware inversion — carried from dev-111826 `nrdr/features/lateral/vfn_eps_core.py`.

This copy holds ONE image: the Clarity's `39990-TRW,A020` calibration (`CLARITY_A020`, its command map, P key
axis, speed envelope and rate feedback) and its column load model (`CLARITY_EPS_LOAD`). The other eleven images
the source carries — Civic C020 / C120 / TGG-A120 / TBA-A030 / TEG-A010, CR-V TLA-A040 / A220, Insight TXM-A040,
RDX TJB-A220, Odyssey THR-A020, Ridgeline T6Z-A110 — are not here, and with them went their Table A-derived R6
shapes, their load fits and their P/I trims (178 lines), the `rdx_rack` import and the measured-RDX member of the
Table A lookup's type. `EpsFirmwareCalibration` itself is unchanged: a second image could be added without
editing the algorithm, and nothing in this tree is asked for one. A request for another Table A returns nothing
rather than borrowing the Clarity's (the profile lookup is Clarity-only, see `honda_vgr.py`).

Every number is the source's verbatim — command map, P row, envelope, `KFF 45`, `KEY_CLAMP 1663`,
`R6_PER_RAW_DEG_S -122`, the six load coefficients, the friction-width schedule, the smoothing times, the P/I
trims, the output LPF and the feedforward gating. Only imports were retargeted: this tree's `common.filter_simple`(`FirstOrderFilter` is identical in both trees) and this port's own `honda_vgr` / `integral_pid`. The provenance the
source recorded for each constant — JamesL787/openpilot commits, the routes tables and fits were measured on — is
left in the comments where it explains a number, including the cross-checks that were done on the other images:
they are evidence about `R6_PER_RAW_DEG_S`, not a calibration this tree runs.

The rest of this docstring is the source's, unchanged, because it is the explanation of the whole method.

The Clarity's LKAS path is not a torque command. The firmware turns our 0xE4 value into a target R5,
compares it with R6 -- a filtered steering RATE, taken before its angle table (see computed_r6) --
and runs P + D + KFF on the difference in its fast control loop (1-2 kHz). So every command first has to cancel
the firmware's own rate damping (Kp * 133 / 1024 = 15..34 counts per deg/s, 2-5x the rack's physical
damping), which is why vfn's angle PID trails a turn-in by ~250 ms x steering rate below 25 mph. On a turn
exit that same damping is the braking that holds the line -- which is why the symmetric rate feedforward
of 709dbba828 cut exits and was reverted.

This inverts the chain instead. A column load model (stiffness, speed stiffness, viscous, Coulomb friction,
road roll) says what motor output a motion needs; the firmware law is solved for the R5 that produces it,
rate damping included; the command map is inverted back to a lateral output. On a turn-in the load and
damping terms add, on an exit they cancel, so no hand-tuned asymmetry is needed. vfn's angle PID stays on
the residual (HondaEpsLateralCore), with the gains and output filter the car ran on vfn 35ddc44b.

Evidence, routes 00000352 / 00000353 (vfn 35ddc44b, P-minus-5 firmware):
  - E4 = -3840 * u; R5 = 7.7 * E4 ~20 ms later (corr 0.998); firmware output reproduced to 1-2 counts
    (corr 0.999) by the law in firmware_output() below.
  - Load model fitted on 352. On the held-out 353, the target this computes from the desired angle alone
    matches the R5 the car actually ran with R^2 0.79 on turning frames (|angle| > 2 deg; 0.75 below
    25 mph, 0.86 above) and explains 46% of vfn's command over all engaged frames. The kf * angle * v^2
    feedforward it replaces explains 5% or less on either measure.

Firmware constants are for ONE build: Clarity_Pminus5_P117to265_D737_KFF45_NoR6L2_Tracker3200_Norm1650
(rwd-xray-2026chatgpt/CLARITY_PMINUS5_TRACKER3200_NORM1650_20260728). The version string does not
identify the build, so re-check these after any reflash.
"""
import math

import numpy as np

from openpilot.frogpilot.controls.lateral.honda_vgr import HONDA_VGR_PROFILES, HondaVgrProfile, ptm_inverse
from openpilot.common.filter_simple import FirstOrderFilter
from openpilot.frogpilot.controls.lateral.integral_pid import IntegralScaledPIDController as PIDController

# 0xE4 value per unit of lateral output: torqueBP/V = [0, 3840] identity, apply_torque = -u * 3840
E4_PER_OUTPUT = 3840.0

# command map, row 0 (0x13810 / 0x1388E); key = trunc(trunc(E4 * 56756 / 32768) / 4) with the no-SHLL2 decode
R5_KEY_BP = [0, 111, 222, 333, 443, 665, 887, 1108, 1663]
R5_V = [0, 2000, 4000, 6000, 8000, 12000, 16000, 20000, 30000]
KEY_CLAMP = 1663

# FUN_29C14 speed envelope: a CEILING on |key| (0x13660 / 0x136DE), speed axis in 0.5 km/h counts.
# 1774 up to 100 km/h, so the 1663 key clamp binds first until ~107 km/h; 1330 from 130 km/h.
ENVELOPE_BP = [0, 50, 100, 150, 200, 260, 300, 350, 400]
ENVELOPE_V = [1774, 1774, 1774, 1774, 1774, 1330, 1330, 1330, 1330]

# P row 0 (0x13B5E / 0x13BDC), indexed by the command key; project-added feedforward KFF45
KP_KEY_BP = [0, 222, 443, 665, 887, 1108, 1330, 1552, 1774]
KP_V = [117, 148, 184, 220, 245, 257, 263, 265, 265]
KFF = 45.0
R5_PER_KEY = 18.04
# the same P row as pieces over |R5|: (lo, hi, Kp at lo, dKp/d|R5|), flat past the last breakpoint
KP_PIECES = [(lo * R5_PER_KEY, hi * R5_PER_KEY, kp_lo, (kp_hi - kp_lo) / ((hi - lo) * R5_PER_KEY))
             for lo, hi, kp_lo, kp_hi in zip(KP_KEY_BP[:-1], KP_KEY_BP[1:], KP_V[:-1], KP_V[1:], strict=True)]
KP_PIECES.append((KP_KEY_BP[-1] * R5_PER_KEY, math.inf, KP_V[-1], 0.0))

# R6, the firmware's rate feedback, is computed from the image's own Table A, not measured. The estimator (FUN_343FC)
# takes the per-sample advance of the motor-side, PRE-table angle; NORM scales it into the tracker-1 target (1650 in
# every corrected image: Clarity, C020, C120, TGG-A120, A030, TEG-A010, TXM-A040, TLA-A040, TLA-A220; stock is 3429) and
# tracker-1 filters it (its coefficient, 3200 / 4000 / 4250 by image, sets a 4-5 ms time constant, not a gain). The
# motor-to-angle constant (3121) is the same in every image, so per published deg/s (the derivative of the 0x14A angle,
# which comes out of Table A: published = raw * 2**14 / A):
#   R6(angle) = -122 * (A[0] / 16384) * slope(angle) / slope(0),   then clamped to +/-32765 (0x1380C, every image)
# with slope = d(linear)/d(published) as a +/-10 deg chord of Table A and -122 the Clarity's R6 per raw deg/s at NORM
# 1650 (flat at -120..-123 on routes 363/365/366/369 once scaled by the slope). Checked 2026-10-18 against the telemetry
# R6 word on every car that has it, unrailed frames (10-150 deg/s): mean |error| over the angle bands 0.7% on the
# Clarity (363/365/369), 1.9% on the C020 (287/289/294), 0.8% on the TEG-A010 (133/134/137/13d). The rail is real:
# R6 sits at 32765 for 92% of frames at 200-260 deg/s on the Civics (from ~185 deg/s; ~260 on the Clarity), which is
# why the C020's and TEG's earlier telemetry-fitted shapes read 4-7% low past 150 deg (railed frames in the fit).
# Ported from JamesL787 ns-bosch-radar-testing (computed_r6).
# steeringRateDeg (0x14A STEER_ANGLE_RATE) is NOT the derivative of the published angle: the firmware publishes it
# through its second, B (rate) table. It reads 1.1% fast at centre on the Clarity and 2-5% slow at 45-100 deg, so
# don't feed it here without converting (see steer_ratio.py).
R6_PER_RAW_DEG_S = -122.0  # NORM 1650
R6_CLAMP = 32765.0
COMPUTED_R6_ANGLE_BP = (0, 15, 30, 45, 60, 75, 90, 105, 120, 135, 150, 180, 210, 240, 270, 300, 360, 420, 480)  # |angle|


def computed_r6(profile: HondaVgrProfile, norm: float = 1650.0) -> tuple[float, tuple, tuple]:
  """(R6 per published deg/s at centre, |angle| axis, gain by angle) from an image's Table A; see above."""
  linear_bp, angle_bp = ptm_inverse(profile)

  def linear(a: float) -> float:
    return float(np.interp(a, angle_bp, linear_bp)) if a <= angle_bp[-1] else a * linear_bp[-1] / angle_bp[-1]

  def slope(a: float) -> float:
    lo = max(a - 10.0, 0.0)
    return (linear(a + 10.0) - linear(lo)) / (a + 10.0 - lo)

  centre = R6_PER_RAW_DEG_S * norm / 1650.0 * profile.center_divisor / 16384.0
  return round(centre, 2), COMPUTED_R6_ANGLE_BP, tuple(round(slope(a) / slope(0.0), 4) for a in COMPUTED_R6_ANGLE_BP)


def _table_a(name: str) -> HondaVgrProfile:
  return next(p for p in HONDA_VGR_PROFILES if p.name == name)


R6_PER_CENTRE_DEG_S, R6_ANGLE_BP, R6_ANGLE_GAIN = computed_r6(_table_a("Clarity TRW-A020"))
# 0x6A2 scale word while the request is held, re-measured on routes 35e/360/361: median 256 (252 on 352). Hands
# off it only moves on a fast column-torque RATE (A280) or above ~400 counts of torque (helper A).
SCALE_Q8 = 256.0       # helper A * B / 256 while the request is held

# Column load model, firmware output counts (A030 sign convention), fitted on route 00000352:
#   load = k0*th + k1*th*v^2 + c*thd + fr*tanh(thd/w) + bias + kroll*roll*v^2
# th/thd: steering-wheel deg, deg/s; v: m/s; roll: rad. R^2 0.82 in-route, 0.72 on the held-out route.
LOAD_K0 = -7.00387
LOAD_K1 = -0.21857
LOAD_C = -6.8317
LOAD_FRICTION = -314.07279
LOAD_BIAS = 20.46793
LOAD_KROLL = -7.20003
# The fit's friction width is 2 deg/s; 5 deg/s keeps the Coulomb term from flipping on desired-rate
# noise near straight driving (command roughness 0.0029 -> 0.0020 in replay, tracking nearly unchanged).
# Keyed on the DESIRED rate, even 5 deg/s turns the model's small path wiggles into a friction square wave
# in the city: closed-loop sim, a +/-2 deg 1 Hz wiggle at 10 m/s comes out at the wheel with gain 1.40; with
# 20 deg/s 0.96, and turn-ins (30-200 deg/s) keep the full friction. The price is lag on slow, small motions,
# which only pays off at city speed: replaying hands-off chunks of routes 35e/360/361, 20 deg/s cut the 0.6-2 Hz
# wheel/target transfer 0.93 -> 0.73 at 10-16 m/s for +25 ms, but above 16 m/s bought nothing (1.02 -> 0.97) for
# +45 ms of lag. So 20 deg/s up to 8 m/s, back to 5 by 15 m/s (10-16 m/s: 0.76 at +10 ms; above: unchanged).
FRICTION_WIDTH_DEG_S = 5.0
FRICTION_WIDTH_SPEED_BP = [8.0, 15.0]  # m/s
FRICTION_WIDTH_V = [20.0, FRICTION_WIDTH_DEG_S]  # deg/s


def friction_width(v_ego: float, widths=FRICTION_WIDTH_V) -> float:
  return float(np.interp(v_ego, FRICTION_WIDTH_SPEED_BP, widths))


# Smoothing, picked in the closed-loop replay of route 352 over three plants (nominal, the 353 fit, +15 ms
# motor lag): unsmoothed, the command carried 3.8x vfn's 5-8 Hz content (the Clarity column's stutter band);
# with these it is 1.14x, for RMS error below 25 mph 2.3 deg vs vfn's 4.7, turn-in lag 10-20 ms vs 250 and
# exits 50 ms vs 130. A longer lead bought back turn-in but started 25-50 mph exits early, so it stays 0.07.
DESIRED_RATE_TAU = 0.10  # s, EMA on the frame-to-frame desired-angle rate
LEAD_S = 0.07            # s, covers the output LPF plus CAN/firmware transport (~20 ms)
FF_OUTPUT_TAU = 0.15     # s, first-order smoothing of the feedforward itself
R5_CAP = 27000.0         # stay clear of the 30000 rail, where the classic stutter lived (route 154)
R5_CAP_ENVELOPE_FRAC = 0.9

# HondaEpsLateralCore. The feedback path is vfn 35ddc44b's modified-EPS angle PID with the P/I trims the car
# ran on it (2026-09-26, LatPScale 125/100/125, LatIScale 70/95/35), fixed here because the replay validated
# the feedforward against exactly that PID. The output LPF is the NRDR setting (these are the car's values).
MPH_TO_MS = 0.44704
BAND_LOW_MAX = 25.0 * MPH_TO_MS
BAND_STD_MAX = 50.0 * MPH_TO_MS
P_SCALE = (1.25, 1.00, 1.25)
I_SCALE = (0.70, 0.95, 0.35)
OUTPUT_LPF_TAU = (0.07, 0.05, 0.01)
INTEGRATOR_MIN_SPEED = 2.0  # m/s, below this the integrator is held at zero (as vfn)
OVERRIDE_FADE_I_BLEED_TAU = 0.5  # s, upstream 94d287bb: release stale I during override recovery only

# The feedforward asks for the torque that moves the wheel ALONG the desired path, so it is only right
# once the wheel is on it. Engaging mid-turn at low speed routinely starts 20-70 deg off (45 engagements on
# routes 352/353/34f), where it would have pushed against the PID at up to 0.9. So it joins only once the
# angle error is small, then fades in; a driver press or dropping below walking speed takes it out again.
FF_JOIN_ERROR_DEG = 10.0
FF_FADE_IN_S = 0.5
FF_SPEED_BP = [2.0, 4.0]    # m/s, faded in with speed; the desired angle is ill-conditioned near standstill

# At a crawl the feedforward also passes the model's small path wiggles to the wheel 1:1 (target -> wheel gain
# 1.02 measured below 4 m/s on route 361, 0.41 for the PID alone), and column stiction makes that gain grow with
# amplitude, so a near-straight crawl can build a ~0.9 Hz wobble through the camera and the model (route 361
# t 823-829, hands off). Below FF_CRAWL_SPEED_BP the feedforward therefore joins with |desired angle| (none under
# 5 deg, all from 20 deg: every real crawl turn), fading out of effect by 8 m/s so nothing changes at speed.
# Replay of that window through firmware + column plant: wheel/target 1.09 (logged 1.05) -> 0.54 (PID alone 0.51).
FF_CRAWL_ANGLE_BP = [5.0, 20.0]  # deg
FF_CRAWL_SPEED_BP = [5.0, 8.0]   # m/s


class EpsFirmwareCalibration:
  """Per-image command map, P key axis, envelope and rate feedback; no shared mutable state."""

  def __init__(self, e4_per_output, r5_key_bp, r5_v, envelope_bp, envelope_v, r6_per_deg_s,
               *, r5_per_key=None, r6_angle_bp=None, r6_angle_gain=None, kp_key_bp=None, kp_v=KP_V,
               key_clamp=KEY_CLAMP, friction_width_v=FRICTION_WIDTH_V, kff=KFF, scale_q8=SCALE_Q8, p_clamp=None):
    if p_clamp is not None and kff != 0.0:
      raise ValueError("a P clamp with KFF is not modeled")
    self.kff, self.scale_q8, self.p_clamp = kff, scale_q8, p_clamp
    self.e4_per_output = e4_per_output
    # The command-input clamp, the header word just before the row 0 command map: 1663 (E4 3840) on every image here
    # except the CR-V's, which clamp at 1774 (E4 4096).
    self.key_clamp = key_clamp
    self.r5_key_bp, self.r5_v = tuple(r5_key_bp), tuple(r5_v)
    self.envelope_bp, self.envelope_v = tuple(envelope_bp), tuple(envelope_v)
    self.r6_per_deg_s = r6_per_deg_s
    self.r6_angle_bp, self.r6_angle_gain = r6_angle_bp, r6_angle_gain
    self.r5_per_key = r5_per_key
    self.friction_width_v = tuple(friction_width_v)
    # The P row's key axis and values belong to the same firmware image as the command map.
    self.kp_key_bp = tuple(KP_KEY_BP if kp_key_bp is None else kp_key_bp)
    if r5_per_key is not None:
      if self.kp_key_bp != tuple(KP_KEY_BP) or tuple(kp_v) != tuple(KP_V):
        raise ValueError("a linear command map uses the shared Clarity P pieces")
      self.kp_pieces = tuple(KP_PIECES)
    else:
      # Kp(key(R5)) has knots at BOTH maps' breakpoints. Keeping only the P
      # breakpoints would make the quadratic inverse wrong on C020's nonlinear map.
      knots = sorted(set(r5_v) | {float(np.interp(k, r5_key_bp, r5_v)) for k in self.kp_key_bp if k <= r5_key_bp[-1]})
      kps = [float(np.interp(np.interp(r, r5_v, r5_key_bp), self.kp_key_bp, kp_v)) for r in knots]
      pieces = [(lo, hi, kp_lo, (kp_hi - kp_lo) / (hi - lo))
                for lo, hi, kp_lo, kp_hi in zip(knots[:-1], knots[1:], kps[:-1], kps[1:], strict=True)]
      self.kp_pieces = (*pieces, (knots[-1], math.inf, kps[-1], 0.0))
    self.kp_r5_bp = tuple(p[0] for p in self.kp_pieces)
    self.kp_r5_v = tuple(p[2] for p in self.kp_pieces)

  def output_ceiling(self) -> float:
    """Largest useful command before the row ends or the input clamps.

    The CR-V's 4096-count transport reaches its row's last key at E4 3841
    (rounded up); Ridgeline rev b5 reaches its row end at E4 3732. Larger commands add no R5.
    Do not include the speed envelope or change any calibration here.
    Adapted from JamesL787/openpilot 6a2ac5424fb19e4f753badb4e44da6ded3f9542b.
    """
    key = min(self.key_clamp, self.r5_key_bp[-1])
    return min(1.0, math.ceil(key * 4.0 * 32768.0 / 56756.0) / self.e4_per_output)


CLARITY_A020 = EpsFirmwareCalibration(
  E4_PER_OUTPUT, R5_KEY_BP, R5_V, ENVELOPE_BP, ENVELOPE_V, R6_PER_CENTRE_DEG_S,
  r5_per_key=R5_PER_KEY, r6_angle_bp=R6_ANGLE_BP, r6_angle_gain=R6_ANGLE_GAIN,
)
CLARITY_EPS_LOAD = (LOAD_K0, LOAD_K1, LOAD_C, LOAD_FRICTION, LOAD_BIAS, LOAD_KROLL)


def command_key(e4: float) -> int:
  return int(math.trunc(math.trunc(e4 * 56756 / 32768) / 4))


def key_ceiling(v_ego: float, cal: EpsFirmwareCalibration = CLARITY_A020) -> float:
  return min(float(np.interp(v_ego * 3.6 * 2.0, cal.envelope_bp, cal.envelope_v)), cal.key_clamp)


def r5_from_output(output: float, v_ego: float, cal: EpsFirmwareCalibration = CLARITY_A020) -> float:
  """What the firmware makes of a lateral output: forward model of 0xE4 -> key -> R5."""
  key = command_key(-output * cal.e4_per_output)
  mag = float(np.interp(min(abs(key), key_ceiling(v_ego, cal)), cal.r5_key_bp, cal.r5_v))
  return math.copysign(mag, key) if key else 0.0


def output_from_r5(r5: float, cal: EpsFirmwareCalibration = CLARITY_A020) -> float:
  """Inverse of r5_from_output (up to integer truncation)."""
  key = float(np.interp(min(abs(r5), cal.r5_v[-1]), cal.r5_v, cal.r5_key_bp))
  e4 = key * 4.0 * 32768.0 / 56756.0
  return -math.copysign(e4, r5) / cal.e4_per_output


def firmware_kp(r5: float, cal: EpsFirmwareCalibration = CLARITY_A020) -> float:
  if cal.r5_per_key is not None:
    return float(np.interp(abs(r5) / cal.r5_per_key, KP_KEY_BP, KP_V))
  return float(np.interp(abs(r5), cal.kp_r5_bp, cal.kp_r5_v))


def firmware_r6(steering_rate_deg_s: float, angle_deg: float, cal: EpsFirmwareCalibration = CLARITY_A020) -> float:
  """The firmware's rate feedback for a published steering rate at a published angle, clamped where it clamps."""
  gain = 1.0 if cal.r6_angle_bp is None else float(np.interp(abs(angle_deg), cal.r6_angle_bp, cal.r6_angle_gain))
  return max(min(cal.r6_per_deg_s * gain * steering_rate_deg_s, R6_CLAMP), -R6_CLAMP)


def firmware_output(r5: float, steering_rate_deg_s: float, angle_deg: float = 0.0,
                    cal: EpsFirmwareCalibration = CLARITY_A020) -> float:
  """Steady-state firmware output for a target and a rate (D term omitted): scale*(Kp*(R5-R6) + KFF*R5)/1024/256."""
  r6 = firmware_r6(steering_rate_deg_s, angle_deg, cal)
  p = firmware_kp(r5, cal) * (r5 - r6)
  if cal.p_clamp is not None:
    p = max(min(p, 1024.0 * cal.p_clamp), -1024.0 * cal.p_clamp)
  return cal.scale_q8 * (p + cal.kff * r5) / 1024.0 / 256.0


def column_load(angle_deg: float, rate_deg_s: float, v_ego: float, roll: float,
                friction_width: float = FRICTION_WIDTH_DEG_S, coefficients=CLARITY_EPS_LOAD) -> float:
  k0, k1, damping, friction, bias, kroll = coefficients
  return (k0 * angle_deg + k1 * angle_deg * v_ego ** 2 + damping * rate_deg_s
          + friction * math.tanh(rate_deg_s / friction_width) + bias + kroll * roll * v_ego ** 2)


def r5_for_motion(load: float, rate_deg_s: float, r5_guess: float = 0.0, angle_deg: float = 0.0,
                  cal: EpsFirmwareCalibration = CLARITY_A020) -> float:
  """Solve the firmware law for the target that yields `load` while the wheel moves at `rate_deg_s` through `angle_deg`.

  load = scale * (Kp*(R5 - R6) + KFF*R5) / 1024 / 256, with Kp piecewise linear in |R5|. On each piece
  that is a quadratic in R5, so solve every piece exactly and keep the root nearest `r5_guess` (more than
  one root only exists when a fast unwind outruns a small target). A fixed-point iteration is not enough
  here: it is 1-4% off after three passes from rest and need not contract during a fast unwind.
  """
  x = 1024.0 * load * 256.0 / cal.scale_q8
  if cal.p_clamp is not None:
    x = max(min(x, 1024.0 * cal.p_clamp), -1024.0 * cal.p_clamp)
  r6 = firmware_r6(rate_deg_s, angle_deg, cal)
  roots = []
  for lo, hi, kp_lo, slope in cal.kp_pieces:
    for side in (1.0, -1.0):
      # on this piece Kp = a + b*R5, and R5*(Kp + KFF) - Kp*R6 = x
      a, b = kp_lo - slope * lo, slope * side
      qa, qb, qc = b, a + cal.kff - b * r6, -(a * r6 + x)
      if abs(qa) < 1e-12:
        candidates = [-qc / qb]
      else:
        disc = qb * qb - 4.0 * qa * qc
        if disc < 0.0:
          continue
        candidates = [(-qb + sq) / (2.0 * qa) for sq in (math.sqrt(disc), -math.sqrt(disc))]
      roots += [r for r in candidates if lo <= side * r <= hi]
  # g(R5) = R5*(Kp + KFF) - Kp*R6 - x runs from -inf to +inf, so a root always exists
  return min(roots, key=lambda r: abs(r - r5_guess))


class HondaEpsFirmwareFeedforward:
  def __init__(self, dt: float, rate_tau: float = DESIRED_RATE_TAU, lead_s: float = LEAD_S,
               output_tau: float = FF_OUTPUT_TAU, friction_width: float | None = None,
               *, cal: EpsFirmwareCalibration = CLARITY_A020, load=CLARITY_EPS_LOAD):
    self.dt = dt
    self.alpha = dt / (rate_tau + dt)
    self.output_alpha = dt / (output_tau + dt)
    self.lead_s = lead_s
    self.friction_width = friction_width  # None: the speed schedule above
    self.cal = cal
    self.load_coefficients = load
    self.reset()

  def reset(self):
    self.prev_angle = None
    self.rate = 0.0
    self.r5 = 0.0
    self.load = 0.0
    self.output = 0.0

  def update(self, desired_angle_no_offset: float, v_ego: float, roll: float) -> float:
    first = self.prev_angle is None
    if not first:
      raw_rate = (desired_angle_no_offset - self.prev_angle) / self.dt
      self.rate += self.alpha * (max(min(raw_rate, 400.0), -400.0) - self.rate)
    self.prev_angle = desired_angle_no_offset

    angle = desired_angle_no_offset + self.lead_s * self.rate
    width = self.friction_width if self.friction_width is not None else friction_width(v_ego, self.cal.friction_width_v)
    self.load = column_load(angle, self.rate, v_ego, roll, width, self.load_coefficients)
    cap = min(R5_CAP, R5_CAP_ENVELOPE_FRAC * float(np.interp(key_ceiling(v_ego, self.cal), self.cal.r5_key_bp, self.cal.r5_v)))
    self.r5 = max(min(r5_for_motion(self.load, self.rate, self.r5, angle, self.cal), cap), -cap)
    target = output_from_r5(self.r5, self.cal)
    self.output = target if first else self.output + self.output_alpha * (target - self.output)
    return self.output


def speed_band(v_ego: float, values):
  return values[0] if v_ego < BAND_LOW_MAX else values[1] if v_ego < BAND_STD_MAX else values[2]


class HondaEpsLateralCore:
  """Angle PID on the residual + firmware-inversion feedforward, faded in once the wheel is on the path.

  Pure (no messaging, no params), so the closed-loop replay can drive exactly the code the car runs.
  """

  def __init__(self, kp_bp, kp_v, ki_bp, ki_v, dt: float, ff: HondaEpsFirmwareFeedforward | None = None,
               *, p_scale=P_SCALE, i_scale=I_SCALE):
    self.dt = dt
    self.p_scale, self.i_scale = p_scale, i_scale
    self.pid = PIDController((kp_bp, kp_v), (ki_bp, ki_v), pos_limit=1.0, neg_limit=-1.0, rate=1.0 / dt)
    self.ff = ff if ff is not None else HondaEpsFirmwareFeedforward(dt)
    # The NRDR torque-output LPF, run exactly as LatControlPID runs it (the car controller deliberately does
    # not filter, so this is the only one): same filter class, same per-band update_alpha, reset to 0.
    self.output_lpf = FirstOrderFilter(0.0, OUTPUT_LPF_TAU[0], dt)
    self.reset()

  def reset(self):
    self.pid.reset()
    self.ff.reset()
    self.ff_ramp = 0.0
    self.ff_weight = 0.0
    self.since_press_s = math.inf
    self.output_lpf.x = 0.0
    self.output_lpf.initialized = True
    self.output = 0.0

  output_lpf_enabled = True
  output_lpf_tau = OUTPUT_LPF_TAU

  def update(self, desired_angle_no_offset: float, angle_offset: float, angle: float, v_ego: float, roll: float,
             steering_pressed: bool, steer_limited: bool, *, optimized_lane_change: bool = False,
             override_fade_up_s: float = 0.0) -> float:
    error = desired_angle_no_offset + angle_offset - angle
    ff_full = self.ff.update(desired_angle_no_offset, v_ego, roll)

    if steering_pressed or v_ego < FF_SPEED_BP[0]:
      self.ff_ramp = 0.0
    elif self.ff_ramp > 0.0 or abs(error) < FF_JOIN_ERROR_DEG:
      self.ff_ramp = min(1.0, self.ff_ramp + self.dt / FF_FADE_IN_S)
    crawl = float(np.interp(v_ego, FF_CRAWL_SPEED_BP, [1.0, 0.0]))
    crawl_gate = 1.0 - crawl * (1.0 - float(np.interp(abs(desired_angle_no_offset), FF_CRAWL_ANGLE_BP, [0.0, 1.0])))
    self.ff_weight = self.ff_ramp * float(np.interp(v_ego, FF_SPEED_BP, [0.0, 1.0])) * crawl_gate
    # Owner-requested adaptation: no feedforward (including modeled EPS damping)
    # during optimized lane changes. Reset its rejoin ramp to prevent a jump on exit.
    if optimized_lane_change:
      self.ff_ramp = self.ff_weight = 0.0
    ff = self.ff_weight * ff_full

    self.since_press_s = 0.0 if steering_pressed else self.since_press_s + self.dt
    # Limiter feedback arrives one frame late. Only bleed after this controller's existing press detector
    # releases, within the configured recovery window; held presses and unrelated limits still freeze I.
    if (steer_limited and not steering_pressed and override_fade_up_s > 0.0 and
        self.since_press_s <= override_fade_up_s + self.dt):
      self.pid.i *= math.exp(-self.dt / OVERRIDE_FADE_I_BLEED_TAU)

    # Keep anti-windup and both output clamps at the end of the usable row.
    limit = self.ff.cal.output_ceiling()
    self.pid.set_limits(limit, -limit)
    i_scale = speed_band(v_ego, self.i_scale)
    self.pid.update(error, speed=v_ego, feedforward=ff,
                    freeze_integrator=steer_limited or steering_pressed or v_ego < INTEGRATOR_MIN_SPEED,
                    integrator_gain_scale=i_scale,
                    reset_integrator=i_scale <= 0.0 or v_ego < INTEGRATOR_MIN_SPEED)
    output = max(min(self.pid.p * speed_band(v_ego, self.p_scale) + self.pid.i + self.pid.d + ff, limit), -limit)

    if self.output_lpf_enabled:
      self.output_lpf.update_alpha(speed_band(v_ego, self.output_lpf_tau))
      output = float(self.output_lpf.update(output))
    else:
      self.output_lpf.x = output
      self.output_lpf.initialized = True
    self.output = max(min(output, limit), -limit)
    return self.output
