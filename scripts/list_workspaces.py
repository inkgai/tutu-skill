#!/usr/bin/env python3
"""图图 — 工作空间列表查询脚本（"空间发现"）。

用法:
    python list_workspaces.py [--api-key ak_xxx]

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

输出（stdout，JSON 数组）：
    [
      {
        "id":              42,
        "name":            "治愈系小红书",
        "description":     "...",
        "scene":           "comic",
        "workType":        "COMIC",
        "typeId":          12,
        "aspectRatio":     "3:4",
        "outputMode":      "split",
        "shotCount":       4,
        "whitespaceRatio": 85,
        "updatedAt":       "2026-05-15T10:00:00"
      },
      ...
    ]

用途：
    - 调创作脚本前先查"我有哪些空间"，按 name 匹配挑出 workspaceId
    - 列出所有空间供用户选择
    - 空数组表示用户还没建过空间，建议去前端 https://tutu.inkgai.com/workspace 建一个

为什么推荐用空间创作？
    空间锁定了一套完整创作参数（风格 / 比例 / 输出模式 / 分镜数 / 留白等），
    一次配好长期复用，比每次裸创作稳定得多。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import get, resolve_api_key  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 工作空间列表查询")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    api_key = resolve_api_key(args.api_key)

    print("📤 查询「我的空间」列表…", file=sys.stderr)
    data = get("/workspaces", api_key)
    # data 直接就是 List<SkillWorkspaceVO>

    if isinstance(data, list) and len(data) == 0:
        print("⚠️  你还没有建过工作空间。建议去前端 https://tutu.inkgai.com/workspace 建一个，"
              "锁定风格 / 比例 / 输出模式后长期复用，比每次裸创作稳定。", file=sys.stderr)

    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
