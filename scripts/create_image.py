#!/usr/bin/env python3
"""图图 — 自定义生图脚本（无 LLM 阶段，直接 prompt → 图）。

用法:
    python create_image.py --prompt "画面描述" [--title "标题"]
                           [--ratio 1:1] [--seed 42]
                           [--ref ./sketch.png] [--ref https://s.inkgai.com/xx.png]
                           [--api-key ak_xxx]

参考图（--ref，可重复，最多 3 张）：
    - 本地文件路径 → 自动先调 POST /upload-reference 上传到图图 OSS，再把返回的 URL 填入请求
    - http(s) URL  → 直接透传；⚠️ 必须是图图 OSS 域名（s.inkgai.com）的 URL，
      外部 URL 会被后端 400 拒绝（「参考图链接无效，请重新上传」）
    - 本地文件限制：≤5MB，仅 jpg / jpeg / png / gif / webp（上传前本地先校验）

    示例：
        # 用本地草图当参考
        python create_image.py --prompt "把这张草图变成水彩插画" --ref ./sketch.png
        # 混用本地文件 + 已上传的 OSS URL
        python create_image.py --prompt "融合两图风格" --ref ./a.jpg --ref https://s.inkgai.com/uploads/b.png

计费：每次生成 2 积分，失败自动退。

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

提示：底层模型对英文 prompt 更敏感，中文 prompt 会先被翻译再喂模型。

注意：结果在 work.coverImageUrl，shots[] 为空 —— 这与漫画/配图不同。

输出（stdout，JSON 格式）：
    {"workId": "...", "title": "...", "imageUrl": "...", "status": "completed|failed|timeout"}
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import (  # noqa: E402
    MAX_REF_IMAGES,
    OSS_URL_HINT,
    failure_hint,
    poll_until_done,
    post,
    resolve_api_key,
    upload_reference_image,
    validate_local_image,
)

RECOMMENDED_RATIOS = {"3:4", "1:1", "4:3", "2:3", "3:2", "16:9", "9:16"}


def resolve_reference_urls(refs: list[str], api_key: str) -> list[str]:
    """把 --ref 列表解析成 OSS URL 列表：URL 透传，本地文件上传。

    先对全部本地文件做本地校验（存在 / ≤5MB / 图片扩展名），全部通过后再逐个上传，
    避免传到一半才发现后面的文件有问题。
    """
    local_paths = [r for r in refs if not r.startswith(("http://", "https://"))]
    for path in local_paths:
        validate_local_image(path)

    urls: list[str] = []
    for ref in refs:
        if ref.startswith(("http://", "https://")):
            if not ref.lower().startswith(("https://" + OSS_URL_HINT + "/", "http://" + OSS_URL_HINT + "/")):
                print(
                    f"⚠️  {ref}\n"
                    f"   看起来不是图图 OSS 域名（{OSS_URL_HINT}）的 URL——"
                    "外部 URL 会被后端 400 拒绝（参考图链接无效，请重新上传）。\n"
                    "   本地文件请直接传路径，脚本会自动上传。",
                    file=sys.stderr,
                )
            urls.append(ref)
        else:
            print(f"📤 上传参考图 {ref}…", file=sys.stderr)
            uploaded = upload_reference_image(ref, api_key)
            print(f"   ✅ {uploaded.get('fileName', ref)} → {uploaded['url']}", file=sys.stderr)
            urls.append(uploaded["url"])
    return urls


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 自定义生图（提交并轮询到完成）")
    ap.add_argument("--prompt", required=True, help="图像描述（≤2000 字符，英文效果更佳）")
    ap.add_argument("--title", default="", help="标题（可选，≤100 字）")
    ap.add_argument("--ratio", default="1:1",
                    help="画面比例：3:4 竖图 / 1:1 方图 / 4:3 横图 / 2:3 竖图 / 3:2 横图 / 16:9 宽屏 / 9:16 长屏（默认 1:1）")
    ap.add_argument("--seed", type=int, default=None, help="随机种子（可选，复现同画面用）")
    ap.add_argument("--ref", action="append", default=[], metavar="PATH_OR_URL",
                    help=f"参考图，可重复，最多 {MAX_REF_IMAGES} 张。本地文件路径（≤5MB，"
                         "jpg/jpeg/png/gif/webp，自动上传到图图 OSS）或图图 OSS 的 http(s) URL"
                         "（外部 URL 会被后端拒绝）")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    if len(args.ref) > MAX_REF_IMAGES:
        sys.exit(f"❌ 参考图最多 {MAX_REF_IMAGES} 张，当前 {len(args.ref)} 张")
    if args.ratio not in RECOMMENDED_RATIOS:
        print(f"⚠️  比例 {args.ratio} 不在推荐值内（3:4 / 1:1 / 4:3 / 2:3 / 3:2 / 16:9 / 9:16），"
              "可能被后端拒绝或回落", file=sys.stderr)

    api_key = resolve_api_key(args.api_key)

    ref_urls = resolve_reference_urls(args.ref, api_key)

    body: dict = {"prompt": args.prompt, "aspectRatio": args.ratio}
    if args.title:
        body["title"] = args.title
    if args.seed is not None:
        body["seed"] = args.seed
    if ref_urls:
        body["referenceImageUrls"] = ref_urls

    print("📤 提交自定义生图任务…", file=sys.stderr)
    data = post("/image", body, api_key)
    work_id = data.get("workId")
    if not work_id:
        sys.exit(f"❌ 后端未返回 workId：{data}")

    work, status = poll_until_done(work_id, api_key)
    cover = work.get("coverImageUrl", "") or ""

    if status == "failed":
        print(f"\n❌ 生图失败（积分已自动退还）。{failure_hint(work_id, work)}", file=sys.stderr)
    elif status == "timeout":
        print(f"\n⚠️  超时但保留最后状态。{failure_hint(work_id, work)}", file=sys.stderr)

    result = {
        "workId": work_id,
        "title": work.get("title", ""),
        "imageUrl": cover,
        "status": status,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if status == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
