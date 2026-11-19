import re

from .config import CANCEL_WORDS


class UserCancelled(Exception):
    pass


def log(level: str, message: str):
    print(f"[{level}] {message}")


def safe_filename(name: str) -> str:
    name = name.strip()
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def normalize_key(name: str) -> str:
    """
    用于相似文件名提醒：
    Better pantyhose / Better_pantyhose / better-pantyhose 会归一到近似 key。
    只做提醒，不做强制拦截。
    """
    name = name.lower().strip()
    name = re.sub(r"\.md$", "", name, flags=re.I)
    name = re.sub(r"[\s_\-\.]+", "", name)
    return name


def ask(prompt: str, default: str = "") -> str:
    value = input(prompt).strip()
    if value.lower() in CANCEL_WORDS:
        raise UserCancelled()
    return value if value else default


def ask_confirm(prompt: str, default_no: bool = True) -> bool:
    suffix = "y/N" if default_no else "Y/n"
    raw = ask(f"{prompt} [{suffix}]：").strip().lower()

    if not raw:
        return not default_no

    if raw in {"y", "yes", "是", "确认", "继续"}:
        return True
    if raw in {"n", "no", "否", "不", "取消"}:
        return False

    log("WARN", "输入无法识别，按取消处理")
    return False