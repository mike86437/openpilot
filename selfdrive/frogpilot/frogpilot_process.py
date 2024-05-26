import datetime
import http.client
import os
import socket
import time
import urllib.error
import urllib.request

import cereal.messaging as messaging

from cereal import log
from openpilot.common.params import Params
from openpilot.common.realtime import DT_MDL, Priority, config_realtime_process
from openpilot.common.time import system_time_valid
from openpilot.system.hardware import HARDWARE

from openpilot.selfdrive.frogpilot.controls.frogpilot_planner import FrogPilotPlanner
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_functions import FrogPilotFunctions
from openpilot.selfdrive.frogpilot.controls.lib.frogpilot_variables import FrogPilotVariables

WIFI = log.DeviceState.NetworkType.wifi

def github_pinged(url="https://github.com", timeout=5):
  try:
    urllib.request.urlopen(url, timeout=timeout)
    return True
  except (urllib.error.URLError, socket.timeout, http.client.RemoteDisconnected):
    return False

def automatic_update_check(params):
  update_available = params.get_bool("UpdaterFetchAvailable")
  update_ready = params.get_bool("UpdateAvailable")
  update_state = params.get("UpdaterState", encoding='utf8')

  if update_ready:
    HARDWARE.reboot()
  elif update_available:
    os.system("pkill -SIGHUP -f selfdrive.updated.updated")
  elif update_state == "idle":
    os.system("pkill -SIGUSR1 -f selfdrive.updated.updated")

def time_checks(automatic_updates, deviceState, maps_downloaded, now, params, params_memory):
  screen_off = deviceState.screenBrightnessPercent == 0
  wifi_connection = deviceState.networkType == WIFI

  if screen_off and wifi_connection or not maps_downloaded:
    if automatic_updates:
      automatic_update_check(params)

    update_maps(maps_downloaded, now, params, params_memory)

def update_maps(maps_downloaded, now, params, params_memory):
  day = now.day
  is_first = day == 1
  is_Sunday = now.weekday() == 6
  maps_selected = params.get("MapsSelected")
  schedule = params.get_int("PreferredSchedule")

  if maps_downloaded and (maps_selected is None or schedule == 0 or (schedule == 1 and not is_Sunday) or (schedule == 2 and not is_first)):
    return

  suffix = "th" if 4 <= day <= 20 or 24 <= day <= 30 else ["st", "nd", "rd"][day % 10 - 1]
  todays_date = now.strftime(f"%B {day}{suffix}, %Y")

  if params.get("LastMapsUpdate") == todays_date:
    return

  if params.get("OSMDownloadProgress") is None:
    params_memory.put("OSMDownloadLocations", params.get("MapsSelected"))
    params.put("LastMapsUpdate", todays_date)

def frogpilot_thread(frogpilot_toggles):
  config_realtime_process(5, Priority.CTRL_LOW)

  params = Params()
  params_memory = Params("/dev/shm/params")

  frogpilot_functions = FrogPilotFunctions()
  frogpilot_planner = FrogPilotPlanner()

  current_day = None

  first_run = True
  maps_downloaded = os.path.exists('/data/media/0/osm/offline') or params.get("MapsSelected") is None
  time_validated = system_time_valid()

  pm = messaging.PubMaster(['frogpilotPlan'])
  sm = messaging.SubMaster(['carState', 'controlsState', 'deviceState', 'frogpilotCarControl', 'frogpilotCarState', 'frogpilotNavigation',
                            'frogpilotPlan', 'liveLocationKalman', 'longitudinalPlan', 'modelV2', 'radarState'],
                            poll='modelV2', ignore_avg_freq=['radarState'])

  while True:
    sm.update()

    now = datetime.datetime.now()

    deviceState = sm['deviceState']
    started = deviceState.started

    if started and sm.updated['modelV2']:
      frogpilot_planner.update(sm['carState'], sm['controlsState'], sm['frogpilotCarControl'], sm['frogpilotCarState'],
                               sm['frogpilotNavigation'], sm['liveLocationKalman'], sm['modelV2'], sm['radarState'], frogpilot_toggles)
      frogpilot_planner.publish(sm, pm, frogpilot_toggles)

    if FrogPilotVariables.toggles_updated:
      FrogPilotVariables.update_frogpilot_params(started)

      if not started:
        frogpilot_functions.backup_toggles()

    if not time_validated:
      time_validated = system_time_valid()
      if not time_validated:
        continue

    if now.second == 0 or first_run or params_memory.get_bool("ManualUpdateInitiated"):
      if (not started or not maps_downloaded) and github_pinged():
        time_checks(frogpilot_toggles.automatic_updates, deviceState, maps_downloaded, now, params, params_memory)
        maps_downloaded = os.path.exists('/data/media/0/osm/offline') or params.get("OSMDownloadProgress") is not None or params.get("MapsSelected") is None

      if now.day != current_day:
        params.remove("FingerprintLogged")
        current_day = now.day

    first_run = False

    time.sleep(DT_MDL)

def main():
  frogpilot_thread(FrogPilotVariables.toggles)

if __name__ == "__main__":
  main()
