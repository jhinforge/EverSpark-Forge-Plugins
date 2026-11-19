import subprocess
from pathlib import Path
from datetime import datetime

LOCAL_DIR = r"D:\Model"
REMOTE_DIR = "r2-assets:comfyui-assets/models_cold/loras/"

INCLUDE_EXTS = [
    "*.safetensors",
    "*.ckpt",
    "*.pt",
]

DRY_RUN = False  # 第一次必须 True，确认无误后再改 False


def run(cmd):
    print("\n[CMD]")
    print(" ".join(cmd))
    return subprocess.run(cmd, text=True)


def main():
    local = Path(LOCAL_DIR)

    if not local.exists():
        print(f"[ERROR] 本地目录不存在: {LOCAL_DIR}")
        return

    log_dir = Path(r"D:\PythonTools\r2_upload_logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / f"r2_upload_loras_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    cmd = [
        r"C:\rclone\rclone.exe",
        "copy",
        LOCAL_DIR,
        REMOTE_DIR,

        "--progress",
        "--transfers", "2",
        "--checkers", "4",
        "--retries", "5",
        "--low-level-retries", "20",

        "--s3-upload-cutoff", "64M",
        "--s3-chunk-size", "32M",
        "--s3-upload-concurrency", "4",

        "--log-file", str(log_file),
        "--log-level", "INFO",
    ]

    for ext in INCLUDE_EXTS:
        cmd.extend(["--include", ext])

    cmd.extend(["--exclude", "*"])

    if DRY_RUN:
        cmd.append("--dry-run")
        print("[MODE] DRY-RUN 测试模式，不会真正上传。")
    else:
        print("[MODE] 正式上传模式。")

    print(f"[LOCAL]  {LOCAL_DIR}")
    print(f"[REMOTE] {REMOTE_DIR}")
    print(f"[LOG]    {log_file}")

    result = run(cmd)

    if result.returncode == 0:
        print("\n[OK] rclone 执行完成")
    else:
        print(f"\n[ERROR] rclone 执行失败，返回码: {result.returncode}")

    print(f"[LOG] 查看日志: {log_file}")


if __name__ == "__main__":
    main()