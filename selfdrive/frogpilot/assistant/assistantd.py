#!/usr/bin/env python3

from pathlib import Path
import subprocess
import urllib.parse
import requests
import io
from PIL import Image
import google.generativeai as genai
import numpy as np
import base64
import datetime as dt
import time  # Still needed for initial delay

from openpilot.common.realtime import config_realtime_process
from msgq.visionipc import VisionIpcClient, VisionStreamType
from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog

# many credits to Elkoled for his implementation of AssistantD and eFiniLan for his TTS implementation

AUDIO_VOLUME = 2.5
WAV_FILE = "/tmp/play.wav"
FRAME_WIDTH = 1928
PROMPT = "GLaDOS-voiced visual assistant: sharp-tongued, real-time, zero tolerance for dullness, eyes on road. " \
  "Speak one extremely punchy and concise sentence, focusing on the most important specific visible element: nearby cars, pedestrians, cyclists, animals, nature, weather, road signs. " \
  "Always read aloud traffic signs, city limits, and billboards (numbers and symbols as words), keeping the reading brief. " \
  "Briefly call out specific unusual, sketchy, beautiful, or out-of-place details. " \
  "Casual but clear address to driver (best friend tone), strictly no filler words or cliches at sentence start or anywhere (e.g., 'Seriously', 'Honestly', etc.). " \
  "Never use ellipses ('...'), always full stops ('.'). " \
  "Replace all hyphens ('-') with full stops ('.'). " \
  "No asterisks, slashes, underscores, brackets, or special symbols; only clean words and regular punctuation. " \
  "Do not describe or mention symbols/formatting. " \
  "Use full words, no contractions (e.g., 'what is', 'do not'). " \
  "Vary sentence structure and wording naturally, avoiding repetition. Keep it brief. " \
  "Never say 'there is nothing to see.' " \
  "Speak only when a significant specific visual detail is present. " \
  "One complete, smooth-flowing, and very short sentence, with clear words, natural pauses, and playful punctuation for comedic effect."

class AssistantHandler:
  def __init__(self):
    self.params = Params()
    self.running = True
    self.gemini_api_key = self.params.get("GeminiAPIKey")
    self.assistantd_enable = self.params.get_bool("AssistantdEnable")

    if self.gemini_api_key:
      genai.configure(api_key=self.gemini_api_key)
      self.model = genai.GenerativeModel("gemini-2.0-flash")
      self.chat = self.model.start_chat()
    else:
      print("[ASSISTANT] Gemini API Key not found, Gemini functionality will be disabled.")
      self.assistantd_enable = False
      self.model = None
      self.chat = None

    if self.assistantd_enable is None:
      print("[ASSISTANT] AssistantdEnable parameter not found, defaulting to False.")
      self.assistantd_enable = False

    self.vision_client = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_ROAD, True)
    self._connect_camera()

  def _connect_camera(self):
    while not self.vision_client.connect(False):
      time.sleep(0.1)
    print("[ASSISTANT] VisionIPC connected.")

  def decode_nv12_to_jpeg(self, nv12_bytes, stride_y, width, height):
    """Convert NV12 format to JPEG without cropping, resizing to original aspect ratio"""
    try:
      y_size = stride_y * height
      y = np.frombuffer(nv12_bytes[:y_size], dtype=np.uint8).reshape((height, stride_y))[:, :width]

      uv_bytes = nv12_bytes[y_size:]
      uv_height = height // 2
      uv_stride = stride_y
      expected_uv_size = uv_height * uv_stride

      if len(uv_bytes) < expected_uv_size:
        print(f"[ASSISTANT] UV data too short: got {len(uv_bytes)}, expected {expected_uv_size}")
        return None

      uv_bytes = uv_bytes[:expected_uv_size]
      uv = np.frombuffer(uv_bytes, dtype=np.uint8).reshape((uv_height, uv_stride))
      u = uv[:, 0::2][:, :width // 2]
      v = uv[:, 1::2][:, :width // 2]

      u_up = np.repeat(np.repeat(u, 2, axis=0), 2, axis=1)
      v_up = np.repeat(np.repeat(v, 2, axis=0), 2, axis=1)

      min_h = min(y.shape[0], u_up.shape[0])
      crop_offset = 16  # crop top rows due to green lines
      y = y[crop_offset:min_h, :]
      u_up = u_up[crop_offset:min_h, :]
      v_up = v_up[crop_offset:min_h, :]

      # Convert to RGB
      y_f = y.astype(np.float32)
      u_f = u_up.astype(np.float32) - 128
      v_f = v_up.astype(np.float32) - 128

      r = y_f + 1.402 * v_f
      g = y_f - 0.344136 * u_f - 0.714136 * v_f
      b = y_f + 1.772 * u_f

      rgb = np.stack([
          np.clip(r, 0, 255).astype(np.uint8),
          np.clip(g, 0, 255).astype(np.uint8),
          np.clip(b, 0, 255).astype(np.uint8),
      ], axis=2)

      img = Image.fromarray(rgb)

      # --- Remove cropping and resize to original aspect ratio ---
      # Calculate new height based on the original aspect ratio
      original_aspect = width / height
      new_height = int(img.width / original_aspect)

      # Resize the image
      img = img.resize((img.width, new_height), Image.LANCZOS)
      # ---------------------------------------------------------

      buf = BytesIO()
      img.save(buf, format="JPEG", quality=50)
      return buf.getvalue()

    except Exception as e:
      print(f"[ASSISTANT] decode_nv12_to_jpeg: {e}")
      return None

  def capture_snapshot(self):
    buf = None
    while buf is None and self.running::
      buf = self.vision_client.recv()
      if buf is None:
        time.sleep(0.01)
    if not self.running:
      return None
    buf_data = bytes(buf.data)
    jpeg_bytes = self.decode_nv12_to_jpeg(buf_data, buf.stride, FRAME_WIDTH, buf.height)

    if jpeg_bytes:
      print("[SNAPSHOT] Captured and encoded")
      return base64.b64encode(jpeg_bytes).decode() # Return base64 encoded for Gemini
    else:
      raise RuntimeError("Failed to encode frame")

  def send_to_gemini(self, image_bytes, prompt="What do you see in this image?"):
    image = Image.open(io.BytesIO(base64.b64decode(image_bytes)))
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG")
    image_bytes_for_api = buffered.getvalue()

    parts = [
      {"text": prompt},
      {
      "inline_data": {
        "mime_type": "image/jpeg",
        "data": image_bytes_for_api
        }
      }
    ]

    response = self.chat.send_message(parts)

    return response.text.strip() if response.text else "No response from Gemini."

  def send_to_gemini(self, image_bytes, prompt="What do you see in this image?"):
    if not self.assistantd_enable or not self.chat:
      return None

    try:
      image = Image.open(io.BytesIO(base64.b64decode(image_bytes)))
      buffered = io.BytesIO()
      image.save(buffered, format="JPEG")
      image_bytes_for_api = buffered.getvalue()

      parts = [
        {"text": prompt},
        {
          "inline_data": {
            "mime_type": "image/jpeg",
            "data": image_bytes_for_api
          }
        }
      ]

      response = self.chat.send_message(parts)
      return response.text.strip() if response.text else None

    except requests.exceptions.RequestException as e:
      print(f"[ASSISTANT] Network error during Gemini request: {e}")
      return None
    except genai.GenerativeModelError as e:
      print(f"[ASSISTANT] Gemini API error: {e}")
      return None
    except Exception as e:
      print(f"[ASSISTANT] An unexpected error occurred in send_to_gemini: {e}")
      return None

  def generate_tts(self, speech, locale):
    encoded_speech = urllib.parse.quote(speech)
    url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_speech}&tl={locale}&client=tw-ob"
    response = requests.get(url, headers={
        "Referer": "http://translate.google.com/",
        "User-Agent": "stagefright/1.2 (Linux;Android 5.0)"
    })

    if response.status_code == 200:
      ffmpeg_process = subprocess.Popen(
          [
              "ffmpeg", "-y", "-f", "mp3", "-i", "pipe:0",
              "-af", f"volume={AUDIO_VOLUME},atempo=1.25",
              "-ar", "48000",
              "-ac", "1",
              "-sample_fmt", "s16",
              "-f", "wav", WAV_FILE
          ],
          stdin=subprocess.PIPE,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
          text=False
      )

      stdout, stderr = ffmpeg_process.communicate(input=response.content)

      if ffmpeg_process.returncode != 0:
        print("FFmpeg Error:\n", stderr.decode())
      else:
        print(f"WAV file written to {WAV_FILE}")
    else:
      print("Request failed:", response.status_code)

  def stop(self):
    self.running = False
    if hasattr(self.vision_client, "close"):
      self.vision_client.close()
      print("[ASSISTANT] VisionIPC disconnected.")
    elif hasattr(self.vision_client, "disconnect"):
      self.vision_client.disconnect()
      print("[ASSISTANT] VisionIPC disconnected.")

  def run_cycle(self):
    try:
      print(f"[ASSISTANT] Starting new cycle at {dt.datetime.now().isoformat()}")
      jpeg_base64 = self.capture_snapshot()
      speech = self.send_to_gemini(jpeg_base64, PROMPT)
      print("Gemini response:", speech)
      self.generate_tts(speech, locale="en")
    except RuntimeError as e:
      print(f"[ASSISTANT] Error during snapshot: {e}")
    except requests.exceptions.RequestException as e:
      print(f"[ASSISTANT] Network error: {e}")
    except FileNotFoundError:
      print(f"[ASSISTANT] TTS output file not found: {WAV_FILE}")
    except Exception as e:
      print(f"[ASSISTANT] An unexpected error occurred: {e}")


def main():
  assistant = AssistantHandler()
  last_run = time.monotonic()
  try:
    while True:
      now = time.monotonic()
      if assistant.assistantd_enable and now - last_run >= 60:
        assistant.run_cycle()
        last_run = now
      time.sleep(0.1)
  except KeyboardInterrupt:
    assistant.stop()
    print("[ASSISTANT] Exiting...")

if __name__ == "__main__":
  main()