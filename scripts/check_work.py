#!/usr/bin/env python3
"""图图 — 查询单个作品完整状态（防漏看）。

用法:
    python check_work.py --work-id <workId>           # 单次查询
    python check_work.py --work-id <workId> --wait    # 轮询到全部完成才退出

为什么不直接 curl GET /work/{workId}？
    裸响应里 shots[] 是个数组，每个 shot 有独立 status，**很容易只看第一张就以为搞定了**。
    本脚本强制把响应汇总成「N/M 完成、X 张生成中、Y 张失败」+ 完整 URL 列表，
    Claude 拿到后不可能漏报后续未完成的图。

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

输出（stdout，JSON 格式）：
    {
      "workId":       "uuid",
      "title":        "...",
      "status":       "generating|completed|failed",   # work 整体状态
      "summary": {
        "total":      4,                                # 总 shot 数
        "completed":  2,                                # 已完成
        "generating": 2,                                # 生成中
        "ready":      0,                                # 提示词就绪、待生图
        "failed":     0
      },
      "shots": [
        {"shotIndex": 0, "shotId": 8521, "status": "completed", "imageUrl": "https://...", "caption": "..."},
        {"shotIndex": 1, "shotId": 8522, "status": "generating", "imageUrl": null,         "caption": "..."},
        ...
      ],
      "imageUrls":    ["https://...", "https://..."],  # 已完成的所有 URL（按 shotIndex 升序）
      "markdownContent": "正文…\n![配图](https://…)\n…",  # 配图作品：图已嵌入正文的成品文章（漫画/自定义为 null）
      "isAllDone":    false,                            # 所有 shot 完成 = true（含 coverImageUrl 兜底）
      "errorMessage": null,                             # work.status=failed 时的失败原因（已脱敏）
      "advice":       "还有 2 张生成中，建议 30 秒后再查"  # 给 Claude / 用户的下一步建议
    }
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import collect_image_urls, failure_hint, get, poll_until_done, resolve_api_key  # noqa: E402


def _summarize(work: dict) -> dict:
    """把 work 响应聚合成强制可见的进度结构。"""
    shots = work.get("shots") or []
    total = len(shots)
    counts = {"completed": 0, "generating": 0, "ready": 0, "failed": 0}
    for s in shots:
        st = (s.get("status") or "").lower()
        if st in counts:
            counts[st] += 1

    summary = {"total": total, **counts}

    # work.status: completed/generating/failed
    work_status = (work.get("status") or "").lower()
    # 是否全部完成（漫画 / 配图：所有 shot 完成 = 全完；自定义生图：coverImageUrl 存在 = 全完）
    is_all_done = (
        (total > 0 and counts["completed"] == total) or
        (total == 0 and bool(work.get("coverImageUrl")))
    )

    # 已完成图 URL 列表
    image_urls = collect_image_urls(work)
    if not image_urls and work.get("coverImageUrl"):
        # 自定义生图场景：结果在 coverImageUrl，shots 为空
        image_urls = [work["coverImageUrl"]]

    # 给 Claude / 用户的下一步建议
    if work_status == "failed":
        advice = "❌ 作品失败，错误原因见 errorMessage 字段；可调 render_work.py 重试，或重新 create_*.py"
    elif is_all_done:
        advice = f"✅ 全部 {total or 1} 张图已就绪，可直接展示给用户"
        if work.get("markdownContent"):
            advice += "；配图文章成品见 markdownContent 字段（图已嵌入正文，可直接复制/发布）"
    elif counts["generating"] > 0 or counts["ready"] > 0:
        remaining = counts["generating"] + counts["ready"]
        eta = remaining * 30  # 粗略：每张约 30s
        advice = (
            f"⏳ 还有 {remaining} 张在生成中（{counts['completed']}/{total} 已完成），"
            f"建议 {eta} 秒后再查；或加 --wait 等到全部完成自动返回"
        )
    elif counts["failed"] > 0 and counts["completed"] == 0:
        advice = f"❌ 所有 {counts['failed']} 张都失败了，建议 render_work.py 重试或检查 errorMessage"
    else:
        advice = "（无明确建议，请人工判断）"

    return {
        "summary": summary,
        "isAllDone": is_all_done,
        "imageUrls": image_urls,
        "advice": advice,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 作品完整状态查询（防漏看）")
    ap.add_argument("--work-id", required=True, help="作品 ID")
    ap.add_argument("--wait", action="store_true",
                    help="轮询到全部 shot 完成才退出（默认单次查询即返回）")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    api_key = resolve_api_key(args.api_key)

    if args.wait:
        print(f"⏳ workId={args.work_id}，等待全部 shot 完成…", file=sys.stderr)
        work, _status = poll_until_done(args.work_id, api_key)
    else:
        print(f"📤 查询作品 {args.work_id} 当前状态（单次）…", file=sys.stderr)
        work = get(f"/work/{args.work_id}", api_key)

    summary_data = _summarize(work)

    # 失败原因（仅 status=failed 时有值，已脱敏）
    err = None
    if (work.get("status") or "").lower() == "failed":
        err = work.get("errorMessage") or "作品失败但后端未返回 errorMessage"

    result = {
        "workId": args.work_id,
        "title": work.get("title", ""),
        "status": work.get("status"),
        "summary": summary_data["summary"],
        "shots": [
            {
                "shotIndex": s.get("shotIndex"),
                "shotId": s.get("shotId"),
                "status": s.get("status"),
                "imageUrl": s.get("imageUrl"),
                "caption": s.get("caption") or "",
                "errorMessage": s.get("errorMessage"),
            }
            for s in sorted(work.get("shots") or [], key=lambda x: x.get("shotIndex") or 0)
        ],
        "imageUrls": summary_data["imageUrls"],
        # 配图作品专属：图已嵌入正文的成品 Markdown（最终交付物）。漫画/自定义生图为 null。
        "markdownContent": work.get("markdownContent"),
        "isAllDone": summary_data["isAllDone"],
        "errorMessage": err,
        "advice": summary_data["advice"],
    }

    # 进度日志写到 stderr，让用户在终端也能扫一眼
    s = summary_data["summary"]
    print(
        f"📊 进度: {s['completed']}/{s['total']} 完成 | "
        f"⏳ 生成中: {s['generating']} | ✅ 提示词就绪: {s['ready']} | ❌ 失败: {s['failed']}",
        file=sys.stderr,
    )
    print(f"💡 {summary_data['advice']}", file=sys.stderr)
    if err:
        print(f"\n{failure_hint(args.work_id, work)}", file=sys.stderr)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
