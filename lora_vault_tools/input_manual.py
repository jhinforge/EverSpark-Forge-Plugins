from .config import CATEGORIES
from .common import ask, log, safe_filename


def select_category(default: str = "") -> str:
    print("\n请选择分类：")
    for i, c in enumerate(CATEGORIES, 1):
        mark = "  ← 当前默认" if c == default else ""
        print(f"{i}. {c}{mark}")

    while True:
        raw = ask("输入数字，直接回车使用默认分类：" if default in CATEGORIES else "输入数字：").strip()

        if not raw and default in CATEGORIES:
            return default

        if raw.isdigit() and 1 <= int(raw) <= len(CATEGORIES):
            return CATEGORIES[int(raw) - 1]

        log("ERROR", "分类编号无效，请重新输入；输入 q 可取消")


def ask_with_default(label: str, default: str = "") -> str:
    default = str(default or "")
    if default:
        return ask(f"{label} [{default}]：", default)
    return ask(f"{label}：")


def build_manual_payload() -> dict:
    title = safe_filename(ask("\n请输入 md/template/title 名称："))
    if not title:
        raise RuntimeError("title 不能为空")

    category = select_category()

    fields = {
        "lora_name": ask_with_default("lora_name", title),
        "lora_version": ask_with_default("lora_version"),
        "download_url": ask_with_default("download_url"),
        "trigger_words": ask_with_default("trigger_words"),
        "category": category,
        "model_support": ask_with_default("model_support"),
        "effect": ask_with_default("effect"),
        "notes": ask_with_default("notes"),
    }

    return {
        "title": title,
        "category": category,
        "fields": fields,
    }