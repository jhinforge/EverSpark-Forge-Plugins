from pathlib import Path


def print_final_preview(
    title: str,
    category: str,
    fields: dict,
    selected_images: list[Path],
    md_path: Path,
    target_bucket: Path,
    planned_dsts: list[Path],
):
    print("\n========== 最终确认预览 ==========")
    print(f"title / md名：{title}")
    print(f"分类：{category}")
    print(f"目标 md：{md_path}")
    print(f"目标 bucket：{target_bucket}")

    print("\n字段：")
    for k, v in fields.items():
        print(f"  {k}: {v}")

    print("\n本次将入库的源图片：")
    for p in selected_images:
        print(f"  - {p}")

    print("\n计划写入的资产文件：")
    for p in planned_dsts:
        print(f"  - {p}")

    print("==================================")