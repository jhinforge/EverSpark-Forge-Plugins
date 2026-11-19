# -*- coding: utf-8 -*-
"""
LoraVault 现有 MD 资源组一次性 RAR 备份脚本

功能：
1. 扫描现有 Checkpoint 与 LoRA 的 md 文件。
2. 按 md 文件名匹配对应预览图：
      Better_pantyhose.md
      Better_pantyhose_001.jpg
      Better_pantyhose_002.png
3. 每个 md + 对应预览图生成一个同名 RAR。
4. 输出目录沿用原有分类结构。
5. 目标 RAR 已存在时直接跳过，不覆盖。
6. 最后输出成功、跳过、缺图、失败清单。

依赖：
- Windows
- 已安装 WinRAR
"""

from __future__ import annotations

import getpass
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# =========================
# 固定目录配置
# =========================

CHECKPOINT_MD_DIR = Path(r"D:\Vault\LoraVault\Checkpoints\Checkpoints")
LORA_MD_ROOT = Path(r"D:\Vault\LoraVault\lora")

CHECKPOINT_IMAGE_DIR = Path(r"D:\Vault\LoraVault\Assets\Checkpoints\001")
LORA_IMAGE_ROOT = Path(r"D:\Vault\LoraVault\Assets\Loras")

BACKUP_ROOT = Path(r"D:\Vaultbackup")

LORA_CATEGORIES = (
    "服装",
    "画风",
    "外貌外观",
    "部位",
    "角色",
    "玩法",
)

LORA_IMAGE_BUCKETS = (
    "001",
    "002",
    "003",
    "004",
    "005",
    "006",
    "007",
)

IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".gif",
}


@dataclass(frozen=True)
class BackupGroup:
    md_file: Path
    image_dirs: tuple[Path, ...]
    output_dir: Path
    group_type: str
    category: str


def find_winrar() -> Path:
    """自动寻找 WinRAR.exe。"""
    candidates = (
        Path(r"C:\Program Files\WinRAR\WinRAR.exe"),
        Path(r"C:\Program Files (x86)\WinRAR\WinRAR.exe"),
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    print("[ERROR] 未找到 WinRAR.exe。")
    print("请确认 WinRAR 已安装在以下任一位置：")
    for candidate in candidates:
        print(f"  {candidate}")
    sys.exit(1)


def validate_directories() -> None:
    """启动前检查关键源目录。"""
    required_dirs = (
        CHECKPOINT_MD_DIR,
        LORA_MD_ROOT,
        CHECKPOINT_IMAGE_DIR,
        LORA_IMAGE_ROOT,
    )

    missing = [path for path in required_dirs if not path.is_dir()]
    if missing:
        print("[ERROR] 以下目录不存在：")
        for path in missing:
            print(f"  {path}")
        sys.exit(1)


def build_groups() -> list[BackupGroup]:
    """建立所有需要处理的 md 资源组。"""
    groups: list[BackupGroup] = []

    # Checkpoint：只扫描当前层。
    for md_file in sorted(CHECKPOINT_MD_DIR.glob("*.md"), key=lambda p: p.name.lower()):
        groups.append(
            BackupGroup(
                md_file=md_file,
                image_dirs=(CHECKPOINT_IMAGE_DIR,),
                output_dir=BACKUP_ROOT / "Checkpoints" / "Checkpoints",
                group_type="Checkpoint",
                category="Checkpoints",
            )
        )

    # LoRA：只扫描指定的六个分类目录当前层。
    lora_image_dirs = tuple(LORA_IMAGE_ROOT / bucket for bucket in LORA_IMAGE_BUCKETS)

    for category in LORA_CATEGORIES:
        category_dir = LORA_MD_ROOT / category

        if not category_dir.is_dir():
            print(f"[WARN] LoRA 分类目录不存在，已跳过：{category_dir}")
            continue

        for md_file in sorted(category_dir.glob("*.md"), key=lambda p: p.name.lower()):
            groups.append(
                BackupGroup(
                    md_file=md_file,
                    image_dirs=lora_image_dirs,
                    output_dir=BACKUP_ROOT / "lora" / category,
                    group_type="LoRA",
                    category=category,
                )
            )

    return groups


def find_matching_images(md_file: Path, image_dirs: Iterable[Path]) -> list[Path]:
    """
    匹配规则：
      md 主体名 + "_" + 数字编号 + 图片扩展名

    示例：
      Better_pantyhose.md
      Better_pantyhose_001.jpg
      Better_pantyhose_002.png
    """
    stem = md_file.stem
    pattern = re.compile(
        rf"^{re.escape(stem)}_(\d+)$",
        flags=re.IGNORECASE,
    )

    matched: list[Path] = []

    for image_dir in image_dirs:
        if not image_dir.is_dir():
            continue

        for file_path in image_dir.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            if pattern.fullmatch(file_path.stem):
                matched.append(file_path)

    return sorted(matched, key=lambda p: p.name.lower())


def create_rar(
    winrar_exe: Path,
    archive_path: Path,
    source_files: list[Path],
    password: str,
) -> tuple[bool, str]:
    """调用 WinRAR 创建 RAR5 加密压缩包，并隐藏内部文件名。"""
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        str(winrar_exe),
        "a",
        "-ma5",              # RAR5
        "-m5",               # 最大压缩率
        "-ep1",              # 压缩包内不保留完整源路径
        "-idq",              # 安静模式
        "-y",                # 自动确认
        f"-hp{password}",    # 加密内容并隐藏文件名
        str(archive_path),
        *[str(path) for path in source_files],
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return False, f"无法启动 WinRAR：{exc}"

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        return False, f"WinRAR 返回代码 {result.returncode}：{message}"

    if not archive_path.is_file():
        return False, "WinRAR 未报错，但目标压缩包没有生成"

    if archive_path.stat().st_size <= 0:
        return False, "生成的压缩包大小为 0"

    return True, ""


def print_path_list(title: str, paths: list[Path]) -> None:
    if not paths:
        return

    print()
    print(title)
    for path in paths:
        print(f"  {path}")


def main() -> None:
    print("=" * 68)
    print("LoraVault 现有 MD 资源组一次性 RAR 备份")
    print("=" * 68)

    validate_directories()
    winrar_exe = find_winrar()
    groups = build_groups()

    if not groups:
        print("[INFO] 没有找到任何 md 文件。")
        return

    print(f"WinRAR：{winrar_exe}")
    print(f"备份位置：{BACKUP_ROOT}")
    print(f"共扫描到 {len(groups)} 个 md 文件。")
    print()

    password = getpass.getpass("请输入所有 RAR 使用的统一密码：")
    if not password:
        print("[ERROR] 密码不能为空，任务已取消。")
        return

    confirm_password = getpass.getpass("请再次输入密码：")
    if password != confirm_password:
        print("[ERROR] 两次密码不一致，任务已取消。")
        return

    print()
    answer = input(f"即将处理 {len(groups)} 组资源，输入 YES 开始：").strip()
    if answer != "YES":
        print("[INFO] 用户取消。")
        return

    created: list[Path] = []
    skipped: list[Path] = []
    missing_images: list[Path] = []
    failed: list[Path] = []

    for index, group in enumerate(groups, start=1):
        archive_path = group.output_dir / f"{group.md_file.stem}.rar"

        print()
        print(f"[{index}/{len(groups)}] {group.group_type} / {group.category}")
        print(f"MD：{group.md_file.name}")

        # 最简单的防重复：同名压缩包存在就跳过。
        if archive_path.exists():
            print(f"[SKIP] 已存在：{archive_path}")
            skipped.append(archive_path)
            continue

        images = find_matching_images(group.md_file, group.image_dirs)

        if not images:
            print("[MISS] 没有找到对应预览图，本组不压缩。")
            missing_images.append(group.md_file)
            continue

        source_files = [group.md_file, *images]

        print(f"图片：{len(images)} 张")
        for image in images:
            print(f"  - {image.name}")

        ok, error = create_rar(
            winrar_exe=winrar_exe,
            archive_path=archive_path,
            source_files=source_files,
            password=password,
        )

        if ok:
            size_mb = archive_path.stat().st_size / 1024 / 1024
            print(f"[OK] {archive_path} ({size_mb:.2f} MB)")
            created.append(archive_path)
        else:
            print(f"[ERROR] 压缩失败：{error}")
            failed.append(group.md_file)

            # 避免残留损坏或未完成的同名压缩包。
            try:
                if archive_path.exists():
                    archive_path.unlink()
            except OSError as exc:
                print(f"[WARN] 无法删除失败残留：{exc}")

    print()
    print("=" * 68)
    print("处理完成")
    print("=" * 68)
    print(f"扫描 md：{len(groups)}")
    print(f"成功创建：{len(created)}")
    print(f"已存在跳过：{len(skipped)}")
    print(f"缺少预览图：{len(missing_images)}")
    print(f"压缩失败：{len(failed)}")

    print_path_list("缺少预览图的 md：", missing_images)
    print_path_list("压缩失败的 md：", failed)

    print()
    print("备份根目录：")
    print(f"  {BACKUP_ROOT}")


if __name__ == "__main__":
    main()
