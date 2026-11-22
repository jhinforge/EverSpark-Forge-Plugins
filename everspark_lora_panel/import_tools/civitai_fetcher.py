import os
import json
import re
from pathlib import Path
from urllib.parse import urlparse

from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


CIVITAI_API_TOKEN = os.environ.get("CIVITAI_API_TOKEN", "").strip()
REQUEST_TIMEOUT = 20
USER_AGENT = "LoraVault-CivitaiFetcher/1.0"


def build_headers(token=None):
    headers = {"User-Agent": USER_AGENT}
    token = CIVITAI_API_TOKEN if token is None else token
    if token and not token.startswith("这里填"):
        headers["Authorization"] = f"Bearer {token}"
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


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_model_data(model_id: str, token=None):
    api_url = f"https://civitai.com/api/v1/models/{model_id}"
    request = Request(api_url, headers=build_headers(token))
    try:
        with build_opener(NoRedirect).open(request, timeout=REQUEST_TIMEOUT) as response:
            data = response.read(4_194_305)
    except HTTPError as exc:
        raise RuntimeError(f"Civitai API 请求失败：HTTP {exc.code}") from exc
    if len(data) > 4_194_304:
        raise RuntimeError("Civitai 返回的数据太大")
    return json.loads(data)


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

    return [img["url"] for img in images if isinstance(img, dict) and img.get("type") != "video" and isinstance(img.get("url"), str) and img["url"]]


def download_preview_images(title: str, image_urls: list[str]):
    from .common import log, safe_filename
    import requests
    from .config import SOURCE_IMAGE_DIR

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

        resp = requests.get(url, headers=build_headers(""), timeout=REQUEST_TIMEOUT)

        if resp.status_code != 200:
            raise RuntimeError(f"图片下载失败：HTTP {resp.status_code} | {url}")

        dst.write_bytes(resp.content)
        downloaded.append(dst)

    return downloaded


def write_pending_json(payload: dict):
    from .config import PENDING_JSON_PATH

    if PENDING_JSON_PATH.exists():
        raise RuntimeError(f"pending 文件已存在，停止防止覆盖：{PENDING_JSON_PATH}")

    PENDING_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    PENDING_JSON_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def fetch_civitai_to_pending(url: str) -> dict:
    from .common import log
    from .config import PENDING_JSON_PATH

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