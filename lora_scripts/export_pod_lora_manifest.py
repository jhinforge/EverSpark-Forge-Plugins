from pathlib import Path
import json
from datetime import datetime

# =====================================================
# Export Pod LoRA Pull Manifest
#
# 功能：
# 1. 扫描 D:\Vault\LoraVault\lora 下所有 md
# 2. 找到 frontmatter 中 pod_loaded: true 的 LoRA
# 3. 取 md 文件名作为模型名
#    规则：xxx.md -> xxx.safetensors
# 4. 导出 JSON manifest，供 Pod 上的 pull_cold_models.sh --manifest 使用
#
# 注意：
# - 不修改任何 md
# - 不复制任何模型
# - 只导出清单
# =====================================================

VAULT_ROOT = Path(r"D:\Vault\LoraVault")
LORA_MD_ROOT = VAULT_ROOT / "lora"
OUTPUT_PATH = VAULT_ROOT / "temp" / "pod_lora_pull_manifest.json"


def log(level: str, msg: str):
    print(f"[{level}] {msg}")


def read_frontmatter(text: str) -> str:
    """
    只读取 YAML frontmatter。
    如果文件没有标准 frontmatter，返回空字符串。
    """
    if not text.startswith("---"):
        return ""

    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""

    return parts[1]


def frontmatter_bool(frontmatter: str, key: str) -> bool:
    """
    解析简单布尔字段：
    pod_loaded: true
    pod_loaded: True
    pod_loaded: "true"
    pod_loaded: 'true'
    """
    key_prefix = f"{key}:"

    for line in frontmatter.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if not line.startswith(key_prefix):
            continue

        value = line[len(key_prefix):].strip().strip('"').strip("'").lower()
        return value == "true"

    return False


def main():
    print("===== Export Pod LoRA Pull Manifest =====")

    if not LORA_MD_ROOT.exists():
        raise RuntimeError(f"LoRA md 目录不存在：{LORA_MD_ROOT}")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    md_files = sorted(LORA_MD_ROOT.rglob("*.md"))

    items = []
    skipped = 0
    failed = 0

    for md_path in md_files:
        try:
            text = md_path.read_text(encoding="utf-8")
            fm = read_frontmatter(text)

            if not fm:
                skipped += 1
                log("WARN", f"无 frontmatter，跳过：{md_path}")
                continue

            if frontmatter_bool(fm, "pod_loaded"):
                model_name = md_path.stem
                items.append(model_name)

        except Exception as e:
            failed += 1
            log("WARN", f"读取失败，跳过：{md_path} -> {e}")

    items = sorted(set(items), key=lambda x: x.lower())

    manifest = {
        "type": "lora",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": "Obsidian LoRA Vault",
        "rule": "md filename == R2 model filename without .safetensors",
        "count": len(items),
        "items": items,
    }

    OUTPUT_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\n===== 完成 =====")
    print(f"[OK] 扫描 md：{len(md_files)}")
    print(f"[OK] pod_loaded=true：{len(items)}")
    print(f"[OK] 跳过：{skipped}")
    print(f"[WARN] 失败：{failed}")
    print(f"[OK] manifest：{OUTPUT_PATH}")

    if items:
        print("\n本次导出模型：")
        for name in items:
            print(f"  - {name}")
    else:
        print("\n[WARN] 没有找到 pod_loaded: true 的 LoRA。")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}")
