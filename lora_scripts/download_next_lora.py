import os
from pathlib import Path
import re
import time
import requests

# =========================
# Config
# =========================
CIVITAI_API_TOKEN = os.environ.get("CIVITAI_API_TOKEN", "").strip()

TASK_FILE = Path(r"D:\PythonTools\real_lora_download_urls.txt")
DOWNLOAD_DIR = Path(r"D:\Model")

REQUEST_TIMEOUT = 30
CHUNK_SIZE = 1024 * 1024  # 1MB


def build_headers():
    return {
        "User-Agent": "LoraVault-Downloader/1.0",
        "Authorization": f"Bearer {CIVITAI_API_TOKEN.strip()}",
    }


def parse_blocks(text: str):
    blocks = re.split(r"\n(?=\[\d{3}\])", text)
    tasks = []

    for block in blocks:
        md_match = re.search(r"md文件:\s*(.+)", block)
        url_match = re.search(r"real_download_url:\s*(.+)", block)
        file_match = re.search(r"file_name:\s*(.+)", block)

        if not md_match or not url_match:
            continue

        tasks.append({
            "block": block,
            "md_file": md_match.group(1).strip(),
            "real_url": url_match.group(1).strip(),
            "file_name": file_match.group(1).strip() if file_match else "",
        })

    return tasks


def get_suffix(file_name: str):
    suffix = Path(file_name).suffix
    return suffix if suffix else ".safetensors"


def remove_first_task(text: str):
    blocks = re.split(r"\n(?=\[\d{3}\])", text)
    kept = []
    removed = False

    for block in blocks:
        if not removed and re.search(r"\[\d{3}\]", block):
            removed = True
            continue
        kept.append(block)

    return "\n".join(kept).lstrip()


def format_size(n: int):
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.2f} MB"
    return f"{n / 1024:.2f} KB"


def download_one(url: str, dst: Path):
    tmp = dst.with_suffix(dst.suffix + ".part")

    headers = build_headers()

    resume_from = tmp.stat().st_size if tmp.exists() else 0
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"
        print(f"[INFO] 发现未完成文件，尝试断点续传：{format_size(resume_from)}")

    with requests.get(
        url,
        headers=headers,
        stream=True,
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    ) as resp:
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"下载请求失败 HTTP {resp.status_code}")

        total_header = resp.headers.get("content-length")
        total = int(total_header) if total_header else 0

        if resp.status_code == 206:
            total += resume_from
            mode = "ab"
            downloaded = resume_from
        else:
            mode = "wb"
            downloaded = 0

        last_print = time.time()

        with tmp.open(mode) as f:
            for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue

                f.write(chunk)
                downloaded += len(chunk)

                now = time.time()
                if now - last_print >= 1:
                    if total:
                        pct = downloaded / total * 100
                        print(
                            f"\r[DOWNLOADING] {format_size(downloaded)} / "
                            f"{format_size(total)} ({pct:.1f}%)",
                            end="",
                        )
                    else:
                        print(f"\r[DOWNLOADING] {format_size(downloaded)}", end="")
                    last_print = now

    print(f"\r[DOWNLOADING] {format_size(downloaded)} / {format_size(total)} (100.0%)")

    if total and downloaded != total:
        raise RuntimeError(
            f"下载大小不完整：已下载 {format_size(downloaded)} / 预期 {format_size(total)}"
        )
    if dst.exists():
        raise RuntimeError(f"目标文件已存在，停止防止覆盖：{dst}")
    
    tmp.rename(dst)

def main():
    if not CIVITAI_API_TOKEN.strip() or CIVITAI_API_TOKEN.startswith("这里填"):
        raise RuntimeError("请先填写 CIVITAI_API_TOKEN")

    if not TASK_FILE.exists():
        raise RuntimeError(f"找不到任务文件：{TASK_FILE}")

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

    while True:
        text = TASK_FILE.read_text(encoding="utf-8-sig", errors="ignore")
        tasks = parse_blocks(text)

        if not tasks:
            print("全部下载完成！任务队列已空。")
            return

        task = tasks[0]

        md_stem = Path(task["md_file"]).stem
        suffix = get_suffix(task["file_name"])
        save_name = md_stem + suffix
        dst = DOWNLOAD_DIR / save_name

        print("=" * 80)
        print(f"剩余任务数: {len(tasks)}")
        print(f"MD: {task['md_file']}")
        print(f"保存为: {dst}")
        print("=" * 80)

        if dst.exists():
            print("[WARN] 目标文件已存在，视为已完成，删除队列中的这一条。")
            TASK_FILE.write_text(remove_first_task(text), encoding="utf-8-sig")
            continue

        try:
            download_one(task["real_url"], dst)
        except Exception as e:
            tmp = dst.with_suffix(dst.suffix + ".part")

            if tmp.exists():
                try:
                    tmp.unlink()
                    print(f"[CLEAN] 已删除半残文件: {tmp}")
                except Exception as clean_error:
                    print(f"[WARN] 半残文件删除失败: {clean_error}")

            print()
            print(f"[ERROR] 下载失败：{e}")
            print("[INFO] 当前任务没有从队列删除。")
            return

        TASK_FILE.write_text(remove_first_task(text), encoding="utf-8-sig")

        print(f"[OK] 下载完成: {dst}")
        print("[OK] 已从队列删除。")


if __name__ == "__main__":
    main()