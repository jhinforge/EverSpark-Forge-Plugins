import sys
from pathlib import Path

# 允许直接运行本目录中的脚本，同时导入工作区根目录下的共享包。
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from lora_vault_tools.common import UserCancelled
from lora_vault_tools.input_manual import build_manual_payload
from lora_vault_tools.commit_engine import commit_import


def main():
    print("===== LoRA MD Import Manual V3.0 =====")

    payload = build_manual_payload()
    commit_import(payload, cleanup_pending=False)


if __name__ == "__main__":
    try:
        main()
    except UserCancelled:
        print("\n[CANCEL] 用户主动取消，未写入任何文件")
        sys.exit(0)
    except KeyboardInterrupt:
        print("\n[CANCEL] 用户键盘中断，未完成的入库会尽量回滚")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)
