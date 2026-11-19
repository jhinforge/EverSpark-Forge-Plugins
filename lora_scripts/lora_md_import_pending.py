import sys
import os
from pathlib import Path

# 允许直接运行本目录中的脚本，同时导入工作区根目录下的共享包。
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from lora_vault_tools.common import UserCancelled, ask, log

from lora_vault_tools.config import (
    PENDING_JSON_PATH,
    SOURCE_IMAGE_DIR,
    PREVIEW_REVIEW_THRESHOLD,
)

from lora_vault_tools.civitai_fetcher import fetch_civitai_to_pending
from lora_vault_tools.input_pending import (
    build_pending_payload,
    load_pending_json,
)
from lora_vault_tools.commit_engine import commit_import

from lora_vault_tools.workflow_state import (
    ensure_state,
    save_json,
    print_state,
    mark_state,
    is_done,
)

from lora_vault_tools.model_pipeline import (
    run_model_pipeline,
    cleanup_local_model,
)


def ask_model_pipeline_enabled() -> bool:
    print("\n是否下载模型并上传 R2？")
    print("直接回车 = 确认执行")
    print("输入任意内容后回车 = 跳过模型下载")

    raw = ask("选择：").strip()
    return raw == ""


def review_preview_images_if_needed(pending: dict) -> dict:
    if is_done(pending, "preview_review_completed"):
        log("INFO", "检测到预览图已筛选，跳过图片筛选阶段")
        return pending

    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    images = [
        p for p in Path(SOURCE_IMAGE_DIR).iterdir()
        if p.is_file() and p.suffix.lower() in image_exts
    ]

    if len(images) <= PREVIEW_REVIEW_THRESHOLD:
        log("INFO", f"预览图数量 {len(images)} 张，不需要强制筛选")
        pending = mark_state(pending, "preview_review_completed", True)
        save_json(pending, PENDING_JSON_PATH)
        return pending

    log("WARN", f"检测到 {len(images)} 张预览图，超过 {PREVIEW_REVIEW_THRESHOLD} 张")
    log("WARN", f"即将打开目录，请删除不想入库的图片：{SOURCE_IMAGE_DIR}")

    if hasattr(os, "startfile"):
        os.startfile(SOURCE_IMAGE_DIR)

    input("\n请筛选预览图：删除不想入库的图片后，按 Enter 继续...")

    remaining_images = [
        p.name for p in Path(SOURCE_IMAGE_DIR).iterdir()
        if p.is_file() and p.suffix.lower() in image_exts
    ]

    pending["selected_images"] = remaining_images

    pending = mark_state(pending, "preview_review_completed", True)
    save_json(pending, PENDING_JSON_PATH)

    log("INFO", f"预览图筛选完成，保留 {len(remaining_images)} 张")

    return pending


def ensure_pending_json() -> None:
    if PENDING_JSON_PATH.exists():
        log("INFO", f"检测到已有 pending JSON：{PENDING_JSON_PATH}")
        return

    url = ask("\n未检测到 pending JSON，请输入 Civitai URL：").strip()
    if not url:
        raise RuntimeError("Civitai URL 不能为空")

    fetch_civitai_to_pending(url)


def main() -> None:
    print("===== LoRA MD Import Pending V3.2 One-Click =====")

    ensure_pending_json()

    pending = load_pending_json()
    pending = ensure_state(pending)
    save_json(pending, PENDING_JSON_PATH)
    print_state(pending)

    pending = review_preview_images_if_needed(pending)

    if is_done(pending, "metadata_confirmed"):
        log("INFO", "检测到字段已确认，跳过字段录入")
        payload = pending
    else:
        payload = build_pending_payload()

        # 把人工确认后的字段写回 pending JSON，避免断点续跑时用回 lora_name 原始名。
        pending.update(payload)

        pending = mark_state(
            pending,
            "metadata_confirmed",
            True,
        )

        save_json(
            pending,
            PENDING_JSON_PATH,
        )

    local_model_path = None
    model_pipeline_enabled = ask_model_pipeline_enabled()

    if is_done(pending, "r2_uploaded"):
        log("INFO", "检测到模型已上传 R2，跳过模型下载 / 校验 / 上传流程")

    elif model_pipeline_enabled:
        log("INFO", "已选择执行模型下载 / 校验 / R2 上传流程")
        local_model_path = run_model_pipeline(payload["title"], pending)

        pending = mark_state(pending, "model_downloaded", True)
        pending = mark_state(pending, "model_verified", True)
        pending = mark_state(pending, "r2_uploaded", True)
        save_json(pending, PENDING_JSON_PATH)

    else:
        log("WARN", "已跳过模型下载 / 校验 / R2 上传流程")

    # 无论模型流程是执行、跳过，还是已经上传过 R2，md 入库都必须继续执行。
    commit_import(payload, cleanup_pending=True)

    # 只有本轮确实下载过本地模型，才删除本地模型。
    if local_model_path:
        cleanup_local_model(local_model_path)


if __name__ == "__main__":
    try:
        main()
    except UserCancelled:
        print("\n[CANCEL] 用户主动取消，未写入任何文件")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n[CANCEL] 用户键盘中断，未完成的入库会尽量回滚")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
