import json
import subprocess
from pathlib import Path
from datetime import datetime

# =========================
# 路径配置
# =========================

CONFIG_PATH = Path(
    r"D:\Vault\LoraVault\temp\bendihuancunshuju\config.json"
)

# =========================
# 读取配置
# =========================

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

RCLONE_EXE = r"C:\rclone\rclone.exe"

REMOTE = (
    f"{config['rclone_remote']}"
    f"{config['lora_remote_path']}"
)

MANIFEST_FILE = Path(config["manifest_file"])
REPORT_FILE = Path(config["report_file"])
LOG_FILE = Path(config["log_file"])

# =========================
# 执行 rclone lsjson
# =========================

cmd = [
    RCLONE_EXE,
    "lsjson",
    REMOTE,
    "--max-depth",
    "1"
]

print("[INFO] 正在扫描 R2 LoRA 目录...")

result = subprocess.run(
    cmd,
    capture_output=True,
    text=True,
    encoding="utf-8"
)

if result.returncode != 0:
    print("[ERROR] rclone 执行失败")
    print(result.stderr)
    exit()

# =========================
# 解析 JSON
# =========================

data = json.loads(result.stdout)

manifest = {}

for item in data:

    if item.get("IsDir"):
        continue

    name = item["Name"]

    manifest[name] = {
        "size": item["Size"],
        "modtime": item["ModTime"],
        "path": item["Path"]
    }

# =========================
# 写 manifest
# =========================

MANIFEST_FILE.parent.mkdir(
    parents=True,
    exist_ok=True
)

with open(MANIFEST_FILE, "w", encoding="utf-8") as f:
    json.dump(
        manifest,
        f,
        ensure_ascii=False,
        indent=2
    )

# =========================
# 写 report
# =========================

report = {
    "sync_time": datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    ),
    "total_models": len(manifest)
}

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    json.dump(
        report,
        f,
        ensure_ascii=False,
        indent=2
    )

# =========================
# 写日志
# =========================

with open(LOG_FILE, "a", encoding="utf-8") as f:

    f.write(
        f"[{report['sync_time']}] "
        f"同步完成 "
        f"模型数量: {len(manifest)}\n"
    )

print(
    f"[OK] 同步完成，共 {len(manifest)} 个模型"
)