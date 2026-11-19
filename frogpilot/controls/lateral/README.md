# `frogpilot/controls/lateral/` — the lateral geometry ported from dev-111826

What lives here, and what each file is for. Source: `/root/frog/nrdr-111826/openpilot/nrdr/features/lateral/`
(branch `dev-111826`, the build on the car). Plan: `analysis/NRDR-LATERAL-PORT-PLAN-2026-11-18.md` §S2.
Ledger: `analysis/PORT-LATERAL-LEDGER.md` §1a (port status per module), §8 (the parameter table).

| file | source | what it is |
|---|---|---|
| `honda_vgr.py` | `honda_vgr.py` (200 L) | Table A: the EPS's own position map (`_TRW_A020_X/Y`, 30 knots) and the interpolation on it. **Clarity only.** |
| `honda_rack_map.py` | `honda_rack_map.py` (287 L) | `CLARITY_TRW_A020_RACK`: the effective rack ratio by wheel angle measured on this car's VSA yaw, plus `RackMapGeometry` (Table A on the map, angle ⇄ curvature both ways). **Clarity only, one table.** |
| `steer_ratio_tuning.py` | `steer_ratio_tuning.py` (476 L) | The mode enum, `SteerRatioSelection` (both directions, per-frame `VM.sR`), `SteerRatioModeLatch` (requested vs accepted, with `rejected_reason`). |

Nothing in this directory reads Params. `steer_ratio_tuning.py` takes a `LateralSettings` snapshot
(`frogpilot/common/lateral_settings.py`) and calls `int_of("NrdrSteerRatioMode")` — that is the whole
configuration surface. Nothing here is wired into `controlsd` yet (Task 10); the controller that would consume
it (`latcontrol_fw` + `vfn_eps_core`) is Task 8.

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

- Other cars: the Civic / Insight / CR-V / Ridgeline / Odyssey Table A profiles and rack maps, the spec-predicted
  maps and `honda_spec_plant` that predicted them, the RDX identity path. A lookup for another car returns `None`.
- `RawSteerRatioProfile` and the mode-2 curve; the manual center/final edit fields and `STEER_RATIO_METADATA`
  that fed them; `NrdrSteerRatioHybrid` / `hybrid_steer_ratio.py`; `NrdrSteerRatioModelBlend` and
  `model_blend_endpoint` (its keys are not registered here — see ledger §8, they arrive with a later ladder).
- `sunnypilot`, `CarParamsSP`, `HondaFlagsSP`. And no `clarity_mod_eps`: the car's EPS-modified fact is
  `FrogPilotCarParams.flags & HondaFrogPilotFlags.EPS_MODIFIED`.
- `ptm_testing`, which existed only for a Clarity model-blend experiment in the source.
  `ptm_baseline` *is* kept: it selects the biscuit-PTM interpolation grid the actuator model core expects, and
  the consumer passes it (Task 8), the source's controlsd hook does the same at `:104-106`.

## Checking it

```
/root/frog/venv/bin/python analysis/lateral_geometry_probe.py     # the tables equal the source's, field for field
/root/frog/venv/bin/python analysis/lateral_selection_probe.py    # the modes resolve as the table above says
/root/frog/venv/bin/python analysis/test_lateral_geometry.py      # property test: round trip + source equivalence
```

The last two run each tree in its own subprocess (both trees ship a package named `openpilot`) and compare the
two trees' numbers rather than a hand-written expectation.
