from pathlib import Path
import re
from typing import Optional

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None


# =====================================================
# LoRA Thumb Cache Rebuilder
# 功能：
# 1. 扫描 D:\Vault\LoraVault\lora 下所有 md
# 2. 解析 md 正文里的第一张图片引用
# 3. 按 DataviewJS 面板 V3.4.2+ 的缓存协议重建缩略图
# 4. 默认清空旧缓存后重建
#
# 注意：
# - 不修改 md
# - 不修改 Assets 原图
# - 只处理 temp/lora_thumb_cache
# =====================================================

VAULT_ROOT = Path(r"D:\Vault\LoraVault")
LORA_MD_ROOT = VAULT_ROOT / "lora"
THUMB_CACHE_ROOT = VAULT_ROOT / "temp" / "lora_thumb_cache"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
THUMB_SIZE = (420, 420)
THUMB_EXT = ".jpg"
THUMB_FORMAT = "JPEG"
THUMB_QUALITY = 86

# 默认清空旧缓存后重建。
# 如果你只是想补缺失缓存，可以改成 False。
CLEAR_OLD_CACHE = True


class CacheBuildStats:
    def __init__(self):
        self.total_md = 0
        self.created = 0
        self.skipped_existing = 0
        self.no_image_ref = 0
        self.image_missing = 0
        self.failed = 0
        self.deleted_old = 0


def log(level: str, msg: str):
    print(f"[{level}] {msg}")


def normalize_vault_path(path: str) -> str:
    return str(path or "").replace("\\", "/")


def fnv1a_32(text: str) -> str:
    """
    必须和 DataviewJS 面板里的 fnv1a32() 保持一致。
    输入：md 的 vault 相对路径，例如：
    lora/服装/Better_pantyhose.md

    输出：8位十六进制 hash，例如：
    9a4e1c2f
    """
    h = 0x811C9DC5
    for ch in text:
        h ^= ord(ch)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def safe_stem(stem: str) -> str:
    """
    必须和 DataviewJS 面板里的 safeStem 规则一致：
    stem.replace(/[\\/:*?"<>|#^\\[\\]]+/g, "_").slice(0, 80) || "lora"
    """
    cleaned = re.sub(r'[\\/:*?"<>|#^\[\]]+', "_", stem)
    cleaned = cleaned[:80]
    return cleaned or "lora"


def thumb_cache_name_from_md_rel(md_rel_path: str) -> str:
    """
    当前缓存协议：
    md 相对路径：lora/服装/Better_pantyhose.md
    缓存名：Better_pantyhose_<fnv1a32(md路径)>.jpg
    """
    md_rel_path = normalize_vault_path(md_rel_path)
    stem = Path(md_rel_path).name
    if stem.lower().endswith(".md"):
        stem = stem[:-3]
    return f"{safe_stem(stem)}_{fnv1a_32(md_rel_path)}{THUMB_EXT}"


def find_first_image_link(md_text: str) -> Optional[str]:
    """
    解析 md 正文中的第一张图片引用。
    支持：
    ![[Assets/Loras/001/xxx.jpg]]
    ![[xxx.jpg]]
    ![](Assets/Loras/001/xxx.jpg)
    """
    wiki_matches = re.findall(r'!\[\[([^\]]+)\]\]', md_text)
    for raw in wiki_matches:
        link = raw.split("|", 1)[0].strip()
        if Path(link).suffix.lower() in IMAGE_EXTS:
            return link

    md_matches = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', md_text)
    for raw in md_matches:
        link = raw.strip().strip("<>").split("?", 1)[0]
        if Path(link).suffix.lower() in IMAGE_EXTS:
            return link

    return None


def resolve_image_path(link: str, md_path: Path) -> Optional[Path]:
    """
    尽量模拟 Obsidian 的图片解析：
    1. 如果 link 是 vault 相对路径，直接找 VAULT_ROOT/link
    2. 如果 link 是相对 md 所在目录的路径，找 md_dir/link
    3. 如果只是文件名，在 Assets/Loras 下递归查找
    """
    link = normalize_vault_path(link).strip()
    link = link.split("#", 1)[0].split("?", 1)[0]
    link = link.replace("%20", " ")

    candidates = [
        VAULT_ROOT / link,
        md_path.parent / link,
    ]

    for c in candidates:
        if c.exists() and c.is_file():
            return c

    if "/" not in link and "\\" not in link:
        asset_root = VAULT_ROOT / "Assets" / "Loras"
        if asset_root.exists():
            matches = [p for p in asset_root.rglob(link) if p.is_file()]
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                log("WARN", f"图片文件名存在多个匹配，使用第一个：{link}")
                for p in matches:
                    log("WARN", f"  - {p}")
                return matches[0]

    return None


def clear_old_cache(stats: CacheBuildStats):
    if not THUMB_CACHE_ROOT.exists():
        return

    old_files = [p for p in THUMB_CACHE_ROOT.iterdir() if p.is_file()]
    for p in old_files:
        try:
            p.unlink()
            stats.deleted_old += 1
        except Exception as e:
            log("WARN", f"旧缓存删除失败：{p} -> {e}")


def build_thumb(src_image: Path, dst_thumb: Path):
    if Image is None or ImageOps is None:
        raise RuntimeError("未安装 Pillow。请先运行：python -m pip install pillow")

    dst_thumb.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(src_image) as im:
        im = ImageOps.exif_transpose(im)
        im.thumbnail(THUMB_SIZE, Image.Resampling.LANCZOS)

        if im.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", im.size, (255, 255, 255))
            bg.paste(im, mask=im.getchannel("A"))
            im = bg
        elif im.mode != "RGB":
            im = im.convert("RGB")

        im.save(dst_thumb, THUMB_FORMAT, quality=THUMB_QUALITY, optimize=True)


def rebuild():
    stats = CacheBuildStats()

    if Image is None:
        raise RuntimeError("未安装 Pillow。请先运行：python -m pip install pillow")

    if not LORA_MD_ROOT.exists():
        raise RuntimeError(f"LoRA md 目录不存在：{LORA_MD_ROOT}")

    THUMB_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    print("===== LoRA Thumb Cache Rebuilder =====")
    log("INFO", f"Vault: {VAULT_ROOT}")
    log("INFO", f"LoRA md root: {LORA_MD_ROOT}")
    log("INFO", f"Thumb cache: {THUMB_CACHE_ROOT}")
    log("INFO", f"Clear old cache: {CLEAR_OLD_CACHE}")

    if CLEAR_OLD_CACHE:
        log("INFO", "清空旧缓存...")
        clear_old_cache(stats)
        log("OK", f"旧缓存删除完成：{stats.deleted_old} 个文件")

    md_files = sorted(LORA_MD_ROOT.rglob("*.md"))
    stats.total_md = len(md_files)

    log("INFO", f"发现 md 文件：{stats.total_md}")

    for md_path in md_files:
        try:
            md_rel = md_path.relative_to(VAULT_ROOT).as_posix()
            cache_name = thumb_cache_name_from_md_rel(md_rel)
            thumb_path = THUMB_CACHE_ROOT / cache_name

            if thumb_path.exists() and not CLEAR_OLD_CACHE:
                stats.skipped_existing += 1
                continue

            text = md_path.read_text(encoding="utf-8")
            image_link = find_first_image_link(text)

            if not image_link:
                stats.no_image_ref += 1
                log("WARN", f"未找到图片引用：{md_rel}")
                continue

            image_path = resolve_image_path(image_link, md_path)

            if not image_path:
                stats.image_missing += 1
                log("WARN", f"图片引用无法解析：{md_rel} -> {image_link}")
                continue

            build_thumb(image_path, thumb_path)
            stats.created += 1
            log("OK", f"缓存生成：{cache_name}")

        except Exception as e:
            stats.failed += 1
            log("WARN", f"处理失败：{md_path} -> {e}")

    print("\n===== 重建完成 =====")
    print(f"[OK] md 总数：{stats.total_md}")
    print(f"[OK] 新建缓存：{stats.created}")
    print(f"[OK] 跳过已有：{stats.skipped_existing}")
    print(f"[WARN] 无图片引用：{stats.no_image_ref}")
    print(f"[WARN] 图片缺失/无法解析：{stats.image_missing}")
    print(f"[WARN] 处理失败：{stats.failed}")
    print(f"[OK] 删除旧缓存：{stats.deleted_old}")

    if stats.no_image_ref or stats.image_missing or stats.failed:
        print("\n[WARN] 有部分条目未生成缓存，请查看上面的 WARN 日志。")
    else:
        print("\n[OK] 全部缓存重建成功。")


if __name__ == "__main__":
    try:
        rebuild()
    except Exception as e:
        print(f"\n[ERROR] {e}")
