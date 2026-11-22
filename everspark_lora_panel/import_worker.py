"""Run one archive transaction with the request's private staging directory."""
import json
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path


def main():
    package = types.ModuleType("everspark_lora_panel")
    package.__path__ = [str(Path(__file__).resolve().parent)]
    sys.modules[package.__name__] = package
    from everspark_lora_panel.import_tools.commit_engine import commit_import

    request = json.load(sys.stdin)
    with redirect_stdout(sys.stderr):
        commit_import(
            request["record"],
            selected_images=[Path(path) for path in request["images"]],
            approve_similar=request["approve_similar"],
        )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), flush=True)
        sys.exit(1)
