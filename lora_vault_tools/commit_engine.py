from pathlib import Path

from .config import VAULT_ROOT, LORA_MD_ROOT, PENDING_JSON_PATH
from .common import ask_confirm, log, UserCancelled
from .checks import (
    early_md_duplicate_check,
    warn_similar_md_names,
    preflight_check,
)
from .image_assets import (
    ensure_source_images_exist_early,
    get_all_source_images,
    find_target_bucket,
    print_bucket_info,
    plan_asset_dsts,
    make_asset_links,
)
from .md_builder import build_md
from .thumbnail import build_thumb_cache
from .staging import (
    make_staging_dir,
    cleanup_staging,
    copy_images_to_staging,
    commit_staged_images,
    rollback_committed,
)
from .preview import print_final_preview


def cleanup_source_images(selected_images: list[Path]):
    log("INFO", "清理源图片...")
    for src in selected_images:
        try:
            src.unlink()
            log("OK", f"源图片已删除：{src}")
        except Exception as e:
            log("WARN", f"源图片删除失败，请手动检查：{src} -> {e}")


def cleanup_pending_json():
    if not PENDING_JSON_PATH.exists():
        return

    try:
        PENDING_JSON_PATH.unlink()
        log("OK", f"pending JSON 已删除：{PENDING_JSON_PATH}")
    except Exception as e:
        log("WARN", f"pending JSON 删除失败，请手动检查：{PENDING_JSON_PATH} -> {e}")


def commit_import(payload: dict, cleanup_pending: bool = False):
    """
    payload 标准结构：

    {
        "title": "...",
        "category": "...",
        "fields": {
            "lora_name": "...",
            "lora_version": "...",
            "download_url": "...",
            "trigger_words": "...",
            "category": "...",
            "model_support": "...",
            "effect": "...",
            "notes": "..."
        }
    }

    注意：
    - 图片不从 payload 传入
    - 默认使用 D:\\logtemp 当前剩余全部图片
    - 用户应在运行 importer 前手动删掉不想入库的图片
    """
    title = payload["title"]
    category = payload["category"]
    fields = payload["fields"]

    log("INFO", "执行第一轮 md 同名查重...")
    early_md_duplicate_check(title)
    log("OK", "第一轮 md 查重通过：当前 LoRA 库未发现同名 md")

    warn_similar_md_names(title)

    log("INFO", "执行 D:\\logtemp 预览图前置检查...")
    ensure_source_images_exist_early()

    selected_images = get_all_source_images()

    target_bucket = find_target_bucket(len(selected_images))
    print_bucket_info(target_bucket, len(selected_images))

    md_dir = LORA_MD_ROOT / category
    md_dir.mkdir(parents=True, exist_ok=True)

    md_path = md_dir / f"{title}.md"
    md_rel_path = md_path.relative_to(VAULT_ROOT).as_posix()

    planned_dsts = plan_asset_dsts(title, selected_images, target_bucket)

    log("INFO", "执行最终入库前检查...")
    preflight_check(md_path, planned_dsts)
    log("OK", "最终入库前检查通过：未发现同名 md / 同名目标图片")

    print_final_preview(
        title,
        category,
        fields,
        selected_images,
        md_path,
        target_bucket,
        planned_dsts,
    )

    staging_dir = None
    committed_files = []
    thumb_path = None
    md_created = False
    import_completed = False

    try:
        staging_dir = make_staging_dir(title)

        log("INFO", "复制图片到 staging...")
        staged_files = copy_images_to_staging(
            selected_images,
            planned_dsts,
            staging_dir,
        )

        log("INFO", "提交图片到正式 Assets...")
        committed_files = commit_staged_images(
            staged_files,
            planned_dsts,
        )

        asset_links = make_asset_links(committed_files)

        log("INFO", "写入 md 文件...")
        md_text = build_md(title, fields, asset_links)

        # 第三层防覆盖：即使前面检查后外部突然创建同名 md，x 模式也会拒绝覆盖
        with md_path.open("x", encoding="utf-8") as f:
            f.write(md_text)
        md_created = True
        log("OK", f"md 已创建：{md_path}")

        log("INFO", "生成缩略图缓存...")
        if committed_files:
            thumb_path = build_thumb_cache(
                committed_files[0],
                md_rel_path,
            )

        import_completed = True

    except Exception:
        rollback_committed(
            committed_files,
            md_path if md_created else None,
            thumb_path,
        )
        raise

    finally:
        cleanup_staging(staging_dir)

        if import_completed:
            cleanup_source_images(selected_images)

            if cleanup_pending:
                cleanup_pending_json()
        else:
            log("WARN", "入库未完整成功，已保留 D:\\logtemp 源图片，避免误删")

    print("\n[OK] 入库完成")
    print(f"[OK] md 文件：{md_path}")
    print(f"[OK] bucket：{target_bucket}")
    print(f"[OK] 图片数量：{len(committed_files)}")
    print(f"[OK] 缩略图缓存：{thumb_path if thumb_path else '未生成 / 已跳过'}")