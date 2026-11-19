from pathlib import Path

VAULT_ROOT = Path(r"D:\Vault\LoraVault")
LORA_MD_ROOT = VAULT_ROOT / "lora"
SOURCE_IMAGE_DIR = Path(r"D:\logtemp")
ASSET_ROOT = VAULT_ROOT / "Assets" / "Loras"
THUMB_CACHE_ROOT = VAULT_ROOT / "temp" / "lora_thumb_cache"
STAGING_ROOT = VAULT_ROOT / "temp" / "lora_import_staging"
CIVITAI_API_TOKEN = ""

LOGTEMP_DIR = Path(r"D:\logtemp")
PREVIEW_REVIEW_THRESHOLD = 4

MODEL_DIR = Path(r"D:\Model")
RCLONE_EXE = Path(r"C:\rclone\rclone.exe")
R2_LORA_REMOTE_DIR = "r2-assets:comfyui-assets/models_cold/loras/"

MODEL_REQUEST_TIMEOUT = 30
MODEL_CHUNK_SIZE = 1024 * 1024

CATEGORIES = ["部位", "服装", "画风", "角色", "外貌外观", "玩法"]
BUCKET_LIMIT = 100
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# 必须和 DataviewJS 面板 V3.4.2 的缓存协议保持一致
THUMB_SIZE = (240, 240)
THUMB_FORMAT = "JPEG"
THUMB_EXT = "jpg"
THUMB_QUALITY = 88

CANCEL_WORDS = {"q", "quit", "exit", "cancel", "取消", "退出"}

PENDING_JSON_PATH = Path(r"D:\logtemp\lora_import_pending.json")