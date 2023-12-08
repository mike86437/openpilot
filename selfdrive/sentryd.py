#!/usr/bin/env python3
import numpy as np
from cereal import car, messaging
from typing import Optional, Union, Dict
from datetime import datetime
import time
import json
import io
import base64
import requests
from common.params import Params
from PIL import Image

params = Params()
SENSITIVITY_THRESHOLD = 0.05
TRIGGERED_TIME = 2


class SentryMode:

  def __init__(self):
    self.sm = messaging.SubMaster(['accelerometer'], poll=['accelerometer'])
    self.curr_accel = 0
    self.prev_accel = None
    self.sentry_status = False
    self.secDelay = 0
    self.webhook_url = params.get("SentryDhook", encoding='utf8')
    self.transition_to_offroad_last = time.monotonic()
    self.offroad_delay = 90
    self.sentryd_init = False
    self.sentryjson = {}
    self.back_image_url = ""
    self.front_image_url = ""

  def takeSnapshot(self) -> Optional[Union[str, Dict[str, str]]]:
    from openpilot.system.camerad.snapshot.snapshot import jpeg_write, snapshot
    ret = snapshot()
    if ret is not None:
      def b64jpeg(x):
        if x is not None:
          f = io.BytesIO()
          jpeg_write(f, x)
          return base64.b64encode(f.getvalue()).decode("utf-8")
        else:
          return None
      return {'jpegBack': b64jpeg(ret[0]),
              'jpegFront': b64jpeg(ret[1])}
    else:
      raise Exception("not available while camerad is started")

  def base64_to_image(self, base64_data, output_file):
    binary_data = base64.b64decode(base64_data)
    with open(output_file, 'wb') as file:
      file.write(binary_data)

  def send_discord_webhook(self, webhook_url, message):
    data = {"content": message}
    headers = {"Content-Type": "application/json"}
    response = requests.post(webhook_url, json=data, headers=headers)
    if response.status_code == 200:
      print("Message sent successfully")
    else:
      print(f"Failed to send message. Status code: {response.status_code}")

  def get_movement_type(self, current, previous):
    ax_mapping = {0: "X", 1: "Y", 2: "Z"}
    dominant_axis = np.argmax(np.abs(current - previous))
    return ax_mapping[dominant_axis]

  def stitch_images(front_image_path, back_image_path, output_path):
    # Open images using PIL
    front_image = Image.open(front_image_path)
    back_image = Image.open(back_image_path)

    # Get image sizes
    front_width, front_height = front_image.size
    back_width, back_height = back_image.size

    # Check if images have the same height
    if front_height != back_height:
        print("Error: Images must have the same height.")
        return

    # Create a new image with double width
    result_image = Image.new("RGB", (front_width + back_width, front_height))

    # Paste front and back images side by side
    result_image.paste(front_image, (0, 0))
    result_image.paste(back_image, (front_width, 0))

    # Save the stitched image
    result_image.save(output_path)



  def update(self):
    t = time.monotonic()
    if not self.sentryd_init:
      self.sentryjson['SentrydActive'] = False
      with open('sentryjson.json', 'w') as json_file:
        json.dump(self.sentryjson, json_file, indent=4)
      self.sentryd_init = True
    if (t - self.transition_to_offroad_last) > self.offroad_delay:
      # Extract acceleration data
      self.curr_accel = np.array(self.sm['accelerometer'].acceleration.v)

      # Initialize
      if self.prev_accel is None:
        self.prev_accel = self.curr_accel
        self.sentryjson['SentrydActive'] = True
        with open('sentryjson.json', 'w') as json_file:
          json.dump(self.sentryjson, json_file, indent=4)

      # Calculate magnitude change
      delta = abs(np.linalg.norm(self.curr_accel) - np.linalg.norm(self.prev_accel))

      # Trigger Check
      if delta > SENSITIVITY_THRESHOLD:
        self.last_timestamp = t
        self.sentry_status = True
        self.secDelay += 1

        if self.secDelay % 100 == 0 and self.webhook_url is not None:
          self.secDelay = 0
          snapshot_result = self.takeSnapshot()
          self.back_image_url = snapshot_result.get('jpegBack')
          self.front_image_url = snapshot_result.get('jpegFront')
          self.sentryjson['SentrydAlarm'] = True
          self.sentryjson['SentrydAlarmT'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
          with open('sentryjson.json', 'w') as json_file:
            json.dump(self.sentryjson, json_file, indent=4)
          message = 'ALERT! Sentry Detected Movement!'
          self.send_discord_webhook(self.webhook_url, message)
          stitch_images('front_image.jpg', 'back_image.jpg', '360_image.jpg')

      # Trigger Reset
      elif self.sentry_status and time.monotonic() - self.last_timestamp > TRIGGERED_TIME:
        self.sentry_status = False
        print("Movement Ended")
        self.sentryjson['SentrydAlarm'] = False
        with open('sentryjson.json', 'w') as json_file:
          json.dump(self.sentryjson, json_file, indent=4)

      self.prev_accel = self.curr_accel

  def start(self):
    while True:
      self.sm.update()
      self.update()


def main():
  sentry_mode = SentryMode()
  sentry_mode.start()


if __name__ == "__main__":
  main()
