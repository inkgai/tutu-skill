#!/usr/bin/env python3
"""准备画板模板或角色模板的网页登录 payload，不发请求。

模板创建、参考图解析和角色分类目前需要图图网页登录态，不能用 OpenAPI API Key 代替。
"""
from __future__ import annotations

import argparse
import json


def main() -> None:
    ap = argparse.ArgumentParser(description="准备图板/角色模板请求（网页登录态）")
    ap.add_argument("--type", required=True, choices=("poster", "character"), help="模板类型")
    ap.add_argument("--name", required=True, help="模板名称，≤100 字")
    ap.add_argument("--content", required=True, help="版式规则或角色身份/外观规则，≤5000 字")
    ap.add_argument("--category-id", type=int, default=None, help="角色模板必填的创作分类 ID")
    ap.add_argument("--reference-url", default=None, help="已上传的参考图 URL")
    ap.add_argument("--sample-image-url", default=None, help="角色模板样例图 URL")
    ap.add_argument("--aspect-ratio", default=None, help="推荐比例，例如 3:4 / 4:3")
    args = ap.parse_args()
    if len(args.name) > 100:
        ap.error("--name 不超过 100 字")
    if len(args.content) > 5000:
        ap.error("--content 不超过 5000 字")
    if args.type == "character" and args.category_id is None:
        ap.error("角色模板必须传 --category-id")
    if args.type == "poster":
        payload = {"name": args.name, "content": args.content}
        if args.reference_url:
            payload["imageUrl"] = args.reference_url
        endpoint = "POST https://tutu.inkgai.com/v1/supertutu/feature-template/create-poster"
        url = "https://tutu.inkgai.com/inspiration?type=POSTER&create=1"
    else:
        payload = {"templateType": "CHARACTER", "name": args.name, "content": args.content, "categoryId": args.category_id, "scope": "USER"}
        for key, value in (("sampleImageUrl", args.sample_image_url), ("recommendedAspectRatio", args.aspect_ratio)):
            if value:
                payload[key] = value
        endpoint = "POST https://tutu.inkgai.com/v1/supertutu/feature-template/create"
        url = "https://tutu.inkgai.com/inspiration?type=CHARACTER&create=1"
    print(json.dumps({
        "transport": "web_session",
        "endpoint": endpoint,
        "webUrl": url,
        "payload": payload,
        "next": "在已登录的图图网页提交；如需看图解析，先调用 analyze-reference。当前 API Key 开放平台未提供模板接口。",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
