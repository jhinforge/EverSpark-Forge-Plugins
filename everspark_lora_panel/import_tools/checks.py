from pathlib import Path

from .config import LORA_MD_ROOT
from .common import normalize_key, ask_confirm, log, UserCancelled


def find_existing_md_by_title(title: str) -> list[Path]:
    """
    第一轮交互拿到 title 后立即全库精确查重。
    """
    if not LORA_MD_ROOT.exists():
        return []

    target_name = f"{title}.md"
    return sorted(
        p for p in LORA_MD_ROOT.rglob(target_name)
        if p.is_file()
    )


def early_md_duplicate_check(title: str):
    existing = find_existing_md_by_title(title)
    if existing:
        lines = "\n".join(str(p) for p in existing)
        raise RuntimeError(
            "md 已存在，停止防止覆盖。\n"
            "这是第一轮 title 查重触发的保护，避免继续填写字段浪费时间：\n"
            f"{lines}"
        )


def warn_similar_md_names(title: str, *, approved=None):
    """
    相似名提醒：只提醒，不拦截。
    """
    if not LORA_MD_ROOT.exists():
        return

    target_key = normalize_key(title)
    similar = []

    for p in LORA_MD_ROOT.rglob("*.md"):
        if normalize_key(p.stem) == target_key and p.stem != title:
            similar.append(p)

    if not similar:
        return

    if approved is True:
        return
    if approved is False:
        names = ", ".join(p.stem for p in similar[:5])
        raise ValueError(f"发现相似笔记名：{names}。确认后勾选「允许相似笔记名」再提交。")

    print("\n[WARN] 发现相似 md 文件名，请确认不是重复入库：")
    for p in similar[:20]:
        print(f"  - {p}")
    if len(similar) > 20:
        print(f"  ... 还有 {len(similar) - 20} 个未显示")

    if not ask_confirm("是否继续？", default_no=True):
        raise UserCancelled()


def preflight_check(md_path: Path, planned_dsts: list[Path]):
    """
    入库前统一检查，尽量在真正 copy/write 前失败。
    核心保险：
    1. md 同名禁止覆盖
    2. 图片目标同名禁止覆盖
    """
    if md_path.exists():
        raise RuntimeError(f"md 已存在，停止防止覆盖：{md_path}")

    duplicated_dsts = [p for p in planned_dsts if p.exists()]
    if duplicated_dsts:
        lines = "\n".join(str(p) for p in duplicated_dsts)
        raise RuntimeError(f"目标图片已存在，停止防止覆盖：\n{lines}")