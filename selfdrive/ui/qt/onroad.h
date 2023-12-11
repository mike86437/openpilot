#pragma once

#include <memory>

#include <QElapsedTimer>
#include <QPushButton>
#include <QStackedLayout>
#include <QWidget>

#include "common/util.h"
#include "selfdrive/ui/ui.h"
#include "selfdrive/ui/qt/widgets/cameraview.h"


const int btn_size = 192;
const int img_size = (btn_size / 4) * 3;

// FrogPilot global variables
static bool reverseCruise;
static bool speedHidden;
static double fps;

// ***** onroad widgets *****
class OnroadAlerts : public QWidget {
  Q_OBJECT

public:
  OnroadAlerts(QWidget *parent = 0) : QWidget(parent), scene(uiState()->scene) {}
  void updateAlert(const Alert &a);

protected:
  void paintEvent(QPaintEvent*) override;

private:
  QColor bg;
  Alert alert = {};

  // FrogPilot variables
  const UIScene &scene;
};

class Compass : public QWidget {
public:
  explicit Compass(QWidget *parent = nullptr);

  void initializeStaticElements();
  void updateState(int bearing_deg);

protected:
  void paintEvent(QPaintEvent *event) override;

private:
  int bearingDeg;
  int circleOffset;
  int compassSize;
  int degreeLabelOffset;
  int innerCompass;
  int x;
  int y;
  QPixmap compassInnerImg;
  QPixmap staticElements;
};

class ExperimentalButton : public QPushButton {
  Q_OBJECT

public:
  explicit ExperimentalButton(QWidget *parent = 0);
  void updateState(const UIState &s, bool leadInfo);

private:
  void paintEvent(QPaintEvent *event) override;
  void changeMode();

  Params params;
  QPixmap engage_img;
  QPixmap experimental_img;
  bool experimental_mode;
  bool engageable;

  // FrogPilot variables
  int wheelIcon;
  int y_offset;

  std::map<int, QPixmap> wheelImages;

  Params paramsMemory{"/dev/shm/params"};
  const UIScene &scene;
};


class MapSettingsButton : public QPushButton {
  Q_OBJECT

public:
  explicit MapSettingsButton(QWidget *parent = 0);

private:
  void paintEvent(QPaintEvent *event) override;

  QPixmap settings_img;
};

// container window for the NVG UI
class AnnotatedCameraWidget : public CameraWidget {
  Q_OBJECT

public:
  explicit AnnotatedCameraWidget(VisionStreamType type, QWidget* parent = 0);
  void updateState(const UIState &s);

  MapSettingsButton *map_settings_btn;
  MapSettingsButton *map_settings_btn_bottom;

private:
  void drawText(QPainter &p, int x, int y, const QString &text, int alpha = 255);

  QVBoxLayout *main_layout;
  ExperimentalButton *experimental_btn;
  QPixmap dm_img;
  float speed;
  QString speedUnit;
  float setSpeed;
  float speedLimit;
  bool is_cruise_set = false;
  bool is_metric = false;
  bool dmActive = false;
  bool hideBottomIcons = false;
  bool rightHandDM = false;
  float dm_fade_state = 1.0;
  bool has_us_speed_limit = false;
  bool has_eu_speed_limit = false;
  bool v_ego_cluster_seen = false;
  int status = STATUS_DISENGAGED;
  std::unique_ptr<PubMaster> pm;

  int skip_frame_count = 0;
  bool wide_cam_requested = false;

  // FrogPilot widgets
  void drawLeadInfo(QPainter &p);
  void drawStatusBar(QPainter &p);
  void drawTurnSignals(QPainter &p);
  void initializeFrogPilotWidgets();
  void updateFrogPilotWidgets(QPainter &p);

  // FrogPilot variables
  bool accelerationPath;
  bool adjacentPath;
  bool alwaysOnLateral;
  bool blindSpotLeft;
  bool blindSpotRight;
  bool compass;
  bool conditionalExperimental;
  bool experimentalMode;
  bool leadInfo;
  bool mapOpen;
  bool muteDM;
  bool roadNameUI;
  bool showDriverCamera;
  bool turnSignalLeft;
  bool turnSignalRight;
  double maxAcceleration;
  float desiredFollow;
  float laneWidthLeft;
  float laneWidthRight;
  float obstacleDistance;
  float obstacleDistanceStock;
  float stoppedEquivalence;
  float stoppedEquivalenceStock;
  int bearingDeg;
  int cameraView;
  int conditionalSpeed;
  int conditionalSpeedLead;
  int conditionalStatus;
  int customColors;
  int customSignals;
  int totalFrames = 8;
  QTimer *animationTimer;
  size_t animationFrameIndex;

  std::unordered_map<int, std::pair<QString, std::pair<QColor, std::map<double, QBrush>>>> themeConfiguration;
  std::vector<QPixmap> signalImgVector;

  QHBoxLayout *bottom_layout;

  Compass *compass_img;

  Params params;
  Params paramsMemory{"/dev/shm/params"};
  const UIScene &scene;

protected:
  void paintGL() override;
  void initializeGL() override;
  void showEvent(QShowEvent *event) override;
  void updateFrameMat() override;
  void drawLaneLines(QPainter &painter, const UIState *s);
  void drawLead(QPainter &painter, const cereal::RadarState::LeadData::Reader &lead_data, const QPointF &vd);
  void drawHud(QPainter &p);
  void drawDriverState(QPainter &painter, const UIState *s);
  inline QColor redColor(int alpha = 255) { return QColor(201, 34, 49, alpha); }
  inline QColor whiteColor(int alpha = 255) { return QColor(255, 255, 255, alpha); }
  inline QColor blackColor(int alpha = 255) { return QColor(0, 0, 0, alpha); }

  double prev_draw_t = 0;
  FirstOrderFilter fps_filter;
};

// container for all onroad widgets
class OnroadWindow : public QWidget {
  Q_OBJECT

public:
  OnroadWindow(QWidget* parent = 0);
  bool isMapVisible() const { return map && map->isVisible(); }
  void showMapPanel(bool show) { if (map) map->setVisible(show); }

signals:
  void mapPanelRequested();

private:
  void paintEvent(QPaintEvent *event);
  void mousePressEvent(QMouseEvent* e) override;
  OnroadAlerts *alerts;
  AnnotatedCameraWidget *nvg;
  QColor bg = bg_colors[STATUS_DISENGAGED];
  QWidget *map = nullptr;
  QHBoxLayout* split;

  // FrogPilot variables
  QPoint timeoutPoint = QPoint(420, 69);
  QTimer clickTimer;

  Params params;
  Params paramsMemory{"/dev/shm/params"};
  const UIScene &scene;

private slots:
  void offroadTransition(bool offroad);
  void primeChanged(bool prime);
  void updateState(const UIState &s);
};
