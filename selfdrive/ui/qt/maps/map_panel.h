#pragma once

#include <QFrame>
#include <QMapboxGL>
#include <QStackedLayout>

class MapPanel : public QFrame {
  Q_OBJECT

public:
  explicit MapPanel(const QMapboxGLSettings &settings, QWidget *parent = nullptr);
  void setVisible(bool visible);

signals:
  void mapPanelRequested();

public slots:
  void toggleMapSettings();

private:
  QStackedLayout *content_stack;
};
