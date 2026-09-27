#!/usr/bin/env python3
"""图图 — 分镜精修脚本（修改单个分镜的字幕 / 气泡 / 提示词）。

用法:
    python update_shot.py --shot-id 12345 \
        [--caption "新字幕文案"] \
        [--dialogue '[{"role":"猫","text":"喵！","direction":"右"}]'] \
        [--prompt "新图像提示词文本"] \
        [--api-key ak_xxx]

至少传入 --caption / --dialogue / --prompt 之一；可同时传多个，本脚本会逐个调用对应端点。

典型场景：分步精修流程
    1) 先调 create_prompt.py 生成分镜（不生图）
    2) 用 list_works.py 或 GET /work/{workId} 拿到 shots[]，挨个 review
    3) 不满意的字幕 / 气泡 / 提示词，用 update_shot.py 改
    4) 改好后调创作脚本（或 reroll 端点）出图

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

dialogue JSON 结构（与 LLM 写入一致）：
    [
      {
        "role":      "猫咪",    // 选填，独白/旁白可空
        "text":      "我饿了！", // 必填，最多 200 字
        "type":      "speech",  // 选填，speech（默认气泡）/ caption（旁白矩形框）
        "direction": "右"       // 选填，左/右/上/下（气泡尾巴方向）
      }
    ]
    空数组 [] 视为清空所有台词。最多 20 条。

输出（stdout，JSON 格式）：
    {
      "shotId":   12345,
      "updates":  ["caption", "dialogue", "prompt"],
      "results":  { "caption": {...}, "dialogue": {...}, "prompt": {...} }
    }
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import BASE_URL, API_KEY_URL, resolve_api_key  # noqa: E402

# 直接走 requests，绕过 _client.post 的"失败 sys.exit"行为——这里我们想 partial-success
# 第一个字段挂了不该阻断后续字段的修改
try:
    import requests
except ImportError:
    sys.exit("缺少依赖：pip install requests")


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-KEY": api_key, "Content-Type": "application/json"}


def _request(method: str, path: str, body: dict, api_key: str) -> dict:
    """通用 PATCH/PUT 请求，返回 data 字段或抛 RuntimeError。"""
    url = f"{BASE_URL}{path}"
    try:
        r = requests.request(method, url, json=body, headers=_headers(api_key), timeout=30)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"网络错误：{e}") from e

    if r.status_code == 401:
        raise RuntimeError(f"API Key 无效或已过期（HTTP 401）。重新获取：{API_KEY_URL}")

    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"后端返回非 JSON（HTTP {r.status_code}）：{r.text[:200]}")

    if data.get("code") != 200:
        raise RuntimeError(data.get("message", f"业务错误（HTTP {r.status_code}）"))

    return data.get("data") or {}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="图图 分镜精修（修改字幕 / 气泡 / 提示词）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--shot-id", type=int, required=True, help="分镜 ID（必填，从 work.shots[].shotId 拿）")
    ap.add_argument("--caption", default=None,
                    help="新字幕文案（≤500 字，空串=清空）；仅 split / split_with_bubble 输出模式生效")
    ap.add_argument("--dialogue", default=None,
                    help="气泡对话 JSON 数组字符串；空数组 []=清空所有台词")
    ap.add_argument("--prompt", default=None, help="新图像提示词（覆盖 LLM 生成版本，不消耗积分）")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    # 至少传一个字段
    if args.caption is None and args.dialogue is None and args.prompt is None:
        sys.exit("❌ 至少需要传入 --caption / --dialogue / --prompt 之一")

    api_key = resolve_api_key(args.api_key)

    # 提前解析 dialogue JSON，校验失败的话不动 caption 也不动 prompt
    dialogue_list: list | None = None
    if args.dialogue is not None:
        try:
            dialogue_list = json.loads(args.dialogue)
        except json.JSONDecodeError as e:
            sys.exit(f"❌ --dialogue 不是合法 JSON：{e}")
        if not isinstance(dialogue_list, list):
            sys.exit(f"❌ --dialogue 必须是 JSON 数组，当前是 {type(dialogue_list).__name__}")

    updates: list[str] = []
    results: dict[str, object] = {}
    errors: dict[str, str] = {}

    # 1) caption
    if args.caption is not None:
        print(f"✏️  更新字幕（shotId={args.shot_id}, len={len(args.caption)}）…", file=sys.stderr)
        try:
            results["caption"] = _request("PATCH", f"/shot/{args.shot_id}/caption",
                                          {"caption": args.caption}, api_key)
            updates.append("caption")
        except RuntimeError as e:
            errors["caption"] = str(e)
            print(f"  ❌ 字幕更新失败：{e}", file=sys.stderr)

    # 2) dialogue
    if dialogue_list is not None:
        print(f"💬 更新气泡对话（shotId={args.shot_id}, items={len(dialogue_list)}）…", file=sys.stderr)
        try:
            results["dialogue"] = _request("PATCH", f"/shot/{args.shot_id}/dialogue",
                                           {"dialogue": dialogue_list}, api_key)
            updates.append("dialogue")
        except RuntimeError as e:
            errors["dialogue"] = str(e)
            print(f"  ❌ 气泡更新失败：{e}", file=sys.stderr)

    # 3) prompt
    if args.prompt is not None:
        print(f"🎨 更新提示词（shotId={args.shot_id}, len={len(args.prompt)}）…", file=sys.stderr)
        try:
            results["prompt"] = _request("PUT", f"/shot/{args.shot_id}/prompt",
                                         {"finalPrompt": args.prompt}, api_key)
            updates.append("prompt")
        except RuntimeError as e:
            errors["prompt"] = str(e)
            print(f"  ❌ 提示词更新失败：{e}", file=sys.stderr)

    out: dict = {
        "shotId": args.shot_id,
        "updates": updates,
        "results": results,
    }
    if errors:
        out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))

    # 任何一个失败就退出码 1，方便脚本检测
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
