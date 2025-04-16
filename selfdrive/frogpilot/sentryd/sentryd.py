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

WARNING_RESET_COUNT = 10
MAX_TRIGGER_COUNT = 25
ALARM_TRIGGER_COUNT = 300
RESET_FRAME_COUNT = 600
SENSITIVITY_THRESHOLD = 0.08
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
    try:
      self.vision_client_w = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_WIDE_ROAD, True)
      self.vision_client_d = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_DRIVER, True)
      self._connect_camera()
      self._play_prebuilt_sound(ARMING_SOUND_FILE)
    except Exception as e:
      print(f"[SENTRY] Error connecting to camera: {e}")
      self._play_prebuilt_sound(PROBLEM_SOUND_FILE)

  def _connect_camera(self):
    self.vision_client_w.connect(True)
    self.vision_client_d.connect(True)
    print("[SENTRY] VisionIPC connected.")

  def _play_prebuilt_sound(self, filename):
    """Copies the specified sound file to /tmp/play.wav."""
    source_path = os.path.join(SOUND_PATH, filename)
    try:
      subprocess.Popen(["aplay", sound_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
      print(f"[SENTRY] Playing sound: {sound_path}")
    except Exception as e:
      print(f"[SENTRY] Error playing sound file: {e}")

  def takeSnapshot(self):
    try:
      pic, fpic = None, None
      pic = self.extract_image(self.vision_client_w.recv())
      fpic = self.extract_image(self.vision_client_d.recv())
      timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
      target_directory = "/data/media/0/sentryd/"
      os.makedirs(target_directory, exist_ok=True)
      back_path = f"{target_directory}back_image_{timestamp}.jpg"
      front_path = f"{target_directory}front_image_{timestamp}.jpg"
      stitch_path = f"{target_directory}360_image_{timestamp}.jpg"
      if pic is not None:
        self.jpeg_write(back_path, pic)
      if fpic is not None:
        self.jpeg_write(front_path, fpic)
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

  def extract_image(self, buf):
    if buf.uv_offset >= len(buf.data):
      print("⚠️ Warning: UV offset is greater than data length.")
      return None
    y = np.array(buf.data[:buf.uv_offset], dtype=np.uint8).reshape((-1, buf.stride))[:buf.height, :buf.width]
    u = np.array(buf.data[buf.uv_offset::2], dtype=np.uint8).reshape((-1, buf.stride//2))[:buf.height//2, :buf.width//2]
    v = np.array(buf.data[buf.uv_offset+1::2], dtype=np.uint8).reshape((-1, buf.stride//2))[:buf.height//2, :buf.width//2]

    return self.yuv_to_rgb(y, u, v)

  def yuv_to_rgb(self, y, u, v):
    ul = np.repeat(np.repeat(u, 2).reshape(u.shape[0], y.shape[1]), 2, axis=0).reshape(y.shape)
    vl = np.repeat(np.repeat(v, 2).reshape(v.shape[0], y.shape[1]), 2, axis=0).reshape(y.shape)

    yuv = np.dstack((y, ul, vl)).astype(np.int16)
    yuv[:, :, 1:] -= 128

    m = np.array([
      [1.00000,  1.00000, 1.00000],
      [0.00000, -0.39465, 2.03211],
      [1.13983, -0.58060, 0.00000],
    ])
    rgb = np.dot(yuv, m).clip(0, 255)
    return rgb.astype(np.uint8)

  def jpeg_write(self, fn, dat):
    img = Image.fromarray(dat)
    img.save(fn, "JPEG")

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
    t = time.monotonic()
    if (t - self.transition_to_offroad_last) <= OFFROAD_DELAY:
      return

    if self.sm['accelerometer'] is None or self.sm['accelerometer'].acceleration is None:
      print("⚠️ Warning: No accelerometer data available.")
      if not self.sentry_problem:
        self._play_prebuilt_sound(PROBLEM_SOUND_FILE)
        self.sentry_problem = True
      return

    if self.armed == False:
      self._play_prebuilt_sound(ARMED_SOUND_FILE)
      self.armed = True
      print("🔒 SentryD Armed")

    curr_accel = np.array(self.sm['accelerometer'].acceleration.v)
    if self.prev_accel is None:
      self.prev_accel = curr_accel

    delta = abs(np.linalg.norm(curr_accel) - np.linalg.norm(self.prev_accel))
    if delta > SENSITIVITY_THRESHOLD and self.armed:
      self.trigger_counter += 1
    if self.trigger_counter == WARNING_RESET_COUNT:
      print("Movement Detected!")
      self._play_prebuilt_sound(WARNING_SOUND_FILE)
    if self.trigger_counter > MAX_TRIGGER_COUNT and self.reset_counter == ALARM_TRIGGER_COUNT and self.armed:
      print("🚨 Movement Detected! Taking snapshot...")
      self._play_prebuilt_sound(ALARM_SOUND_FILE)
      if self.frontAllowed:
        self.takeSnapshot()
      else:
        self.send_discord_webhook(ALERT_MESSAGE)
    if self.trigger_counter > 0:
      self.reset_counter += 1
      if self.reset_counter == RESET_FRAME_COUNT:
        print("✅ Movement Ended")
        self.trigger_counter = 0
        self.reset_counter = 0

    self.prev_accel = curr_accel

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
