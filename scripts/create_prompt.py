#!/usr/bin/env python3
"""图图 — 仅生成分镜提示词（不生图）。

用法（推荐：用空间创作）:
    python create_prompt.py --workspace-id 42 --content "故事文案"

用法（自定义创作，需明确指定风格 + 输出模式）:
    python create_prompt.py --content "故事文案" [--style-id 12] [--output-mode split]
                            [--shots 4] [--title "标题"]

适合「先看 prompt 再决定要不要生图」（分步精修流程入口）或「拿提示词去别的图像服务」。
轮询到 shots[].status == "ready" 即终止，比走完整生图省时省积分。

⚠️ 强烈推荐用空间创作（--workspace-id）——参数一次配好长期复用，比每次裸创作稳定。
   先调 list_workspaces.py 查询「我的空间」，按 name 匹配挑出 workspaceId。

⚠️ 不用空间时，默认 --output-mode split（带字幕条），让 LLM 真的生成 caption
   供 review。**否则分步精修阶段什么都看不到**（image_only 下 LLM 不生成文字）。

   按风格 defaultLayout 推 outputMode：caption → split，bubble → merged。

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

输出（stdout，JSON 格式）：
    {
      "workId": "...",
      "title": "...",
      "status": "completed|failed|timeout",
      "shots": [
        {"shotIndex": 0, "prompt": "...", "caption": "...", "dialogue": [...]},
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
from _client import failure_hint, poll_until_done, post, resolve_api_key  # noqa: E402

VALID_OUTPUT_MODES = {"image_only", "split", "merged", "split_with_bubble"}


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 仅生成分镜提示词")
    ap.add_argument("--content", required=True, help="故事文案（≤5000 字）")
    ap.add_argument("--workspace-id", type=int, default=None,
                    help="工作空间 ID（强烈推荐！锁定所有参数，长期复用更稳定）"
                         "；指定后 --style-id / --output-mode 被忽略")
    ap.add_argument("--title", default="", help="标题（可选）")
    ap.add_argument("--shots", type=int, default=4, help="格数 1-8（默认 4）")
    ap.add_argument("--style-id", type=int, default=None,
                    help="风格 ID（workspace_types.id；用 list_styles.py 查询）")
    ap.add_argument("--output-mode", default="split",
                    help=("输出模式（默认 split 带字幕条；分步精修必备）："
                          "image_only=不生成文字 / split=生成 caption / "
                          "merged=生成 dialogue / split_with_bubble=两者都生成"))
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    if args.output_mode and args.output_mode not in VALID_OUTPUT_MODES:
        sys.exit(f"❌ 无效 --output-mode '{args.output_mode}'，"
                 f"可选：{', '.join(sorted(VALID_OUTPUT_MODES))}")

    api_key = resolve_api_key(args.api_key)

    body: dict = {
        "content": args.content,
        "shotCount": args.shots,
    }
    if args.title:
        body["title"] = args.title

    if args.workspace_id is not None:
        body["workspaceId"] = args.workspace_id
        print(f"📤 提交提示词生成任务（用空间 {args.workspace_id}）…", file=sys.stderr)
    else:
        if args.style_id is not None:
            body["styleTypeId"] = args.style_id
        if args.output_mode:
            body["outputMode"] = args.output_mode
        print(f"📤 提交提示词生成任务（自定义模式，outputMode={args.output_mode}）…", file=sys.stderr)

    data = post("/prompt", body, api_key)
    work_id = data.get("workId")
    if not work_id:
        sys.exit(f"❌ 后端未返回 workId：{data}")

    # ready_means_done=True：shots 全部到 ready 即视为完成（不必等图像生成）
    work, status = poll_until_done(work_id, api_key, ready_means_done=True)

    shots_out = []
    for s in sorted(work.get("shots") or [], key=lambda x: x.get("shotIndex") or 0):
        if s.get("prompt"):
            shots_out.append({
                "shotIndex": s.get("shotIndex"),
                "shotId": s.get("shotId"),
                "prompt": s.get("prompt"),
                "caption": s.get("caption") or "",
                "dialogue": s.get("dialogue") or [],
            })

    if status == "failed":
        print(f"\n❌ 提示词生成失败。{failure_hint(work_id, work)}", file=sys.stderr)
    elif status == "timeout":
        print(f"\n⚠️  超时但保留 {len(shots_out)} 个已就绪分镜。{failure_hint(work_id, work)}", file=sys.stderr)

    result = {
        "workId": work_id,
        "title": work.get("title", ""),
        "status": status,
        "shots": shots_out,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if status == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
