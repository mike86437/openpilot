#pragma once

#include <set>

#include "selfdrive/frogpilot/ui/qt/widgets/frogpilot_controls.h"
#include "selfdrive/ui/qt/offroad/settings.h"
#include "selfdrive/ui/ui.h"

class FrogPilotControlsPanel : public FrogPilotListWidget {
  Q_OBJECT

public:
  explicit FrogPilotControlsPanel(SettingsWindow *parent);

signals:
  void openParentToggle();
  void openSubParentToggle();

private:
  void hideEvent(QHideEvent *event);
  void hideSubToggles();
  void hideToggles();
  void updateCarToggles();
  void updateMetric();
  void updateState(const UIState &s);
  void updateToggles();

  FrogPilotDualParamControl *conditionalSpeedsImperial;
  FrogPilotDualParamControl *conditionalSpeedsMetric;

  std::set<QString> aolKeys = {"AlwaysOnLateralMain", "HideAOLStatusBar", "PauseAOLOnBrake"};
  std::set<QString> conditionalExperimentalKeys = {"CECurves", "CECurvesLead", "CENavigation", "CESignal", "CESlowerLead", "CEStopLights", "HideCEMStatusBar"};
  std::set<QString> deviceManagementKeys = {};
  std::set<QString> experimentalModeActivationKeys = {};
  std::set<QString> laneChangeKeys = {};
  std::set<QString> lateralTuneKeys = {};
  std::set<QString> longitudinalTuneKeys = {"AccelerationProfile", "AggressiveAcceleration", "DecelerationProfile"};
  std::set<QString> mtscKeys = {};
  std::set<QString> qolKeys = {};
  std::set<QString> speedLimitControllerKeys = {};
  std::set<QString> speedLimitControllerControlsKeys = {};
  std::set<QString> speedLimitControllerQOLKeys = {};
  std::set<QString> speedLimitControllerVisualsKeys = {};
  std::set<QString> visionTurnControlKeys = {};

  std::map<std::string, ParamControl*> toggles;

  Params params;
  Params paramsMemory{"/dev/shm/params"};

  bool hasAutoTune;
  bool hasOpenpilotLongitudinal;
  bool hasPCMCruise;
  bool isMetric;
  bool started;
};
