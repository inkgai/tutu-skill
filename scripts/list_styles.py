#!/usr/bin/env python3
"""图图 — 风格列表查询脚本（"风格发现"）。

用法:
    python list_styles.py [--category comic|article_illustration]
                          [--api-key ak_xxx]

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

输出（stdout，JSON 数组）：
    [
      {
        "id":                     12,
        "slug":                   "healing",
        "name":                   "治愈漫画风",
        "emoji":                  "🌿",
        "styleLabel":             "温柔系",
        "tagline":                "...",
        "recommendedAspectRatio": "1:1"
      },
      ...
    ]

用途：
    - 用户说"治愈风漫画"时，Claude 先调本脚本拿列表，按 slug/name 做 fuzzy 匹配挑出 id，
      再调 create_comic.py 时用 --style-id 传入
    - 列出所有风格供用户选择
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import get, resolve_api_key  # noqa: E402

VALID_CATEGORIES = {"comic", "article_illustration", "article"}


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 风格列表查询")
    ap.add_argument("--category", default="comic",
                    help=f"大类，默认 comic，可选：{', '.join(sorted(VALID_CATEGORIES))}")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    if args.category not in VALID_CATEGORIES:
        sys.exit(f"❌ 无效 --category '{args.category}'，"
                 f"可选：{', '.join(sorted(VALID_CATEGORIES))}")

    api_key = resolve_api_key(args.api_key)

    print(f"📤 查询 {args.category} 风格列表…", file=sys.stderr)
    data = get("/styles", api_key, params={"category": args.category})
    # data 直接就是 List<SkillStyleVO>
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
