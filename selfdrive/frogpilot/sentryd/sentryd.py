#!/usr/bin/env python3

import subprocess
import shutil
import numpy as np
import cereal.messaging as messaging
import time
import os
import requests
from PIL import Image
from datetime import datetime
from common.params import Params
from msgq.visionipc import VisionIpcClient, VisionStreamType
from openpilot.common.realtime import config_realtime_process, set_core_affinity
from openpilot.system.camerad.snapshot.snapshot import extract_image, yuv_to_rgb, jpeg_write
from openpilot.system.manager.process_config import managed_processes

WARNING_TRIGGER_COUNT = 10
MAX_TRIGGER_COUNT = 25
ALARM_TRIGGER_COUNT = 240
RESET_FRAME_COUNT = 600
SENSITIVITY_THRESHOLD = 0.04
OFFROAD_DELAY = 90
ALERT_MESSAGE = "🚨 ALERT! Sentry Detected Movement!"
WAV_FILE = "/tmp/play.wav"
SOUND_PATH = "/data/openpilot/selfdrive/frogpilot/sentryd/"
OHNO_SOUND_FILE = "ohno.wav"
ARMING_SOUND_FILE = "arming.wav"
ARMED_SOUND_FILE = "armed.wav"
WARNING_SOUND_FILE = "warning.wav"
ALARM_SOUND_FILE = "alarm.wav"
PROBLEM_SOUND_FILE = "problem.wav"

class SentryMode:
  def __init__(self):
    self.sm = messaging.SubMaster(['accelerometer'])
    self.transition_to_offroad_last = time.monotonic()
    self.prev_accel = None
    params = Params()
    self.webhook_url = params.get("SentryDhook", encoding='utf8')
    self.sentryd_Enable = bool(int(params.get("SentryDEnable", "0")))
    self.frontAllowed = bool(int(params.get("RecordFront", "0")))
    self.reset_counter = 0
    self.trigger_counter = 0
    self.armed = False
    self.sentry_problem = False
    self.played = False
    self.triggered_alarm = False
    self.camera_counter = 0

  def _play_prebuilt_sound(self, filename):
    """Copies the specified sound file to /tmp/play.wav."""
    source_path = os.path.join(SOUND_PATH, filename)
    try:
      subprocess.Popen(["aplay", source_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
      print(f"[SENTRY] Playing sound: {source_path}")
    except Exception as e:
      print(f"[SENTRY] Error playing sound file: {e}")

  def takeSnapshot(self):
    try:
      self.vision_client_w = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_WIDE_ROAD, True)
      self.vision_client_d = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_DRIVER, True)
      while not self.vision_client_w.connect(False) and not self.vision_client_d.connect(False):
        time.sleep(0.1)
      print("[SENTRY] VisionIPC connected.")
      pic, fpic = None, None
      pic = extract_image(self.vision_client_w.recv())
      fpic = extract_image(self.vision_client_d.recv())
      timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
      target_directory = "/data/media/0/sentryd/"
      os.makedirs(target_directory, exist_ok=True)
      back_path = f"{target_directory}back_image_{timestamp}.jpg"
      front_path = f"{target_directory}front_image_{timestamp}.jpg"
      stitch_path = f"{target_directory}360_image_{timestamp}.jpg"
      if pic is not None:
        jpeg_write(back_path, pic)
      if fpic is not None:
        jpeg_write(front_path, fpic)
      # If both images are available, create a stitched image
      if pic is not None and fpic is not None:
        front_image = Image.open(front_path)
        back_image = Image.open(back_path)
        if front_image.height == back_image.height:
          result_image = Image.new("RGB", (front_image.width + back_image.width, front_image.height))
          result_image.paste(front_image, (0, 0))
          result_image.paste(back_image, (front_image.width, 0))
          result_image.save(stitch_path)
          self.send_discord_webhook(ALERT_MESSAGE, stitch_path)
        else:
          print("⚠️ Error: Images must have the same height.")
      else:
        if pic is not None:
          self.send_discord_webhook(ALERT_MESSAGE, back_path)
        elif fpic is not None:
          self.send_discord_webhook(ALERT_MESSAGE, front_path)
        else:
          print("⚠️ No images available.")
    except Exception as e:
      print(f"❌ Error in takeSnapshot: {e}")
      self._play_prebuilt_sound(OHNO_SOUND_FILE)

  def send_discord_webhook(self, message, image_path=None):
    if not self.webhook_url:
      print("⚠️ Warning: Webhook URL is not set.")
      return
    try:
      if image_path:
        with open(image_path, "rb") as file:
          response = requests.post(self.webhook_url, data={"content": message}, files={"file": file})
        print(f"✅ Webhook sent, status: {response.status_code}")
      else:
        data = {"content": message}
        headers = {"Content-Type": "application/json"}
        response = requests.post(self.webhook_url, json=data, headers=headers)
        print(f"✅ Webhook sent without image, status: {response.status_code}")
    except Exception as e:
      print(f"❌ Error sending webhook: {e}")

  def update(self):
    t = time.monotonic() #  Get time
    if (t - self.transition_to_offroad_last) >= OFFROAD_DELAY * 0.5 and not self.played: # Delay half of offroad delay
      self.played = True # Play sound only once
      self._play_prebuilt_sound(ARMING_SOUND_FILE) # Play sound
    if (t - self.transition_to_offroad_last) <= OFFROAD_DELAY: # Delay full offroad delay
      return # Return while waiting for offroad delay

    if self.sm['accelerometer'] is None or self.sm['accelerometer'].acceleration is None: # Check if accelerometer data is available
      print("⚠️ Warning: No accelerometer data available.")
      if not self.sentry_problem: # Check if sentry problem is not already triggered
        self._play_prebuilt_sound(PROBLEM_SOUND_FILE) # Play problem sound
        self.sentry_problem = True # Prevents future sound playing
      return # Return if no accelerometer data

    if self.armed == False: # Check if sentry is not armed
      self._play_prebuilt_sound(ARMED_SOUND_FILE) # Play armed sound
      self.armed = True # Set armed to true
      print("🔒 SentryD Armed")

    curr_accel = np.array(self.sm['accelerometer'].acceleration.v) # Get current acceleration data
    if self.prev_accel is None: # Check if first run
      self.prev_accel = curr_accel # Initialize previous acceleration data

    delta = abs(np.linalg.norm(curr_accel) - np.linalg.norm(self.prev_accel)) # Calculate delta between current and previous acceleration data
    if self.armed:
      if delta > SENSITIVITY_THRESHOLD: # Check if delta is greater than sensitivity threshold and sentry is armed
        self.trigger_counter += 1 # Count number of triggers
      if self.trigger_counter == WARNING_TRIGGER_COUNT: # Trigger Warning threshold one shot
        print("Movement Detected!")
        self._play_prebuilt_sound(WARNING_SOUND_FILE) # Play warning sound
      if self.trigger_counter > MAX_TRIGGER_COUNT and self.reset_counter == ALARM_TRIGGER_COUNT: # Trigger Alarm threshold one shot
        print("🚨 Movement Detected! Taking snapshot...")
        self.triggered_alarm = True # Set triggered alarm to true
        if self.frontAllowed: # Check if snapshot should be performed
          managed_processes['camerad'].start() # Start camerad
      if self.triggered_alarm: # Check if alarm is triggered
        self.camera_counter += 1 # Increment for camera delay
      if self.triggered_alarm and self.camera_counter == 60: # Delay 4 seconds  after starting camerad before taking snapshot one shot
        self._play_prebuilt_sound(ALARM_SOUND_FILE) # Play alarm sound
        self.triggered_alarm = False # Reset triggered alarm
        self.camera_counter = 0 # Reset camera delay counter
        if self.frontAllowed: # Check if snapshot should be performed
          self.takeSnapshot() # Take snapshot
          managed_processes['camerad'].stop() # Stop camerad
        else:
          self.send_discord_webhook(ALERT_MESSAGE) # send webhook without image
      if self.trigger_counter > 0: # After first trigger, before reset
        self.reset_counter += 1 # Increment reset counter
        if self.reset_counter == RESET_FRAME_COUNT: # Reset trigger and reset counter
          print("✅ Movement Ended")
          self.trigger_counter = 0
          self.reset_counter = 0

    self.prev_accel = curr_accel # Ready for next iteration

  def start(self):
    while True:
      if self.sentryd_Enable:
        self.sm.update()
        self.update()
      time.sleep(0.1)


def main():
  try:
    set_core_affinity([0, 1, 2, 3])
  except Exception:
    print("AssistantD: failed to set core affinity")
  config_realtime_process([0, 1, 2, 3], priority=5)
  SentryMode().start()


if __name__ == "__main__":
  main()