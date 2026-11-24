"""Bridge the panel's import forms to the existing archive engine."""
import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .import_tools import civitai_fetcher as civitai
from .import_tools.schema import CATEGORIES

MAX_IMAGE = 12 * 1024 * 1024
MAX_IMAGES = 24
MAX_TOTAL = 24 * 1024 * 1024
FIELDS = ("lora_name", "lora_version", "download_url", "trigger_words", "category",
          "model_support", "effect", "notes")
CIVITAI_HOSTS = {"civitai.com", "www.civitai.com", "civitai.red", "www.civitai.red"}
IMAGE_HOSTS = {"image.civitai.com", "images.civitai.com", "imagecache.civitai.com"}


def remote_image(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in IMAGE_HOSTS:
        raise ValueError("不支持这个 Civitai 预览图地址。")
    return url


class PreviewRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            remote_image(newurl)
        except ValueError as exc:
            raise ValueError(f"预览图服务器返回 HTTP {code}，跳转目标不在支持的 Civitai 图片域名内。") from exc
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_fields(url, token):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in CIVITAI_HOSTS:
        raise ValueError("请填写 Civitai 模型页面的 HTTPS 链接。")
    try:
        model_id, version_id = civitai.parse_civitai_url(url)
        model = civitai.fetch_model_data(model_id, token)
        version = civitai.select_model_version(model, version_id)
        fields = civitai.normalize(model, version, url)
    except (RuntimeError, URLError, TimeoutError) as exc:
        raise ValueError(f"无法读取 Civitai 模型资料：{exc}") from exc
    previews = []
    for url in civitai.get_preview_image_urls(version):
        try:
            previews.append(remote_image(url))
        except ValueError:
            continue
    title = re.sub(r'[\\/:*?"<>|\[\]#\x00-\x1f]', "_", fields["title"]).strip(" .")[:100]
    return {"fields": {name: fields[name] for name in FIELDS}, "title": title, "previews": list(dict.fromkeys(previews))[:MAX_IMAGES]}


def fields_for_commit(payload):
    title = payload.get("title")
    if (not isinstance(title, str) or not 0 < len(title.strip()) <= 100 or title.strip().endswith(".")
            or re.search(r'[\\/:*?"<>|\[\]#\x00-\x1f]', title)
            or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\..*)?", title.strip(), re.I)):
        raise ValueError("请输入有效的笔记文件名（不含 .md）。")
    title = title.strip()
    if title.lower().endswith(".md"):
        title = title[:-3].rstrip(" .")
    if not title:
        raise ValueError("请输入有效的笔记文件名。")
    submitted = payload.get("fields")
    if not isinstance(submitted, dict):
        raise ValueError("缺少录入字段。")
    fields = {key: submitted.get(key, "") for key in FIELDS}
    if any(not isinstance(field, str) or len(field) > 8000 for field in fields.values()):
        raise ValueError("录入字段格式有误或超出长度限制。")
    fields = {key: field.strip() for key, field in fields.items()}
    if not fields["lora_name"] or fields["category"] not in CATEGORIES:
        raise ValueError("请填写模型名称并选择分类。")
    return {"title": title, "category": fields["category"], "fields": fields}


def image_bytes(item):
    if not isinstance(item, dict):
        raise ValueError("预览图格式有误。")
    if isinstance(item.get("url"), str):
        url = remote_image(item["url"])
        request = Request(url, headers={
            "User-Agent": civitai.USER_AGENT,
            "Accept": "image/webp,image/png,image/jpeg,image/gif,image/*;q=0.8",
        })
        try:
            with build_opener(PreviewRedirect).open(request, timeout=15) as response:
                return response.read(MAX_IMAGE + 1)
        except HTTPError as exc:
            raise ValueError(f"预览图服务器返回 HTTP {exc.code}。") from exc
        except (TimeoutError, URLError) as exc:
            reason = exc.reason if isinstance(exc, URLError) else exc
            if isinstance(reason, TimeoutError):
                raise ValueError("连接 Civitai 图片服务器超时。") from exc
            raise ValueError(f"无法连接 Civitai 图片服务器（{type(reason).__name__}）。") from exc
    if not isinstance(item.get("data"), str) or len(item["data"]) > (MAX_IMAGE + 2) // 3 * 4:
        raise ValueError("单张预览图最大 12 MB。")
    try:
        return base64.b64decode(item["data"], validate=True)
    except ValueError as exc:
        raise ValueError("无法读取所选预览图。") from exc


def image_suffix(data):
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("预览图须为 PNG、JPEG、GIF 或 WebP。")


def commit(config, payload):
    record = fields_for_commit(payload)
    images = payload.get("images")
    if not isinstance(images, list) or not 1 <= len(images) <= MAX_IMAGES:
        raise ValueError("请选择 1 至 24 张预览图。")

    root = config["temp_dir"]
    root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="lora-import-", dir=root) as temporary:
        stage = Path(temporary)
        total = 0
        sources = []
        for index, item in enumerate(images, 1):
            try:
                data = image_bytes(item)
            except ValueError as exc:
                raise ValueError(f"第 {index} 张预览图读取失败：{exc}") from exc
            total += len(data)
            if len(data) > MAX_IMAGE or total > MAX_TOTAL:
                raise ValueError("预览图超过单张 12 MB 或合计 24 MB 的限制。")
            image = stage / f"{index:03d}{image_suffix(data)}"
            image.write_bytes(data)
            sources.append(str(image))
        cfg = {key: str(path) for key, path in config.items()}
        cfg["temp_dir"] = str(stage)
        settings = stage / "lora-config.json"
        settings.write_text(json.dumps(cfg), encoding="utf-8")
        request = {"record": record, "images": sources, "approve_similar": payload.get("approve_similar") is True}
        result = subprocess.run(
            [sys.executable, "-X", "utf8", str(Path(__file__).with_name("import_worker.py"))],
            input=json.dumps(request), encoding="utf-8", capture_output=True,
            env={**os.environ, "LORA_PLUGIN_CONFIG": str(settings)},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise ValueError(result.stdout.strip() or "LoRA 入库进程运行失败。")
        return {"note": (Path(record["category"]) / (record["title"] + ".md")).as_posix()}
