# `frogpilot/controls/lateral/` — the lateral stack ported from dev-111826

What lives here, and what each file is for. Source: `/root/frog/nrdr-111826/openpilot/nrdr/features/lateral/`
(branch `dev-111826`, the build on the car). Plan: `analysis/NRDR-LATERAL-PORT-PLAN-2026-11-18.md` §S2, §S3.
Ledger: `analysis/PORT-LATERAL-LEDGER.md` §1a (port status per module), §1a.1 (the shared-library facts the
S3 copies depend on), §8 (the parameter table).

| file | source | what it is |
|---|---|---|
| `honda_vgr.py` | `honda_vgr.py` (200 L) | Table A: the EPS's own position map (`_TRW_A020_X/Y`, 30 knots) and the interpolation on it. **Clarity only.** |
| `honda_rack_map.py` | `honda_rack_map.py` (287 L) | `CLARITY_TRW_A020_RACK`: the effective rack ratio by wheel angle measured on this car's VSA yaw, plus `RackMapGeometry` (Table A on the map, angle ⇄ curvature both ways). **Clarity only, one table.** |
| `steer_ratio_tuning.py` | `steer_ratio_tuning.py` (476 L) | The mode enum, `SteerRatioSelection` (both directions, per-frame `VM.sR`), `SteerRatioModeLatch` (requested vs accepted, with `rejected_reason`). |
| `pid.py` | `pid.py` (15 L) | `FeedforwardPIDController`: this tree's `common.pid.PIDController` with the feedforward multiplied by `k_f` on the way in. | 
| `integral_pid.py` | `integral_pid.py` (32 L) | `IntegralScaledPIDController`: scales `k_i`, not the stored integral; `update_lateral` is the decision table (which conditions freeze the integrator, which reset it). **This is the class `vfn_eps_core` imports *as* its `PIDController`.** | 
| `torque_output_filter.py` | `torque_output_filter.py` (39 L) | `HondaTorqueOutputFilter` + `torque_lpf_tau`: the comfort output LPF and its 25 mph / 50 mph bands. |
| `vfn_eps_core.py` | `vfn_eps_core.py` (608 L → 441 L) | **The actuator model**: the command map and its key clamp, the firmware P row as pieces over \|R5\|, the speed envelope, `R6` derived from the image's own Table A, the column load model, the piecewise-quadratic solve `r5_for_motion`, `EpsFirmwareCalibration` + `CLARITY_A020`, and the two classes the controller composes (`HondaEpsFirmwareFeedforward`, `HondaEpsLateralCore`). **Clarity only: one calibration object.** |
| `yaw_control_timing.py` | `yaw_control_timing.py` (66 L) | **Model-side prediction delay** (`DELAY_SCHEDULE_BP/V`, `prediction_delay_schedule`) and the controller's **command-delay line** (`CommandDelay`, a fixed-rate 0.30 s buffer read by linear interpolation). **Clarity only: one prediction row, one command-delay row.** |
| `model_source.py` | `model_source.py` (55 L) | Which model output the curvature came from (`lateral_source`), which input carried the told delay (`delay_input`), `PTM_LAT_SMOOTH_SECONDS` / `CMD_DELAY_RAMP_S`, and `ModelActionRamp` (the 20 Hz action interpolated across 100 Hz frames). Names shared with the `Action` stamps in `cereal/log.capnp`. |
| `controller_selection.py` | `controller_selection.py` (130 L) | **The admission**: the `(fingerprint, EPS firmware)` table, the four conditions on top of it, and the profile record (`name`, `calibration`, `prediction_schedule`, `provisional`, `required_rwd`). **Clarity only: one entry.** |

## The three PID helpers (S3)

The actuator model (`vfn_eps_core`, ported in the same stage) is built out of these three, so they come across
or the core does not.
`integral_pid.py` and `torque_output_filter.py` are byte-identical to the source apart from their module
docstrings; `pid.py` is the same syntax tree with the `Gain` annotations dropped, because this tree's
`common/pid.py` does not export that name (ledger §1a.1: it wraps a scalar gain as `[[0],[k]]` where dev-111826
wraps it as `([0],[k])`, and its `update`/anti-windup/`k_i` are otherwise identical). No edit was made to this
tree's `common/pid.py`, and no `Gain` alias was invented to make the annotations compile.

`torque_output_filter.update`'s `live` argument is duck-typed on the source's live-torque-edit keys
(`torque_lpf_enabled`, `lpf_tau_low / …_standard / …_highway`). **None of those keys is registered in this port**
(ledger §8). The parameter is kept as the source wrote it rather than flattened into three floats, so the day a
live-tuning snapshot exists it can be passed straight in; until then a caller must supply an object with those
attributes. That is Task 10/19's job, not this file's.

## The actuator model (`vfn_eps_core.py`)

Copied first, then narrowed — the order matters because a re-typed table is where a port loses a digit. What was
removed is whole blocks: eleven images' `EpsFirmwareCalibration` objects, their load fits, their Table A-derived
`R6` shapes and their P/I trims (178 lines), plus the `rdx_rack` import and the measured-RDX member of
`computed_r6`'s parameter type. Every def and class that survived is the source's syntax tree with annotations
dropped — measured, not asserted, by `analysis/lateral_core_tables_probe.py`.

It is **pure**: no capnp, no Params, no `selfdrive`, no modeld — plain values in, plain values out, which is what
makes the frame-for-frame equivalence harness (Task 18) possible. The angle-PID gains it gets constructed with
(`GAIN_BP`/`KP`/`KI`, `latcontrol_fw.py:28-30`) belong to the controller, not to this file; `P_SCALE`, `I_SCALE`,
`INTEGRATOR_MIN_SPEED` and `OUTPUT_LPF_TAU` are the core's own constants and are the source's verbatim.

`vfn_geometry.py` and `vfn_rack_map.py` are deliberately **not** ported: in the source each is imported only by
`nrdr/tests/test_cleanup_policy.py`, and what they build is what `honda_vgr.ptm_inverse` already builds here —
which is exactly the call `computed_r6` makes.

Nothing in this directory reads Params. `steer_ratio_tuning.py` takes a `LateralSettings` snapshot
(`frogpilot/common/lateral_settings.py`) and calls `int_of("NrdrSteerRatioMode")`; `controller_selection.py` takes the
same snapshot for `NrdrLateralController` and an `FrogPilotCarParams` for the EPS-modified fact. That is the whole
configuration surface. Nothing here is wired into `controlsd` yet: admission exists (Task 10) and can be printed from
a boot log by `analysis/ptm111826_boot_check.sh`, but the controller that would consume the selection and the
admitted profile (`latcontrol_fw`) is Task 19, behind this core.

## The timing layer (S4)

Two kinds of delay, and only one of them is a number this car would ever tune:

* **Prediction delay** — `DELAY_SCHEDULE_BP (3.5, 7, 12, 20, 30) m/s` over `DELAY_SCHEDULE_V (0.15, 0.08, 0.10,
  0.20, 0.30) s` is the Clarity's measured row. `prediction_delay_schedule(profile)` returns it for a profile that
  asks for one and `None` otherwise, and `None` is what this tree sees today: nothing in `modeld` calls it yet,
  because the profile does not exist until admission (Task 10). What Task 10 swaps is the *value* of
  `lat_delay`, not the mechanism — this tree already composes `lat_delay + DT_MDL + action_delay` and hands it to
  `get_action_from_model` (`selfdrive/modeld/modeld.py:435`), which is the same arithmetic the source writes as
  `lat_action_t = lat_delay + frame_delay + action_delay` (ledger §2 D4; measured both ways by
  `analysis/lateral_timing_probe.py`, which evaluates each tree's own expression rather than quoting it).
* **Command delay** — `COMMAND_DELAY_ENDPOINTS["clarity_a020"] = (0.20, 0.10)` over `(10.0, 15.0) m/s`, read
  through `CommandDelay`. Where it is applied is `latcontrol_fw` (Task 19), and there the source first scales it:
  `_command_delay` drives `cmd_delay_scale` to **zero** whenever `action.lateralSource == plan` and back to the
  calibration otherwise (`latcontrol_fw.py:86-92`). This tree's models all read the plan, and the real
  dev-111826 drive on this car says so too (`plan` on 48 325 of 48 325 model frames), so the honest expectation
  is that the command delay ramps out here. Both directions are implemented and tested from the ramp itself —
  a mechanism shipped one way is half a mechanism.

These are calibration data, not settings: `command_delay` accepts its `settings` argument and ignores it exactly
as the source wrote it, and the retired `NrdrYawCommandDelayLow/High` (0.145 / 0.125 on this car) is not read
by anything here and is not registered here (ledger §8).

## Admission (`controller_selection.py`, S5)

Everything above is a capability. Admission is the question "does this car qualify, and which calibration is it
qualified *to*" — and it is the gate the rest of the port is judged against, because the actuator model, the geometry
and the delay schedules are all keyed to one calibration id.

The admission is the source's, unchanged in structure: a `(carFingerprint, normalized EPS firmware)` lookup, and on top
of it four conditions — the car's EPS reports as modified, this tree holds a measured Table A for exactly that
fingerprint+firmware pair, the CarParams asks for a `pid`-shaped lateral tune, and `NrdrLateralController` is 1 or 2.
For this Clarity all four answer yes from data the car itself reports: `HONDA_CLARITY` + `39990-TRW,A020` →
`Clarity A020`, calibration `clarity_a020`, `prediction_schedule=True`, `provisional=False`, `required_rwd=-` — the
same answer the source tree prints on the car today (ledger §5), proved side by side in
`analysis/lateral_admission_probe.py` (34/34).

**One substitution, stated plainly:** the source reads the EPS-modified fact from `CarParamsSP.flags &
HondaFlagsSP.EPS_MODIFIED` (value 2). This tree has no `CarParamsSP` (D1), so it reads
`FrogPilotCarParams.flags & HondaFrogPilotFlags.EPS_MODIFIED` (value 1) — the bit its own
`CarInterfaceBase.get_frogpilot_params` writes from the same `carFw`, from the same test
(`fw.ecu == "eps" and b"," in fw.fwVersion`) the Honda interface already uses for its tuning. Different object,
different bit value, same decision; the probe compares the decision and never the number.

**What admission does not do.** It enables nothing. `controlsd` still constructs this tree's own lateral controller
until Task 19 puts `latcontrol_fw` behind it (ISC-3). The `NrdrLateralController` read is the source's own two states
(1 = the model, 2 = the model plus its measurement trace) read through `lateral_settings.py` as a registered INT;
unset, `0`, out of range or unparseable is 0, i.e. this tree's stock controller — the same rule the mode ladder uses
(`_mode_value`), which is why the probe can compare the two trees' answers for every parameter state.

`required_rwd` is carried, never checked: it names the corrected-PTM build a calibration models by RWD SHA-256 prefix,
and admission cannot see a flash. The Clarity's is empty, so `provisional=False` means "this family is exactly what
the calibration models", **not** "the build in this car is known" — that is still walk §8.2's open question, and only
a drive (`epsFfR5` against 0xE4) can close it.

Nothing in the file names another car. The other twelve profiles, `rdx_identity` (whose `confirmed_rdx` gate needs an
owner receipt that does not exist — `RDX_ROUTE_A_SHA256` is `None`), and `PTM_EPS_REVISIONS` are not ported. The last
one is not a judgement call: that map holds `HONDA_RIDGELINE` and `HONDA_ODYSSEY` only
(`opendbc/sunnypilot/car/honda/values_ext.py:14-17`), so its "the reported version must be the revision this
calibration models" gate has never once applied to a Clarity. `analysis/lateral_admission_probe.py` prints that lookup
and prints each of the five fleet cars the source's thirteen-entry table answers and this one-entry table cannot.

## The settings surface (`lateral_settings.py`, S5)

Nothing in this directory is a settings file, and it stays that way: the two keys are read through
`frogpilot/common/lateral_settings.py` snapshots, and they are *offered* in The Pond's `lateral_settings.py` panel —
two `select` rows at Driving Controls → STEERING → Advanced Lateral Tuning (`order` 8, 9), each gated on
`firmware_lateral_visible`, which is `context.car_reason(context.can_use_firmware_lateral)` and nothing more. That
car fact is computed once, in `FrogPilotVariables.update()`, from `FPCP.flags & HondaFrogPilotFlags.EPS_MODIFIED` and
`CP.lateralTuning.which() == "pid"` — the car-side half of the admission above, written with this tree's own enum —
and copied onto the Pond `Context` exactly like every other car fact, so the panel reads no Params of its own.

What each row offers is only what this tree can honour: the controller row offers 0 (this tree's own controller) and 1
(the measured EPS model Task 19 will build); 2 is not offered because no testing variant exists yet. The geometry row
offers 0 and 3; 1 is left out because for this car it is numerically the car's own ratio, and 2 because this tree
refuses it (table below). Both ask for a reboot `on_change`, since `controlsd` builds the controller at startup. A
`manage` subgroup is deliberately not added for them: every `manage` row in this panel is gated on a registered
parameter, and a grouping-only key would be a knob nothing reads.

`analysis/lateral_ui_probe.py` reads the rows out of the panel's own syntax tree, the registrations out of the header
the car compiles, runs the visibility helper as written on a car it can and cannot admit, and asks
`firmware_controller_selected` / `firmware_controller_testing_selected` / `resolve_steer_ratio_selection` what each
offered value actually does.

## Lane-change policy (`lane_change_tuning.py`, S6)

One line: in this tree the **request shaping is inert, and it is inert because the source made it inert**; the
thing that is not inert is the **gate**, and its caller is Task 19.

`LaneChangeEntry` and `shape_lane_change_curvature` are the source's code unchanged, and they cannot change a
curvature here: the entry reduction both trees read is `OPTIMIZED_VALUES["NrdrLaneChangeEntrySrReduction"]`, and
the source fixed it to `0.0` — in both of its tables, with its own comment "Keep the selected geometry/request
unchanged, including with legacy saved values". `onset` needs `requested > 0.0`, so no envelope is ever armed,
`applied` is `0.0` on every frame, and the shaping returns `desired_curvature` at its first line. The source's
tests agree with that (`test_optimized_entry_keeps_the_current_steering_ratio` expects 200 frames of `0.0`);
one of them has drifted from its own code and **fails at `4a806bf`** (`test_lane_change_retired_sliders…`
expects `5`, gets `0.0`). §B and §C of the gate run the tables and the source's own suite in both trees instead of
taking either on faith. The
shaping machinery is still ported whole, and tested at reductions 3 and 5, because the rule it encodes —
reshape only through the selected geometry, restore `VM.sR`, never amplify or reverse a request — is what a
reduction would have to obey if one ever existed.

What the five fixed values do in each tree:

| key | value (both tables) | source: who reads it | this tree |
|---|---|---|---|
| `NrdrLaneChangeEntrySrReduction` | `0.0` | `LaneChangeEntry.onset` | read, always `0.0` → nothing |
| `NrdrLaneChangeEntryReturnTime` | `1.0` | the envelope's return ramp | read, unreachable (`reduction` is 0) |
| `NrdrLaneChangeMinTime` | 0.5 / 1.0 | `desire_helper.py:82` (lane-change state machine) | **nothing** — this tree's knob for the same thing is FrogPilot's own `LaneChangeTime` → `toggle.lane_change_delay` → `desire_helper.py:91,94`; no second knob is registered |
| `NrdrLaneChangeTorqueFactor` | 2.0 / 1.0 | `nrdr/features/driver_policy/lane_change.py` | **nothing** (not a lateral module, not ported) |
| `NrdrLaneChangeFrictionPercent` | 0.0 / 100.0 | fallback `latcontrol_torque.py:100` | **nothing** (D5: no fallback path) |

The table is kept complete for the same reason `torque_output_filter.py` kept its duck-typed `live` argument:
flattening it would rewrite the source's policy while looking like a copy. The one function that is *not* the
source's is `optimized_lane_changes_enabled`: it reads `NrdrOptimizedLaneChanges` through
`LateralSettings.bool_of`, so an unset key is off here (ISC-3) where the source defaults it on
(`nrdr/params/profiles.py:252`, which is what this car has saved — measured: `NrdrOptimizedLaneChanges=1`,
`LaneGuidanceMode=0`, `LaneCentering=0`). A comparable drive states the key in both trees, as it must for
`NrdrSteerRatioMode` (D8).

`optimized_lane_change_active` is the reason this file exists in the port. The source's controller calls it per
frame (`latcontrol_fw.py:135`) and hands the result to the core, which for the duration of a `starting` or
`finishing` maneuver drops the feedforward — including the modeled EPS damping — and zeroes its rejoin ramp so
the exit does not jump (`vfn_eps_core.py:579-582`). That branch is already in this tree's core and was run
inside V20's equivalence frames; what is missing is the caller, and Task 19 is where it is reached, with the
`LateralSettings` snapshot this module reads and the `modelV2` this tree's `controlsd.py` already passes to
`LaC.update`. `state` is the capnp enum's `.raw` (`cereal/log.capnp:447-452`: off 0, pre 1, starting 2,
finishing 3) — waiting for a nudge is not yet a lane change, which is the source's rule, kept.

## The mode table

`SteerRatioMode` keeps the source's four numbers and labels verbatim. What each one *does* in this tree:

| value | label | geometry this tree runs | notes |
|---|---|---|---|
| 0 | `Manual override` | **Stock.** `VehicleModel` from `CP.steerRatio` + this tree's own lateral tuning. `effective_mode = None`. | Registered default (`common/params_keys.h`, `STOCK_DEFAULTS`). The one deliberate divergence from the source, which falls back to FIRMWARE for 0 (`steer_ratio_tuning.py:367-368`) because that fork's default is 3. Here a default never changes a control number (ISC-3). |
| 1 | `Comma’s Learner (Legacy)` | `CP.steerRatio`, no measured map. | Numerically the same as 0 for this car. It exists so a drive can be *reported* against stock geometry. |
| 2 | `NRDR measured-angle curve` | **Refused** → stock, `unavailable_reason` records it. | `RawSteerRatioProfile` / `CLARITY_RAW_STEER_RATIO` is a second geometry source with its own parameter; not ported, not registered. |
| 3 | `PTM (Auto)` | **Measured:** Table A on `CLARITY_TRW_A020_RACK`, both directions, its slip factor used in the speed-aware paths. | The value a comparable drive must set. Matched on fingerprint + reported EPS firmware (`39990-TRW,A020` → `39990-TRW-A020`); no car-specific helper. |

`resolve_steer_ratio_selection` never substitutes a nearby car's geometry. If the lookup does not answer — a
different Honda, a different EPS image, a `carFw` that does not report the EPS — the selection is stock with a
reason, and the reason is what the boot probe prints.

## What is deliberately not here

- Other cars: the Civic / Insight / CR-V / Ridgeline / Odyssey / RDX Table A profiles and rack maps, the
  spec-predicted maps and `honda_spec_plant` that predicted them, the RDX identity path, and in the core the
  eleven non-Clarity `EpsFirmwareCalibration` images with their load fits, `R6` shapes and P/I trims. A lookup for
  another car returns `None`, and the core holds exactly one calibration object. In admission the same rule: one
  `_PROFILES` entry against the source's thirteen, twelve profile objects not constructed, and `PTM_EPS_REVISIONS`
  left out because it holds no Clarity entry to gate.
- `RawSteerRatioProfile` and the mode-2 curve; the manual center/final edit fields and `STEER_RATIO_METADATA`
  that fed them; `NrdrSteerRatioHybrid` / `hybrid_steer_ratio.py`; `NrdrSteerRatioModelBlend` and
  `model_blend_endpoint` (its keys are not registered here — see ledger §8, they arrive with a later ladder).
- `sunnypilot`, `CarParamsSP`, `HondaFlagsSP`. And no `clarity_mod_eps`: the car's EPS-modified fact is
  `FrogPilotCarParams.flags & HondaFrogPilotFlags.EPS_MODIFIED`.
- The **low-speed action clamp** `action[0,0] / max(2.5, v)**2` (`modeld.py:72` there). It is not an omission:
  it sits on the source's *action-head* branch, and this tree has no action head at all — no
  `model_output['action']`, no `actionHead` outside the schema enum, no action constant in `ModelConstants`. The
  plan path both trees do share is the same `curv_from_psis` with the same `MIN_SPEED = 1.0` floor, and with the
  source's PTM setting (`min_stable_delay = 0.0`) its plan conversion produces this tree's numbers on every
  speed/horizon point tested. Adding a 2.5 m/s floor here would be inventing a second one. Measured, not
  assumed: `analysis/lateral_timing_probe.py` checks 13a–13f.
- The other twelve images' command-delay rows and the five other prediction rows (`_PREDICTION_SCHEDULE_V` is
  empty here because in both trees the Clarity *is* the default row). A calibration not kept raises `KeyError`
  rather than borrowing the Clarity's numbers.
- `Action.laneGuidanceMode @6` and `Action.ptmTimingRestored @7`, **left undefined and written down as reserved**
  in `cereal/log.capnp` (`cereal/log.capnp:1265-1275`). Decided at S6: this tree carries neither. Centring here
  is model centring — `lane_centering.py` is not ported (D5), so the source's own honesty mechanism, demoting
  BLENDFUL to MODEL_ONLY every frame it cannot serve it (`modeld.py:479-483`), has nothing to demote, and a
  field that could only ever be stamped with one value is a name for a knob that does not exist. `@7` names a
  legacy-timing restoration nothing in this tree does. Both ids stay free: something else landing at `@6` is the
  struct-field version of the `@151`/`@71` Event-union trap.
- `lane_guidance.py` (138 L): the mode enum, its parsing, its backup/restore and the per-frame model-atomic
  arbitration. Not ported because the only mode this tree could run is MODEL_ONLY (the car's
  `LaneGuidanceMode=0`, and no centring code exists to blend with), the callers are the source's `modeld`,
  `controlsd_ext`, its two settings UIs and sunnylink — none of which exists here — and the field that would
  carry its answer (`@6`) is reserved above. What *is* stated is the consequence: centring in this tree is model
  centring, written in the reservation.
- `phase_detector.py` (8 L). Its only consumer in the source is `latcontrol_pid.py:23` (the fallback path, D5) —
  everything else is `features/lateral/__init__.py`'s re-export, a legacy shim and its own tests. An 8-line
  helper with no caller here is inert code.
- the source's **caller**: `nrdr/hooks/controlsd.py:142-165`, `lane_change_request(...)`, which builds the entry
  envelope per control frame and calls `shape_lane_change_curvature`. Not wired, because that call cannot change
  a curvature: `requested` is the fixed `0.0` and `onset` requires `requested > 0.0`, so `reduction` is `0.0` and
  the shaping returns its input (measured over 618 frames in both trees, `lateral_lane_change_probe.py` §C).
  Wiring it would add a per-frame call, a `steer_ratio_latch`/`sm.all_checks` dependency and a
  `record_applied_settings("lane_change_entry", …)` report to this tree's controlsd for an output that is always
  the input. The live half of lane-change policy is the **gate** — `optimized_lane_change_active` — and its
  caller is `latcontrol_fw` (Task 19), which is where the envelope gets a home if it ever gets a reason.
- the **model-eligibility half** of `optimized_lane_changes_enabled` (`OPTIMIZED_MODEL_FAMILIES`, the 16
  `OPTIMIZED_MODEL_REFS`, the `is_big`/chestnut exclusions): no carrier here. The only model row this tree writes
  has three keys — id, name and `lat_smooth_seconds` — and whatever else the remote list carries is dropped at that
  line (`frogpilot/system/model_manager.py:116-121`), so there is no family, no ref hash, no big-model flag and no
  chestnut to test. Refusing it cannot disagree with the source on this car: there
  is no `ModelManager_ActiveBundle` parameter here at all, and the source's own no-bundle default ref is in its
  own admitted list. Reasoning and measurements in `lane_change_tuning.py`'s header and
  `lateral_lane_change_probe.py` §E; if a drive ever shows a model that must not get the adaptation, this tree's
  convention is a named model set beside `ACTION_DELAY_MODELS` / `MIN_STABLE_DELAY_MODELS`
  (`frogpilot/common/frogpilot_variables.py:107-111`) — arriving with the measurement.
- No `NrdrLaneChange*` key is registered (`common/params_keys.h` is still exactly the seven from Task 6), and no
  Pond row for `NrdrOptimizedLaneChanges` yet. Both arrive with the consumer that acts on them (Task 19), for the
  same reason `NrdrSteerRatioModelBlend` is not registered: a key or a row that nothing acts on is a knob a user
  cannot tell the difference about.
- `ptm_testing`, which existed only for a Clarity model-blend experiment in the source.
  `ptm_baseline` *is* kept: it selects the biscuit-PTM interpolation grid the actuator model core expects, and
  the consumer passes it (Task 19), the source's controlsd hook does the same at `:104-106`.

The ledger (`analysis/PORT-LATERAL-LEDGER.md` §1a) carries a status line for every module in the source
directory, ported or not, so nothing above is an unrecorded omission.

## Checking it

```
/root/frog/venv/bin/python analysis/lateral_geometry_probe.py     # the tables equal the source's, field for field
/root/frog/venv/bin/python analysis/lateral_selection_probe.py    # the modes resolve as the table above says
/root/frog/venv/bin/python analysis/test_lateral_geometry.py      # property test: round trip + source equivalence
/root/frog/venv/bin/python analysis/lateral_pid_probe.py          # the three helpers, replaying the source's own tests
/root/frog/venv/bin/python analysis/lateral_timing_probe.py       # the timing layer: schedules, delay line, action ramp,
                                                                 # the horizon each tree composes, the schema and both drives
/root/frog/venv/bin/python analysis/lateral_admission_probe.py     # the admission: the same car, both trees, the same
                                                                 # profile — and every refusal condition refused
/root/frog/venv/bin/python analysis/lateral_ui_probe.py          # the settings surface: what each offered option
                                                                 # selects, the registry behind it, who is offered it
/root/frog/venv/bin/python analysis/lateral_lane_change_probe.py  # lane-change policy: the module against the source's
                                                                 # (def for def), the fixed 0.0 in both tables and the
                                                                 # source's own red test, 17 scenarios + 405 shaped
                                                                 # cases through each tree's own geometry, the model
                                                                 # catalog both ways, and that nothing moved in the
                                                                 # control path
```

`lateral_timing_probe.py` also settles two things that are easy to get wrong from the source's file list alone:
that the low-speed action clamp has nowhere to land in this tree, and that a dev-111826 drive reads under this
tree's schema field for field — which is what will let the source's own tools read a port drive (Task 12).

The last two run each tree in its own subprocess (both trees ship a package named `openpilot`) and compare the
two trees' numbers rather than a hand-written expectation.
