#!/usr/bin/env python3
"""图图 — AI 生成画板 / 流程图（结构化图解 → 可在图图「画板(Beta)」打开的 .tutu.json）。

一句话 → 流程图 / 架构图 / 图解。给定 prompt + API Key：
  1) 调 `POST /v1/openapi/diagram` 拿结构化 spec（title + nodes + edges，不含坐标）
  2) 本地自动布局（分层自顶向下，移植自前端 whiteboard/engine/autoLayout.ts）
  3) 本地把布局好的图转成白板元素（移植自 whiteboard/engine/diagramFromSpec.ts）
  4) 序列化成 `.tutu.json`（结构对齐 whiteboard/engine/export.ts 的 serializeScene）写文件

产物 `.tutu.json` 可在图图「画板(Beta)」里用「打开」导入，继续手绘 / 调整 / 导出。

用法:
    python diagram.py --prompt "用户注册登录流程" [--out 路径.tutu.json]
                      [--api-key ak_xxx]

API Key 两种传入方式（任选其一）：
    1) 命令行参数：--api-key ak_xxx
    2) 环境变量：  export TUTU_API_KEY=ak_xxx

输出（stdout，JSON 格式）：
    {
      "file":  "用户注册登录流程.tutu.json",   # 写出的画板文件路径
      "title": "用户注册登录流程",
      "nodeCount": 8,
      "edgeCount": 9,
      "spec": { "title": "...", "nodes": [...], "edges": [...] }   # 结构化中间表示，可直接复用
    }

积分：1（生成结构化图解）。本地布局 / 转换不额外扣分。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _client import post, resolve_api_key  # noqa: E402

# ============================================================================
# id / seed —— 对齐 utils/element.ts：id 用 nanoid（21 位 url-safe），seed 随机整数
# ============================================================================

# nanoid 默认字母表（url-safe），与前端 nanoid() 同字符集
_NANOID_ALPHABET = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict"


def nanoid(size: int = 21) -> str:
    """生成 21 位 url-safe 随机 id（nanoid 风格，与前端元素工厂同口径）。"""
    return "".join(_NANOID_ALPHABET[secrets.randbelow(len(_NANOID_ALPHABET))] for _ in range(size))


def random_seed() -> int:
    """rough.js 随机种子（对齐 element.ts randomSeed：0 ~ 2**31-1）。"""
    return secrets.randbelow(2 ** 31)


# ============================================================================
# 自动布局 —— 移植自 whiteboard/engine/autoLayout.ts（Sugiyama-lite 分层布局）
#   坐标：场景坐标，原点左上，x 向右 y 向下；(x,y) 为节点矩形左上角。
#   纯函数 / 确定性 / 无副作用。常量与算法原样照搬。
# ============================================================================

# —— 布局常量（与 autoLayout.ts 一致） ——
NODE_MIN_WIDTH = 120
NODE_MAX_WIDTH = 280
CHAR_WIDTH = 17          # 中文字约 17px/字
TEXT_PADDING = 32        # 左右内边距合计
ROW_HEIGHT = 56          # rectangle / ellipse 行高
DIAMOND_EXTRA_WIDTH = 24  # diamond 文字塞进旋转方块，略宽
DIAMOND_HEIGHT = 72      # diamond 略高
H_GAP = 64               # 同层节点水平间距
V_GAP = 96               # 层间垂直间距
COMPONENT_GAP = 120      # 连通分量之间水平间距

_MAX_SAFE_INTEGER = 2 ** 53 - 1  # 对齐 JS Number.MAX_SAFE_INTEGER


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, v))


def _measure_node(node: dict) -> tuple[float, float]:
    """由 label 估算节点尺寸（确定性，不量 DOM）。按码点数（含中文）计长。"""
    label = node.get("label") or ""
    length = len(label)  # Python str 按 Unicode 码点迭代，等价 Array.from(label).length
    raw = length * CHAR_WIDTH + TEXT_PADDING
    is_diamond = node.get("shape") == "diamond"
    width = _clamp(raw + (DIAMOND_EXTRA_WIDTH if is_diamond else 0), NODE_MIN_WIDTH, NODE_MAX_WIDTH)
    height = DIAMOND_HEIGHT if is_diamond else ROW_HEIGHT
    return width, height


def auto_layout(spec: dict) -> dict:
    """自动布局入口。输入未排版 spec，输出每节点带绝对坐标 + 尺寸；title / edges 透传。

    返回 {title, nodes:[{...node, x, y, width, height}], edges}。
    """
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []

    # 边界：空图。
    if not nodes:
        return {"title": spec.get("title"), "nodes": [], "edges": edges}

    # —— 建索引（仅保留端点都存在的有效边） ——
    by_id: dict[str, dict] = {}
    for n in nodes:
        w, h = _measure_node(n)
        by_id[n["id"]] = {"node": n, "width": w, "height": h, "layer": 0, "x": 0.0, "y": 0.0}

    children: dict[str, list[str]] = {}
    parents: dict[str, list[str]] = {}
    in_degree: dict[str, int] = {}
    for n in nodes:
        children[n["id"]] = []
        parents[n["id"]] = []
        in_degree[n["id"]] = 0
    for e in edges:
        # 端点缺失 / 自环 → 忽略（不抛）。
        if e["from"] not in by_id or e["to"] not in by_id:
            continue
        if e["from"] == e["to"]:
            continue
        children[e["from"]].append(e["to"])
        parents[e["to"]].append(e["from"])
        in_degree[e["to"]] = in_degree.get(e["to"], 0) + 1

    # —— 选根：无入边的节点；全有入边（有环）→ 取第一个节点。 ——
    order = [n["id"] for n in nodes]  # 稳定顺序保证确定性
    roots = [nid for nid in order if in_degree.get(nid, 0) == 0]
    if not roots:
        roots = [order[0]]

    # —— 最长路径分层 + DFS 破环（迭代实现，避免大图递归爆栈；语义同 autoLayout.ts 递归 DFS） ——
    layer_of: dict[str, int] = {}

    def dfs(root: str, root_depth: int) -> None:
        on_path: set[str] = set()
        # 栈帧：(node, depth, child_index)
        stack: list[list] = [[root, root_depth, 0]]
        on_path.add(root)
        prev = layer_of.get(root)
        if prev is None or root_depth > prev:
            layer_of[root] = root_depth
        while stack:
            frame = stack[-1]
            node_id, _depth, ci = frame
            kids = children.get(node_id, [])
            if ci < len(kids):
                frame[2] += 1
                c = kids[ci]
                if c in on_path:
                    continue  # 破环：指回当前路径祖先的边忽略
                child_depth = layer_of.get(node_id, _depth) + 1
                prev_c = layer_of.get(c)
                if prev_c is None or child_depth > prev_c:
                    layer_of[c] = child_depth
                on_path.add(c)
                stack.append([c, child_depth, 0])
            else:
                on_path.discard(node_id)
                stack.pop()

    for r in roots:
        dfs(r, 0)

    # 从根不可达的节点（其它连通分量 / 环上无根入口）：当作新分量 layer 0 根继续分层。
    for nid in order:
        if nid not in layer_of:
            dfs(nid, 0)

    for nid in order:
        by_id[nid]["layer"] = layer_of.get(nid, 0)

    # —— 划分连通分量（无向连通：双向 BFS） ——
    undirected: dict[str, set[str]] = {nid: set() for nid in order}
    for e in edges:
        if e["from"] not in by_id or e["to"] not in by_id or e["from"] == e["to"]:
            continue
        undirected[e["from"]].add(e["to"])
        undirected[e["to"]].add(e["from"])
    comp_of: dict[str, int] = {}
    comp_count = 0
    for nid in order:
        if nid in comp_of:
            continue
        comp = comp_count
        comp_count += 1
        queue = [nid]
        comp_of[nid] = comp
        while queue:
            cur = queue.pop(0)
            for nb in undirected.get(cur, set()):
                if nb not in comp_of:
                    comp_of[nb] = comp
                    queue.append(nb)

    # —— 逐连通分量布局，水平并排 ——
    cursor_x = 0.0
    for comp in range(comp_count):
        comp_ids = [nid for nid in order if comp_of.get(nid) == comp]
        width_used = _layout_component(comp_ids, by_id, parents, cursor_x)
        cursor_x += width_used + COMPONENT_GAP

    # —— 输出 ——
    laid_nodes = []
    for n in nodes:
        l = by_id[n["id"]]
        laid_nodes.append({**n, "x": l["x"], "y": l["y"], "width": l["width"], "height": l["height"]})

    return {"title": spec.get("title"), "nodes": laid_nodes, "edges": edges}


def _layout_component(
    comp_ids: list[str],
    by_id: dict[str, dict],
    parents: dict[str, list[str]],
    offset_x: float,
) -> float:
    """布局单个连通分量，坐标写回 by_id。返回该分量占用总宽度。"""
    if not comp_ids:
        return 0.0

    # 单节点：直接放在偏移处。
    if len(comp_ids) == 1:
        l = by_id[comp_ids[0]]
        l["x"] = offset_x
        l["y"] = 0.0
        return l["width"]

    # 按层分桶（稳定顺序）。
    layers: dict[int, list[str]] = {}
    max_layer = 0
    for nid in comp_ids:
        ly = by_id[nid]["layer"]
        layers.setdefault(ly, []).append(nid)
        if ly > max_layer:
            max_layer = ly

    # 一遍 barycenter：自上而下，按父节点 x 均值排序同层减少交叉。
    temp_x: dict[str, float] = {}
    layer0 = layers.get(0, [])
    acc_x = 0.0
    for nid in layer0:
        temp_x[nid] = acc_x
        acc_x += by_id[nid]["width"] + H_GAP

    for ly in range(1, max_layer + 1):
        ids = layers.get(ly, [])
        bary: dict[str, float] = {}
        for idx, nid in enumerate(ids):
            ps = [p for p in parents.get(nid, []) if p in temp_x]
            if not ps:
                bary[nid] = _MAX_SAFE_INTEGER - (len(ids) - idx)  # 稳定收尾，排到末尾
            else:
                s = sum(temp_x.get(p, 0.0) for p in ps)
                bary[nid] = s / len(ps)
        # 稳定排序：barycenter 升序，平手保持原顺序。
        sorted_ids = [
            e[0]
            for e in sorted(
                ((nid, idx) for idx, nid in enumerate(ids)),
                key=lambda e: (bary.get(e[0], 0.0), e[1]),
            )
        ]
        layers[ly] = sorted_ids
        a = 0.0
        for nid in sorted_ids:
            temp_x[nid] = a
            a += by_id[nid]["width"] + H_GAP

    # —— 每层总宽与公共中心，使各层居中对齐 ——
    layer_width: dict[int, float] = {}
    global_width = 0.0
    for ly in range(max_layer + 1):
        ids = layers.get(ly, [])
        w = 0.0
        for i, nid in enumerate(ids):
            w += by_id[nid]["width"]
            if i < len(ids) - 1:
                w += H_GAP
        layer_width[ly] = w
        if w > global_width:
            global_width = w
    center = offset_x + global_width / 2

    # —— 纵向：层 y 累加；行高用该层最大节点高度 ——
    layer_y: dict[int, float] = {}
    y = 0.0
    for ly in range(max_layer + 1):
        layer_y[ly] = y
        ids = layers.get(ly, [])
        row_h = max((by_id[nid]["height"] for nid in ids), default=0.0)
        y += row_h + V_GAP

    # —— 落每层节点绝对坐标：本层围绕公共中心水平居中 ——
    for ly in range(max_layer + 1):
        ids = layers.get(ly, [])
        start_x = center - layer_width.get(ly, 0.0) / 2
        for nid in ids:
            l = by_id[nid]
            l["x"] = start_x
            l["y"] = layer_y.get(ly, 0.0)
            start_x += l["width"] + H_GAP

    return global_width


# ============================================================================
# spec → 白板元素 —— 移植自 whiteboard/engine/diagramFromSpec.ts
#   样式基线 diagramAppState()：黑色描边 #1e1e1e、透明填充、roughness 1 手绘、Virgil 字体。
#   每节点：形状 + 居中绑定文字；每边：两端绑定箭头 + 可选中点 label。
#   z-order：形状 → 文字 → 箭头。
# ============================================================================

STROKE = "#1e1e1e"
LABEL_FONT_SIZE = 18
LABEL_FONT_FAMILY = "Virgil, Segoe UI, sans-serif"
EDGE_LABEL_FONT_SIZE = 14
CHAR_WIDTH_RATIO = 0.6   # 估算文字宽度：字号 * 字符数 * 此比例
LINE_HEIGHT_RATIO = 1.25  # 与 drawText / measureTextSize 一致


def _diagram_app_state() -> dict:
    """图解专用样式基线 appState（不读外部，避免被用户当前画笔污染）。"""
    return {
        "activeTool": "selection",
        "toolLocked": False,
        "scrollX": 0,
        "scrollY": 0,
        "zoom": 1,
        "gridSize": 0,
        "currentItemStrokeColor": STROKE,
        "currentItemBackgroundColor": "transparent",
        "currentItemFillStyle": "solid",
        "currentItemStrokeWidth": 2,
        "currentItemStrokeStyle": "solid",
        "currentItemRoughness": 1,
        "currentItemOpacity": 100,
        "currentItemFontSize": LABEL_FONT_SIZE,
        "currentItemFontFamily": LABEL_FONT_FAMILY,
        "selectedElementIds": [],
        "editingTextId": None,
        "selectionBox": None,
    }


def _common_props(app: dict) -> dict:
    """从 appState 抽取公共样式字段（对齐 element.ts commonProps）。"""
    return {
        "id": nanoid(),
        "angle": 0,
        "strokeColor": app["currentItemStrokeColor"],
        "backgroundColor": app["currentItemBackgroundColor"],
        "fillStyle": app["currentItemFillStyle"],
        "strokeWidth": app["currentItemStrokeWidth"],
        "strokeStyle": app["currentItemStrokeStyle"],
        "roughness": app["currentItemRoughness"],
        "opacity": app["currentItemOpacity"],
        "seed": random_seed(),
        "version": 1,
        "isDeleted": False,
    }


def _new_shape_element(shape_type: str, x: float, y: float, app: dict) -> dict:
    """矩形 / 椭圆 / 菱形（对齐 element.ts newShapeElement，初始 0 尺寸，下方写入 w/h）。"""
    return {**_common_props(app), "type": shape_type, "x": x, "y": y, "width": 0, "height": 0}


def _new_linear_element(line_type: str, x: float, y: float, app: dict) -> dict:
    """线 / 箭头（对齐 element.ts newLinearElement）。"""
    return {
        **_common_props(app),
        "type": line_type,
        "x": x,
        "y": y,
        "width": 0,
        "height": 0,
        "points": [{"x": 0, "y": 0}, {"x": 0, "y": 0}],
    }


def _new_text_element(x: float, y: float, app: dict) -> dict:
    """文字（对齐 element.ts newTextElement）。"""
    return {
        **_common_props(app),
        "type": "text",
        "x": x,
        "y": y,
        "width": 0,
        "height": app["currentItemFontSize"] * 1.25,
        "text": "",
        "fontSize": app["currentItemFontSize"],
        "fontFamily": app["currentItemFontFamily"],
        "textAlign": "left",
        "verticalAlign": "top",
    }


def _estimate_text_size(text: str, font_size: float) -> tuple[float, float]:
    """估算一段文字宽高（确定性，不量 DOM；与 diagramFromSpec.ts estimateTextSize 一致）。"""
    lines = text.split("\n") if text else [""]
    max_w = 0.0
    for line in lines:
        length = len(line)  # 按码点数
        max_w = max(max_w, length * font_size * CHAR_WIDTH_RATIO)
    return max_w, len(lines) * font_size * LINE_HEIGHT_RATIO


def _build_node(node: dict, app: dict) -> tuple[dict, dict]:
    """节点 → 容器形状 + 居中绑定文字标签。返回 (shape, text)，text 入场景排在 shape 之后。"""
    shape_type = node.get("shape") or "rectangle"

    shape = _new_shape_element(shape_type, node["x"], node["y"], app)
    shape["width"] = node["width"]
    shape["height"] = node["height"]

    cx = node["x"] + node["width"] / 2
    cy = node["y"] + node["height"] / 2
    label = node.get("label") or ""
    tw, th = _estimate_text_size(label, LABEL_FONT_SIZE)
    text = _new_text_element(cx - tw / 2, cy - th / 2, app)
    text["text"] = label
    text["width"] = tw
    text["height"] = th
    text["textAlign"] = "center"
    text["fontSize"] = LABEL_FONT_SIZE
    # 双向绑定：text.containerId ↔ shape.boundTextId
    text["containerId"] = shape["id"]
    shape["boundTextId"] = text["id"]

    return shape, text


def _build_arrow(
    from_node: dict,
    to_node: dict,
    from_shape_id: str,
    to_shape_id: str,
    label: str | None,
    app: dict,
) -> list[dict]:
    """一条边 → 绑定箭头（from 底边中点 → to 顶边中点），两端绑定到形状；有 label 加中点小字。"""
    start_x = from_node["x"] + from_node["width"] / 2
    start_y = from_node["y"] + from_node["height"]
    end_x = to_node["x"] + to_node["width"] / 2
    end_y = to_node["y"]

    arrow = _new_linear_element("arrow", start_x, start_y, app)
    rel_x = end_x - start_x
    rel_y = end_y - start_y
    arrow["points"] = [{"x": 0, "y": 0}, {"x": rel_x, "y": rel_y}]
    arrow["width"] = abs(rel_x)
    arrow["height"] = abs(rel_y)
    arrow["startBinding"] = {"elementId": from_shape_id}
    arrow["endBinding"] = {"elementId": to_shape_id}

    out = [arrow]

    if label and label.strip():
        mid_x = start_x + rel_x / 2
        mid_y = start_y + rel_y / 2
        tw, th = _estimate_text_size(label, EDGE_LABEL_FONT_SIZE)
        label_el = _new_text_element(mid_x - tw / 2, mid_y - th / 2, app)
        label_el["text"] = label
        label_el["width"] = tw
        label_el["height"] = th
        label_el["textAlign"] = "center"
        label_el["fontSize"] = EDGE_LABEL_FONT_SIZE
        out.append(label_el)

    return out


def diagram_to_elements(laid: dict) -> list[dict]:
    """排版好的图解 → 白板元素扁平数组（形状 / 文字 / 箭头）。z-order：形状 → 文字 → 箭头。"""
    app = _diagram_app_state()
    shapes: list[dict] = []
    texts: list[dict] = []
    arrows: list[dict] = []

    shape_id_by_node: dict[str, str] = {}
    node_by_id: dict[str, dict] = {}
    for node in laid.get("nodes", []):
        node_by_id[node["id"]] = node
        shape, text = _build_node(node, app)
        shape_id_by_node[node["id"]] = shape["id"]
        shapes.append(shape)
        texts.append(text)

    for edge in laid.get("edges", []):
        from_node = node_by_id.get(edge["from"])
        to_node = node_by_id.get(edge["to"])
        from_shape_id = shape_id_by_node.get(edge["from"])
        to_shape_id = shape_id_by_node.get(edge["to"])
        if not from_node or not to_node or not from_shape_id or not to_shape_id:
            continue  # 缺失端点静默跳过（与 autoLayout 一致）
        if edge["from"] == edge["to"]:
            continue  # 自环跳过（无合理锚点）
        arrows.extend(_build_arrow(from_node, to_node, from_shape_id, to_shape_id, edge.get("label"), app))

    return [*shapes, *texts, *arrows]


# ============================================================================
# 序列化 .tutu.json —— 结构对齐 whiteboard/engine/export.ts serializeScene
#   顶层：{type:'vue-excalidraw', version:1, elements:[...过滤已删], appState:{子集}}
#   deserializeScene 校验 type==='vue-excalidraw' && Array.isArray(elements)。
# ============================================================================


def serialize_scene(elements: list[dict], app: dict) -> dict:
    """场景序列化为 .tutu.json 顶层 dict（字段集与 serializeScene 完全一致）。"""
    return {
        "type": "vue-excalidraw",
        "version": 1,
        "elements": [e for e in elements if not e.get("isDeleted")],
        "appState": {
            "currentItemStrokeColor": app["currentItemStrokeColor"],
            "currentItemBackgroundColor": app["currentItemBackgroundColor"],
            "zoom": app["zoom"],
            "scrollX": app["scrollX"],
            "scrollY": app["scrollY"],
        },
    }


# ============================================================================
# CLI
# ============================================================================

_ILLEGAL_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe_filename(title: str) -> str:
    """把 title 清成合法文件名（去非法字符 + 折叠空白 + 去首尾点/空格）。"""
    name = _ILLEGAL_FILENAME_CHARS.sub("", title or "").strip()
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or "画板"


_VALID_SHAPES = {"rectangle", "ellipse", "diamond"}


def _normalize_spec(spec: dict) -> dict:
    """客户端兜底消毒，对齐后端 DiagramAiLogic.validateAndNormalize。

    即使 spec 来源不可信（手搓 / 改过输出再喂 / 后端归一化回归），也不会让
    下游 len(label) 崩、不会把非法 shape 写成画不出的空框元素、不会留零宽不可见文字。
    - 节点：label 转字符串并 strip，空 label / 空 id 的节点丢弃；shape 收敛白名单，非法→rectangle；id 去重（保留首个）。
    - 边：from/to 必须指向存活节点，否则丢弃；label 转字符串，空则 None。
    """
    seen_ids: set[str] = set()
    nodes = []
    for n in spec.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        nid = n.get("id")
        nid = str(nid).strip() if nid is not None else ""
        label = n.get("label")
        label = str(label).strip() if label is not None else ""
        if not nid or not label or nid in seen_ids:
            continue
        seen_ids.add(nid)
        shape = n.get("shape")
        nodes.append({
            "id": nid,
            "label": label,
            "shape": shape if shape in _VALID_SHAPES else "rectangle",
        })

    edges = []
    for e in spec.get("edges") or []:
        if not isinstance(e, dict):
            continue
        f = e.get("from")
        t = e.get("to")
        f = str(f).strip() if f is not None else ""
        t = str(t).strip() if t is not None else ""
        if f not in seen_ids or t not in seen_ids:
            continue
        lbl = e.get("label")
        lbl = str(lbl).strip() if lbl is not None else ""
        edges.append({"from": f, "to": t, "label": lbl or None})

    out: dict = {"nodes": nodes, "edges": edges}
    if spec.get("title") is not None:
        out["title"] = spec.get("title")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="图图 AI 生成画板 / 流程图（→ 可在画板(Beta)打开的 .tutu.json）")
    ap.add_argument("--prompt", required=True, help="要画的内容描述（≤5000 字），如「用户注册登录流程」")
    ap.add_argument("--out", default=None,
                    help="输出文件路径（默认当前目录 <title>.tutu.json）")
    ap.add_argument("--api-key", default=None,
                    help="API Key（优先于 TUTU_API_KEY 环境变量）")
    args = ap.parse_args()

    prompt = (args.prompt or "").strip()
    if not prompt:
        sys.exit("❌ --prompt 不能为空")
    if len(prompt) > 5000:
        sys.exit(f"❌ prompt 过长（{len(prompt)} 字），上限 5000 字")

    api_key = resolve_api_key(args.api_key)

    print("📤 提交图解生成任务…", file=sys.stderr)
    data = post("/diagram", {"prompt": prompt}, api_key)

    spec = data.get("spec")
    if not isinstance(spec, dict):
        sys.exit(f"❌ 后端未返回 spec：{json.dumps(data, ensure_ascii=False)[:300]}")

    # 客户端兜底消毒（即便 spec 绕过后端归一化也不崩、不写坏文件）
    spec = _normalize_spec(spec)

    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    if not nodes:
        sys.exit("❌ 后端返回的图解没有任何节点（spec.nodes 为空），无法生成画板")

    title = spec.get("title") or prompt[:20]

    # 本地：自动布局 → 转元素 → 序列化
    laid = auto_layout(spec)
    elements = diagram_to_elements(laid)
    scene = serialize_scene(elements, _diagram_app_state())

    # 输出路径
    out_path = args.out or f"{_safe_filename(title)}.tutu.json"
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            # allow_nan=False：万一坐标出现 NaN/Infinity，立即报错而不是悄悄写出图图打不开的坏文件
            json.dump(scene, f, ensure_ascii=False, allow_nan=False)
    except (OSError, ValueError) as e:
        sys.exit(f"❌ 写文件失败：{e}")

    abs_path = os.path.abspath(out_path)
    node_count = len(nodes)
    edge_count = len(edges)

    print(
        f"\n✅ 已生成画板文件: {abs_path}（{node_count} 个节点 / {edge_count} 条连线）",
        file=sys.stderr,
    )
    print(
        "👉 在图图「画板(Beta)」里用「打开」导入这个 .tutu.json 即可继续编辑。",
        file=sys.stderr,
    )

    result = {
        "file": abs_path,
        "title": title,
        "nodeCount": node_count,
        "edgeCount": edge_count,
        "spec": spec,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
