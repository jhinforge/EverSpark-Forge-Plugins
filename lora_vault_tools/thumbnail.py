from pathlib import Path

from .config import (
    THUMB_CACHE_ROOT,
    THUMB_SIZE,
    THUMB_FORMAT,
    THUMB_QUALITY,
)
from .common import log
from everspark_lora_panel.thumbnail_names import normalize_vault_path, thumb_cache_name_from_md_path

try:
    from PIL import Image, ImageOps
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


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