#!/usr/bin/env python3
import numpy as np
from cereal import messaging
import time
from openpilot.common.realtime import DT_CTRL
import requests
from common.params import Params
from common.filter_simple import FirstOrderFilter
params = Params()
SENSITIVITY_THRESHOLD = 0.05
TRIGGERED_TIME = 2

MAX_TIME_ONROAD = 5 * 60.  # after this is reached, car stops recording, disregarding movement
MOVEMENT_TIME = 60.  # each movement resets onroad timer to this
MIN_TIME_ONROAD = MOVEMENT_TIME + 5.
INACTIVE_TIME = 2. * 60.  # car needs to be inactive for this time before sentry mode is enabled
DEBUG = False


class SentryMode:

  def __init__(self):
    self.sm = messaging.SubMaster(['deviceState', 'accelerometer'], poll=['accelerometer'])
    self.pm = messaging.PubMaster(['sentryState'])
    self.curr_accel = 0
    self.prev_accel = None
    self.sentry_status = False
    
    self.secDelay = 0
    self.webhook_url = params.get("SentryDhook", encoding='utf8')

    # sshane variables
    self.sentry_enabled = params.get_bool("SentryMode")
    self.last_read_ts = time.monotonic()
    self.sentry_tripped = False
    self.sentry_armed = False
    self.sentry_tripped_ts = 0.
    self.car_active_ts = time.monotonic()  # start at active
    self.movement_ts = 0.
    self.accel_filters = [FirstOrderFilter(0, 0.5, DT_CTRL) for _ in range(3)]

  def sprint(self, *args, **kwargs):  # slow print
    if DEBUG:
      if self.sm.frame % (100 / 20.) == 0:  # 20 hz
        print(*args, **kwargs)

  def send_discord_webhook(self, webhook_url, message):
    data = {"content": message}
    headers = {"Content-Type": "application/json"}

    response = requests.post(webhook_url, json=data, headers=headers)

    if response.status_code == 200:
      print("Message sent successfully")
    else:
      print(f"Failed to send message. Status code: {response.status_code}")

  def is_sentry_armed(self, now_ts):
    """Returns if sentry is actively monitoring for movements/can be alarmed"""
    # Handle car interaction, reset interaction timeout
    car_active = self.sm['deviceState'].started
    if car_active:
      self.car_active_ts = float(now_ts)
    car_inactive_long_enough = now_ts - self.car_active_ts > INACTIVE_TIME
    return self.sentry_enabled and (car_inactive_long_enough)

  def update_sentry_tripped(self, now_ts):
    movement = any([abs(a_filter.x) > .01 for a_filter in self.accel_filters])
    if movement:
      self.movement_ts = float(now_ts)

    # For as long as we see movement, extend timer by MOVEMENT_TIME.
    tripped_long_enough = now_ts - self.movement_ts > MOVEMENT_TIME
    tripped_long_enough &= now_ts - self.sentry_tripped_ts > MIN_TIME_ONROAD  # minimum of
    tripped_long_enough |= now_ts - self.sentry_tripped_ts > MAX_TIME_ONROAD  # maximum of

    sentry_tripped = False
    self.sentry_armed = self.is_sentry_armed(now_ts)
    self.sprint(f"{now_ts - self.sentry_tripped_ts=} > {MIN_TIME_ONROAD=}")
    if self.sentry_armed:
      if movement:  # trip if armed and there's movement
        sentry_tripped = True
      elif self.sentry_tripped and not tripped_long_enough:  # trip for long enough
        sentry_tripped = True

    # set when we first tripped
    if sentry_tripped and not self.sentry_tripped:
      self.sentry_tripped_ts = time.monotonic()
    self.sentry_tripped = sentry_tripped

  def update(self):    
    # sshane version
    now_ts = time.monotonic()
    if now_ts - self.last_read_ts > 15.:
      self.sentry_enabled = params.get_bool("SentryMode")
      self.last_read_ts = float(now_ts)

    self.update_sentry_tripped(now_ts)

    # roygbiversion
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
      self.last_timestamp = time.monotonic()
      self.sentry_status = True
      self.secDelay += 1

      if self.secDelay % 150 == 0: 
        self.secDelay = 0
        # self.sentry_tripped = True
        if self.webhook_url is not None:
          message = 'ALERT! Sentry Detected Movement!'
          self.send_discord_webhook(self.webhook_url, message)

    # Trigger Reset
    elif self.sentry_status and time.monotonic() - self.last_timestamp > TRIGGERED_TIME:
      self.sentry_status = False
      # self.sentry_tripped = False
      print("Movement Ended")

    self.prev_accel = self.curr_accel


  def publish(self):
    sentry_state = messaging.new_message('sentryState')
    sentry_state.sentryState.started = bool(self.sentry_tripped)
    sentry_state.sentryState.armed = bool(self.sentry_armed)

    self.pm.send('sentryState', sentry_state)

  # def publish(self):
  #   sentry_state = messaging.new_message('sentryState')
  #   sentry_state.sentryState.status = bool(self.sentry_status)
  #   self.pm.send('sentryState', sentry_state)


  def start(self):
    while True:
      self.sm.update()
      self.update()
      self.publish()


def main():
  sentry_mode = SentryMode()
  sentry_mode.start()


if __name__ == "__main__":
  main()
