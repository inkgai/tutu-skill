#!/usr/bin/env python3
"""图图 — 文章配图脚本。

用法:
    # 自定义模式（指定风格）
    python create_article_illustration.py --content "文章正文（≥300 字）"
                                          [--count 4] [--style warm_illustration]
                                          [--ratio 2:3] [--mode pure_image]
                                          [--character-id 12] [--ref-image URL ...]
                                          [--api-key ak_xxx]
    # 空间创作（风格 / 比例 / 生图模式 / 角色由空间锁定，与漫画 --workspace-id 对齐）
    python create_article_illustration.py --workspace-id 42 --content "文章正文" [--count 4]
    #   先用 list_workspaces.py 查 scene=article 的空间，拿 id

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

风格可选值（--style）：
    workplace           职场 / 商务
    warm_illustration   温暖 / 治愈（默认）
    rednote             小红书
    infographic         知识图 / 信息图
    humor               幽默 / 搞笑
    narrative           故事 / 叙事
    literary            文艺 / 文学
    cute                可爱 / Q 版

输出（stdout，JSON 格式）：
    {
      "workId": "...", "title": "...",
      "imageUrls": [...],                 # 各张配图 URL（按 shotIndex 升序）
      "markdownContent": "正文…\n![配图](https://…)\n更多正文…",  # 配好图的成品文章，completed 才有值
      "status": "completed|failed|timeout"
    }

注：markdownContent 是文章配图的最终交付物（图已嵌入正文），可直接整篇复制 / 发布；
    各张图也仍单独列在 imageUrls 里。
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import collect_image_urls, failure_hint, poll_until_done, post, resolve_api_key  # noqa: E402

VALID_STYLES = {
    "workplace", "warm_illustration", "rednote", "infographic",
    "humor", "narrative", "literary", "cute",
}
VALID_MODES = {"pure_image", "text_blend"}
# 配图含 LLM 提示词阶段 + 图像派发，慢于漫画／自定义；轮询上限放宽到 ≈ 15 分钟
ARTICLE_MAX_POLLS = 150


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 文章配图（提交并轮询到完成）")
    ap.add_argument("--content", required=True, help="文章正文（≥300 字，≤5000 字）")
    ap.add_argument("--count", type=int, default=4, help="生成张数 1-10（默认 4）")
    ap.add_argument("--workspace-id", type=int, default=None,
                    help="工作空间 ID（空间创作：风格/比例/生图模式/角色由空间锁定，覆盖下列参数）；"
                         "先用 list_workspaces.py 查 scene=article 的空间")
    ap.add_argument("--style", default=None,
                    help=f"风格 key（默认 warm_illustration；用 --workspace-id 时由空间决定），可选：{', '.join(sorted(VALID_STYLES))}")
    ap.add_argument("--style-id", type=int, default=None,
                    help="风格 ID（workspace_types.id；若指定则覆盖 --style）")
    ap.add_argument("--ratio", default=None,
                    help="画面比例 1:1 / 3:4 / 4:3 / 2:3 / 3:2（默认 2:3 竖图；用 --workspace-id 时由空间决定）")
    ap.add_argument("--mode", default=None,
                    help=f"生成模式（默认 pure_image；用 --workspace-id 时由空间决定），可选：{', '.join(sorted(VALID_MODES))}")
    ap.add_argument("--character-id", type=int, default=None,
                    help="角色模板 ID（可选，跨张保持角色一致）")
    ap.add_argument("--ref-image", action="append", default=[],
                    help="风格参考图 URL，可重复，最多 3 张")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    workspace_mode = args.workspace_id is not None

    # 参数校验
    if len(args.content) < 300:
        sys.exit(f"❌ 文章内容过短（{len(args.content)} 字），需要至少 300 字")
    if args.style is not None and args.style not in VALID_STYLES:
        sys.exit(f"❌ 无效风格 '{args.style}'，可选：{', '.join(sorted(VALID_STYLES))}")
    if args.mode is not None and args.mode not in VALID_MODES:
        sys.exit(f"❌ 无效模式 '{args.mode}'，可选：{', '.join(sorted(VALID_MODES))}")
    if args.ratio is not None and args.ratio not in {"1:1", "3:4", "4:3", "2:3", "3:2"}:
        sys.exit(f"❌ 无效比例 '{args.ratio}'。当前生产文章配图 API 仅支持 1:1 / 3:4 / 4:3 / 2:3 / 3:2；16:9 / 9:16 需等待后端 DTO 放开校验")
    if len(args.ref_image) > 3:
        sys.exit(f"❌ 参考图最多 3 张，当前 {len(args.ref_image)} 张")

    api_key = resolve_api_key(args.api_key)

    body: dict = {
        "articleContent": args.content,
        "imageCount": args.count,
        "referenceImageUrls": args.ref_image,
    }
    # character 即使在空间模式下也允许按调用覆盖（后端：仅空间没锁角色时才用空间的）
    if args.character_id is not None:
        body["characterId"] = args.character_id

    if workspace_mode:
        # 空间创作：风格 / 比例 / 生图模式由空间锁定，不下发（后端服务端解析覆盖）
        body["workspaceId"] = args.workspace_id
    else:
        # 自定义模式：补默认并下发（注意 aspectRatio 仅 1:1/2:3/3:2，3:4 / 4:3 可直接使用）
        body["aspectRatio"] = args.ratio or "2:3"
        body["generationMode"] = args.mode or "pure_image"
        if args.style_id is not None:
            body["illustrationStyleId"] = args.style_id
        else:
            body["illustrationStyle"] = args.style or "warm_illustration"

    print(f"📤 提交文章配图任务（空间 {args.workspace_id}）…" if workspace_mode
          else "📤 提交文章配图任务…", file=sys.stderr)
    data = post("/article-illustration", body, api_key)
    work_id = data.get("workId")
    if not work_id:
        sys.exit(f"❌ 后端未返回 workId：{data}")

    work, status = poll_until_done(work_id, api_key, max_polls=ARTICLE_MAX_POLLS)
    urls = collect_image_urls(work)

    if status == "failed":
        print(f"\n❌ 配图生成失败。{failure_hint(work_id, work)}", file=sys.stderr)
    elif status == "timeout":
        print(f"\n⚠️  超时但保留 {len(urls)} 张已完成的配图。{failure_hint(work_id, work)}", file=sys.stderr)

    result = {
        "workId": work_id,
        "title": work.get("title", ""),
        "imageUrls": urls,
        # 配好图的成品文章（图片已按均匀分布嵌入正文的 Markdown）——文章配图的最终交付物。
        # 仅 status=completed 时有值；可直接整篇复制 / 发布给用户。
        "markdownContent": work.get("markdownContent"),
        "status": status,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if status == "completed" and not result["markdownContent"]:
        print("⚠️  已完成但 markdownContent 为空（后端可能未部署该字段或非配图作品），"
              "仅返回 imageUrls。", file=sys.stderr)

    if status == "failed":
        sys.exit(1)


if __name__ == "__main__":
    main()
