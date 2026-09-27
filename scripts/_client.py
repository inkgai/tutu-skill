"""图图 OpenAPI 共享客户端。

被 create_*.py / list_works.py 复用。提供：
- API Key 解析（--api-key 参数 > TUTU_API_KEY 环境变量）
- 提交 / 查询 / 轮询的统一封装
- 自适应轮询间隔（前 3 次 4s，之后 6s）
- 友好的错误提示（HTTP 401 / 网络异常 / 非 JSON 响应 / 业务码非 200）
- 超时时返回部分进度（不丢已完成的 shots）
"""
from __future__ import annotations

import os
import sys
import time
from typing import Any

try:
    import requests
except ImportError:
    sys.exit("缺少依赖：pip install requests")

BASE_URL = os.environ.get("TUTU_BASE_URL", "https://tutu.inkgai.com/api/v1/openapi").rstrip("/")
FRONTEND_URL = os.environ.get("TUTU_FRONTEND_URL", "https://tutu.inkgai.com").rstrip("/")
API_KEY_URL = "https://sso.inkgai.com/home/apikey"

# 参考图约束（与后端 POST /upload-reference、POST /image 契约一致）
MAX_REF_IMAGES = 3
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5MB
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
OSS_URL_HINT = "s.inkgai.com"  # 图图 OSS 域名；referenceImageUrls 必须是它名下的 URL
_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}

# 轮询策略：前 3 次 4s（赶上快的任务），之后退避到 6s（多数任务 30s+，省一半请求）
FAST_POLL_INTERVAL = 4
SLOW_POLL_INTERVAL = 6
FAST_POLL_COUNT = 3
DEFAULT_MAX_POLLS = 75  # ≈ 7.5 分钟（3*4 + 72*6）


def resolve_api_key(cli_arg: str | None = None) -> str:
    """优先级：--api-key 参数 > TUTU_API_KEY 环境变量 > 旧名 SUPERTUTU_API_KEY。两者都没有则友好退出。"""
    key = (cli_arg or "").strip() or os.environ.get("TUTU_API_KEY", "").strip() or os.environ.get("SUPERTUTU_API_KEY", "").strip()
    if not key:
        sys.exit(
            "❌ 缺少 API Key。两种传入方式任选其一：\n"
            "   1) 命令行参数：--api-key ak_xxxx\n"
            "   2) 环境变量：  export TUTU_API_KEY=ak_xxxx\n"
            f"   获取地址：{API_KEY_URL}"
        )
    return key


def _headers(api_key: str) -> dict[str, str]:
    return {"X-API-KEY": api_key, "Content-Type": "application/json"}


def _err_msg(data: dict[str, Any]) -> str:
    """业务错误文案：优先 errorMessage（BusinessException 的详细原因，如
    「该工作空间不是配图空间…」），回退 message（通用错误码文案，如「请求体错误」）。"""
    return data.get("errorMessage") or data.get("message") or "未知错误"


def post(path: str, body: dict[str, Any], api_key: str, timeout: int = 120) -> dict[str, Any]:
    """提交创作任务，返回 `data` 字段。失败时友好退出。"""
    url = f"{BASE_URL}{path}"
    try:
        r = requests.post(url, json=body, headers=_headers(api_key), timeout=timeout)
    except requests.exceptions.RequestException as e:
        sys.exit(f"❌ 网络错误：{e}")

    if r.status_code == 401:
        sys.exit(f"❌ API Key 无效或已过期（HTTP 401）\n   重新获取：{API_KEY_URL}")

    try:
        data = r.json()
    except ValueError:
        sys.exit(f"❌ 后端返回非 JSON（HTTP {r.status_code}）：{r.text[:200]}")

    if data.get("code") != 200:
        sys.exit(f"❌ 提交失败：{_err_msg(data)}")

    return data.get("data") or {}


def get(path: str, api_key: str, params: dict[str, Any] | None = None, timeout: int = 15) -> dict[str, Any]:
    """GET 请求，返回 `data` 字段。失败时友好退出。"""
    try:
        r = requests.get(f"{BASE_URL}{path}", headers=_headers(api_key), params=params, timeout=timeout)
    except requests.exceptions.RequestException as e:
        sys.exit(f"❌ 网络错误：{e}")

    if r.status_code == 401:
        sys.exit(f"❌ API Key 无效或已过期（HTTP 401）\n   重新获取：{API_KEY_URL}")

    try:
        data = r.json()
    except ValueError:
        sys.exit(f"❌ 后端返回非 JSON（HTTP {r.status_code}）：{r.text[:200]}")

    if data.get("code") != 200:
        sys.exit(f"❌ 查询失败：{_err_msg(data)}")

    return data.get("data") or {}


def validate_local_image(path: str) -> None:
    """本地参考图预校验（存在 / 是文件 / 扩展名 / ≤5MB），不合格直接友好退出。

    在发起上传前调用，避免白跑一次网络请求。约束与后端 /upload-reference 一致。
    """
    if not os.path.exists(path):
        sys.exit(f"❌ 参考图不存在：{path}")
    if not os.path.isfile(path):
        sys.exit(f"❌ 参考图不是文件：{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTS:
        sys.exit(
            f"❌ 参考图格式不支持：{path}\n"
            f"   仅支持：{' / '.join(sorted(ALLOWED_IMAGE_EXTS))}"
        )
    size = os.path.getsize(path)
    if size > MAX_UPLOAD_BYTES:
        sys.exit(
            f"❌ 参考图超过 5MB 上限（实际 {size / 1024 / 1024:.1f}MB）：{path}\n"
            "   请压缩后重试"
        )


def upload_reference_image(path: str, api_key: str, timeout: int = 60) -> dict[str, Any]:
    """上传本地参考图到图图 OSS（POST /upload-reference，multipart 字段名 `image`）。

    返回 data：{"url": "https://s.inkgai.com/...", "fileName": "...", "size": 12345}。
    失败时友好退出。

    注意：multipart 的 Content-Type（含 boundary）由 requests 自动生成，
    所以这里不复用 _headers()（它带 application/json，会破坏 multipart 编码）。
    """
    validate_local_image(path)
    ext = os.path.splitext(path)[1].lower()
    mime = _EXT_TO_MIME.get(ext, "application/octet-stream")
    url = f"{BASE_URL}/upload-reference"
    try:
        with open(path, "rb") as f:
            r = requests.post(
                url,
                files={"image": (os.path.basename(path), f, mime)},
                headers={"X-API-KEY": api_key},
                timeout=timeout,
            )
    except requests.exceptions.RequestException as e:
        sys.exit(f"❌ 上传参考图网络错误：{e}")

    if r.status_code == 401:
        sys.exit(f"❌ API Key 无效或已过期（HTTP 401）\n   重新获取：{API_KEY_URL}")

    try:
        data = r.json()
    except ValueError:
        sys.exit(f"❌ 后端返回非 JSON（HTTP {r.status_code}）：{r.text[:200]}")

    if data.get("code") != 200:
        sys.exit(f"❌ 参考图上传失败：{_err_msg(data)}")

    payload = data.get("data") or {}
    if not payload.get("url"):
        sys.exit(f"❌ 上传成功但后端未返回 url：{payload}")
    return payload


def _get_work_safe(work_id: str, api_key: str) -> dict[str, Any]:
    """查询作品状态，失败时抛 RuntimeError 由轮询层决定重试 vs 终止。"""
    try:
        r = requests.get(f"{BASE_URL}/work/{work_id}", headers=_headers(api_key), timeout=15)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"网络错误：{e}") from e

    if r.status_code == 401:
        sys.exit(f"❌ API Key 无效或已过期（HTTP 401）\n   重新获取：{API_KEY_URL}")

    try:
        data = r.json()
    except ValueError:
        raise RuntimeError(f"后端返回非 JSON（HTTP {r.status_code}）") from None

    if data.get("code") != 200:
        raise RuntimeError(_err_msg(data))

    return data.get("data") or {"workId": work_id}


def poll_until_done(
    work_id: str,
    api_key: str,
    max_polls: int = DEFAULT_MAX_POLLS,
    ready_means_done: bool = False,
) -> tuple[dict[str, Any], str]:
    """轮询作品状态直到完成 / 失败 / 超时。

    Args:
        work_id: 作品 ID
        api_key: API Key
        max_polls: 最多轮询次数（默认 75 ≈ 7.5 分钟）
        ready_means_done: True 时所有 shots `status=ready` 也视为完成（用于 /prompt 端点）

    Returns:
        (work_dict, status_label) 元组，status_label ∈ {"completed", "failed", "timeout"}。
        三种情况下 work_dict 都尽量带上最新的 shots 部分进度，不丢数据。

    自适应轮询：前 FAST_POLL_COUNT 次 FAST_POLL_INTERVAL 秒，之后退避到 SLOW_POLL_INTERVAL 秒。
    连续 3 次查询异常会停止轮询并视为 timeout。
    """
    print(f"⏳ workId={work_id}，轮询中…", file=sys.stderr)
    last_work: dict[str, Any] = {"workId": work_id}
    consecutive_errors = 0

    for i in range(max_polls):
        interval = FAST_POLL_INTERVAL if i < FAST_POLL_COUNT else SLOW_POLL_INTERVAL
        time.sleep(interval)

        try:
            work = _get_work_safe(work_id, api_key)
            consecutive_errors = 0
            last_work = work
        except RuntimeError as e:
            consecutive_errors += 1
            print(f"  [{i+1}/{max_polls}] 查询异常：{e}", file=sys.stderr)
            if consecutive_errors >= 3:
                print(f"⚠️  连续 3 次查询失败，停止轮询。workId={work_id}", file=sys.stderr)
                return last_work, "timeout"
            continue

        status = work.get("status")
        shots = work.get("shots") or []
        if shots:
            done_count = sum(1 for s in shots if s.get("status") in ("ready", "completed"))
            progress = f"{done_count}/{len(shots)}"
        else:
            progress = "—"
        print(f"  [{i+1}/{max_polls}] status={status} shots={progress}", file=sys.stderr)

        if status == "completed":
            return work, "completed"
        if status == "failed":
            return work, "failed"
        if ready_means_done and shots and all(s.get("status") in ("ready", "completed") for s in shots):
            # /prompt 端点：shots 全部到 ready 即可
            return work, "completed"

    print(f"⏰ 轮询超时（{max_polls} 次），workId={work_id}", file=sys.stderr)
    return last_work, "timeout"


def failure_hint(work_id: str, work: dict[str, Any] | None = None) -> str:
    """构造统一的失败 / 超时提示文案。

    注：当前 OpenAPI 响应未暴露 errorMessage 字段，因此只能提示 workId 和前端 URL。
    待后端 SkillWorkStatusResponse 补字段后，本函数可以直接读 work['errorMessage'] 透传。
    """
    msg = f"工作 ID：{work_id}\n请到前端查看详情：{FRONTEND_URL}/gallery"
    # 预留 errorMessage hook：后端补字段后这里能立即生效
    if work and isinstance(work, dict):
        err = work.get("errorMessage") or work.get("error_message")
        if err:
            msg = f"失败原因：{err}\n" + msg
    return msg


def collect_image_urls(work: dict[str, Any]) -> list[str]:
    """从 work.shots[] 按 shotIndex 升序收集 imageUrl（漫画 / 配图）。"""
    shots = work.get("shots") or []
    shots_sorted = sorted(shots, key=lambda s: s.get("shotIndex") or 0)
    return [s["imageUrl"] for s in shots_sorted if s.get("imageUrl")]
