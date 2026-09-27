#!/usr/bin/env python3
"""图图 — 作品列表查询脚本。

用法:
    python list_works.py [--page 1] [--page-size 10]
                         [--type comic|article_illustration|custom_image]
                         [--api-key ak_xxx]

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

输出（stdout，JSON 格式）：
    {
      "total":    100,
      "current":  1,
      "pageSize": 10,
      "records": [
        {
          "workId":        "uuid",
          "title":         "...",
          "type":          "comic",
          "status":        "completed",
          "coverImageUrl": "https://...",
          "createdAt":     "2026-05-01T10:00:00"
        },
        ...
      ]
    }
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import get, resolve_api_key  # noqa: E402

VALID_TYPES = {"comic", "article_illustration", "custom_image"}


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 作品列表查询")
    ap.add_argument("--page", type=int, default=1, help="页码（默认 1）")
    ap.add_argument("--page-size", type=int, default=10, help="每页数量 1-50（默认 10）")
    ap.add_argument("--type", default=None,
                    help=f"作品类型过滤（可选）：{', '.join(sorted(VALID_TYPES))}")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    if args.type and args.type not in VALID_TYPES:
        sys.exit(f"❌ 无效类型 '{args.type}'，可选：{', '.join(sorted(VALID_TYPES))}")
    if not (1 <= args.page_size <= 50):
        sys.exit("❌ --page-size 必须在 1-50 之间")

    api_key = resolve_api_key(args.api_key)
    params: dict = {"page": args.page, "pageSize": args.page_size}
    if args.type:
        params["type"] = args.type

    print(f"📤 查询作品列表（page={args.page}, pageSize={args.page_size}, type={args.type or 'all'}）…",
          file=sys.stderr)
    data = get("/works", api_key, params=params)
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
