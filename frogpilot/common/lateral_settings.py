"""Settings reader for the lateral control ported from dev-111826.

Scope, on purpose (analysis/PORT-LATERAL-LEDGER.md §2 D3/D6, plan §4): this is the *read shape* the
ported stack uses - one object per control-loop frame, `settings.get(key)` everywhere else - and nothing
more. The source's parameter registry (nrdr/params/{specs,profiles,snapshots,tuning_policy}.py, 1 487 LOC)
is not ported, and neither is a second config system: the keys live in this tree's own registry
(common/params_keys.h) and are read through openpilot.common.params.

Three rules this file exists to enforce:
  1. Storage is touched once per snapshot, never inside a control loop (see LateralSettingsSource).
  2. An unset key resolves to THIS tree's stock behaviour (STOCK_DEFAULTS, all off/zero), so a car that
     never enables the port runs its own lateral controller. The source's profile defaults are kept as
     SOURCE_REFERENCE - the numbers a ported drive has to reproduce - and are never applied.
  3. Key names are the source's (`Nrdr*`), which is what lets the boot probe, drive notes and
     analysis/* tools run unchanged against both trees.
  4. A key this tree has no code path for is still *reported*, but never presented as honoured. Lane centring is
     that case: centring in this tree is model centring (plan §4, ledger D5 - `selfdrive/controls/lib/lane_centering.py`
     is not ported), so `LaneGuidanceMode` 1 and 2 select nothing and the three `LaneCentering*` keys are read by no
     control path. `describe()` prints their values like every other key, so what carries the truth is this file's
     own comment on each one and `frogpilot/controls/lateral/README.md`; the source's mechanism for the same honesty
     - demoting `BLENDFUL` to `MODEL_ONLY` per frame (`modeld.py:479-483` there) - has nothing to demote here,
     because the answer is `MODEL_ONLY` before the parameter is read. Task 11 / S6.
"""
from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from openpilot.common.params import Params
from openpilot.common.params_pyx import UnknownKeyName

# Same bound as the source's polling cycle (nrdr/params/snapshots.py:6): a saved tuning edit reaches a
# running control loop within about half a second, and the actuation loop never waits on storage.
REFRESH_PERIOD = 0.5

# The keys this port reads. Registered in common/params_keys.h under these exact names.
LATERAL_KEYS: tuple[str, ...] = (
  "NrdrLateralController",
  "NrdrSteerRatioMode",
  "NrdrOptimizedLaneChanges",
  "HondaDriverAssistDuringOverride",
  "HondaOverrideFadeDownSecs",
  "HondaOverrideFadeUpSecs",
  "HondaOverrideTorqueScale",
  "LaneGuidanceMode",
  "LaneCenteringMinSpeed",
  "LaneCenteringStrength",
  "LaneCenterOffset",
)

# Unset = what this tree does today (ISC-3). Kept in the same order as LATERAL_KEYS so the two can be
# diffed by eye and by test; analysis/lateral_settings_probe.py asserts common/params_keys.h agrees.
STOCK_DEFAULTS: dict[str, Any] = {
  "NrdrLateralController": 0,        # 0 -> this tree's own LatControlPID / LatControlTorque (controlsd.py:65-70); 1 asks for the port's controller, and controlsd builds it only where the admission also accepts the car (controlsd.py:89-95)
  "NrdrSteerRatioMode": 0,           # 0 -> the car's own ratio. controlsd resolves the ported ladder every frame (controlsd.py:140-157); 0/unset answers "Stock car ratio (safe fallback)", 3 answers this car's measured EPS and rack map (D8)
  "NrdrOptimizedLaneChanges": False,  # the live lane key: arms the controller's lane-change gate (lane_change_tuning.py, reached from latcontrol_fw - controlsd hands it the snapshot this reader produces). No Pond row yet: with a code path in place, presenting it is a change of its own. The source defaults it ON (profiles.py:252, and this car has 1); unset is off here, so a comparable drive states it (D8)
  "HondaDriverAssistDuringOverride": False,  # the source's "Assist Pass-Through" switch: with it on, the assist hands the wheel over while the driver is in it. Unset = today's behaviour, where assist continues through an override (override_ramp.py, read by the Honda car controller)
  "HondaOverrideFadeDownSecs": 0.1,  # seconds the command fades to the floor when a press starts. Harmless on its own: with the stock floor of 100 % there is nothing below it to fade to
  "HondaOverrideFadeUpSecs": 0.0,    # seconds the command returns to full after the press ends, and from zero on a fresh lateral activation. 0.0 here because the source's 1.0 is not inert: its ramp starts every activation at zero and climbs for a second, which is not what this tree does today
  "HondaOverrideTorqueScale": 100,   # percent of the command that survives the fade-out. 100 here is the inert value: the ramp multiplies by 1.0 in both directions. The source registers 0 (specs.py:197), which is its own full removal
  "LaneGuidanceMode": 0,             # MODEL_ONLY, and 1/2 select nothing: centring here is model centring (rule 4). The car reports 0 and LaneCentering=False today
  "LaneCenteringMinSpeed": 0,        # registered only, read by no control path: centring is deliberately not wired (D5)
  "LaneCenteringStrength": 0.0,      # registered only, read by no control path: centring is deliberately not wired (D5)
  "LaneCenterOffset": 0.0,           # registered only, read by no control path: centring is deliberately not wired (D5)
}

# Reference only - the source's own profile defaults (nrdr/params/profiles.py:268, specs.py:112-140).
# Printed by describe() so a drive can be compared against the source run mode; never used as a default.
SOURCE_REFERENCE: dict[str, Any] = {
  "NrdrLateralController": 1,        # 1 = firmware controller, 2 = testing controller
  "NrdrSteerRatioMode": 3,           # 3 = FIRMWARE (measured Clarity TRW-A020 rack map)
  "NrdrOptimizedLaneChanges": True,
  "HondaDriverAssistDuringOverride": True,   # specs.py:198 / ui/settings/override_tuning.py:45 - "Assist Pass-Through", on in the source's Honda profile (profiles.py:259)
  "HondaOverrideFadeDownSecs": 0.1,          # specs.py:195, and 0.10 in the source's Honda profile
  "HondaOverrideFadeUpSecs": 1.0,            # specs.py:196, and 1.0 there
  "HondaOverrideTorqueScale": 0,             # specs.py:197: assist fully out at the end of the fade
  "LaneGuidanceMode": 2,
  "LaneCenteringMinSpeed": 12,
  "LaneCenteringStrength": 0.95,
  "LaneCenterOffset": 0.0,
}

# Sentinel for a key that is not in common/params_keys.h at all: Params() raises UnknownKeyName for those,
# so a registry/reader drift would otherwise either crash controlsd or be silently swallowed.
UNREGISTERED = object()


def _is_unset(value: Any) -> bool:
  return value is None or (isinstance(value, (str, bytes)) and not value.strip())


def _bool_value(value: Any, default: bool = False) -> bool:
  if _is_unset(value):
    return default
  if isinstance(value, (bytes, str)):
    text = value.decode() if isinstance(value, bytes) else value
    return text.strip().lower() not in ("", "0", "false")
  return bool(value)


def _number_value(value: Any, cast, default):
  if _is_unset(value):
    return default
  if isinstance(value, bool):
    return cast(value)
  if isinstance(value, (int, float)):
    return cast(value)
  try:
    text = value.decode() if isinstance(value, bytes) else str(value)
    return cast(text.strip())
  except (AttributeError, ValueError):
    return default


@dataclass(frozen=True)
class LateralSettings:
  """One immutable read of the lateral keys. `generation` is what a control loop compares against to see
  whether tuning changed mid-drive, exactly like the source's ParamSnapshot."""
  generation: int = 0
  values: Mapping[str, Any] = field(default_factory=dict, repr=False)

  @classmethod
  def snapshot(cls, pm: Params | None = None, generation: int = 0) -> LateralSettings:
    """Read every key exactly once. pm is injectable so the reader is testable without params_pyx."""
    params = pm if pm is not None else Params()
    values: dict[str, Any] = {}
    for key in LATERAL_KEYS:
      try:
        values[key] = params.get(key)
      except UnknownKeyName:
        values[key] = UNREGISTERED
    return cls(generation=generation, values=MappingProxyType(values))

  @property
  def unregistered(self) -> tuple[str, ...]:
    return tuple(key for key in LATERAL_KEYS if self.values.get(key) is UNREGISTERED)

  def get(self, key: str, default: Any = None) -> Any:
    """Raw value for a key, or `default` when it is unset or missing from the registry."""
    value = self.values.get(key, UNREGISTERED)
    return default if value is UNREGISTERED or _is_unset(value) else value

  def bool_of(self, key: str) -> bool:
    return _bool_value(self.get(key), STOCK_DEFAULTS.get(key, False))

  def int_of(self, key: str) -> int:
    return _number_value(self.get(key), int, STOCK_DEFAULTS.get(key, 0))

  def float_of(self, key: str) -> float:
    return _number_value(self.get(key), float, STOCK_DEFAULTS.get(key, 0.0))

  def describe(self) -> dict[str, dict[str, Any]]:
    """The printable run-mode table for the boot probe / drive notes (Task 10): value, whether it came
    from the car or from stock, and the source value a comparable drive would have had."""
    out: dict[str, dict[str, Any]] = {}
    for key in LATERAL_KEYS:
      unset = _is_unset(self.get(key))
      out[key] = {
        "effective": STOCK_DEFAULTS[key] if unset else self.get(key),
        "source": "stock default" if unset else "car",
        "stock": STOCK_DEFAULTS[key],
        "source_reference": SOURCE_REFERENCE[key],
        "registered": key not in self.unregistered,
      }
    return out


class LateralSettingsSource:
  """Hands a control loop a snapshot without touching storage on every frame.

  Refreshes on the caller's clock, at most once per REFRESH_PERIOD. The source keeps a background thread
  for this (nrdr/params/snapshots.py LiveParams); the port stays thread-free until a second consumer needs
  one. The first call is eager, so frame 0 already has values.
  """

  def __init__(self, pm: Params | None = None, refresh_period: float = REFRESH_PERIOD) -> None:
    self._params = pm if pm is not None else Params()
    self._period = max(refresh_period, 0.0)
    self._generation = 0
    self._snapshot = LateralSettings.snapshot(self._params, self._generation)
    self._next_refresh = time.monotonic() + self._period

  def current(self) -> LateralSettings:
    now = time.monotonic()
    if now >= self._next_refresh:
      self._refresh(now)
    return self._snapshot

  def refresh(self) -> LateralSettings:
    """Force a read - used when a settings screen has just written a key."""
    return self._refresh(time.monotonic())

  def _refresh(self, now: float) -> LateralSettings:
    self._generation += 1
    self._snapshot = LateralSettings.snapshot(self._params, self._generation)
    self._next_refresh = now + self._period
    return self._snapshot

