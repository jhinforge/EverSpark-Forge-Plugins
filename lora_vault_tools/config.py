import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = Path(os.environ.get("LORA_PLUGIN_CONFIG") or REPO_ROOT / "lora-config.json").expanduser().resolve()


def load_config():
    if "LORA_PLUGIN_CONFIG" not in os.environ and not CONFIG_PATH.exists():
        return None
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise RuntimeError(f"无法读取 LoRA 目录配置：{CONFIG_PATH}（{e}）") from e
    if not isinstance(config, dict):
        raise RuntimeError(f"LoRA 目录配置必须是 JSON 对象：{CONFIG_PATH}")
    return config


def configured_path(config, key, *, required=False):
    value = config.get(key)
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"LoRA 目录配置 {key} 必须是非空路径：{CONFIG_PATH}")
    return (CONFIG_PATH.parent / Path(value.strip()).expanduser()).resolve()


config = load_config()
if config is None:
    # 保留既有脚本的目录布局，兼容尚未创建配置的用户。
    VAULT_ROOT = Path(r"D:\Vault\LoraVault")
    LORA_MD_ROOT = VAULT_ROOT / "lora"
    ASSET_ROOT = VAULT_ROOT / "Assets" / "Loras"
    THUMB_CACHE_ROOT = VAULT_ROOT / "temp" / "lora_thumb_cache"
    TEMP_ROOT = Path(r"D:\logtemp")
    SOURCE_IMAGE_DIR = TEMP_ROOT
    STAGING_ROOT = VAULT_ROOT / "temp" / "lora_import_staging"
    MODEL_DIR = Path(r"D:\Model")
    POD_MANIFEST_PATH = VAULT_ROOT / "temp" / "pod_lora_pull_manifest.json"
else:
    VAULT_ROOT = configured_path(config, "vault_root")
    LORA_MD_ROOT = configured_path(config, "notes_dir", required=True)
    ASSET_ROOT = configured_path(config, "previews_dir", required=True)
    THUMB_CACHE_ROOT = configured_path(config, "thumbnails_dir", required=True)
    TEMP_ROOT = configured_path(config, "temp_dir", required=True)
    if len({LORA_MD_ROOT, ASSET_ROOT, THUMB_CACHE_ROOT, TEMP_ROOT}) != 4:
        raise RuntimeError("模型笔记、原预览图、缩略图和临时文件必须使用不同目录")
    SOURCE_IMAGE_DIR = (TEMP_ROOT / "previews").resolve()
    if ASSET_ROOT.is_relative_to(SOURCE_IMAGE_DIR) or SOURCE_IMAGE_DIR.is_relative_to(ASSET_ROOT):
        raise RuntimeError("临时预览图目录不能与原预览图目录重叠")
    STAGING_ROOT = TEMP_ROOT / "staging"
    MODEL_DIR = TEMP_ROOT / "models"
    POD_MANIFEST_PATH = TEMP_ROOT / "pod_lora_pull_manifest.json"

PENDING_JSON_PATH = TEMP_ROOT / "lora_import_pending.json"
PREVIEW_REVIEW_THRESHOLD = 4
CIVITAI_API_TOKEN = ""

RCLONE_EXE = Path(r"C:\rclone\rclone.exe")
R2_LORA_REMOTE_DIR = "r2-assets:comfyui-assets/models_cold/loras/"


def notes_relative_path(md_path: Path) -> str:
    if VAULT_ROOT is not None and md_path.is_relative_to(VAULT_ROOT):
        return md_path.relative_to(VAULT_ROOT).as_posix()
    return md_path.relative_to(LORA_MD_ROOT).as_posix()


MODEL_REQUEST_TIMEOUT = 30
MODEL_CHUNK_SIZE = 1024 * 1024

CATEGORIES = ["部位", "服装", "画风", "角色", "外貌外观", "玩法"]
BUCKET_LIMIT = 100
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# 必须和 DataviewJS 面板 V3.6 的缓存协议保持一致
THUMB_SIZE = (240, 240)
THUMB_FORMAT = "JPEG"
THUMB_EXT = "jpg"
THUMB_QUALITY = 88

CANCEL_WORDS = {"q", "quit", "exit", "cancel", "取消", "退出"}
