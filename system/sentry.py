"""Install exception handler for process crash."""
import psutil
import sentry_sdk
import traceback
from datetime import datetime
from enum import Enum
from pathlib import Path
from sentry_sdk.integrations.threading import ThreadingIntegration

from openpilot.common.params import Params, ParamKeyType
from openpilot.system.athena.registration import is_registered_device
from openpilot.system.hardware import HARDWARE, PC
from openpilot.common.swaglog import cloudlog
from openpilot.system.version import get_build_metadata, get_version

from openpilot.selfdrive.frogpilot.frogpilot_variables import CRASHES_DIR

class SentryProject(Enum):
  # python project
  SELFDRIVE = "https://0c2fea9f108f30f51d26ee7d259580ea@o4505034923769856.ingest.us.sentry.io/4505034930651136"
  # native project
  SELFDRIVE_NATIVE = "https://0c2fea9f108f30f51d26ee7d259580ea@o4505034923769856.ingest.us.sentry.io/4505034930651136"


def report_tombstone(fn: str, message: str, contents: str) -> None:
  cloudlog.error({'tombstone': message})

  with sentry_sdk.configure_scope() as scope:
    scope.set_extra("tombstone_fn", fn)
    scope.set_extra("tombstone", contents)
    sentry_sdk.capture_message(message=message)
    sentry_sdk.flush()


def capture_exception(*args, **kwargs) -> None:
  exc_text = traceback.format_exc()

  phrases_to_check = [
    "already exists. To overwrite it, set 'overwrite' to True",
    "setup_quectel failed after retry",
  ]

  if any(phrase in exc_text for phrase in phrases_to_check):
    return

  save_exception(exc_text)
  cloudlog.error("crash", exc_info=kwargs.get("exc_info", 1))

  try:
    sentry_sdk.capture_exception(*args, **kwargs)
    sentry_sdk.flush()  # https://github.com/getsentry/sentry-python/issues/291
  except Exception:
    cloudlog.exception("sentry exception")


def capture_memory_log():
  virtual_memory = psutil.virtual_memory()
  total_used = virtual_memory.used
  total_memory = virtual_memory.total

  process_list = []
  for process in psutil.process_iter(['pid', 'username', 'memory_percent', 'cmdline', 'name']):
    try:
      mem_percent = process.info.get('memory_percent', 0)
      cmdline = process.info.get('cmdline')
      if cmdline and len(cmdline) > 0:
        command = " ".join(cmdline)
      else:
        command = process.info.get('name', '')
      process_list.append({
        "pid": process.info['pid'],
        "user": process.info.get('username', ''),
        "memory_usage_percent": mem_percent,
        "command": command
      })
    except (psutil.NoSuchProcess, psutil.AccessDenied):
      continue

  process_list.sort(key=lambda process: process['memory_usage_percent'], reverse=True)
  top_processes = process_list[:5]

  message = (
    f"High memory detected: "
    f"{(total_used / total_memory) * 100:.2f}% of total."
  )

  with sentry_sdk.push_scope() as scope:
    scope.set_extra("total_memory_usage_percent", (total_used / total_memory) * 100)
    scope.set_extra("top_processes", top_processes)
    scope.set_extra("updater_state", Params().get("UpdaterState", encoding="utf-8"))
    sentry_sdk.capture_message(message, level="fatal")
    sentry_sdk.flush()


def capture_report(discord_user, report, frogpilot_toggles):
  error_file_path = CRASHES_DIR / "error.txt"
  error_content = "No error log found."

  if error_file_path.exists():
    error_content = error_file_path.read_text()

  with sentry_sdk.push_scope() as scope:
    scope.set_context("Error Log", {"content": error_content})
    scope.set_context("Toggle Values", frogpilot_toggles)
    sentry_sdk.capture_message(f"{discord_user} submitted report: {report}", level="fatal")
    sentry_sdk.flush()

def capture_soundd_error(stream, frogpilot_toggles):
  error_report = (
    "AssertionError: Audio stream failed to start!\n"
    "Debugging Information:\n"
    f"  - Stream Object: {stream}\n"
    f"  - Device: {stream.device}\n"
    f"  - Sample Rate: {stream.samplerate} Hz\n"
    f"  - Channels: {stream.channels}\n"
    f"  - Block Size: {stream.blocksize}\n"
    f"  - Data Type: {stream.dtype}\n\n"
    "Possible Causes and Fixes:\n"
    "  1. Audio device is unavailable or busy:\n"
    "     - Run `lsof | grep /dev/snd/` to check if another process is using the audio device.\n"
    "     - Restart the process or select a different audio device.\n\n"
    "  2. Unsupported audio settings (e.g., sample rate, channels):\n"
    "     - Verify that your hardware supports the specified sample rate and channel count.\n"
    "     - Try changing `samplerate=44100` instead of the current setting.\n\n"
    "  3. Permissions issue:\n"
    "     - Run `sudo usermod -aG audio $(whoami)`, then restart your session.\n"
    "     - Ensure PulseAudio or ALSA is properly configured.\n\n"
    "  4. Missing or misconfigured audio drivers:\n"
    "     - Run `aplay -l` or `arecord -l` to list available audio devices.\n"
    "     - Ensure `sounddevice` is installed (`pip install sounddevice`).\n"
    "     - Try setting `device=None` to allow auto-selection of an available device.\n\n"
    "Next Steps:\n"
    "  - Run the suggested debugging commands.\n"
    "  - If the issue persists, test audio with a minimal script:\n"
    "      import sounddevice as sd\n"
    "      stream = sd.OutputStream(samplerate=48000, channels=1)\n"
    "      stream.start()\n"
    "      print('Stream active:', stream.active)\n"
    "  - If this test fails, it is likely a system-level issue rather than a script error."
  )

  with sentry_sdk.push_scope() as scope:
    scope.set_context("Sound Error Log", {"content": error_report})
    scope.set_context("Toggle Values", frogpilot_toggles)
    sentry_sdk.capture_message("Soundd Error", level="fatal")
    sentry_sdk.flush()

def send_tmux(log_path):
  with open(log_path, "r", encoding="utf-8") as log_file:
    log_content = log_file.read()

  with sentry_sdk.push_scope() as scope:
    scope.set_context("Tmux Log", log_content)
    sentry_sdk.capture_message("Lock/Unlock operation completed. Log attached.")
    sentry_sdk.flush()


def set_tag(key: str, value: str) -> None:
  sentry_sdk.set_tag(key, value)


def save_exception(exc_text: str) -> None:
  files = [
    CRASHES_DIR / datetime.now().strftime("%Y-%m-%d--%H-%M-%S.log"),
    CRASHES_DIR / "error.txt"
  ]

  for file_path in files:
    if file_path.name == "error.txt":
      lines = exc_text.splitlines()[-10:]
      file_path.write_text("\n".join(lines))
    else:
      file_path.write_text(exc_text)

  print(f"Logged current crash to {[str(file) for file in files]}")


def init(project: SentryProject) -> bool:
  build_metadata = get_build_metadata()
  FrogPilot = "frogai" in build_metadata.openpilot.git_origin.lower()
  if not FrogPilot or PC:
    return False

  short_branch = build_metadata.channel

  if short_branch == "FrogPilot-Development":
    env = "Development"
  elif build_metadata.release_channel:
    env = "Release"
  elif build_metadata.tested_channel:
    env = "Staging"
  else:
    env = short_branch

  params = Params()
  dongle_id = params.get("DongleId", encoding="utf-8")
  installed = params.get("InstallDate", encoding="utf-8")
  updated = params.get("Updated", encoding="utf-8")

  integrations = []
  if project == SentryProject.SELFDRIVE:
    integrations.append(ThreadingIntegration(propagate_hub=True))

  sentry_sdk.init(project.value,
                  default_integrations=False,
                  release=get_version(),
                  integrations=integrations,
                  traces_sample_rate=1.0,
                  max_value_length=8192,
                  environment=env)

  sentry_sdk.set_user({"id": dongle_id})
  sentry_sdk.set_tag("origin", build_metadata.openpilot.git_origin)
  sentry_sdk.set_tag("branch", short_branch)
  sentry_sdk.set_tag("commit", build_metadata.openpilot.git_commit)
  sentry_sdk.set_tag("updated", updated)
  sentry_sdk.set_tag("installed", installed)

  if project == SentryProject.SELFDRIVE:
    sentry_sdk.Hub.current.start_session()

  return True
