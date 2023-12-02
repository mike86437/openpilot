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

def make_request_with_retry(method, url, data=None, headers=None):
  retries = 3  # Adjust the number of retries as needed
  for attempt in range(retries):
    try:
      if data is not None and method == 'POST':
        # For POST requests, use json parameter for data
        response = requests.request(method, url, json=data, headers=headers, stream=True)
      else:
        # For GET requests or other methods, use data parameter directly
        response = requests.request(method, url, data=data, headers=headers, stream=True)

      return response
    except ConnectionError as e:
      print(f"Error: {e}. Retrying...")

  # If all retries fail, raise the last encountered exception
  raise e

@app.route("/")
def home_page():
  return render_template("index.html")

# Route for handling GET requests
@app.route("/otisserv", methods=['GET'])
def otisserv_get():
  target_server_url = 'http://127.0.0.1:8082/'
  method = request.method
  print(f"GET Request: {request.url}")
  response = make_request_with_retry(method, target_server_url, data=request.data, headers=request.headers)
  return Response(response.iter_content(chunk_size=128), content_type=response.headers.get('Content-type'))

# Route for handling POST requests
@app.route("/otisserv", methods=['POST'])
def otisserv_post():
  target_server_url = 'http://127.0.0.1:8082/'
  method = request.method
  print(f"POST Request: {request.url}\nData: {list(request.form.items())}")
  response = make_request_with_retry(method, target_server_url, data=list(request.form.items()), headers=request.headers)
  return Response(response.iter_content(chunk_size=128), content_type=response.headers.get('Content-type'))

# Route for handling GET requests
@app.route("/otisserv/<path:subpath>", methods=['GET'])
def reverse_proxy_get(subpath):
  target_server_url = f'http://127.0.0.1:8082/{subpath}'
  method = request.method
  print(f"GET Request: {request.url}")
  response = make_request_with_retry(method, target_server_url, data=request.data, headers=request.headers)
  return Response(response.iter_content(chunk_size=128), content_type=response.headers.get('Content-type'))

# Route for handling POST requests
@app.route("/otisserv/<path:subpath>", methods=['POST'])
def reverse_proxy_post(subpath):
  target_server_url = f'http://127.0.0.1:8082/{subpath}'
  method = request.method
  print(f"POST Request: {request.url}\nData: {list(request.form.items())}")
  response = make_request_with_retry(method, target_server_url, data=list(request.form.items()), headers=request.headers)
  return Response(response.iter_content(chunk_size=128), content_type=response.headers.get('Content-type'))

# Route for handling POST requests
@app.route("/confirm_destination_ajax", methods=['POST'])
def confirm_destination_ajax_post():
    target_server_url = 'http://127.0.0.1:8082/'  # Update with your correct URL
    method = request.method
    print(f"POST Request: {request.url}\nData: {list(request.form.items())}")
    response = make_request_with_retry(method, target_server_url, data=list(request.form.items()), headers=request.headers)
    return Response(response.iter_content(chunk_size=128), content_type=response.headers.get('Content-type'))

@app.route("/otisserv/confirm_destination_ajax", methods=['POST'])
def confirm_destination_ajax_post():
    target_server_url = 'http://127.0.0.1:8082/'  # Update with your correct URL
    method = request.method
    print(f"POST Request: {request.url}\nData: {list(request.form.items())}")
    response = make_request_with_retry(method, target_server_url, data=list(request.form.items()), headers=request.headers)
    return Response(response.iter_content(chunk_size=128), content_type=response.headers.get('Content-type'))


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


def main():
  try:
    set_core_affinity([0, 1, 2, 3])
  except Exception:
    cloudlog.exception("fleet_manager: failed to set core affinity")
  app.secret_key = secrets.token_hex(32)
  app.run(host="0.0.0.0", port=5050)


if __name__ == '__main__':
  main()
