from pathlib import Path

LORA_ROOT = Path(r"D:\Vault\LoraVault\lora")

updated = 0
skipped = 0
failed = 0

for md_path in LORA_ROOT.rglob("*.md"):
    try:
        text = md_path.read_text(encoding="utf-8")

        if "pod_loaded: true" in text:
            text = text.replace(
                "pod_loaded: true",
                "pod_loaded: false",
                1
            )

            md_path.write_text(text, encoding="utf-8")

            print(f"[RESET] {md_path.name}")
            updated += 1

        else:
            skipped += 1

    except Exception as e:
        print(f"[ERROR] {md_path}: {e}")
        failed += 1

print("\n===== 完成 =====")
print(f"重置为 false: {updated}")
print(f"已是 false: {skipped}")
print(f"失败: {failed}")