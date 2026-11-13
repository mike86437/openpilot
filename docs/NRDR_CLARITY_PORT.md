# Porting the NRDR Clarity lateral work onto FrogPilot

Working branch: `nrdr111326`, based on `FrogAi/FrogPilot@FrogPilot-Testing` (`5382071`, 2026-11-07).
Purpose: run one tree for both cars (Kia EV9 + Honda Clarity, modified EPS) instead of keeping a
separate NRDR install for the Clarity.

Vehicle facts that drive every decision below:

- EPS firmware reported by the car: `39990-TRW,A020` (contains a dash **and** a comma). The car also
  answers a second EPS record, `b'\x0c BK8F162914D'`, which contains **neither**.
- Modified-EPS detection in this tree is `fw.ecu == "eps" and b"," in fw.fwVersion`
  (`opendbc_repo/opendbc/car/honda/interface.py`), so this car takes the `eps_modified` path.
- **Correction (2026-11-13):** which Clarity table that path picks is decided by a *second*, looser test
  — `any(fw.ecu == "eps" and b"-" not in fw.fwVersion)` — and the serial record above satisfies it. So
  this car never reaches the `[[0, 2560, 10240]]` / `kpV 0.3` branch below; it takes the
  `[[0, 2560, 15360]]` / `kpV 0.1575`, `kiV 0.05175`, `kf 4e-05` branch. Verified by decoding
  `CarParamsPersistent` on the device. NRDR's test requires a dash **and** a comma, so it selects the
  `[[0, 5760, 10240]]` / `0.3` / `0.1` pair for this car.

## Applied in this tree

`opendbc_repo/opendbc/car/interfaces.py`, `CarInterfaceBase.get_frogpilot_params`, `elif platform in HONDA:`
— when the candidate is `HONDA_CLARITY`, the tune is still `pid`, and an EPS record carries both a dash and
a comma, set `lateralParams.torqueBP/torqueV = [[0, 5760, 10240], [0, 2560, 3840]]`,
`pid.kpV/kiV = [[0.3]] / [[0.1]]`, `pid.kf = 0.00006` (NRDR's brand default). Not parameter-gated: scoped
to one car by its EPS firmware, revertable with `git checkout 28f6e09`. `honda/interface.py` itself is left
alone — its test is a genuine bug, but correcting it changes every Clarity owner's tune and has to be a
separate, later decision.

Why the knee matters more than the gains: over the first segment, CAN torque per unit of normalized
command is `torqueV[1] * torqueBP[-1] / torqueBP[1]` — `15360` for the branch this car was on, `10240` for
FrogPilot's intended one, `4551` for NRDR's. With gains included, the branch this car was on asked for
**1.77x** more torque per unit of lateral error than NRDR does, at the same 3840 ceiling.

## Already present in FrogPilot — do not re-port

| NRDR behaviour | FrogPilot equivalent |
| --- | --- |
| Clarity FW bank incl. `39990-TRW,A020` (`opendbc/sunnypilot/car/honda/fingerprints_ext.py`) | `opendbc/car/honda/fingerprints.py` already lists `39990,TRW,A020`, `39990-TRW,A020`, `39990-TRW-A020` |
| Clarity mod-EPS PID tune kp `0.3` / ki `0.1`, torque map `…→3840` (`opendbc/car/honda/interface.py` in nrdr/opendbc + `sunnypilot/car/honda/interface_ext.py` `CAR.HONDA_CLARITY: 3840`) | `opendbc/car/honda/interface.py` `eps_modified` Clarity `else` branch: `[[0,2560,10240]] → [[0,2560,3840]]`, `kpV [[0.3]]`, `kiV [[0.1]]` |
| Per-car torque ceiling map | same 3840 ceiling in the tune |
| Learned lateral/vehicle params, steer-ratio learning | stock `LiveTorqueParameters` / `LiveParametersV2` plus FrogPilot's *Advanced Lateral Tuning* (`SteerKP`, `SteerKI`, `SteerKF`, `SteerFriction`, `SteerDelay`, `SteerRatio`, `ForceTorqueController`) |

Only difference left in the base tune: NRDR's torque-map knee is `5760` where FrogPilot's is `2560`,
and NRDR sets `pid.kf = 0.00004` explicitly where FrogPilot inherits `0.00006`.

## Corrections (2026-11-13, evening) — what NRDR actually runs on this car

Read from the tree that is installed at `/data/openpilotnrdr` (`ea5b156`), whose lateral files are
mirrored locally under `/root/frog/nrdr-device/`. Three findings change the ranking below.

### 1. The calm is in the carcontroller, not the latcontroller

NRDR replaces FrogPilot's stock actuator rate limiter outright. FrogPilot
(`opendbc_repo/opendbc/car/honda/carcontroller.py:133`) does
`limited_torque = rate_limit(actuators.torque, last_torque, ±STEER_DELTA_*·DT_CTRL)` with
`STEER_DELTA_UP = STEER_DELTA_DOWN = 3` (`honda/values.py:39-40`) — a hard 0.33 s full-scale slew clamp.
NRDR's `carcontroller.py:218` calls `HondaControllerFeatures.update_steering_torque()`
(`opendbc_repo/opendbc/sunnypilot/car/honda/controller_features.py`) which, between the controller output
and the `STEER_TORQUE_CMD` message, applies:

| stage | NRDR default on this car | effect on the output |
| --- | --- | --- |
| override ramp | `HondaOverrideFadeDownSecs 0.0`, `HondaOverrideFadeUpSecs **1.0**`, reset to 0 whenever `latActive` drops | torque returns over 1 s after every takeover instead of snapping back |
| torque low-pass | `HondaTorqueLowPassFilter` read with default **True**, τ = `0.1 s` below 25 mph, `0.1 s` 25-50 mph, `0.01 s` highway (`alpha = dt/(tau+dt)` = 0.091 at 100 Hz) | attenuates the ringing itself: 0.53× at 3 Hz, 0.32× at 5 Hz |
| delta limiter | `HondaSteerDeltaLimiter` **False** | the stock slew clamp is gone |

A slew limiter cannot reduce the amplitude of a limit cycle, only its edges; a 0.1 s first-order filter
attenuates the amplitude. That is the difference between the bimodal low↔3840 distribution measured in
`0000001c` and a quiet wheel.

### 2. NRDR's tune is a boot-enforced bundle, not a set of gains

`openpilot/sunnypilot/nrdr/handcrafted_lateral.py` holds a profile named
"Honda Clarity-Derived Road-Tested 2026-08-17" (v12) for every modified-EPS Honda, and
`openpilot/selfdrive/car/card.py:120` calls `restore_handcrafted_lateral_profile()` on every start. It is
gated on `NrdrHandcraftedLateralTune`, which `common/params_keys.h:371` declares default **"1"**. So NRDR's
behaviour on this car is deterministic and is *not* what the settings UI appears to show. Inside that profile:

- `NrdrLegacyDualBpSteerRatio = **False**` → `firmware_vgr_selected` becomes true, so the desired angle is
  computed at `VM.sR = 18.50` (the profile's centre value; `steer_ratio_tuning.py`, Clarity endpoints
  18.50 → 12.72 at 250°) and then mapped through the EPS's **own position table** — `honda_vgr.py`,
  `_TRW_A020_X/_TRW_A020_Y`, keyed `("HONDA_CLARITY", "39990-TRW-A020")`, the firmware this car reports —
  blending into the dual-BP curve above 70-90° of angle. FrogPilot commands against one scalar
  `params.steerRatio` (16.5, learned), i.e. a ~12 % standing angle error at centre that P and I must fight.
- `NrdrLearnSteerRatio = False`, `NrdrTuneLearner = False` → the learning that feeds that error is off.
- `NrdrDriverOverrideThreshold = 2000`, `NrdrOverrideThresholdCenterBoost = 1200`
  (`sunnypilot/car/honda/carstate.py`), vs stock 1200 (`car/honda/carstate.py:152`; Clarity is not in
  `honda/values.py:385`). With `NrdrIncreaseOverrideTolerance = False`, the 2000 is used flat.
- `NrdrLatStiction = **True**` (the param's own default is 0; the profile turns it on): `lat_stiction.py`
  TRACK → CAPTURE → HOLD → REACQUIRE, `MAX_TORQUE_REMOVAL = 0.25`, `CAPTURE_DAMPING = 0.008`, holds torque
  while the wheel is quiet, and freezes the integrator whenever it is not in TRACK. It only ever removes torque.
- **Off** in what this car actually ran: `NrdrStarPilotPid = False` (so `_output_scale` never applied),
  all `LatP/I/FScale* = 100` (no speed-banded gains), `NrdrLatRateDamping = 0`, `HondaSteerDeltaLimiter = False`.

Rate damping is therefore **not** a lever to port: its term is `-strength × 0.010 × steeringRateDeg`, which
at strength 0.3 and 100 deg/s is 0.3 of a torque unit against a 3840 ceiling.

### 3. NRDR freezes the integrator during the unwind

`nrdr/latcontrol_pid.py`: `phase, _ = phase_with_latch(desired_no_offset, angle_delta, v_ego, direction)`
(`phase_detector.py`, 6 lines: `phase = angle × angle_delta`, negative while the commanded angle magnitude is
falling) and then `if phase < 0.0 and self.pid.i * error > 0.0: freeze_integrator = True`. FrogPilot's
condition is only `steer_limited_by_safety or CS.steeringPressed or vEgo < 5`
(`selfdrive/controls/lib/latcontrol_pid.py:35`). Same class of fix as stiction, ~6 lines, no parameters.

### What the two measured runs actually contained

`/data/params/d` holds 398 keys and **no `Nrdr*` key of any kind**; the lateral ones are
`LateralTune 1`, `AdvancedLateralTune 0` (so `SteerKP`/`SteerRatio`/`SteerDelay` are unused),
`AlwaysOnLateral 1`, `QOLLateral 1` with `PauseLateralSpeed 0.0` (its only effect), `HondaAltTune 0`,
`MaxLateralAcceleration {}`. Both `0000001a` and `0000001c` were stock-FrogPilot lateral plus the tune
patch. Nothing hidden was active in either run, and there are no NRDR routes on the device to compare with.

## What has to be ported

Re-ranked on 2026-11-13 by observed effect per line of change.

1. **Actuator smoothing in `car/honda/carcontroller.py`** — the τ-banded torque low-pass and the 1 s
   post-override fade-up, replacing the stock `rate_limit` for this car. ~20 lines, Python only, no
   parameters, no build. Directly attacks the limit cycling in fact 46.
2. **Phase-latched integrator freeze** — `phase_detector.py` plus two lines in FrogPilot's
   `latcontrol_pid.py`. Attacks the windup half of the same symptom.
3. **Tunable driver-override threshold** — NRDR `opendbc/sunnypilot/car/honda/carstate.py`:
   `NrdrDriverOverrideThreshold` (default 1400 vs stock 1200), a separate centre-boost threshold and
   centre-angle window, and `sensitive_eps` (`HONDA_CLARITY`, `HONDA_CIVIC`, `HONDA_CIVIC_BOSCH`)
   doubling the threshold under `NrdrIncreaseOverrideTolerance`. This is the piece that decides whether
   a hard takeover registers as `steeringPressed` and therefore whether openpilot keeps commanding
   torque through the override. FrogPilot is stock here:
   `ret.steeringPressed = abs(ret.steeringTorque) > STEER_THRESHOLD.get(self.CP.carFingerprint, 1200)`.
4. **The desired-angle model** — `honda_vgr.py` + `steer_ratio_tuning.py` (~15.5 KB of tables and
   consumers) plus turning steer-ratio learning off for this car. Largest lever on the *setpoint*, largest
   job; do it after 1-2 or the measurement cannot attribute anything.
5. **`NrdrLatStiction`** — `lat_stiction.py` (8.6 KB, TRACK → CAPTURE → HOLD → REACQUIRE). Self-contained
   and ports cleanly, but it changes overshoot feel and is only evaluable once 1-2 are settled.
6. **Clarity hybrid controller + trained model** — NRDR `latcontrol_clarity_hybrid.py` plus
   `neural_network_lateral_control/HONDA_CLARITY.json`. Only selected when `lateralTuning.which() ==
   'torque'` (`controlsd_ext.py:47`), which this car is not. Out of scope.
7. **Rate damping (D term)** — kept for completeness; the coefficient is negligible and it is off in the
   profile NRDR ran.

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
