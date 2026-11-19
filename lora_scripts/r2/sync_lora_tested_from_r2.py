import json
import re
from pathlib import Path
from datetime import datetime

CONFIG_PATH = Path(r"D:\Vault\LoraVault\temp\bendihuancunshuju\config.json")

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

LORA_ROOT = Path(config["vault_lora_root"])
MANIFEST_FILE = Path(config["manifest_file"])
CACHE_DIR = Path(config["cache_dir"])

with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
    manifest = json.load(f)

r2_names = {Path(name).stem.lower() for name in manifest.keys()}

md_files = list(LORA_ROOT.rglob("*.md"))

local_md_keys = {
    md_path.stem.lower()
    for md_path in md_files
}

orphan_r2_loras = []

for r2_name in manifest.keys():

    r2_key = Path(r2_name).stem.lower()

    if r2_key not in local_md_keys:
        orphan_r2_loras.append(r2_name)

print(f"[INFO] R2 孤儿模型数量: {len(orphan_r2_loras)}")

if orphan_r2_loras:

    print("\n===== R2 有但本地无 md 的模型 =====")

    for name in orphan_r2_loras:
        print(name)

changed = 0
matched = 0
unmatched = 0
skipped_no_lora_name = 0

def extract_yaml(text):
    if not text.startswith("---"):
        return None, None, None

    end = text.find("\n---", 3)
    if end == -1:
        return None, None, None

    yaml_block = text[3:end].strip("\n")
    body = text[end + 4:]
    return yaml_block, body, end

for md_path in md_files:
    text = md_path.read_text(encoding="utf-8")
    yaml_block, body, end_pos = extract_yaml(text)

    if yaml_block is None:
        continue

    md_key = md_path.stem.lower()
    is_downloaded = md_key in r2_names

    if is_downloaded:
        matched += 1
        new_tested_line = "tested: true"
    else:
        unmatched += 1
        new_tested_line = "tested: false"

    if re.search(r"^tested:\s*(true|false)\s*$", yaml_block, re.MULTILINE):
        new_yaml = re.sub(
            r"^tested:\s*(true|false)\s*$",
            new_tested_line,
            yaml_block,
            flags=re.MULTILINE
        )
    else:
        new_yaml = yaml_block + "\n" + new_tested_line

    new_text = "---\n" + new_yaml.rstrip() + "\n---" + body

    if new_text != text:

        md_path.write_text(new_text, encoding="utf-8")
        changed += 1

print("[OK] tested 同步完成")
print(f"[INFO] 扫描 md 数量: {len(md_files)}")
print(f"[INFO] R2 匹配成功: {matched}")
print(f"[INFO] R2 未匹配: {unmatched}")
print(f"[INFO] 缺少 lora_name 跳过: {skipped_no_lora_name}")
print(f"[INFO] 实际修改 md 数量: {changed}")
