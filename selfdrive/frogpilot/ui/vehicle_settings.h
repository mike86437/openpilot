#pragma once

#include <QStringList>

#include "selfdrive/ui/qt/offroad/settings.h"

class FrogPilotVehiclesPanel : public ListWidget {
  Q_OBJECT

public:
  explicit FrogPilotVehiclesPanel(SettingsWindow *parent);

private:
  void setModels();
  void setToggles();

  ButtonControl *selectMakeButton;
  ButtonControl *selectModelButton;

  ToggleControl *lockDoorsToggle;

  ToggleControl *longPitchToggle;

  QString brandSelection;
  QStringList models;

  Params params;
  Params paramsMemory{"/dev/shm/params"};
};
