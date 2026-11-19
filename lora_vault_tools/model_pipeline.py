from pathlib import Path
import subprocess
import time
import requests

from .common import log

from .config import (
    CIVITAI_API_TOKEN,
    MODEL_DIR,
    RCLONE_EXE,
    R2_LORA_REMOTE_DIR,
    MODEL_REQUEST_TIMEOUT,
    MODEL_CHUNK_SIZE,
)


def build_headers():
    headers = {
        "User-Agent": "LoraVault-ModelPipeline/1.0",
    }

    if CIVITAI_API_TOKEN.strip() and not CIVITAI_API_TOKEN.startswith("这里填"):
        headers["Authorization"] = f"Bearer {CIVITAI_API_TOKEN.strip()}"

    return headers


def format_size(n: int):
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.2f} MB"
    if n >= 1024:
        return f"{n / 1024:.2f} KB"
    return f"{n} B"


def get_suffix(file_name: str):
    suffix = Path(str(file_name or "")).suffix
    return suffix if suffix else ".safetensors"


def get_model_path(title: str, file_name: str) -> Path:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    suffix = get_suffix(file_name)
    return MODEL_DIR / f"{title}{suffix}"


def get_remote_size(url: str):
    try:
        resp = requests.head(
            url,
            headers=build_headers(),
            timeout=MODEL_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code in (200, 206):
            size = resp.headers.get("content-length")
            if size and size.isdigit():
                return int(size)
    except Exception:
        pass

    resp = requests.get(
        url,
        headers=build_headers(),
        timeout=MODEL_REQUEST_TIMEOUT,
        allow_redirects=True,
        stream=True,
    )

    try:
        if resp.status_code not in (200, 206):
            raise RuntimeError(f"远程大小获取失败 HTTP {resp.status_code}")

        size = resp.headers.get("content-length")
        if size and size.isdigit():
            return int(size)

        return None
    finally:
        resp.close()


def download_model(real_url: str, dst: Path):
    if dst.exists():
        log("WARN", f"本地模型已存在，跳过下载：{dst}")
        return dst

    tmp = dst.with_suffix(dst.suffix + ".part")
    headers = build_headers()

    resume_from = tmp.stat().st_size if tmp.exists() else 0
    if resume_from > 0:
        headers["Range"] = f"bytes={resume_from}-"
        log("INFO", f"发现未完成文件，尝试断点续传：{format_size(resume_from)}")

    try:
        with requests.get(
            real_url,
            headers=headers,
            stream=True,
            timeout=MODEL_REQUEST_TIMEOUT,
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
                for chunk in resp.iter_content(chunk_size=MODEL_CHUNK_SIZE):
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

        print()

        if total and downloaded != total:
            raise RuntimeError(
                f"下载大小不完整：已下载 {format_size(downloaded)} / 预期 {format_size(total)}"
            )

        if dst.exists():
            raise RuntimeError(f"目标文件已存在，停止防止覆盖：{dst}")

        tmp.rename(dst)
        log("OK", f"模型下载完成：{dst}")
        return dst

    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
                log("CLEAN", f"已删除半残文件：{tmp}")
            except Exception as e:
                log("WARN", f"半残文件删除失败：{e}")
        raise


def verify_model_size(real_url: str, local_path: Path):
    if not local_path.exists():
        raise RuntimeError(f"本地模型不存在，无法校验：{local_path}")

    local_size = local_path.stat().st_size
    remote_size = get_remote_size(real_url)

    if remote_size is None:
        raise RuntimeError("远程未返回 content-length，无法判断模型大小")

    if local_size != remote_size:
        raise RuntimeError(
            f"模型大小不一致：本地 {format_size(local_size)} / 远程 {format_size(remote_size)}"
        )

    log("OK", f"模型大小校验通过：{format_size(local_size)}")


def upload_model_to_r2(local_path: Path):
    if not RCLONE_EXE.exists():
        raise RuntimeError(f"找不到 rclone：{RCLONE_EXE}")

    if not local_path.exists():
        raise RuntimeError(f"本地模型不存在，无法上传：{local_path}")

    remote_target = R2_LORA_REMOTE_DIR.rstrip("/") + "/" + local_path.name

    cmd = [
        str(RCLONE_EXE),
        "copyto",
        str(local_path),
        remote_target,

        "--progress",
        "--transfers", "2",
        "--checkers", "4",
        "--retries", "5",
        "--low-level-retries", "20",

        "--s3-upload-cutoff", "64M",
        "--s3-chunk-size", "32M",
        "--s3-upload-concurrency", "4",
    ]

    log("INFO", "开始上传模型到 R2")
    print("[CMD]")
    print(" ".join(cmd))

    result = subprocess.run(cmd, text=True)

    if result.returncode != 0:
        raise RuntimeError(f"rclone 上传失败，返回码：{result.returncode}")

    log("OK", f"R2 上传完成：{remote_target}")


def run_model_pipeline(title: str, pending: dict) -> Path:
    real_url = str(pending.get("real_download_url") or "").strip()
    file_name = str(pending.get("file_name") or "").strip()

    if not real_url:
        raise RuntimeError("pending JSON 缺少 real_download_url，无法下载模型")

    local_path = get_model_path(title, file_name)

    log("INFO", f"模型最终命名：{local_path.name}")

    download_model(real_url, local_path)
    verify_model_size(real_url, local_path)
    upload_model_to_r2(local_path)

    return local_path


def cleanup_local_model(local_path: Path | None):
    if not local_path:
        return

    try:
        if local_path.exists():
            local_path.unlink()
            log("OK", f"本地模型已删除：{local_path}")
    except Exception as e:
        log("WARN", f"本地模型删除失败，请手动检查：{local_path} -> {e}")