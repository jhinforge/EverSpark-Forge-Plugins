import json


def yaml_quote(value: str) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def yaml_block(value: str) -> str:
    value = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if not value:
        return '""'
    lines = value.split("\n")
    return ">-\n" + "\n".join(f"  {line}" for line in lines)


def build_md(title: str, fields: dict, asset_links: list[str]) -> str:
    image_block = "\n".join(asset_links)

    return f"""---
lora_name: {yaml_quote(fields["lora_name"])}
lora_version: {yaml_quote(fields["lora_version"])}
download_url: {yaml_quote(fields["download_url"])}
trigger_words: {yaml_block(fields["trigger_words"])}
category: {yaml_quote(fields["category"])}
model_support: {yaml_quote(fields["model_support"])}
tested: false
pod_loaded: false
effect: {yaml_quote(fields["effect"])}
notes: {yaml_quote(fields["notes"])}
---

# {title}

{image_block}
"""