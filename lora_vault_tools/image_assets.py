from pathlib import Path

from .config import (
    SOURCE_IMAGE_DIR,
    ASSET_ROOT,
    BUCKET_LIMIT,
    IMAGE_EXTS,
    VAULT_ROOT,
)
from .common import log


def list_source_images() -> list[Path]:
    if not SOURCE_IMAGE_DIR.exists():
        return []

    files = [
        p for p in SOURCE_IMAGE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def ensure_source_images_exist_early():
    if not SOURCE_IMAGE_DIR.exists():
        raise RuntimeError(f"源图片目录不存在：{SOURCE_IMAGE_DIR}")

    images = list_source_images()
    if not images:
        raise RuntimeError(
            f"{SOURCE_IMAGE_DIR} 没有找到预览图。\n"
            "请先把 LoRA 预览图下载到 D:\\logtemp 后再运行脚本。"
        )

    log("OK", f"预览图前置检查通过：D:\\logtemp 当前有 {len(images)} 张图片")


def get_all_source_images() -> list[Path]:
    """
    当前 D:\\logtemp 剩余全部图片
    = 本次正式入库图片
    前提：用户已经手动删掉不想要的图
    """
    images = list_source_images()

    if not images:
        raise RuntimeError(f"源图片目录没有找到图片：{SOURCE_IMAGE_DIR}")

    print("\nD:\\logtemp 本次将入库的全部图片：")
    for p in images:
        print(f"  - {p.name}")

    return images


def bucket_number(path: Path) -> int:
    try:
        return int(path.name)
    except ValueError:
        return 0


def get_bucket_file_count(bucket: Path) -> int:
    if not bucket.exists():
        return 0
    return sum(1 for p in bucket.iterdir() if p.is_file())


def find_target_bucket(need_count: int) -> Path:
    ASSET_ROOT.mkdir(parents=True, exist_ok=True)

    buckets = [
        p for p in ASSET_ROOT.iterdir()
        if p.is_dir() and p.name.isdigit()
    ]
    buckets = sorted(buckets, key=bucket_number)

    if not buckets:
        bucket = ASSET_ROOT / "001"
        bucket.mkdir(parents=True, exist_ok=True)
        return bucket

    # 先从旧桶开始扫描，找到第一个能完整容纳本次图片的 bucket
    for bucket in buckets:
        used = get_bucket_file_count(bucket)
        remaining = BUCKET_LIMIT - used

        if remaining >= need_count:
            return bucket

    # 所有旧桶都放不下，才创建新 bucket
    next_num = bucket_number(buckets[-1]) + 1
    next_bucket = ASSET_ROOT / f"{next_num:03d}"
    next_bucket.mkdir(parents=True, exist_ok=True)
    return next_bucket


def print_bucket_info(bucket: Path, need_count: int):
    used = get_bucket_file_count(bucket)
    remaining = BUCKET_LIMIT - used
    after_remaining = remaining - need_count

    log("INFO", f"当前目标 bucket：{bucket}")
    log("INFO", f"bucket 已用：{used} / {BUCKET_LIMIT}")
    log("INFO", f"本次计划写入图片：{need_count}")
    log("INFO", f"写入后预计剩余：{after_remaining}")


def plan_asset_dsts(title: str, selected_images: list[Path], target_bucket: Path) -> list[Path]:
    return [
        target_bucket / f"{title}{i:03d}{src.suffix.lower()}"
        for i, src in enumerate(selected_images, 1)
    ]


def make_asset_links(committed_files: list[Path]) -> list[str]:
    return [p.relative_to(VAULT_ROOT).as_posix() for p in committed_files]