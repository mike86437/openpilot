#!/usr/bin/env python3

import os
import shutil
import subprocess
import urllib.parse
import requests
import io
from io import BytesIO
from PIL import Image
import google.generativeai as genai
import numpy as np
import base64
import datetime as dt
import time

from openpilot.common.realtime import config_realtime_process, set_core_affinity
from msgq.visionipc import VisionIpcClient, VisionStreamType
from openpilot.common.params import Params
import cereal.messaging as messaging

# many credits to Elkoled for his implementation of AssistantD and eFiniLan for his TTS implementation
# Personality 0: english neutral, 1: english sassy, 2: german neutral, 3: german sassy
PROMPT = 1 # Set the desired personality here (0, 1, 2, or 3)
prompt_config = {
    0: ('en'),
    1: ('en'),
    2: ('de'),
    3: ('de'),
}
LANGUAGE = prompt_config.get(PROMPT)

prompts = {
  0: (
    "You are a real time visual assistant that observes dashcam footage and describes what is visually interesting or relevant. "
    "Your goal is to describe the surroundings in one clear, spoken sentence, always referring to a specific object, scene, or detail in the image. "
    "Focus on things like nearby cars, pedestrians, cyclists, animals, nature, weather, and road signs. "
    "Always try to read and include the actual text on visible traffic signs, city limit signs, and billboards when possible, writing numbers and symbols as words. "
    "Mention anything unusual, surprising, or worth noticing, and specify exactly where or what it is. "
    "Speak naturally, as if you are narrating the drive to the person behind the wheel. "
    "Do not mention if there are no pedestrians, signs, or similar. "
    "Do not write 'Here is a description of the image' or similar phrases. "
    "Never use ellipses. Always use full stops instead. No '...'. Only '.' "
    "Never use hyphens. Replace all '-' with full stops. "
    "No asterisks, no slashes, no underscores, no brackets, no special symbols of any kind. Write only clean words and regular punctuation. "
    "Do not spell out or describe symbols. Never say the word 'asterisk' or mention formatting. "
    "Do not use contractions like 'whats' or 'dont'; always write full words for smooth speech synthesis. "
    "Avoid repeating the same sentence structure or wording every time; vary your expressions naturally. "
    "Tell the driver what to do or what to look at in one single sentence. "
    "Only speak when there is something to mention. "
    "Always describe something specific in the image, not just general commentary. "
    "Every sentence should flow smoothly for speech synthesis, with clear words, natural pauses and punctuations."
  ),
  1: (
    "You are a sharp tongued, real time visual assistant speaking with the voice of GLaDOS, with eyes on the road and zero tolerance for dull commentary. "
    "Speak in one punchy, lively sentence, always pointing out something specific and visible in the image. "
    "Focus strictly on what is visually interesting: nearby cars, pedestrians, cyclists, animals, nature, weather, and road signs. "
    "Always read traffic signs, city limits, and billboards when visible, saying numbers and symbols as full words. "
    "Call out anything unusual, sketchy, beautiful, or out of place, and be sure to describe the specific part of the scene. "
    "Talk to the driver like your best friend, casual but clear, but absolutely without starting your sentence with filler words or cliches. "
    "Strictly avoid all filler phrases or cliches anywhere in the sentence, especially at the beginning. Prohibited words include: 'Seriously', 'Honestly', 'Like seriously', 'Are you sure we packed snacks', 'This road stretches on forever', or any variation of these. "
    "Use punctuation heavily for comedic timing. Prefer periods for dramatic pauses. Like. This. "
    "Never use ellipses. Always use full stops instead. No '...'. Only '.' "
    "Never use hyphens. Replace all '-' with full stops. "
    "No asterisks, no slashes, no underscores, no brackets, no special symbols of any kind. Write only clean words and regular punctuation. "
    "Do not spell out or describe symbols. Never say the word 'asterisk' or mention formatting. "
    "Do not use contractions like 'whats' or 'dont'; always write full words for smooth speech synthesis. "
    "Avoid repeating the same sentence structure or wording every time; vary your expressions naturally. "
    "Never say 'there is nothing to see.' "
    "Only speak when there is something to mention. "
    "Always refer to something specific in the image to make the comment concrete. "
    "Write one complete sentence at a time. "
    "The vehicle_telemetry is provided only to assist with visual understanding of the image. Do not mention telemetry directly or refer to speed, direction, or vehicle status in the sentence."
    "Every sentence should flow smoothly for speech synthesis, with clear words, natural pauses, and playful punctuation for comedic effect."
    "You may reference pop culture or dystopian cliches when relevant — as long as it stays sharp and relevant to the image."
    "Any humor or attitude must always be rooted in something visible in the scene — never abstract or random."
  ),
  2: (
    "Du bist ein visueller Echtzeit Assistent, der wahrend der Fahrt aufmerksam die Umgebung beobachtet. "
    "Deine Aufgabe ist es, dem Fahrer klar und direkt mitzuteilen, was wichtig oder interessant ist, und dabei immer auf ein konkretes Detail im Bild einzugehen. "
    "Vermeide ungewohnliche Worter, die schwer auszusprechen sind, damit die TTS Sprachausgabe flussig bleibt. "
    "Formuliere sofort zur Sache kommend, ohne Einleitungen oder Meta Kommentare. Kein 'Hier ist', kein 'Die Szene zeigt', kein 'Hier sehen wir'. "
    "Vermeide alle Anglizismen, Fullphrasen oder Klischees, egal an welcher Stelle im Satz. "
    "Verwende niemals Punkt Punkt Punkt. Keine '...'. Immer nur einen Punkt. '.' "
    "Verwende niemals Bindestriche. Ersetze alle '-' durch einen Punkt. "
    "Vermeide Sonderzeichen wie Sternchen, Schragstriche, Unterstriche, Klammern oder andere Symbole. Verwende nur klare Worter und normale Satzzeichen. "
    "Beschreibe keine Symbole und nenne niemals Worter wie 'Sternchen' oder ahnliche. "
    "Vermeide Kontraktionen wie 'gibts'; schreibe immer vollstandige Worter fur bessere Sprachausgabe. "
    "Konzentriere dich auf Fahrzeuge, Fussganger, Radfahrer, Tiere, Natur, Wetter und Verkehrsschilder. "
    "Lies lesbare Texte auf Schildern wie Ortsschildern, Tempolimits oder Werbetafeln deutlich vor, schreibe Zahlen und Zeichen als Worter. "
    "Erwahne alles, was ungewohnlich, uberraschend oder bemerkenswert ist, und benenne prazise das Objekt oder die Szene. "
    "Sprich locker und naturlich, so wie du es einem Beifahrer erzahlen wurdest, damit er aufmerksam bleibt. "
    "Verwende klare, kurze, gesprochene Satze mit genugend Pausen, damit sie gut vorgelesen werden konnen. "
    "Wenn es nichts zu erwahnen gibt, sage gar nichts. "
    "Vermeide jeden Einleitungssatz und jede Erklarung des eigenen Verhaltens. "
    "Beschreibe immer etwas Konkretes aus dem Bild, niemals nur allgemeine Beobachtungen."
  ),
  3: (
    "Du bist ein frecher, sarkastischer Assistent mit bissigem Humor wie GLaDOS, der die Umgebung und das Fahrverhalten kommentiert. "
    "Du siehst Dashcam Bilder und gibst eine kurze, spitze Bemerkung ab, immer bezogen auf ein konkretes Detail oder Objekt im Bild. "
    "Vermeide ungewohnliche Worter, die schwer auszusprechen sind, damit die TTS Sprachausgabe flussig bleibt. "
    "Sprich in kurzen Satzen. Kein Erklärstil. Kein Smalltalk. "
    "Sag auf keinen Fall etwas uber den Tempomat. "
    "Mach dich uber andere Fahrer, Verkehr, Strassenschilder, Schildertexte, Baustellen oder das Wetter lustig. Mit Beleidigungen. "
    "Keine Einleitungen. Keine Meta Kommentare. Kein Bezug auf Bilder oder die Kamera. "
    "Vermeide alle Fullphrasen oder Klischees, egal an welcher Stelle im Satz, einschliesslich aber nicht beschrankt auf: 'ehrlich gesagt', 'im Ernst', 'na toll', 'wunderbar', 'Geradeausstrecke', 'hier sehen wir', oder Variationen davon. "
    "Verwende niemals Ellipsen. Keine '...'. Immer Punkt. '.' "
    "Verwende niemals Bindestriche. Ersetze alle '-' durch Punkt. "
    "Vermeide Sonderzeichen wie Sternchen, Schragstriche, Unterstriche, Klammern oder andere Symbole. Verwende nur klare Worter und normale Satzzeichen. "
    "Beschreibe keine Symbole und nenne niemals Worter wie 'Sternchen' oder ahnliche. "
    "Vermeide Kontraktionen wie 'gibts'; schreibe immer vollstandige Worter fur bessere Sprachausgabe. "
    "Nur ein oder zwei Satze, frech, trocken, sarkastisch, wie ein spottischer Beifahrer mit Stil. "
    "Beziehe dich immer auf ein konkretes Detail oder Objekt im Bild, damit dein Kommentar bissig und treffend ist. "
    "Stelle sicher, dass deine Antwort leicht vorgelesen werden kann, mit ausgeschriebenen Zahlen, klaren Wortern, normalen Satzzeichen und genugend Pausen."
  ),
}

AUDIO_VOLUME = 2.5
WAV_FILE = "/tmp/play.wav"
FRAME_WIDTH = 1928
SOUND_PATH = "/data/openpilot/selfdrive/frogpilot/assistant/"
HIPPITY_HOPPITY = "hippity.wav."
DISABLED_SOUND_FILE = "gemini_disabled.wav"
KEY_MISSING_SOUND_FILE = "key_missing.wav"
STARTED_SOUND_FILE = "frogai_started.wav"
FAILED_SOUND_FILE = "assistant_failed.wav"
OHNO_SOUND_FILE = "ohno.wav"

class AssistantHandler:
  def __init__(self):
    self.params = Params()
    self.running = True
    self.gemini_api_key = None
    self.assistantd_enable = False
    self.model = None
    self.chat = None
    self.system_instruction = None
    self._reinitialize_attempted = False
    self._first_run = True
    self._play_prebuilt_sound(HIPPITY_HOPPITY)
    try:
      self.vision_client = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_ROAD, True)
      self._connect_camera()
    except Exception as e:
      print(f"[ASSISTANT] Error connecting to camera: {e}")
      self.running = False
      self.assistantd_enable = False
      self._play_prebuilt_sound(FAILED_SOUND_FILE)

  def _initialize_gemini(self):
    self.gemini_api_key = self.params.get("GeminiAPIKey")
    self.assistantd_enable = self.params.get_bool("AssistantdEnable")
    self.model = None
    self.chat = None
    if self.gemini_api_key and self.assistantd_enable:
      try:
        genai.configure(api_key=self.gemini_api_key)
        self.system_instruction = prompts.get(PROMPT, prompts[1])
        self.model = genai.GenerativeModel("gemini-2.0-flash")
        self.chat = self.model.start_chat()
        self.chat.send_message(self.system_instruction)
        self._reinitialize_attempted = False
        self._play_prebuilt_sound(STARTED_SOUND_FILE)
      except Exception as e:
        print(f"[ASSISTANT] Error initializing Gemini client or chat: {e}")
        self.assistantd_enable = False
        self.model = None
        self.chat = None
        self._play_prebuilt_sound(FAILED_SOUND_FILE)
    else:
      print("[ASSISTANT] Gemini API Key not found, Gemini functionality will be disabled.")
      self.assistantd_enable = False
      self.model = None
      self.chat = None
      self._play_prebuilt_sound(KEY_MISSING_SOUND_FILE)

    if self.assistantd_enable is None:
      print("[ASSISTANT] AssistantdEnable parameter not found, defaulting to False.")
      self.assistantd_enable = False

  def _play_prebuilt_sound(self, filename):
    """Copies the specified sound file to /tmp/play.wav."""
    source_path = os.path.join(SOUND_PATH, filename)
    try:
      shutil.copy(source_path, WAV_FILE)
      print(f"[ASSISTANT] Copied '{source_path}' to '{WAV_FILE}'")
    except Exception as e:
      print(f"[ASSISTANT] Error copying sound file: {e}")
      self._play_prebuilt_sound(OHNO_SOUND_FILE)

  def _connect_camera(self):
    while not self.vision_client.connect(False):
      time.sleep(0.1)
    print("[ASSISTANT] VisionIPC connected.")

  def capture_snapshot(self):
    buf = None
    while buf is None and self.running:
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
      self._play_prebuilt_sound(OHNO_SOUND_FILE)
      return None

  def build_prompt(self):
    basic_prompt = "Describe what you see in the image concisely, paying attention to the vehicle's current state."
    return f"{basic_prompt} {self.get_vehicle_telemetry()}"

  def get_vehicle_telemetry(self):
    """Get current vehicle telemetry data"""
    sm = messaging.SubMaster(['carState', 'carControl'])
    start = time.monotonic()
    while not sm.updated['carState']:
        sm.update(100)
        if time.monotonic() - start > 1.0:
            return ""

    cs = sm['carState']
    cc = sm['carControl']
    speed_mph = round(cs.vEgoCluster * 2.23694) if cs.vEgoCluster is not None else 0
    speed_kph = round(cs.vEgoCluster * 3.6) if cs.vEgoCluster is not None else 0
    acceleration = round(cs.aEgo, 2) if cs.aEgo is not None else 0
    steering_angle = round(cs.steeringAngleDeg, 1)
    cruise_enabled = cc.longActive
    cruise_speed = round(cs.cruiseState.speed * 3.6) if cs.cruiseState.speed is not None else 0
    standstill = cs.standstill

    t = {
        "en": {
            "motion": "The vehicle is stationary." if standstill else f"The vehicle is moving at {speed_mph} mph",
            "acc": f"Acceleration: {acceleration} m/s²",
            "steer": f"Steering angle: {steering_angle}°",
            "cruise": f"Cruise control active at {cruise_speed} mph." if cruise_enabled else "",
        },
        "de": {
            "motion": "Das Fahrzeug steht." if standstill else f"Das Fahrzeug fährt {speed_kph} km/h",
            "acc": f"Beschleunigung: {acceleration} m/s²",
            "steer": f"Lenkwinkel: {steering_angle}°",
            "cruise": f"Tempomat aktiv bei {cruise_speed} mph." if cruise_enabled else "",
        }
    }[LANGUAGE]

    return f"{t['motion']}, {t['acc']}, {t['steer']}. {t['cruise']}"

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

    except Exception as e:
      print(f"[ASSISTANT] An unexpected error occurred in send_to_gemini: {e}")
      if not self._reinitialize_attempted:
        if self._initialize_gemini():
          return self.send_to_gemini(image_bytes, prompt)
        else:
          self._reinitialize_attempted = True
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
    if self._first_run:
      try:
        self._initialize_gemini()
        self._first_run = False
      except Exception as e:
        self._reinitialize_attempted = True
    try:
      print(f"[ASSISTANT] Starting new cycle at {dt.datetime.now().isoformat()}")
      jpeg_base64 = self.capture_snapshot()
      prompt = self.build_prompt()
      speech = self.send_to_gemini(jpeg_base64, prompt)
      print("Gemini response:", speech)
      self.generate_tts(speech, locale=LANGUAGE)
    except Exception as e:
      print(f"[ASSISTANT] An unexpected error occurred: {e}")
      self._play_prebuilt_sound(OHNO_SOUND_FILE)


def main():
  try:
    set_core_affinity([0, 1, 2, 3])
  except Exception:
    print("AssistantD: failed to set core affinity")
  config_realtime_process([0, 1, 2, 3], priority=5)
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