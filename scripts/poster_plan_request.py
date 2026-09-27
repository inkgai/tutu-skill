#!/usr/bin/env python3
"""生成灵感画报/多页海报策划的网页登录 payload，不发请求。

当前生产接口需要浏览器登录态；脚本只负责校验和整理，避免 API Key 被错发到 SSO 接口。
"""
from __future__ import annotations

import argparse
import json
import sys

RATIOS = {"2.35:1", "16:9", "3:2", "4:3", "1:1", "3:4", "2:3", "9:16"}
MODES = {"pure_image", "text_blend"}


def main() -> None:
    ap = argparse.ArgumentParser(description="准备灵感画报策划请求（网页登录态）")
    ap.add_argument("--prompt", required=True, help="画报主题、受众、页间叙事和视觉方向（≤10000 字）")
    ap.add_argument("--page-count", type=int, default=1, help="页数 1-8")
    ap.add_argument("--ratio", default="3:4", choices=sorted(RATIOS), help="画面比例")
    ap.add_argument("--mode", default="pure_image", choices=sorted(MODES), help="纯画面或图文混排")
    ap.add_argument("--template-id", default=None, help="已选模板 ID（可选）")
    ap.add_argument("--ref-url", action="append", default=[], help="已上传的参考图 URL，最多 3 张")
    args = ap.parse_args()
    if not 1 <= args.page_count <= 8:
        ap.error("--page-count 必须在 1-8 之间")
    if not args.prompt.strip() or len(args.prompt) > 10000:
        ap.error("--prompt 不能为空且不超过 10000 字")
    if len(args.ref_url) > 3:
        ap.error("--ref-url 最多 3 张")
    payload = {"prompt": args.prompt.strip(), "pageCount": args.page_count, "aspectRatio": args.ratio, "posterOutputMode": args.mode}
    if args.template_id:
        payload["templateId"] = args.template_id
    if args.ref_url:
        payload["referenceImageUrls"] = args.ref_url
    print(json.dumps({
        "transport": "web_session",
        "endpoint": "POST https://tutu.inkgai.com/v1/supertutu/inspiration-poster/plan",
        "webUrl": "https://tutu.inkgai.com/inspiration",
        "payload": payload,
        "next": "在已登录的图图网页提交；计划完成后按 pages[] 为每页创建作品。当前 API Key 开放平台未提供此接口。",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
