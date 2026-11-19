from pathlib import Path
import json

DEFAULT_STATE = {
    "metadata_confirmed": False,
    "preview_images_downloaded": False,
    "preview_review_completed": False,
    "model_downloaded": False,
    "model_verified": False,
    "r2_uploaded": False,
    "md_committed": False,
    "cleaned": False,
}


def load_json(json_path: str | Path) -> dict:
    """
    读取 pending json
    """
    path = Path(json_path)

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    return ensure_state(payload)


def save_json(payload: dict, json_path: str | Path) -> None:
    """
    保存 pending json
    """
    path = Path(json_path)

    with path.open("w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            ensure_ascii=False,
            indent=2,
        )


def ensure_state(payload: dict) -> dict:
    """
    自动补齐缺失状态字段
    兼容旧版本 pending json
    """
    payload.setdefault("state", {})

    for key, default_value in DEFAULT_STATE.items():
        payload["state"].setdefault(
            key,
            default_value,
        )

    return payload


def mark_state(
    payload: dict,
    state_name: str,
    value: bool = True,
) -> dict:
    """
    修改状态
    """

    payload = ensure_state(payload)

    if state_name not in DEFAULT_STATE:
        raise KeyError(
            f"Unknown workflow state: {state_name}"
        )

    payload["state"][state_name] = value

    return payload


def is_done(
    payload: dict,
    state_name: str,
) -> bool:
    """
    查询状态
    """

    payload = ensure_state(payload)

    return bool(
        payload["state"].get(
            state_name,
            False,
        )
    )


def print_state(payload: dict) -> None:
    """
    调试用
    """

    payload = ensure_state(payload)

    print("\n===== Workflow State =====")

    for key, value in payload["state"].items():

        flag = "✓" if value else "✗"

        print(
            f"{flag} {key}"
        )

    print("==========================\n")