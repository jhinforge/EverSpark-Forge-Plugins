import re
from pathlib import Path


def fnv1a_32(text: str) -> str:
    """
    必须和 DataviewJS 面板 V3.4.2 的 fnv1a32() 保持一致。
    """
    h = 0x811C9DC5
    for ch in text:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def normalize_vault_path(path: str) -> str:
    return str(path or "").replace("\\", "/")


def thumb_cache_name_from_md_path(md_rel_path: str) -> str:
    """
    缓存协议固定函数。

    必须和 DataviewJS 面板 V3.4.2 保持一致：
    1. normalizeVaultPath(md_rel_path)
    2. stem = md 文件名去掉 .md
    3. safeStem = stem.replace(/[\\/:*?"<>|#^\\[\\]]+/g, "_").slice(0, 80) || "lora"
    4. cacheName = `${safeStem}_${fnv1a32(md_rel_path)}.jpg`

    注意：
    - 这里不会修改原图归档路径
    - 这里不会修改原图文件名
    - 只影响 temp/lora_thumb_cache 里的缓存图命名
    """
    source_path = normalize_vault_path(md_rel_path)
    if not source_path:
        return ""

    stem = Path(source_path).name
    stem = re.sub(r"\.md$", "", stem, flags=re.I)
    safe_stem = re.sub(r'[\\/:*?"<>|#^\[\]]+', "_", stem)[:80] or "lora"
    return f"{safe_stem}_{fnv1a_32(source_path)}.jpg"
