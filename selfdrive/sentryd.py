#!/usr/bin/env python3
import numpy as np
from cereal import car, messaging
import time
from openpilot.selfdrive.controls.lib.events import Events
import requests

SENSITIVITY_THRESHOLD = 0.05
TRIGGERED_TIME = 2
EventName = car.CarEvent.EventName


class SentryMode:

  def __init__(self):
    self.sm = messaging.SubMaster(['accelerometer'], poll=['accelerometer'])
    # self.pm = messaging.PubMaster(['sentryState'])
    self.curr_accel = 0
    self.prev_accel = None
    self.sentry_status = False
    self.events = Events()

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


  def update(self):    
    # Extract acceleration data
    self.curr_accel = np.array(self.sm['accelerometer'].acceleration.v)

    # Initialize
    if self.prev_accel is None:
      self.prev_accel = self.curr_accel

    # Calculate magnitude change
    delta = abs(np.linalg.norm(self.curr_accel) - np.linalg.norm(self.prev_accel))

    # Trigger Check
    if delta > SENSITIVITY_THRESHOLD:
      # movement_type = self.get_movement_type(self.curr_accel, self.prev_accel)
      # print("Movement {} - {}".format(movement_type, delta))
      print(delta)
      self.events.add(EventName.joystickDebug, static=True)
      self.last_timestamp = time.monotonic()
      self.sentry_status = True
      # Replace 'YOUR_WEBHOOK_URL' with the actual URL of your Discord webhook
      webhook_url = 'YOUR_WEBHOOK_URL'
      message = 'Hello, this is a test message from Python!'
      self.send_discord_webhook(webhook_url, message)

    # Trigger Reset
    elif self.sentry_status and time.monotonic() - self.last_timestamp > TRIGGERED_TIME:
      self.sentry_status = False
      print("Movement Ended")

    self.prev_accel = self.curr_accel


  # def publish(self):
  #   sentry_state = messaging.new_message('sentryState')
  #   sentry_state.sentryState.status = bool(self.sentry_status)
  #   self.pm.send('sentryState', sentry_state)


  def start(self):
    while True:
      self.sm.update()
      self.update()
      # self.publish()


def main():
  sentry_mode = SentryMode()
  sentry_mode.start()


if __name__ == "__main__":
  main()
