import os
import subprocess
from flask import render_template, request, session
from functools import wraps
from pathlib import Path
from openpilot.common.params import Params
from openpilot.system.hardware import PC
from openpilot.system.hardware.hw import Paths
from openpilot.system.loggerd.uploader import listdir_by_creation
from tools.lib.route import SegmentName

# otisserv conversion
from urllib.parse import parse_qs

params = Params()

# path to openpilot screen recordings and error logs
if PC:
  SCREENRECORD_PATH = os.path.join(str(Path.home()), ".comma", "media", "0", "videos", "")
  ERROR_LOGS_PATH = os.path.join(str(Path.home()), ".comma", "community", "crashes", "")
else:
  SCREENRECORD_PATH = "/data/media/0/videos/"
  ERROR_LOGS_PATH = "/data/community/crashes/"


def list_files(path):
  return sorted(listdir_by_creation(path), reverse=True)


def is_valid_segment(segment):
  try:
    segment_to_segment_name(Paths.log_root(), segment)
    return True
  except AssertionError:
    return False


def segment_to_segment_name(data_dir, segment):
  fake_dongle = "ffffffffffffffff"
  return SegmentName(str(os.path.join(data_dir, fake_dongle + "|" + segment)))


def all_segment_names():
  segments = []
  for segment in listdir_by_creation(Paths.log_root()):
    try:
      segments.append(segment_to_segment_name(Paths.log_root(), segment))
    except AssertionError:
      pass
  return segments


def all_routes():
  segment_names = all_segment_names()
  route_names = [segment_name.route_name for segment_name in segment_names]
  route_times = [route_name.time_str for route_name in route_names]
  unique_routes = list(dict.fromkeys(route_times))
  return sorted(unique_routes, reverse=True)


def segments_in_route(route):
  segment_names = [segment_name for segment_name in all_segment_names() if segment_name.time_str == route]
  segments = [segment_name.time_str + "--" + str(segment_name.segment_num) for segment_name in segment_names]
  return segments


def ffmpeg_mp4_concat_wrap_process_builder(file_list, cameratype, chunk_size=1024*512):
  command_line = ["ffmpeg"]
  if not cameratype == "qcamera":
    command_line += ["-f", "hevc"]
  command_line += ["-r", "20"]
  command_line += ["-i", "concat:" + file_list]
  command_line += ["-c", "copy"]
  command_line += ["-map", "0"]
  if not cameratype == "qcamera":
    command_line += ["-vtag", "hvc1"]
  command_line += ["-f", "mp4"]
  command_line += ["-movflags", "empty_moov"]
  command_line += ["-"]
  return subprocess.Popen(
    command_line, stdout=subprocess.PIPE,
    bufsize=chunk_size
  )


def ffmpeg_mp4_wrap_process_builder(filename):
  """Returns a process that will wrap the given filename
     inside a mp4 container, for easier playback by browsers
     and other devices. Primary use case is streaming segment videos
     to the vidserver tool.
     filename is expected to be a pathname to one of the following
       /path/to/a/qcamera.ts
       /path/to/a/dcamera.hevc
       /path/to/a/ecamera.hevc
       /path/to/a/fcamera.hevc
  """
  basename = filename.rsplit("/")[-1]
  extension = basename.rsplit(".")[-1]
  command_line = ["ffmpeg"]
  if extension == "hevc":
    command_line += ["-f", "hevc"]
  command_line += ["-r", "20"]
  command_line += ["-i", filename]
  command_line += ["-c", "copy"]
  command_line += ["-map", "0"]
  if extension == "hevc":
    command_line += ["-vtag", "hvc1"]
  command_line += ["-f", "mp4"]
  command_line += ["-movflags", "empty_moov"]
  command_line += ["-"]
  return subprocess.Popen(
    command_line, stdout=subprocess.PIPE
  )


def ffplay_mp4_wrap_process_builder(file_name):
  command_line = ["ffmpeg"]
  command_line += ["-i", file_name]
  command_line += ["-c", "copy"]
  command_line += ["-map", "0"]
  command_line += ["-f", "mp4"]
  command_line += ["-movflags", "empty_moov"]
  command_line += ["-"]
  return subprocess.Popen(
    command_line, stdout=subprocess.PIPE
  )

def parse_content_type_header(header):
    msg = Message()
    msg['Content-Type'] = header
    return msg.get_content_type(), msg.get_params()

def parse_POST(post_data):
  postvars = parse_qs(post_data, keep_blank_values=1)
  return postvars

def parse_addr(postvars, lon, lat, valid_addr):
  if "fav_val" in postvars:
    addr = postvars.get("fav_val")[0]
    real_addr = None
    lon = None
    lat = None
    if addr != "favorites":
      val = params.get("ApiCache_NavDestinations", encoding='utf8')
      if val is not None:
        val = val.rstrip('\x00')
        dests = json.loads(val)
        for item in dests:
          if "label" in item and item["label"] == addr:
            lat = item["latitude"]
            lon = item["longitude"]
            real_addr = item["place_name"]
            break
        else:
          real_addr = None
  if real_addr is not None:
    valid_addr = True
    return real_addr, lon, lat, valid_addr
  else:
    valid_addr = False
    return postvars, lon, lat, valid_addr

def search_addr(postvars, lon, lat, valid_addr):
  if "addr_val" in postvars:
    addr = postvars.get("addr_val")[0]
    if addr != "":
      real_addr, lat, lon = self.query_addr(addr)
  if real_addr is not None:
    valid_addr = True
    return real_addr, lon, lat, valid_addr
  else:
    valid_addr = False
    return postvars, lon, lat, valid_addr