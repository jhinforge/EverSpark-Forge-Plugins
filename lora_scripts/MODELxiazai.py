import os
import subprocess
from urllib.parse import urlparse, unquote


# =========================
# 固定 Token 配置区
# =========================
BEARER_TOKEN = os.environ.get("CIVITAI_API_TOKEN", "").strip()


MODEL_DIRS = {
    "1": ("checkpoints", "/root/ComfyUI/models/checkpoints"),
    "2": ("loras", "/root/ComfyUI/models/loras"),
    "3": ("vae", "/root/ComfyUI/models/vae"),
    "4": ("embeddings", "/root/ComfyUI/models/embeddings"),
    "5": ("controlnet", "/root/ComfyUI/models/controlnet"),
    "6": ("自定义目录", None),
}


def get_filename_from_url(url: str) -> str:
    path = urlparse(url).path
    name = os.path.basename(path)
    name = unquote(name)
    return name if name else "download.safetensors"


def copy_to_clipboard(text: str) -> bool:
    try:
        subprocess.run("clip", input=text, text=True, check=True)
        return True
    except Exception:
        return False


def choose_save_dir() -> str:
    print("\n选择保存目录：")
    for key, (name, path) in MODEL_DIRS.items():
        if path:
            print(f"{key}. {name} -> {path}")
        else:
            print(f"{key}. {name}")

    choice = input("输入编号 [默认2=loras]: ").strip() or "2"

    if choice not in MODEL_DIRS:
        print("[WARN] 无效选择，默认使用 loras")
        choice = "2"

    name, path = MODEL_DIRS[choice]

    if path is None:
        path = input("输入自定义保存目录: ").strip()

    return path.rstrip("/")


def build_wget(url: str, output_path: str) -> str:
    return f'wget -c "{url}" -O "{output_path}"'


def build_curl(url: str, output_path: str, use_token: bool) -> str:
    if use_token:
        return (
            f'curl -L \\\n'
            f'-H "Authorization: Bearer {BEARER_TOKEN}" \\\n'
            f'"{url}" \\\n'
            f'-o "{output_path}"'
        )

    return (
        f'curl -L \\\n'
        f'"{url}" \\\n'
        f'-o "{output_path}"'
    )


def main():
    print("=" * 46)
    print("模型下载指令生成器 v1.1")
    print("=" * 46)

    while True:
        url = input("\n输入下载链接: ").strip()

        if not url:
            print("[ERROR] 下载链接不能为空")
            continue

        print("\n选择下载方式：")
        print("1. wget")
        print("2. curl 普通模式")
        print("3. curl Bearer Token 模式")

        method = input("输入编号 [默认1=wget]: ").strip() or "1"

        save_dir = choose_save_dir()

        auto_filename = get_filename_from_url(url)
        filename = input(
                    f"\n输入文件名 [默认: {auto_filename}]: "
        ).strip() or auto_filename

        # 自动补后缀
        if "." not in filename:
            filename += ".safetensors"

        output_path = f"{save_dir}/{filename}"

        if method == "1":
            cmd = build_wget(url, output_path)
        elif method == "2":
            cmd = build_curl(url, output_path, use_token=False)
        elif method == "3":
            cmd = build_curl(url, output_path, use_token=True)
        else:
            print("[WARN] 无效下载方式，默认使用 wget")
            cmd = build_wget(url, output_path)

        print("\n" + "=" * 46)
        print("生成结果：")
        print("=" * 46)
        print(cmd)
        print("=" * 46)

        if copy_to_clipboard(cmd):
            print("[OK] 下载命令已自动复制到剪贴板")
        else:
            print("[WARN] 自动复制失败，请手动复制上方命令")

        again = input("\n继续生成下一条？[Y/n]: ").strip().lower()
        if again == "n":
            print("\n退出程序")
            break


if __name__ == "__main__":
    main()