#!/usr/bin/env python3
"""打印可直接复制的图图创作指令模板。无需 API Key、不联网。"""
from pathlib import Path


def main() -> None:
    path = Path(__file__).resolve().parents[1] / "references" / "creation-commands.md"
    print(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
