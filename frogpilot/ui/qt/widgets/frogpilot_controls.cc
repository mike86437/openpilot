#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QMovie>
#include <QRegularExpression>

#include "selfdrive/ui/ui.h"

bool FrogPilotConfirmationDialog::toggleReboot(QWidget *parent) {
  ConfirmationDialog d(tr("Reboot required to take effect."), tr("Reboot Now"), tr("Reboot Later"), false, parent);
  return d.exec();
}

bool FrogPilotConfirmationDialog::yesorno(const QString &prompt_text, QWidget *parent) {
  ConfirmationDialog d(prompt_text, tr("Yes"), tr("No"), false, parent);
  return d.exec();
}

bool useKonikServer() {
  static const bool use_konik = QFile::exists("/cache/use_konik");
  return use_konik;
}

void loadImage(const QString &basePath, QPixmap &pixmap, QMovie *&movie, const QSize &size, QWidget *parent, Qt::AspectRatioMode aspectRatioMode) {
  delete movie;
  movie = nullptr;

  QFileInfo gifFile(basePath + ".gif");
  if (gifFile.exists()) {
    movie = new QMovie(gifFile.filePath(), QByteArray(), parent);
    if (movie->isValid()) {
      movie->setScaledSize(size);
      QObject::connect(movie, &QMovie::frameChanged, parent, [parent](int){parent->update();});
      movie->start();
      return;
    } else {
      delete movie;
      movie = nullptr;
    }
  }

  pixmap = loadPixmap(basePath + ".png", size, aspectRatioMode);
}

void updateFrogPilotToggles() {
  static Params params_memory{"/dev/shm/params"};
  params_memory.putBool("FrogPilotTogglesUpdated", true);
}

QColor loadThemeColors(const QString &colorKey) {
  QFile file("../../frogpilot/assets/active_theme/colors/colors.json");
  if (!file.open(QIODevice::ReadOnly)) {
    return QColor();
  }

  const QJsonObject &colorObj = QJsonDocument::fromJson(file.readAll()).object()[colorKey].toObject();
  return QColor(
    colorObj.value("red").toInt(255),
    colorObj.value("green").toInt(255),
    colorObj.value("blue").toInt(255),
    colorObj.value("alpha").toInt(255)
  );
}

QString processModelName(const QString &modelName) {
  QString modelCleaned = modelName;
  modelCleaned = modelCleaned.remove(QRegularExpression("[🗺️👀📡]")).simplified();
  modelCleaned = modelCleaned.replace("(Default)", "");
  return modelCleaned;
}
