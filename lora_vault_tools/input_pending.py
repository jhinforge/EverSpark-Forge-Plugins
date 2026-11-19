import json

from .config import PENDING_JSON_PATH
from .common import log, safe_filename
from .input_manual import select_category, ask_with_default
from .naming import make_title_from_lora_name


def load_pending_json() -> dict:
    if not PENDING_JSON_PATH.exists():
        raise RuntimeError(f"pending JSON 不存在：{PENDING_JSON_PATH}")

    try:
        data = json.loads(PENDING_JSON_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise RuntimeError(f"pending JSON 读取失败：{e}")

    if not isinstance(data, dict):
        raise RuntimeError("pending JSON 格式错误：根对象必须是 dict")

    log("OK", f"已读取 pending JSON：{PENDING_JSON_PATH}")
    return data


def build_pending_payload() -> dict:
    pending = load_pending_json()

    title_default = make_title_from_lora_name(
    pending.get("lora_name") or pending.get("title", "")
)
    title = safe_filename(
        ask_with_default("\n请输入 md/template/title 名称", title_default)
    )

    if not title:
        raise RuntimeError("title 不能为空")

    category = select_category(pending.get("category", ""))

    fields = {
        "lora_name": ask_with_default("lora_name", pending.get("lora_name", title)),
        "lora_version": ask_with_default("lora_version", pending.get("lora_version", "")),
        "download_url": ask_with_default("download_url", pending.get("download_url", "")),
        "trigger_words": ask_with_default("trigger_words", pending.get("trigger_words", "")),
        "category": category,
        "model_support": ask_with_default("model_support", pending.get("model_support", "")),
        "effect": ask_with_default("effect", pending.get("effect", "")),
        "notes": ask_with_default("notes", pending.get("notes", "")),
    }

    return {
        "title": title,
        "category": category,
        "fields": fields,
    }