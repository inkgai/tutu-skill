#!/usr/bin/env python3
"""图图 — 续接生图脚本（用当前最新分镜状态触发图像渲染）。

用法:
    python render_work.py --work-id <workId> [--seed 42] [--no-wait] [--api-key ak_xxx]

用途：分步精修流程的收尾——调过 /prompt 拿分镜、用 update_shot.py 精修过 caption /
气泡 / prompt 之后，本脚本把所有 READY/FAILED 分镜批量送进图像生成队列，**不重新走 LLM，
不丢精修内容**。

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

参数:
    --work-id    必填，要触发生图的 work ID（从 create_prompt.py 的输出拿）
    --seed       可选，固定随机种子（多格保持画风一致用）
    --no-wait    可选，触发后立即返回，不等待生图完成（默认会轮询到 completed）
    --api-key    API Key（可选，优先于环境变量）

行为：
    - 默认会调 POST /work/{workId}/render 触发生图，然后轮询到 completed/failed/timeout
    - 加 --no-wait 时只触发不等待，立即返回当前 work 状态
    - 失败 / 超时同 create_comic.py：保留已完成的分镜，不丢数据

输出（stdout，JSON 格式）：
    {
      "workId":    "uuid",
      "title":     "...",
      "imageUrls": ["...", ...],
      "status":    "completed|failed|timeout|triggered"
    }
    （--no-wait 时 status="triggered"，imageUrls 通常为空——需要后续轮询）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import collect_image_urls, failure_hint, poll_until_done, post, resolve_api_key  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 续接生图（精修后触发图像生成）")
    ap.add_argument("--work-id", required=True, help="作品 ID")
    ap.add_argument("--seed", default=None, help="随机种子（可选，多格画风一致用）")
    ap.add_argument("--no-wait", action="store_true",
                    help="只触发不轮询，立即返回当前 work 状态")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    api_key = resolve_api_key(args.api_key)

    # 触发生图——POST /work/{workId}/render
    # _client.post 是用于"创作端点的 body POST"——render 走 query param，自己拼一下
    path = f"/work/{args.work_id}/render"
    if args.seed:
        path += f"?seed={quote(str(args.seed), safe='')}"

    print(f"📤 触发生图：workId={args.work_id}, seed={args.seed or '(auto)'}…", file=sys.stderr)
    data = post(path, {}, api_key)
    # data 直接是 SkillWorkStatusResponse —— 含 workId / status / shots / title 等

    if args.no_wait:
        urls = collect_image_urls(data)
        result = {
            "workId": args.work_id,
            "title": data.get("title", ""),
            "imageUrls": urls,
            "status": "triggered",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 默认轮询到完成
    work, status = poll_until_done(args.work_id, api_key)
    urls = collect_image_urls(work)

    if status == "failed":
        print(f"\n❌ 生图失败。{failure_hint(args.work_id, work)}", file=sys.stderr)
    elif status == "timeout":
        print(f"\n⚠️  超时但保留 {len(urls)} 张已完成的分镜。{failure_hint(args.work_id, work)}",
              file=sys.stderr)

    result = {
        "workId": args.work_id,
        "title": work.get("title", ""),
        "imageUrls": urls,
        "status": status,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if status == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
