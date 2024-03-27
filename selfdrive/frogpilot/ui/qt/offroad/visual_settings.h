#pragma once

#include <set>

#include "selfdrive/frogpilot/ui/qt/widgets/frogpilot_controls.h"
#include "selfdrive/ui/qt/offroad/settings.h"
#include "selfdrive/ui/ui.h"

class FrogPilotVisualsPanel : public FrogPilotListWidget {
  Q_OBJECT

public:
  explicit FrogPilotVisualsPanel(SettingsWindow *parent);

signals:
  void openParentToggle();

private:
  void hideToggles();
  void showEvent(QShowEvent *event);
  void updateCarToggles();
  void updateMetric();
  void updateState(const UIState &s);
  void updateToggles();

  std::set<QString> alertVolumeControlKeys = {"DisengageVolume", "EngageVolume", "PromptDistractedVolume", "PromptVolume", "RefuseVolume", "WarningImmediateVolume", "WarningSoftVolume"};
  std::set<QString> customAlertsKeys = {"GreenLightAlert", "LeadDepartingAlert", "LoudBlindspotAlert"};
  std::set<QString> customOnroadUIKeys = {"Compass", "CustomPaths", "FPSCounter", "LeadInfo", "RoadNameUI"};
  std::set<QString> customThemeKeys = {"CustomColors", "CustomIcons", "CustomSignals", "CustomSounds", "HolidayThemes"};
  std::set<QString> modelUIKeys = {"DynamicPathWidth", "HideLeadMarker", "LaneLinesWidth", "PathEdgeWidth", "PathWidth", "RoadEdgesWidth", "UnlimitedLength"};
  std::set<QString> qolKeys = {"BigMap", "CameraView", "DriverCamera", "FullMap", "HideSpeed", "NumericalTemp"};
  std::set<QString> screenKeys = {};

  std::map<std::string, ParamControl*> toggles;

  Params params;
  Params paramsMemory{"/dev/shm/params"};

  bool hasBSM;
  bool hasOpenpilotLongitudinal;
  bool isMetric = params.getBool("IsMetric");
  bool started;
};
