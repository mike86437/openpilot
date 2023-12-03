#!/usr/bin/env python3
import os
import random
import secrets
import threading
import time

from flask import Flask, render_template, Response, request, send_from_directory, session, redirect, url_for
import requests
from requests.exceptions import ConnectionError
from openpilot.common.realtime import set_core_affinity
import openpilot.system.fleetmanager.helpers as fleet
from openpilot.system.hardware.hw import Paths
from openpilot.system.swaglog import cloudlog

app = Flask(__name__)
target_server_base_url = 'http://127.0.0.1:8282/'

def make_request_with_retry(method, url, data=None, headers=None):
  retries = 3 
  for attempt in range(retries):
    try:
      response = requests.request(method, url, data=data, headers=headers, stream=True)
      return response
    except ConnectionError as e:
      print(f"Error: {e}. Retrying...")
  raise e

def build_target_url(subpath=''):
  return f'{target_server_base_url}/{subpath}' if subpath else target_server_base_url

def handle_request(method, subpath=''):
  target_url = build_target_url(subpath)
  if request.is_json:
    data = request.data
  else:
    data = request.form.to_dict()
  response = make_request_with_retry(method, target_url, data=data, headers=request.headers)
  return Response(response.iter_content(chunk_size=128), content_type=response.headers.get('Content-type'))

@app.route("/")
def home_page():
  return render_template("index.html")

@app.route("/otisserv", methods=['GET', 'POST'])
def otisserv_proxy():
  return handle_request(request.method)

@app.route("/otisserv/<path:subpath>", methods=['GET', 'POST'])
def reverse_proxy(subpath):
  return handle_request(request.method, subpath)

@app.route("/navdirections.json", methods=['GET'])
def otisserv_navdirections():
  return handle_request(request.method, "navdirections.json")

@app.route("/CurrentStep.json", methods=['GET'])
def otisserv_CurrentStep():
  return handle_request(request.method, "CurrentStep.json")

@app.route("/locations", methods=['GET'])
def otisserv_locations():
  return handle_request(request.method, "locations")

@app.route("/set_destination", methods=['POST'])
def otisserv_set_destination():
  return handle_request(request.method, "set_destination")

@app.route("/footage/full/<cameratype>/<route>")
def full(cameratype, route):
  chunk_size = 1024 * 512  # 5KiB
  file_name = cameratype + (".ts" if cameratype == "qcamera" else ".hevc")
  vidlist = "|".join(Paths.log_root() + "/" + segment + "/" + file_name for segment in fleet.segments_in_route(route))

  def generate_buffered_stream():
    with fleet.ffmpeg_mp4_concat_wrap_process_builder(vidlist, cameratype, chunk_size) as process:
      for chunk in iter(lambda: process.stdout.read(chunk_size), b""):
        yield bytes(chunk)
  return Response(generate_buffered_stream(), status=200, mimetype='video/mp4')


@app.route("/footage/<cameratype>/<segment>")
def fcamera(cameratype, segment):
  if not fleet.is_valid_segment(segment):
    return render_template("error.html", error="invalid segment")
  file_name = Paths.log_root() + "/" + segment + "/" + cameratype + (".ts" if cameratype == "qcamera" else ".hevc")
  return Response(fleet.ffmpeg_mp4_wrap_process_builder(file_name).stdout.read(), status=200, mimetype='video/mp4')


@app.route("/footage/<route>")
def route(route):
  if len(route) != 20:
    return render_template("error.html", error="route not found")

  if str(request.query_string) == "b''":
    query_segment = str("0")
    query_type = "qcamera"
  else:
    query_segment = (str(request.query_string).split(","))[0][2:]
    query_type = (str(request.query_string).split(","))[1][:-1]

  links = ""
  segments = ""
  for segment in fleet.segments_in_route(route):
    links += "<a href='"+route+"?"+segment.split("--")[2]+","+query_type+"'>"+segment+"</a><br>"
    segments += "'"+segment+"',"
  return render_template("route.html", route=route, query_type=query_type, links=links, segments=segments, query_segment=query_segment)


@app.route("/footage/")
@app.route("/footage")
def footage():
  return render_template("footage.html", rows=fleet.all_routes())


@app.route("/screenrecords/")
@app.route("/screenrecords")
def screenrecords():
  rows = fleet.list_files(fleet.SCREENRECORD_PATH)
  if not rows:
    return render_template("error.html", error="no screenrecords found at:<br><br>" + fleet.SCREENRECORD_PATH)
  return render_template("screenrecords.html", rows=rows, clip=rows[0])


@app.route("/screenrecords/<clip>")
def screenrecord(clip):
  return render_template("screenrecords.html", rows=fleet.list_files(fleet.SCREENRECORD_PATH), clip=clip)


@app.route("/screenrecords/play/pipe/<file>")
def videoscreenrecord(file):
  file_name = fleet.SCREENRECORD_PATH + file
  return Response(fleet.ffplay_mp4_wrap_process_builder(file_name).stdout.read(), status=200, mimetype='video/mp4')


@app.route("/screenrecords/download/<clip>")
def download_file(clip):
  return send_from_directory(fleet.SCREENRECORD_PATH, clip, as_attachment=True)


@app.route("/about")
def about():
  return render_template("about.html")


@app.route("/error_logs")
def error_logs():
  return render_template("error_logs.html", rows=fleet.list_files(fleet.ERROR_LOGS_PATH))


@app.route("/error_logs/<file_name>")
def open_error_log(file_name):
  f = open(fleet.ERROR_LOGS_PATH + file_name)
  error = f.read()
  return render_template("error_log.html", file_name=file_name, file_content=error)

@app.route("/addr_input", methods=['GET'])
def addr_input():
  return render_template("addr_input.html")


@app.route("/addr_input", methods=['POST'])
def addr_input_post():
  token = ""
  lon = float(0.0)
  lat = float(0.0)
  valid_addr = False
  postvars = request.form.to_dict()
  addr, lon, lat, valid_addr, token = fleet.parse_addr(postvars, lon, lat, valid_addr, token)
  if valid_addr:
    return render_template("nav_confirmation.html", addr=addr, lon=lon, lat=lat, token=token)
  else:
    addr, lon, lat, valid_addr = fleet.search_addr(postvars, lon, lat, valid_addr, token)
    if valid_addr:
      return render_template("nav_confirmation.html", addr=addr, lon=lon, lat=lat, token=token)
    else:
      return render_template("error.html")


def main():
  try:
    set_core_affinity([0, 1, 2, 3])
  except Exception:
    cloudlog.exception("fleet_manager: failed to set core affinity")
  app.secret_key = secrets.token_hex(32)
  app.run(host="0.0.0.0", port=8082)


if __name__ == '__main__':
  main()
