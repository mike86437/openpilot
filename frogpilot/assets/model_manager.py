#!/usr/bin/env python3
import json
import os
import re
import requests
import shutil
import sys
import urllib.parse

from pathlib import Path

from openpilot.frogpilot.assets.download_functions import GITLAB_URL, download_file, get_repository_url, handle_error, handle_request_error, verify_download
from openpilot.frogpilot.common.frogpilot_utilities import delete_file, run_cmd
from openpilot.frogpilot.common.frogpilot_variables import DEFAULT_CLASSIC_MODEL, DEFAULT_MODEL, DEFAULT_TINYGRAD_MODEL, MODELS_PATH, RESOURCES_REPO, TINYGRAD_FILES, params, params_default, params_memory

VERSION = "v16"

CANCEL_DOWNLOAD_PARAM = "CancelModelDownload"
DOWNLOAD_PROGRESS_PARAM = "ModelDownloadProgress"
MODEL_DOWNLOAD_PARAM = "ModelToDownload"
MODEL_DOWNLOAD_ALL_PARAM = "DownloadAllModels"

class ModelManager:
  def __init__(self):
    self.downloading_model = False

    self.available_models = (params.get("AvailableModels", encoding="utf-8") or "").split(",")
    self.available_model_names = (params.get("AvailableModelNames", encoding="utf-8") or "").split(",")
    self.model_versions = (params.get("ModelVersions", encoding="utf-8") or "").split(",")

    self.session = requests.Session()
    self.session.headers.update({"User-Agent": "frogpilot-model-downloader/1.0 (https://github.com/FrogAi/FrogPilot)"})

  def check_models(self, boot_run, repo_url):
    downloaded_models = [path for path in MODELS_PATH.iterdir() if path.is_file()]

    for model_file in downloaded_models:
      if not any(model in model_file.name for model in set(self.available_models)):
        print(f"Removing outdated model: {model_file}")
        delete_file(model_file)

    for onnx_file in MODELS_PATH.glob("*.onnx"):
      if onnx_file.is_file():
        print(f"Deleting .onnx file: {onnx_file}")
        delete_file(onnx_file)

    for tmp_file in MODELS_PATH.glob("tmp*"):
      if tmp_file.is_file():
        delete_file(tmp_file)

    if params.get("Model", encoding="utf-8") not in self.available_models:
      params.put("Model", params_default.get("Model", encoding="utf-8"))

    automatically_download_models = not boot_run and params.get_bool("AutomaticallyDownloadModels")
    if not automatically_download_models:
      return

    model_sizes = self.fetch_all_model_sizes(repo_url)
    if not model_sizes:
      print("No model size data available. Skipping model checks")
      return

    needs_download = False
    for model, version in zip(self.available_models, self.model_versions):
      model_files = [model_file for model_file in downloaded_models if model in model_file.name]
      if not model_files:
        needs_download = True
        continue

      for model_file in model_files:
        if model_file.is_file():
          expected_size = model_sizes.get(model_file.name)
          local_size = model_file.stat().st_size
          if expected_size and local_size != expected_size:
            print(f"Model {model} is outdated. Deleting {model_file}...")
            delete_file(model_file)
            needs_download = True

      if version not in {"v1", "v2", "v3", "v4", "v5", "v6"}:
        missing = []
        for filename, _ in TINYGRAD_FILES:
          expected_file = MODELS_PATH / f"{model}_{filename}"
          if not expected_file.is_file():
            missing.append(expected_file)

        if missing:
          print(f"Model {model} is missing required files: {[file.name for file in missing]}")
          for filename, _ in TINYGRAD_FILES:
            delete_file(MODELS_PATH / f"{model}_{filename}")
          needs_download = True
          continue

    if needs_download:
      self.download_all_models()

  @staticmethod
  def compile_model(model_name):
    tinygrad_repo = Path("/data/openpilot/tinygrad_repo")

    compile_script = tinygrad_repo / "examples/openpilot/compile3.py"
    metadata_script = Path("/data/openpilot/frogpilot/tinygrad_modeld/get_model_metadata.py")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{env.get('PYTHONPATH')}:{tinygrad_repo}"

    for suffix in ["driving_policy", "driving_vision"]:
      onnx_path = MODELS_PATH / f"{model_name}_{suffix}.onnx"
      output_path = MODELS_PATH / f"{model_name}_{suffix}_tinygrad.pkl"

      compile_command = [sys.executable, str(compile_script), str(onnx_path), str(output_path)]
      run_cmd(compile_command, success_message="Model compiled successfully!", fail_message="Failed to compile the model...", env=env)

      metadata_command = [sys.executable, str(metadata_script), str(onnx_path)]
      run_cmd(metadata_command, success_message=f"Successfully extracted metadata from {onnx_path.name}!", fail_message=f"Failed to extract metadata from {onnx_path.name}...")

      delete_file(onnx_path)

  @staticmethod
  def copy_default_model():
    classic_default_model_path = MODELS_PATH / f"{DEFAULT_CLASSIC_MODEL}.thneed"
    source_path = Path(__file__).parents[1] / "classic_modeld/models/supercombo.thneed"
    if source_path.is_file() and not classic_default_model_path.is_file():
      shutil.copyfile(source_path, classic_default_model_path)
      print(f"Copied the classic default model from {source_path} to {classic_default_model_path}")

    default_model_path = MODELS_PATH / f"{DEFAULT_MODEL}.thneed"
    source_path = Path(__file__).parents[2] / "selfdrive/modeld/models/supercombo.thneed"
    if source_path.is_file() and not default_model_path.is_file():
      shutil.copyfile(source_path, default_model_path)
      print(f"Copied the default model from {source_path} to {default_model_path}")

    for filename, description in TINYGRAD_FILES:
      source = Path(__file__).parents[1] / "tinygrad_modeld/models" / filename
      target = MODELS_PATH / f"{DEFAULT_TINYGRAD_MODEL}_{filename}"
      if source.is_file() and not target.is_file():
        shutil.copyfile(source, target)
        print(f"Copied the tinygrad {description} from {source} to {target}")

  def download_all_models(self):
    repo_url = get_repository_url(self.session)
    if not repo_url:
      handle_error(None, "GitHub and GitLab are offline...", "Repository unavailable", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
      return

    self.fetch_models(f"{repo_url}/Versions/model_names_{VERSION}.json")

    for model, version in zip(self.available_models, self.model_versions):
      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_ALL_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
        return

      model_files = [model_file for model_file in MODELS_PATH.iterdir() if model_file.is_file() and model in model_file.name]
      if model_files:
        continue

      print(f"Model {model} is not downloaded. Preparing to download...")
      params_memory.put(DOWNLOAD_PROGRESS_PARAM, f"Downloading \"{self.available_model_names[self.available_models.index(model)]}\"...")

      self.download_model(model)

    params_memory.put(DOWNLOAD_PROGRESS_PARAM, "All models downloaded!")

  def download_model(self, model_to_download):
    self.downloading_model = True

    repo_url = get_repository_url(self.session)
    if not repo_url:
      handle_error(None, "GitHub and GitLab are offline...", "Repository unavailable", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
      self.downloading_model = False
      return

    if self.model_versions[self.available_models.index(model_to_download)] in {"v1", "v2", "v3", "v4", "v5", "v6"}:
      model_path = MODELS_PATH / f"{model_to_download}.thneed"
      model_url = f"{repo_url}/Models/{model_to_download}.thneed"

      print(f"Downloading model: {model_to_download}")
      download_file(CANCEL_DOWNLOAD_PARAM, model_path, DOWNLOAD_PROGRESS_PARAM, model_url, MODEL_DOWNLOAD_PARAM, params_memory, self.session)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
        self.downloading_model = False
        return

      if verify_download(model_path, model_url, self.session):
        print(f"Model {model_to_download} downloaded and verified successfully!")
        params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Downloaded!")
        params_memory.remove(MODEL_DOWNLOAD_PARAM)
        self.downloading_model = False
        return

      print(f"Verification failed for model {model_to_download}. Retrying from GitLab...")
      fallback_url = f"{GITLAB_URL}/Models/{model_to_download}.thneed"
      download_file(CANCEL_DOWNLOAD_PARAM, model_path, DOWNLOAD_PROGRESS_PARAM, fallback_url, MODEL_DOWNLOAD_PARAM, params_memory, self.session)

      if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
        handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
        self.downloading_model = False
        return

      if verify_download(model_path, fallback_url, self.session):
        print(f"Model {model_to_download} downloaded and verified successfully from GitLab!")
        params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Downloaded!")
        params_memory.remove(MODEL_DOWNLOAD_PARAM)
        self.downloading_model = False
      else:
        handle_error(model_path, "Verification failed...", "GitLab verification failed", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
        self.downloading_model = False
    else:
      model_files = [
        ("driving_policy.onnx", "driving policy model"),
        ("driving_vision.onnx", "driving vision model"),
      ]

      for index, (file_name, description) in enumerate(model_files, start=1):
        filename = f"{model_to_download}_{file_name}"
        model_path = MODELS_PATH / filename
        model_url = f"{repo_url}/Models/{filename}"

        print(f"Downloading {description} for model: {model_to_download}")
        download_file(CANCEL_DOWNLOAD_PARAM, model_path, DOWNLOAD_PROGRESS_PARAM, model_url, MODEL_DOWNLOAD_PARAM, params_memory, self.session, files=len(model_files), file_number=index)

        if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
          handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
          self.downloading_model = False
          return

        if verify_download(model_path, model_url, self.session):
          print(f"{description.capitalize()} for {model_to_download} downloaded and verified successfully!")
          continue

        print(f"Verification failed for {filename}. Retrying from GitLab...")
        fallback_url = f"{GITLAB_URL}/Models/{filename}"
        download_file(CANCEL_DOWNLOAD_PARAM, model_path, DOWNLOAD_PROGRESS_PARAM, fallback_url, MODEL_DOWNLOAD_PARAM, params_memory, self.session)

        if params_memory.get_bool(CANCEL_DOWNLOAD_PARAM):
          handle_error(None, "Download cancelled...", "Download cancelled...", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
          self.downloading_model = False
          return

        if verify_download(model_path, fallback_url, self.session):
          print(f"{description.capitalize()} for {model_to_download} downloaded and verified successfully from GitLab!")
        else:
          handle_error(model_path, "Verification failed...", f"GitLab verification failed for {filename}", MODEL_DOWNLOAD_PARAM, DOWNLOAD_PROGRESS_PARAM, params_memory)
          self.downloading_model = False
          return

      params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Compiling...")
      print(f"Compiling model '{model_to_download}'...")
      self.compile_model(model_to_download)

      params_memory.put(DOWNLOAD_PROGRESS_PARAM, "Downloaded!")
      params_memory.remove(MODEL_DOWNLOAD_PARAM)

      self.downloading_model = False

  def fetch_all_model_sizes(self, repo_url):
    if "github" in repo_url:
      api_url = f"https://api.github.com/repos/{RESOURCES_REPO}/contents/Models"
    elif "gitlab" in repo_url:
      api_url = f"https://gitlab.com/api/v4/projects/{urllib.parse.quote_plus(RESOURCES_REPO)}/repository/tree?ref=Models"
    else:
      return {}

    try:
      response = self.session.get(api_url)
      response.raise_for_status()

      model_files = [file for file in response.json() if "." in file["name"]]

      if "gitlab" in repo_url:
        model_sizes = {}
        for file in model_files:
          metadata_url = f"https://gitlab.com/api/v4/projects/{urllib.parse.quote_plus(RESOURCES_REPO)}/repository/files/{urllib.parse.quote_plus(file['path'])}/raw?ref=Models"
          metadata_response = self.session.head(metadata_url)
          metadata_response.raise_for_status()
          model_sizes[file["name"]] = int(metadata_response.headers.get("content-length", 0))
        return model_sizes
      else:
        return {file["name"]: file["size"] for file in files if "size" in file}

    except Exception as error:
      handle_request_error(f"Failed to fetch model sizes from {'GitHub' if 'github' in repo_url else 'GitLab'}: {error}", None, None, None, None)
      return {}

  def fetch_models(self, url, boot_run=False):
    try:
      response = self.session.get(url, timeout=10)
      response.raise_for_status()
      model_info = response.json().get("models", [])

      if model_info:
        self.update_model_params(model_info)
        self.check_models(boot_run, url)
    except Exception as error:
      handle_request_error(error, None, None, None, None)
      return []

  def update_model_params(self, model_info):
    self.available_models = [model["id"] for model in model_info]
    self.available_model_names = [model["name"] for model in model_info]
    self.model_versions = [model["version"] for model in model_info]

    params.put("AvailableModels", ",".join(self.available_models))
    params.put("AvailableModelNames", ",".join(self.available_model_names))
    params.put("ModelVersions", ",".join(self.model_versions))
    print("Models list updated successfully")

  def update_models(self, boot_run=False):
    if self.downloading_model:
      return

    repo_url = get_repository_url(self.session)
    if repo_url is None:
      print("GitHub and GitLab are offline...")
      return

    self.fetch_models(f"{repo_url}/Versions/model_names_{VERSION}.json", boot_run)
