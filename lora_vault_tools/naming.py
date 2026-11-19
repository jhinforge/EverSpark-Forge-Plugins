import re

from .common import safe_filename


def make_title_from_lora_name(lora_name: str) -> str:
    """
    自定义 LoRA md/title 命名规则：
    1. 只保留英文、数字、空格、下划线、横杠
    2. 删除其它语言字符
    3. 多余符号统一变成 _
    4. 连续 _ 合并
    5. 去掉首尾 _
    """
    name = str(lora_name or "").strip()

    # 删除非 ASCII 内容，也就是中文/日文/韩文等
    name = re.sub(r"[^\x00-\x7F]+", "", name)

    # 只保留英文数字，其它分隔符统一变成 _
    name = re.sub(r"[^A-Za-z0-9]+", "_", name)

    # 合并多个 _
    name = re.sub(r"_+", "_", name)

    # 去掉首尾 _
    name = name.strip("_")

    # 最后再过一遍 Windows 文件名安全处理
    name = safe_filename(name)

    return name or "untitled_lora"