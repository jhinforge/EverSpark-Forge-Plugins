import re
from pathlib import Path

from .config import (
    THUMB_CACHE_ROOT,
    THUMB_SIZE,
    THUMB_FORMAT,
    THUMB_EXT,
    THUMB_QUALITY,
)
from .common import log

try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


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
    return f"{safe_stem}_{fnv1a_32(source_path)}.{THUMB_EXT}"


def build_thumb_cache(src_image: Path, md_rel_path: str) -> Path | None:
    if not PIL_AVAILABLE:
        log("WARN", "未安装 Pillow，跳过缩略图缓存生成。安装命令：python -m pip install pillow")
        return None

    if not src_image.exists():
        log("WARN", f"原图不存在，跳过缩略图：{src_image}")
        return None

    THUMB_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    thumb_name = thumb_cache_name_from_md_path(md_rel_path)
    thumb_path = THUMB_CACHE_ROOT / thumb_name

    if thumb_path.exists():
        log("INFO", f"缩略图缓存已存在，跳过：{thumb_path.name}")
        return thumb_path

    try:
        with Image.open(src_image) as im:
            im = ImageOps.exif_transpose(im)
            im.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)

            # JPG 不支持透明通道，统一铺白底，避免 RGBA 保存失败
            if im.mode in ("RGBA", "LA"):
                background = Image.new("RGB", im.size, (255, 255, 255))
                alpha = im.getchannel("A")
                background.paste(im.convert("RGBA"), mask=alpha)
                im = background
            elif im.mode != "RGB":
                im = im.convert("RGB")

            im.save(thumb_path, THUMB_FORMAT, quality=THUMB_QUALITY, optimize=True)

        log("OK", f"缩略图缓存已生成：{thumb_path}")
        return thumb_path

    except Exception as e:
        log("WARN", f"缩略图生成失败，但不影响入库：{src_image} -> {e}")
        return None