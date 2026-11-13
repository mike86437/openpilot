# Porting the NRDR Clarity lateral work onto FrogPilot

Working branch: `nrdr111326`, based on `FrogAi/FrogPilot@FrogPilot-Testing` (`5382071`, 2026-11-07).
Purpose: run one tree for both cars (Kia EV9 + Honda Clarity, modified EPS) instead of keeping a
separate NRDR install for the Clarity.

Vehicle facts that drive every decision below:

- EPS firmware reported by the car: `39990-TRW,A020` (contains a dash **and** a comma).
- Modified-EPS detection in this tree is `fw.ecu == "eps" and b"," in fw.fwVersion`
  (`opendbc_repo/opendbc/car/honda/interface.py`), so this car takes the `eps_modified` path.

## Already present in FrogPilot — do not re-port

| NRDR behaviour | FrogPilot equivalent |
| --- | --- |
| Clarity FW bank incl. `39990-TRW,A020` (`opendbc/sunnypilot/car/honda/fingerprints_ext.py`) | `opendbc/car/honda/fingerprints.py` already lists `39990,TRW,A020`, `39990-TRW,A020`, `39990-TRW-A020` |
| Clarity mod-EPS PID tune kp `0.3` / ki `0.1`, torque map `…→3840` (`opendbc/car/honda/interface.py` in nrdr/opendbc + `sunnypilot/car/honda/interface_ext.py` `CAR.HONDA_CLARITY: 3840`) | `opendbc/car/honda/interface.py` `eps_modified` Clarity `else` branch: `[[0,2560,10240]] → [[0,2560,3840]]`, `kpV [[0.3]]`, `kiV [[0.1]]` |
| Per-car torque ceiling map | same 3840 ceiling in the tune |
| Learned lateral/vehicle params, steer-ratio learning | stock `LiveTorqueParameters` / `LiveParametersV2` plus FrogPilot's *Advanced Lateral Tuning* (`SteerKP`, `SteerKI`, `SteerKF`, `SteerFriction`, `SteerDelay`, `SteerRatio`, `ForceTorqueController`) |

Only difference left in the base tune: NRDR's torque-map knee is `5760` where FrogPilot's is `2560`,
and NRDR sets `pid.kf = 0.00004` explicitly where FrogPilot inherits `0.00006`.

## What has to be ported

Ordered by payoff per line of change.

1. **Tunable driver-override threshold** — NRDR `opendbc/sunnypilot/car/honda/carstate.py`:
   `NrdrDriverOverrideThreshold` (default 1400 vs stock 1200), a separate centre-boost threshold and
   centre-angle window, and `sensitive_eps` (`HONDA_CLARITY`, `HONDA_CIVIC`, `HONDA_CIVIC_BOSCH`)
   doubling the threshold under `NrdrIncreaseOverrideTolerance`. This is the piece that decides whether
   a hard takeover registers as `steeringPressed` and therefore whether openpilot keeps commanding
   torque through the override. FrogPilot is stock here:
   `ret.steeringPressed = abs(ret.steeringTorque) > STEER_THRESHOLD.get(self.CP.carFingerprint, 1200)`.
2. **Rate damping (D term)** — NRDR added `output += -(strength * 0.010) * steeringRateDeg * speed_fade`
   in its `latcontrol_pid.py`, defaulted off, with a fade-out speed. The recorded reason: P/I/F are all
   gain knobs and cannot add damping; the Nidec EPS is torque-commanded, so the loop closes around a
   double integrator and rings below ~10 mph where tire damping and `kf * angle * v^2` both vanish.
3. **`NrdrLatStiction`** — NRDR `openpilot/sunnypilot/nrdr/lat_stiction.py` (8.6 KB, default-off
   final-stage overlay, TRACK → CAPTURE → HOLD → REACQUIRE). It only ever *removes* torque, never adds
   or reverses it, and freezes the PID integrator while it owns the output. Self-contained, so it ports
   cleanly, but it changes overshoot feel and should be evaluated only after 1 and 2 are settled.
4. **Clarity hybrid controller + trained model** — NRDR `latcontrol_clarity_hybrid.py` plus
   `neural_network_lateral_control/HONDA_CLARITY.json`. Largest surface, depends on artifacts that only
   exist in the NRDR tree. Out of scope for the first pass.
5. **EPS variant profiles** — NRDR `openpilot/sunnypilot/nrdr/honda_vgr.py`, keyed by
   `("HONDA_CLARITY", "39990-TRW-A020")`. Only worth carrying over if a later step needs per-variant
   maps.

## Checks to run before trusting AlwaysOnLateral on this car

- `selfdrive/controls/controlsd.py` gates `CC.latActive` on `not CS.steerFaultTemporary` even when
  `frogpilotCarState.alwaysOnLateralEnabled` is set, so a `tmp_fault` drops lateral outright.
- `opendbc/dbc/honda_clarity_hybrid_2018_can_generated.dbc` labels `STEER_STATUS` values lowercase
  (`driver_steering`, `no_torque_alert_1`, `no_torque_alert_2`, `tmp_fault`, …) while
  `opendbc/car/honda/carstate.py` compares against uppercase names (`NORMAL`, `LOW_SPEED_LOCKOUT`,
  `NO_TORQUE_ALERT_2`). Confirm on a real route which strings the runtime actually produces; if they do
  not match, every non-zero status becomes `steerFaultTemporary`.
- FrogPilot sets a Clarity-specific safety parameter (`HondaFrogPilotSafetyFlags.CLARITY`, value 64).
  Its panda-side implementation is not in this repository and needs reading before predicting override
  behaviour.

## Bench data already collected for this car (not in this repo)

The NRDR tree holds EPS characterisation recordings that produced the numbers above, e.g.
`eps_tools/rwd/ClarityMax-20260722-1806-FF45-Tracker3200-Norm1650-3840.rwd` and
`eps_tools/rwd/Clarity-1663.rwd`. Keep them; they are the evidence behind the tune, not code to port.
