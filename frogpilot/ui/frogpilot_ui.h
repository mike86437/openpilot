#pragma once

#include <iostream>
#include <memory>

#include <QObject>

#include "cereal/messaging/messaging.h"
#include "selfdrive/ui/qt/network/wifi_manager.h"

#include "frogpilot/ui/qt/widgets/frogpilot_controls.h"

struct FrogPilotUIScene {
  bool downloading_update;
  bool frogpilot_panel_active;
  bool map_open;
  bool online;
  bool parked;

  float speed_limit;

  QJsonObject frogpilot_toggles;
};

class FrogPilotUIState : public QObject {
  Q_OBJECT

public:
  explicit FrogPilotUIState(QObject *parent = nullptr);

  void update();

  std::unique_ptr<SubMaster> sm;

  FrogPilotUIScene frogpilot_scene;

  Params params_memory{"/dev/shm/params"};

  QJsonObject &frogpilot_toggles = frogpilot_scene.frogpilot_toggles;

  WifiManager *wifi;

signals:
  void reviewModel();
};

FrogPilotUIState *frogpilotUIState();
