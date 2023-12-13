#include <QDir>
#include <QRegularExpression>
#include <QTextStream>

#include "selfdrive/frogpilot/ui/vehicle_settings.h"

QStringList getCarNames(const QString &dirPath, const QString &carBrand) {
  QMap<QString, QString> brandMap;
  brandMap["acura"] = "honda";
  brandMap["audi"] = "volkswagen";
  brandMap["buick"] = "gm";
  brandMap["cadillac"] = "gm";
  brandMap["chevrolet"] = "gm";
  brandMap["chrysler"] = "chrysler";
  brandMap["dodge"] = "chrysler";
  brandMap["ford"] = "ford";
  brandMap["gm"] = "gm";
  brandMap["gmc"] = "gm";
  brandMap["genesis"] = "hyundai";
  brandMap["honda"] = "honda";
  brandMap["hyundai"] = "hyundai";
  brandMap["infiniti"] = "nissan";
  brandMap["jeep"] = "chrysler";
  brandMap["kia"] = "hyundai";
  brandMap["lexus"] = "toyota";
  brandMap["lincoln"] = "ford";
  brandMap["man"] = "volkswagen";
  brandMap["mazda"] = "mazda";
  brandMap["nissan"] = "nissan";
  brandMap["ram"] = "chrysler";
  brandMap["seat"] = "volkswagen";
  brandMap["subaru"] = "subaru";
  brandMap["tesla"] = "tesla";
  brandMap["toyota"] = "toyota";
  brandMap["volkswagen"] = "volkswagen";
  brandMap["skoda"] = "volkswagen";

  QStringList names;
  QDir dir(dirPath);
  QString lowerCaseCarBrand = carBrand.toLower();

  QString targetFolder = brandMap.value(lowerCaseCarBrand, lowerCaseCarBrand);

  foreach (const QString &folder, dir.entryList(QDir::Dirs | QDir::NoDotAndDotDot)) {
    if (folder.toLower() == targetFolder) {
      QFile file(dirPath + "/" + folder + "/values.py");
      if (file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        QRegularExpression regex("class CAR\\(StrEnum\\):([\\s\\S]*?)(?=^\\w)", QRegularExpression::MultilineOption);
        QRegularExpressionMatch match = regex.match(QTextStream(&file).readAll());
        file.close();

        if (match.hasMatch()) {
          QRegularExpression nameRegex("=\\s*\"([^\"]+)\"");
          QRegularExpressionMatchIterator it = nameRegex.globalMatch(match.captured(1));
          while (it.hasNext()) {
            names << it.next().captured(1);
          }
        }
      }
    }
  }

  std::sort(names.begin(), names.end());
  return names;
}

FrogPilotVehiclesPanel::FrogPilotVehiclesPanel(SettingsWindow *parent) : ListWidget(parent) {
  selectMakeButton = new ButtonControl(tr("Select Make"), tr("SELECT"));
  brandSelection = QString::fromStdString(params.get("CarBrand"));
  connect(selectMakeButton, &ButtonControl::clicked, [this]() {
    std::string currentBrand = params.get("CarBrand");
    QStringList makes = {
      "Acura", "Audi", "BMW", "Buick", "Cadillac", "Chevrolet", "Chrysler", "Dodge", "Ford", "GM", "GMC", 
      "Genesis", "Honda", "Hyundai", "Infiniti", "Jeep", "Kia", "Lexus", "Lincoln", "MAN", "Mazda", 
      "Mercedes", "Nissan", "Ram", "SEAT", "Subaru", "Tesla", "Toyota", "Volkswagen", "Volvo", "Škoda"
    };

    brandSelection = MultiOptionDialog::getSelection(tr("Select a Make"), makes, QString::fromStdString(currentBrand), this);
    if (!brandSelection.isEmpty()) {
      params.put("CarBrand", brandSelection.toStdString());
      selectMakeButton->setValue(brandSelection);
      setModels();
      setToggles();
    }
  });
  selectMakeButton->setValue(brandSelection);
  addItem(selectMakeButton);

  selectModelButton = new ButtonControl(tr("Select Model"), tr("SELECT"));
  connect(selectModelButton, &ButtonControl::clicked, [this]() {
    std::string currentModel = params.get("CarModel");
    QString modelSelection = MultiOptionDialog::getSelection(tr("Select a Model"), models, QString::fromStdString(currentModel), this);
    if (!modelSelection.isEmpty()) {
      params.put("CarModel", modelSelection.toStdString());
      selectModelButton->setValue(modelSelection);
    }
  });
  selectModelButton->setValue(QString::fromStdString(params.get("CarModel")));
  addItem(selectModelButton);

  setModels();
  setToggles();
}

void FrogPilotVehiclesPanel::setModels() {
  std::string carBrand = params.get("CarBrand");
  QString dirPath = "../../selfdrive/car";
  models = getCarNames(dirPath, QString::fromStdString(carBrand));
}

void FrogPilotVehiclesPanel::setToggles() {
  const bool gm = brandSelection == "Buick" || brandSelection == "Cadillac" || brandSelection == "Chevrolet"|| brandSelection == "GM"|| brandSelection == "GMC";
  const bool toyota = brandSelection == "Lexus" || brandSelection == "Toyota";

  static bool gmTogglesAdded = false;
  static bool toyotaTogglesAdded = false;

  if(evTableToggle) evTableToggle->setEnabled(gm);
  if(longPitchToggle) longPitchToggle->setEnabled(gm);
  if(lowerVoltToggle) lowerVoltToggle->setEnabled(gm);

  if(lockDoorsToggle) lockDoorsToggle->setEnabled(toyota);
  if(sngHackToggle) sngHackToggle->setEnabled(toyota);
  if(tss2TuneToggle) tss2TuneToggle->setEnabled(toyota);

  std::function<ToggleControl*(const char*, const char*, const char*)> addToggle = 
    [&](const char *param, const char *title, const char *description) {
      bool value = params.getBool(param);
      ToggleControl *toggle = new ToggleControl(tr(title), description, "", value);
      QObject::connect(toggle, &ToggleControl::toggleFlipped, [this, param](bool state) {
        params.putBool(param, state);
        paramsMemory.putBool("FrogPilotTogglesUpdated", true);
      });
      addItem(toggle);
      return toggle;
  };

  if (gm && !gmTogglesAdded) {
    evTableToggle = addToggle("EVTable", "EV Lookup Tables", 
                              "Smoothens out the gas and brake controls for EV vehicles.");

    longPitchToggle = addToggle("LongPitch", "Long Pitch Compensation", 
                          "Reduces speed and acceleration error for greater passenger comfort and improved vehicle efficiency.");

    lowerVoltToggle = addToggle("LowerVolt", "Lower Volt Enable Speed", 
                                "Lowers the Volt's minimum enable speed in order to enable openpilot at any speed.");

    gmTogglesAdded = true;
  } else if (toyota && !toyotaTogglesAdded) {
    lockDoorsToggle = addToggle("LockDoors", "Lock Doors In Drive", 
                                "Automatically locks the doors when in drive and unlocks when in park.");

    sngHackToggle = addToggle("SNGHack", "Stop and Go Hack", 
                              "Enable the 'Stop and Go' hack for vehicles without stock stop and go functionality.");

    tss2TuneToggle = addToggle("TSS2Tune", "TSS2 Tune", 
                               "Tuning profile based on the tuning profile from DragonPilot for TSS2 vehicles.");

    toyotaTogglesAdded = true;
  }
}
