import os
from pathlib import Path
import json
import re
import requests
from urllib.parse import urlparse

# =========================
# Config Layer
# =========================
CIVITAI_API_TOKEN = os.environ.get("CIVITAI_API_TOKEN", "").strip()   # 可选，不填就走公开 API
REQUEST_TIMEOUT = 20
USER_AGENT = "LoraVault-Fetcher/1.1"

PENDING_JSON_PATH = Path(r"D:\logtemp\lora_import_pending.json")
SOURCE_IMAGE_DIR = Path(r"D:\logtemp")


# =========================
# Utils
# =========================
def build_headers():
    headers = {
        "User-Agent": USER_AGENT
    }

    if CIVITAI_API_TOKEN.strip():
        headers["Authorization"] = f"Bearer {CIVITAI_API_TOKEN}"

    return headers


def safe_filename(name: str) -> str:
    name = name.strip()
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def parse_civitai_url(url: str):
    url = url.strip()

    model_match = re.search(r"/models/(\d+)", url)
    if not model_match:
        raise RuntimeError("无法解析 modelId，URL 非法")

    model_id = model_match.group(1)

    version_match = re.search(r"modelVersionId=(\d+)", url)
    version_id = version_match.group(1) if version_match else None

    return model_id, version_id


def safe_get(data, *keys, default=""):
    cur = data
    try:
        for key in keys:
            cur = cur[key]
        return cur if cur is not None else default
    except (KeyError, IndexError, TypeError):
        return default


def guess_ext_from_url(url: str) -> str:
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()

    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return suffix

    return ".jpg"


# =========================
# API Layer
# =========================
def fetch_model_data(model_id: str):
    api_url = f"https://civitai.com/api/v1/models/{model_id}"

    resp = requests.get(
        api_url,
        headers=build_headers(),
        timeout=REQUEST_TIMEOUT
    )

    if resp.status_code != 200:
        raise RuntimeError(f"API 请求失败：HTTP {resp.status_code}")

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


# =========================
# Normalize Layer
# =========================
def normalize(model_data: dict, version_data: dict, source_url: str):
    title = safe_get(model_data, "name", default="").strip()
    version_name = safe_get(version_data, "name", default="").strip()

    trained_words = safe_get(
        version_data,
        "trainedWords",
        default=[]
    )

    if isinstance(trained_words, list):
        trigger_words = ", ".join(trained_words)
    else:
        trigger_words = ""

    base_model = safe_get(
        version_data,
        "baseModel",
        default=""
    )

    files = safe_get(version_data, "files", default=[])

    real_download_url = ""
    file_name = ""

    if files and isinstance(files, list):
        first_file = files[0]
        real_download_url = safe_get(
            first_file,
            "downloadUrl",
            default=""
        )
        file_name = safe_get(
            first_file,
            "name",
            default=""
        )

    return {
        "title": title,
        "category": "",
        "lora_name": title,
        "lora_version": version_name,

        # 给 Obsidian md 使用：保存页面 URL
        "download_url": source_url,

        # 给模型下载管线使用：不写入 md
        "real_download_url": real_download_url,
        "file_name": file_name,

        "trigger_words": trigger_words,
        "model_support": base_model,
        "tested": False,
        "effect": "",
        "notes": "",
        "source_url": source_url
    }


def get_preview_image_urls(version_data: dict):
    images = safe_get(version_data, "images", default=[])

    if not isinstance(images, list):
        return []

    urls = []
    for img in images:
        url = img.get("url")
        if url:
            urls.append(url)

    return urls


# =========================
# Image Download Layer
# =========================
def download_preview_images(title: str, image_urls: list[str]):
    SOURCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    if not image_urls:
        print("[WARN] 未找到 preview images，跳过图片下载")
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
        print(f"[INFO] 下载图片：{dst.name}")

        resp = requests.get(
            url,
            headers=build_headers(),
            timeout=REQUEST_TIMEOUT
        )

        if resp.status_code != 200:
            raise RuntimeError(f"图片下载失败：HTTP {resp.status_code} | {url}")

        dst.write_bytes(resp.content)
        downloaded.append(dst)

    return downloaded


# =========================
# Output Layer
# =========================
def write_pending_json(payload: dict):
    if PENDING_JSON_PATH.exists():
        raise RuntimeError(
            f"pending 文件已存在，停止防止覆盖：{PENDING_JSON_PATH}"
        )

    PENDING_JSON_PATH.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


# =========================
# Main
# =========================
def main():
    print("===== LoRA Civitai Fetcher V1.1 =====")

    url = input("\n请输入 Civitai URL：").strip()
    if not url:
        raise RuntimeError("URL 不能为空")

    model_id, version_id = parse_civitai_url(url)

    print(f"\n[INFO] model_id = {model_id}")
    if version_id:
        print(f"[INFO] model_version_id = {version_id}")
    else:
        print("[INFO] 未指定 modelVersionId，将使用最新版本")

    model_data = fetch_model_data(model_id)
    version_data = select_model_version(
        model_data,
        version_id
    )

    payload = normalize(
        model_data,
        version_data,
        url
    )

    image_urls = get_preview_image_urls(version_data)
    print(f"[INFO] 找到 preview images：{len(image_urls)} 张")

    write_pending_json(payload)
    downloaded = download_preview_images(
        payload["title"],
        image_urls
    )

    print("\n[OK] pending JSON 生成成功")
    print(f"[OK] 文件位置：{PENDING_JSON_PATH}")
    print(f"[OK] 图片下载目录：{SOURCE_IMAGE_DIR}")
    print(f"[OK] 下载图片数量：{len(downloaded)}")

    print("\n下一步：")
    print("1. 人工检查 / 修改 pending JSON")
    print("2. 人工删除 D:\\logtemp 里不想入库的图片")
    print("3. 再交给 lora_md_importer.py 正式入库")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}")