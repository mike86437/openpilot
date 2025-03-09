from openpilot.system.camerad.snapshot.snapshot import snapshot
from PIL import Image
import numpy as np
import cereal.messaging as messaging
import time
import os
import requests
from datetime import datetime
from common.params import Params

SENSITIVITY_THRESHOLD = 0.08
TRIGGERED_TIME = 2
OFFROAD_DELAY = 90
ALERT_MESSAGE = "🚨 ALERT! Sentry Detected Movement!"

class SentryMode:
  def __init__(self):
    self.sm = messaging.SubMaster(['accelerometer'])
    self.transition_to_offroad_last = time.monotonic()
    self.sentry_status = False
    self.secDelay = 0
    self.last_trigger_time = 0
    self.prev_accel = None
    params = Params()
    self.webhook_url = params.get("SentryDhook", encoding='utf8')
    self.frontAllowed = bool(int(params.get("RecordFront", "0")))

  def takeSnapshot(self):
    try:
      pic, fpic = snapshot()
      timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
      target_directory = "/data/media/0/sentryd/"
      os.makedirs(target_directory, exist_ok=True)

      back_path = f"{target_directory}back_image_{timestamp}.jpg"
      front_path = f"{target_directory}front_image_{timestamp}.jpg"
      stitch_path = f"{target_directory}360_image_{timestamp}.jpg"

      if pic and fpic:
        pic.save(back_path)
        fpic.save(front_path)
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
        if pic:
          pic.save(back_path)
          self.send_discord_webhook(ALERT_MESSAGE, back_path)
        elif fpic:
          fpic.save(front_path)
          self.send_discord_webhook(ALERT_MESSAGE, front_path)

    except Exception as e:
      print(f"❌ Error in takeSnapshot: {e}")

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
      return

    curr_accel = np.array(self.sm['accelerometer'].acceleration.v)

    if self.prev_accel is None:
      print("🔒 SentryD Active")
      self.prev_accel = curr_accel

    delta = abs(np.linalg.norm(curr_accel) - np.linalg.norm(self.prev_accel))

    if delta > SENSITIVITY_THRESHOLD:
      self.last_trigger_time = t
      self.secDelay += 1
      if self.secDelay >= 150:
        self.sentry_status = True
        print("🚨 Movement Detected! Taking snapshot...")
        self.secDelay = 0
        if self.frontAllowed:
          self.takeSnapshot()
        else:
          self.send_discord_webhook(ALERT_MESSAGE)

    elif self.sentry_status and (t - self.last_trigger_time) > TRIGGERED_TIME:
      self.sentry_status = False
      print("✅ Movement Ended")

    self.prev_accel = curr_accel

  def start(self):
    while True:
      self.sm.update()
      self.update()


def main():
  SentryMode().start()


if __name__ == "__main__":
  main()
