from pathlib import Path
from datetime import datetime
import shutil

from .config import STAGING_ROOT
from .common import log


def make_staging_dir(title: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    staging = STAGING_ROOT / f"{title}_{stamp}"
    staging.mkdir(parents=True, exist_ok=False)
    return staging


def cleanup_staging(staging_dir: Path | None):
    if staging_dir and staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)
        log("OK", f"staging 已清理：{staging_dir}")


def copy_images_to_staging(
    selected_images: list[Path],
    planned_dsts: list[Path],
    staging_dir: Path
) -> list[Path]:
    staged_files = []

    for src, final_dst in zip(selected_images, planned_dsts):
        staged = staging_dir / final_dst.name
        shutil.copy2(src, staged)
        staged_files.append(staged)
        log("OK", f"图片已复制到 staging：{staged.name}")

    return staged_files


def commit_staged_images(
    staged_files: list[Path],
    planned_dsts: list[Path],
    *, committed: list[Path]
) -> list[Path]:

    for staged, dst in zip(staged_files, planned_dsts):
        if dst.exists():
            raise RuntimeError(f"提交前发现目标图片已存在，停止防止覆盖：{dst}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        with dst.open("xb") as output:
            committed.append(dst)
            with staged.open("rb") as source:
                shutil.copyfileobj(source, output)
        log("OK", f"图片已提交到正式库：{dst}")

    return committed


def rollback_committed(
    committed_files: list[Path],
    md_path: Path | None,
    thumb_path: Path | None
):
    """
    防半残：只清理本次脚本明确创建出来的文件。
    不碰历史文件。
    """
    log("WARN", "开始回滚本次已提交文件，防止半残入库")

    for p in committed_files:
        try:
            if p.exists():
                p.unlink()
                log("OK", f"已回滚图片：{p}")
        except Exception as e:
            log("WARN", f"图片回滚失败，请手动检查：{p} -> {e}")

    try:
        if md_path and md_path.exists():
            md_path.unlink()
            log("OK", f"已回滚 md：{md_path}")
    except Exception as e:
        log("WARN", f"md 回滚失败，请手动检查：{md_path} -> {e}")

    try:
        if thumb_path and thumb_path.exists():
            thumb_path.unlink()
            log("OK", f"已回滚缩略图缓存：{thumb_path}")
    except Exception as e:
        log("WARN", f"缩略图回滚失败，请手动检查：{thumb_path} -> {e}")