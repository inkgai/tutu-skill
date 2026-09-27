#!/usr/bin/env python3
"""报告图图 skill 能力边界。

默认不联网，方便 agent 在决定调用前先知道哪些功能走 OpenAPI、哪些需要网页登录。
加 --check-live 时才会用 API Key 检查开放平台的只读接口（不会创建作品）。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _client import get, resolve_api_key  # noqa: E402

CAPABILITIES = [
    {"name": "comic", "label": "漫画", "transport": "openapi", "endpoint": "POST /comic", "ratios": ["1:1", "3:4", "4:3", "2:3", "3:2", "16:9", "9:16"]},
    {"name": "article_illustration", "label": "文章配图", "transport": "openapi", "endpoint": "POST /article-illustration", "ratios": ["1:1", "2:3", "3:4", "4:3", "3:2"], "ratioNote": "生产 DTO 当前未开放 16:9 / 9:16"},
    {"name": "image", "label": "单张图片", "transport": "openapi", "endpoint": "POST /image", "ratios": ["1:1", "3:4", "4:3", "2:3", "3:2", "16:9", "9:16"]},
    {"name": "diagram", "label": "结构化灵感画板", "transport": "openapi", "endpoint": "POST /diagram"},
    {"name": "poster_plan", "label": "灵感画报/多页海报策划", "transport": "web_session", "endpoint": "POST /v1/supertutu/inspiration-poster/plan", "web_url": "https://tutu.inkgai.com/inspiration"},
    {"name": "poster_template", "label": "画板/海报模板设计", "transport": "web_session", "endpoint": "POST /v1/supertutu/feature-template/create-poster", "web_url": "https://tutu.inkgai.com/inspiration?create=1"},
    {"name": "character_template", "label": "角色模板设计", "transport": "web_session", "endpoint": "POST /v1/supertutu/feature-template/create", "web_url": "https://tutu.inkgai.com/inspiration?type=CHARACTER&create=1"},
]


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 skill 能力矩阵（默认离线）")
    ap.add_argument("--check-live", action="store_true", help="用 API Key 检查只读 OpenAPI（不创建作品）")
    ap.add_argument("--api-key", default=None, help="--check-live 时使用；优先于 TUTU_API_KEY")
    args = ap.parse_args()
    result = {"baseUrl": "https://tutu.inkgai.com/api/v1/openapi", "capabilities": CAPABILITIES}
    if args.check_live:
        key = resolve_api_key(args.api_key)
        checks = {}
        for name, path in (("styles", "/styles"), ("workspaces", "/workspaces")):
            try:
                payload = get(path, key)
                checks[name] = {"ok": True, "items": len(payload) if isinstance(payload, list) else None}
            except SystemExit as exc:
                checks[name] = {"ok": False, "error": str(exc)}
        result["liveReadOnlyChecks"] = checks
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
