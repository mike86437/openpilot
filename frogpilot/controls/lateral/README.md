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
(`frogpilot/common/lateral_settings.py`) and calls `int_of("NrdrSteerRatioMode")` — that is the whole
configuration surface. Nothing here is wired into `controlsd` yet (Task 10); the controller that would consume
it (`latcontrol_fw`) is Task 19, behind this core.

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
  another car returns `None`, and the core holds exactly one calibration object.
- `RawSteerRatioProfile` and the mode-2 curve; the manual center/final edit fields and `STEER_RATIO_METADATA`
  that fed them; `NrdrSteerRatioHybrid` / `hybrid_steer_ratio.py`; `NrdrSteerRatioModelBlend` and
  `model_blend_endpoint` (its keys are not registered here — see ledger §8, they arrive with a later ladder).
- `sunnypilot`, `CarParamsSP`, `HondaFlagsSP`. And no `clarity_mod_eps`: the car's EPS-modified fact is
  `FrogPilotCarParams.flags & HondaFrogPilotFlags.EPS_MODIFIED`.
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
```

The last two run each tree in its own subprocess (both trees ship a package named `openpilot`) and compare the
two trees' numbers rather than a hand-written expectation.
