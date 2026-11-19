from pathlib import Path
import re
import requests

CIVITAI_API_TOKEN = "token"

BACKUP_TASK_FILE = Path(r"D:\PythonTools\beifenreal_lora_download_urls.txt")
MODEL_DIR = Path(r"D:\Model")
REPORT_TXT = Path(r"D:\PythonTools\verify_lora_size_report.txt")

REQUEST_TIMEOUT = 30


def build_headers():
    return {
        "User-Agent": "LoraVault-SizeVerifier/1.0",
        "Authorization": f"Bearer {CIVITAI_API_TOKEN.strip()}",
    }


def format_size(n: int):
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n} B"


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
            "md_file": md_match.group(1).strip(),
            "real_url": url_match.group(1).strip(),
            "file_name": file_match.group(1).strip() if file_match else "",
        })

    return tasks


def get_suffix(file_name: str):
    suffix = Path(file_name).suffix
    return suffix if suffix else ".safetensors"


def get_remote_size(url: str):
    # 先 HEAD
    try:
        resp = requests.head(
            url,
            headers=build_headers(),
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code in (200, 206):
            size = resp.headers.get("content-length")
            if size and size.isdigit():
                return int(size)
    except Exception:
        pass

    # HEAD 拿不到就 GET stream，只读响应头，不下载正文
    resp = requests.get(
        url,
        headers=build_headers(),
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
        stream=True,
    )
    try:
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"HTTP {resp.status_code}")

        size = resp.headers.get("content-length")
        if size and size.isdigit():
            return int(size)

        return None
    finally:
        resp.close()


def main():
    if not CIVITAI_API_TOKEN.strip() or CIVITAI_API_TOKEN.startswith("这里填"):
        raise RuntimeError("请先填写 CIVITAI_API_TOKEN")

    text = BACKUP_TASK_FILE.read_text(encoding="utf-8-sig", errors="ignore")
    tasks = parse_blocks(text)

    passed = []
    failed = []
    missing = []
    unknown = []

    print(f"待校验数量: {len(tasks)}")

    for i, task in enumerate(tasks, 1):
        md_stem = Path(task["md_file"]).stem
        suffix = get_suffix(task["file_name"])
        local_path = MODEL_DIR / f"{md_stem}{suffix}"

        print(f"[{i}/{len(tasks)}] {local_path.name}")

        if not local_path.exists():
            missing.append((task, local_path))
            print("  [MISS] 本地文件不存在")
            continue

        local_size = local_path.stat().st_size

        try:
            remote_size = get_remote_size(task["real_url"])
        except Exception as e:
            unknown.append((task, local_path, local_size, str(e)))
            print(f"  [UNKNOWN] 远程大小获取失败: {e}")
            continue

        if remote_size is None:
            unknown.append((task, local_path, local_size, "远程未返回 content-length"))
            print("  [UNKNOWN] 远程未返回 content-length")
            continue

        if local_size == remote_size:
            passed.append((task, local_path, local_size, remote_size))
            print(f"  [OK] {format_size(local_size)}")
        else:
            failed.append((task, local_path, local_size, remote_size))
            print(f"  [FAIL] 本地 {format_size(local_size)} / 远程 {format_size(remote_size)}")

    lines = []
    lines.append(f"备份清单: {BACKUP_TASK_FILE}")
    lines.append(f"模型目录: {MODEL_DIR}")
    lines.append(f"总数: {len(tasks)}")
    lines.append(f"通过: {len(passed)}")
    lines.append(f"大小不一致: {len(failed)}")
    lines.append(f"本地缺失: {len(missing)}")
    lines.append(f"无法判断: {len(unknown)}")
    lines.append("=" * 80)
    lines.append("")

    if failed:
        lines.append("【大小不一致】")
        lines.append("")
        for idx, (task, path, local_size, remote_size) in enumerate(failed, 1):
            lines.append(f"[{idx:03d}]")
            lines.append(f"md文件: {task['md_file']}")
            lines.append(f"本地文件: {path}")
            lines.append(f"本地大小: {format_size(local_size)} / {local_size}")
            lines.append(f"远程大小: {format_size(remote_size)} / {remote_size}")
            lines.append(f"real_download_url: {task['real_url']}")
            lines.append("")

    if missing:
        lines.append("【本地缺失】")
        lines.append("")
        for idx, (task, path) in enumerate(missing, 1):
            lines.append(f"[{idx:03d}]")
            lines.append(f"md文件: {task['md_file']}")
            lines.append(f"应有文件: {path}")
            lines.append(f"real_download_url: {task['real_url']}")
            lines.append("")

    if unknown:
        lines.append("【无法判断】")
        lines.append("")
        for idx, (task, path, local_size, err) in enumerate(unknown, 1):
            lines.append(f"[{idx:03d}]")
            lines.append(f"md文件: {task['md_file']}")
            lines.append(f"本地文件: {path}")
            lines.append(f"本地大小: {format_size(local_size)} / {local_size}")
            lines.append(f"原因: {err}")
            lines.append(f"real_download_url: {task['real_url']}")
            lines.append("")

    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8-sig")

    print("\n校验完成！")
    print(f"通过: {len(passed)}")
    print(f"大小不一致: {len(failed)}")
    print(f"本地缺失: {len(missing)}")
    print(f"无法判断: {len(unknown)}")
    print(f"报告: {REPORT_TXT}")


if __name__ == "__main__":
    main()