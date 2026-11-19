import os
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests

from .config import PENDING_JSON_PATH, SOURCE_IMAGE_DIR
from .common import log, safe_filename

CIVITAI_API_TOKEN = os.environ.get("CIVITAI_API_TOKEN", "").strip()
REQUEST_TIMEOUT = 20
USER_AGENT = "LoraVault-CivitaiFetcher/1.0"


def build_headers():
    headers = {"User-Agent": USER_AGENT}
    if CIVITAI_API_TOKEN.strip() and not CIVITAI_API_TOKEN.startswith("这里填"):
        headers["Authorization"] = f"Bearer {CIVITAI_API_TOKEN.strip()}"
    return headers


def safe_get(data, *keys, default=""):
    cur = data
    try:
        for key in keys:
            cur = cur[key]
        return cur if cur is not None else default
    except (KeyError, IndexError, TypeError):
        return default


def parse_civitai_url(url: str):
    model_match = re.search(r"/models/(\d+)", url)
    if not model_match:
        raise RuntimeError("无法解析 modelId，URL 非法")

    model_id = model_match.group(1)
    version_match = re.search(r"modelVersionId=(\d+)", url)
    version_id = version_match.group(1) if version_match else None
    return model_id, version_id


def fetch_model_data(model_id: str):
    api_url = f"https://civitai.com/api/v1/models/{model_id}"
    resp = requests.get(api_url, headers=build_headers(), timeout=REQUEST_TIMEOUT)

    if resp.status_code != 200:
        raise RuntimeError(f"Civitai API 请求失败：HTTP {resp.status_code}")

    return resp.json()


def select_model_version(model_data: dict, version_id: str | None):
    versions = model_data.get("modelVersions", [])

    if not versions:
        raise RuntimeError("模型没有 modelVersions")

    if version_id:
        for v in versions:
            if str(v.get("id")) == str(version_id):
                return v
        raise RuntimeError(f"找不到 modelVersionId={version_id}")

    return versions[0]


def normalize(model_data: dict, version_data: dict, source_url: str):
    title = safe_get(model_data, "name", default="").strip()
    version_name = safe_get(version_data, "name", default="").strip()

    trained_words = safe_get(version_data, "trainedWords", default=[])
    trigger_words = ", ".join(trained_words) if isinstance(trained_words, list) else ""

    base_model = safe_get(version_data, "baseModel", default="")

    files = safe_get(version_data, "files", default=[])
    real_download_url = ""
    file_name = ""

    if files and isinstance(files, list):
        first_file = files[0]
        real_download_url = safe_get(first_file, "downloadUrl", default="")
        file_name = safe_get(first_file, "name", default="")

    return {
        "title": title,
        "category": "",
        "lora_name": title,
        "lora_version": version_name,
        "download_url": source_url,
        "real_download_url": real_download_url,
        "file_name": file_name,
        "trigger_words": trigger_words,
        "model_support": base_model,
        "tested": False,
        "effect": "",
        "notes": "",
        "source_url": source_url,
    }


def guess_ext_from_url(url: str) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()

    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix

    return ".jpg"


def get_preview_image_urls(version_data: dict):
    images = safe_get(version_data, "images", default=[])

    if not isinstance(images, list):
        return []

    return [img.get("url") for img in images if img.get("url")]


def download_preview_images(title: str, image_urls: list[str]):
    SOURCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    if not image_urls:
        log("WARN", "未找到 preview images，跳过图片下载")
        return []

    safe_title = safe_filename(title)
    planned_files = []

    for i, url in enumerate(image_urls, 1):
        ext = guess_ext_from_url(url)
        dst = SOURCE_IMAGE_DIR / f"{safe_title}{i:03d}{ext}"

        if dst.exists():
            raise RuntimeError(f"目标预览图已存在，停止防止覆盖：{dst}")

        planned_files.append((url, dst))

    downloaded = []

    for url, dst in planned_files:
        log("INFO", f"下载图片：{dst.name}")

        resp = requests.get(url, headers=build_headers(), timeout=REQUEST_TIMEOUT)

        if resp.status_code != 200:
            raise RuntimeError(f"图片下载失败：HTTP {resp.status_code} | {url}")

        dst.write_bytes(resp.content)
        downloaded.append(dst)

    return downloaded


def write_pending_json(payload: dict):
    if PENDING_JSON_PATH.exists():
        raise RuntimeError(f"pending 文件已存在，停止防止覆盖：{PENDING_JSON_PATH}")

    PENDING_JSON_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def fetch_civitai_to_pending(url: str) -> dict:
    model_id, version_id = parse_civitai_url(url)

    log("INFO", f"model_id = {model_id}")
    if version_id:
        log("INFO", f"model_version_id = {version_id}")
    else:
        log("INFO", "未指定 modelVersionId，将使用最新版本")

    model_data = fetch_model_data(model_id)
    version_data = select_model_version(model_data, version_id)

    payload = normalize(model_data, version_data, url)

    image_urls = get_preview_image_urls(version_data)
    log("INFO", f"找到 preview images：{len(image_urls)} 张")

    write_pending_json(payload)
    downloaded = download_preview_images(payload["title"], image_urls)

    log("OK", f"pending JSON 已生成：{PENDING_JSON_PATH}")
    log("OK", f"预览图下载数量：{len(downloaded)}")

    return payload