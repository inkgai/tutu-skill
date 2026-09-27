# 图图 Open Platform API Reference

完整的对外 API 参考文档。SKILL.md 偏 Claude 使用视角；本文档偏「我自己写代码调用」视角，
列每个端点的完整签名、参数、响应、错误。

## 鉴权

所有接口仅接受 API Key 认证。在 HTTP Header 携带：

```
X-API-KEY: ak_xxxxxxxxxxxx
Content-Type: application/json
```

API Key 在 <https://sso.inkgai.com/home/apikey> 获取。

## Base URL

```
https://tutu.inkgai.com/api/v1/openapi
```

本地联调时（前端 dev + 后端 jar 跑起来）替换为：

```
http://localhost:10001/api/v1/openapi
```

## 响应信封

所有响应都用同一份信封结构：

```json
{
  "code":    200,
  "message": "成功",
  "data":    { ... }
}
```

- `code == 200` 表示业务成功，`data` 字段为实际载荷
- 其他 code 表示失败，`message` / `errorMessage` 透传给用户

## HTTP 状态码 + 业务 code

| HTTP | 业务 code | 含义 |
|---|---|---|
| 200 | 200 | 成功 |
| 200 | 非 200 | 业务错误（看 `message`） |
| 401 | 401 | API Key 缺失 / 无效 / 过期 |
| 400 | 40001 | 请求体校验失败（@Valid / @Pattern / @Size） |
| 404 | 40403 | 资源 / 路由不存在 |
| 500 | 50000+ | 服务端错误（已脱敏） |

---

## 端点目录

| 分类 | 端点 | 用途 |
|---|---|---|
| 创作 | `POST /comic` | 漫画生成（自动 LLM + 图像，全程异步） |
| 创作 | `POST /article-illustration` | 文章配图（≥300 字文章 → 4-10 张图） |
| 创作 | `POST /image` | 自定义生图（无 LLM，prompt → 图最快；支持 ≤3 张参考图） |
| 素材 | `POST /upload-reference` | 上传参考图到图图 OSS（multipart），返回 URL 供 `/image` 的 `referenceImageUrls` 用 |
| 创作 | `POST /prompt` | 仅生成分镜提示词，不生图（精修流程入口） |
| 创作 | `POST /diagram` | 生成结构化图解（流程图 / 架构图）—— 返回 nodes + edges 中间表示 |
| 精修 | `PATCH /shot/{shotId}/caption` | 修改单格字幕（split / split_with_bubble 生效） |
| 精修 | `PATCH /shot/{shotId}/dialogue` | 修改单格气泡台词（merged / split_with_bubble 生效） |
| 精修 | `PUT /shot/{shotId}/prompt` | 修改单格图像提示词（不消耗积分） |
| 精修 | `POST /work/{workId}/render` | 续接生图（用当前最新分镜状态触发渲染） |
| 查询 | `GET /work/{workId}` | 查询单个作品状态（轮询用） |
| 查询 | `GET /works` | 分页查询作品列表 |
| 查询 | `GET /styles` | 查询可用风格列表（按大类） |
| 查询 | `GET /workspaces` | **查询当前用户的工作空间列表（漫画创作首选）** |

---

## 创作接口

### `POST /comic` — 漫画生成

LLM 自动生成各格分镜提示词，完成后**自动续接图像生成**，全程一次调用搞定。

**请求体**：
```json
{
  "content":     "故事文案（必填，≤5000 字）",
  "workspaceId": 42,
  "title":       "标题（可选，留空 AI 自动生成）",
  "shotCount":   4,
  "aspectRatio": "1:1",
  "styleTypeId": 12,
  "outputMode":  "split"
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `content` | string | ✓ | — | 故事文案，1-5000 字 |
| `workspaceId` | long | | null | **强烈推荐**！传了之后下面 `aspectRatio` / `styleTypeId` / `outputMode` 一概被忽略，参数从空间锁定值读取。用 `GET /workspaces` 查询 |
| `title` | string | | "" | 留空时 LLM 自动生成 |
| `shotCount` | int | | 4 | 分镜格数 1-8 |
| `aspectRatio` | string | | `1:1` | `1:1` / `3:4` / `4:3` / `16:9` / `9:16`（自定义模式生效）|
| `styleTypeId` | long | | null | 风格 ID（用 `GET /styles` 查询；自定义模式生效）|
| `outputMode` | string | | `image_only` | 见下表（自定义模式生效）|

**outputMode 可选值**：

| 值 | 效果 |
|---|---|
| `image_only` | 纯画面，不带任何文字 / 气泡 |
| `split` | 画面 + 字幕条（图下贴近原文一行） |
| `merged` | 气泡对话（角色头顶气泡） |
| `split_with_bubble` | 字幕 + 气泡同时（长漫场景） |

**响应 data**：`SkillWorkStatusResponse`（shots 字段此时为 null，需轮询 `GET /work/{workId}` 拿结果）

**积分**：1（提示词）+ shotCount × 2（生图） = 4 格漫画 9 积分

---

### `POST /article-illustration` — 文章配图

根据文章内容，AI 自动选取关键段落生成 4-10 张配图。

**请求体**：
```json
{
  "articleContent":      "文章正文（必填，≥300 字，≤5000 字）",
  "imageCount":          4,
  "workspaceId":         42,
  "illustrationStyleId": null,
  "illustrationStyle":   "warm_illustration",
  "aspectRatio":         "2:3",
  "generationMode":      "pure_image",
  "characterId":         null,
  "referenceImageUrls":  []
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `articleContent` | string | ✓ | — | 文章正文，**≥300 字**，≤5000 字 |
| `imageCount` | int | ✓ | — | 配图数量 1-10 |
| `workspaceId` | long | △ | null | **空间创作**：传了之后 `illustrationStyle(Id)` / `aspectRatio` / `generationMode` / 角色一概从空间锁定值读取（覆盖请求里对应字段）；`articleContent` / `imageCount` / 参考图仍取请求值。用 `GET /workspaces` 查 `scene=article` 的空间 |
| `illustrationStyleId` | long | △ | — | 三选一：风格 ID |
| `illustrationStyle` | string | △ | — | 三选一：风格 key（见下表） |
| `aspectRatio` | string | | `2:3` | **支持 `1:1` / `3:4` / `4:3` / `2:3` / `3:2` / `16:9` / `9:16`**；`2:3` 小红书/公众号竖图，`16:9` 横屏，`9:16` 长屏 |

| `generationMode` | string | | `pure_image` | `pure_image` / `text_blend` |
| `characterId` | long | | null | 角色模板 ID（跨张保持角色一致） |
| `referenceImageUrls` | string[] | | [] | 风格参考图，最多 3 张 |

`workspaceId`、`illustrationStyleId`、`illustrationStyle` 三选一（传了 `workspaceId` 时它优先，风格从空间读取）。

**illustrationStyle 可选值**：

| key | 中文 |
|---|---|
| `workplace` | 职场 / 商务 |
| `warm_illustration` | 温暖 / 治愈 |
| `rednote` | 小红书 |
| `infographic` | 知识图 / 信息图 |
| `humor` | 幽默 / 搞笑 |
| `narrative` | 故事 / 叙事 |
| `literary` | 文艺 / 文学 |
| `cute` | 可爱 / Q 版 |

**响应 data**：`SkillWorkStatusResponse`（轮询拿结果）

**积分**：1（提示词）+ imageCount × 2（生图）

---

### `POST /image` — 自定义生图

直接 prompt → 图，**无 LLM 阶段，速度最快**。异步队列执行，返回 workId 后轮询取结果。

**请求体**：
```json
{
  "prompt":      "图像描述（必填，≤2000 字符，英文效果更佳）",
  "title":       "标题（可选，≤100 字）",
  "aspectRatio": "1:1",
  "seed":        "12345",
  "referenceImageUrls": ["https://s.inkgai.com/uploads/xxx.png"]
}
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `prompt` | string | ✓ | — | ≤2000 字符。底层模型对英文 prompt 敏感 |
| `title` | string | | prompt 前 20 字 | 可选，≤100 字；留空时取 prompt 前缀 |
| `aspectRatio` | string | | `1:1` | **推荐 `3:4`（竖图）/ `1:1`（方图）/ `4:3`（横图）；也支持 `2:3` / `3:2`** |
| `seed` | string | | null | 固定随机种子（复现同画面） |
| `referenceImageUrls` | string[] | | [] | 参考图 URL，**最多 3 张**；**必须是图图 OSS 域名（`s.inkgai.com`）的 URL**——本地图先走 `POST /upload-reference` 换取。外部 URL 会被 400 拒绝（「参考图链接无效，请重新上传」） |

**响应 data**：`SkillWorkStatusResponse`，**结果在 `coverImageUrl`，`shots` 为 null**。
轮询 `GET /work/{workId}` 直到 `completed` / `failed`。

**积分**：2 / 次，**失败自动退**。

---

### `POST /upload-reference` — 上传参考图

把本地图片上传到图图 OSS，返回的 `url` 直接填入 `POST /image` 的 `referenceImageUrls`。

**请求**：`multipart/form-data`（**不是** JSON；Content-Type 需带 multipart boundary），鉴权同样走 `X-API-KEY` 头。

| 表单字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `image` | file | ✓ | **≤5MB**，仅 `image/*`（jpg / jpeg / png / gif / webp） |

**响应 data**：
```json
{
  "url":      "https://s.inkgai.com/uploads/xxx.png",
  "fileName": "xxx.png",
  "size":     123456
}
```

**积分**：0（上传本身不扣积分）。

---

### `POST /prompt` — 仅生成分镜提示词

跟 `/comic` 同样的 LLM 阶段，**但不续接图像生成**。适合分步精修流程的入口。

**请求体**：
```json
{
  "content":     "故事文案（必填，≤5000 字）",
  "workspaceId": 42,
  "title":       "标题（可选）",
  "shotCount":   4,
  "styleTypeId": null,
  "outputMode":  "split"
}
```

字段大致同 `/comic`，**不接受** `aspectRatio`（图像阶段才用）。
`workspaceId` 同 `/comic`，传了之后 `styleTypeId` / `outputMode` 被忽略。

⚠️ **`outputMode` 在 prompt 阶段就生效** —— 决定 LLM 是否生成 caption / dialogue：

| outputMode | LLM 行为 |
|---|---|
| `image_only`（默认）| 不生成字幕，不生成气泡。**分步精修阶段没东西可让用户 review** |
| `split` | 生成 caption（画面+字幕）|
| `merged` | 生成 dialogue（气泡对话）|
| `split_with_bubble` | 同时生成 caption + dialogue |

分步精修场景务必按所选风格的 `defaultLayout` 推 outputMode：caption → `split`，bubble → `merged`。

**响应 data**：`SkillWorkStatusResponse`。
轮询到 `shots[].status === "ready"` 表示提示词已生成，`shots[].prompt` / `caption` / `dialogue` 即可用。

**积分**：1

---

### `POST /diagram` — 生成结构化图解（流程图 / 架构图）

一句话 → 结构化图解的**中间表示**（`spec`：title + nodes + edges，**不含坐标**）。
**同步返回**，不进异步队列、不需要轮询。

客户端（如 `scripts/diagram.py`）拿到 `spec` 后，本地自动布局 + 转成白板元素，
产出可在图图「画板(Beta)」打开编辑的 `.tutu.json` 文件。

**请求体**：
```json
{ "prompt": "用户注册登录流程" }
```

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `prompt` | string | ✓ | — | 要画的内容描述，1-5000 字 |

**响应 data**：
```json
{
  "spec": {
    "title": "用户注册登录流程",
    "nodes": [
      { "id": "start",  "label": "开始",        "shape": "ellipse" },
      { "id": "input",  "label": "输入手机号",   "shape": "rectangle" },
      { "id": "check",  "label": "验证码正确吗", "shape": "diamond" }
    ],
    "edges": [
      { "from": "start", "to": "input" },
      { "from": "check", "to": "input", "label": "错误" }
    ]
  }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `spec.title` | string | 图解标题 |
| `spec.nodes[].id` | string | 节点唯一 id（edges 用它引用） |
| `spec.nodes[].label` | string | 节点文字 |
| `spec.nodes[].shape` | string | `rectangle`（流程步骤）/ `ellipse`（开始/结束）/ `diamond`（判断分支） |
| `spec.edges[].from` | string | 起点节点 id |
| `spec.edges[].to` | string | 终点节点 id |
| `spec.edges[].label` | string? | 连线标注（可选，如「是」/「否」/「正确」） |

**说明**：spec 是与白板渲染解耦的中间表示，不含坐标 —— 布局由客户端本地完成
（参考 `scripts/diagram.py` 移植自前端 `whiteboard/engine/autoLayout.ts` 的分层布局）。

**积分**：1

---

## 分镜精修接口

精修接口允许在生图前修改单个分镜的内容。改完后调 `POST /work/{workId}/render` 跑生图。

所有精修接口都做越权校验（`shot.userId == 当前 API Key 用户`），不存在或不属于当前用户都返回
`NOT_EXIST` 不暴露存在性。**精修动作本身不消耗积分**。

### `PATCH /shot/{shotId}/caption` — 修改字幕

**路径参数**：`shotId` — 分镜 ID，从 `work.shots[].shotId` 拿。

**请求体**：
```json
{ "caption": "新字幕文案（≤500 字，空串=清空）" }
```

**响应 data**（`ShotCaptionVO`）：
```json
{
  "id":        12345,
  "shotIndex": 0,
  "caption":   "新字幕文案",
  "updatedAt": "2026-05-17T10:23:00"
}
```

**生效模式**：`outputMode = split` 或 `split_with_bubble`。其他模式下 caption 不会被注入图像 prompt。

---

### `PATCH /shot/{shotId}/dialogue` — 修改气泡对话

**路径参数**：`shotId`

**请求体**：
```json
{
  "dialogue": [
    {
      "role":      "猫咪",
      "text":      "我饿了！",
      "type":      "speech",
      "direction": "右"
    }
  ]
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `role` | 选填 | 说话人；独白 / 旁白可省略 |
| `text` | ✓ | 台词文本，≤200 字 |
| `type` | 选填 | `speech`（默认气泡）/ `caption`（旁白矩形框） |
| `direction` | 选填 | `左` / `右` / `上` / `下`（气泡尾巴方向） |

- 空数组 `[]` 或 `null` 视为清空所有台词
- 最多 20 条

**响应 data**（`ShotDialogueVO`）：
```json
{
  "id":        12345,
  "shotIndex": 0,
  "dialogue": [ {"role":"猫咪","text":"我饿了！","type":"speech","direction":"右"} ],
  "updatedAt": "2026-05-17T10:23:00"
}
```

**生效模式**：`outputMode = merged` 或 `split_with_bubble`。

---

### `PUT /shot/{shotId}/prompt` — 修改图像提示词

**路径参数**：`shotId`

**请求体**：
```json
{ "finalPrompt": "覆盖 LLM 提示词的新文本" }
```

**响应 data**：`true`（boolean）。

**生效**：下一次单格重生或 `POST /work/{workId}/render` 时用新 prompt。

---

### `POST /work/{workId}/render` — 续接生图

把当前 work 下所有 `READY` / `FAILED` 状态的分镜批量送进图像生成队列。
**不重新走 LLM，不丢精修内容**。

**路径参数**：`workId`

**查询参数**：

| 字段 | 必填 | 说明 |
|---|---|---|
| `seed` | 选填 | 固定随机种子，多格保持画风一致 |

**响应 data**：`SkillWorkStatusResponse`（触发后的最新 work + shots 状态）。需要继续轮询
`GET /work/{workId}` 直到 `status=completed`。

**常见错误**：
- `没有可生成的分镜` — work 下所有 shot 不在 READY/FAILED 状态（可能正在生成或已完成）
- `服务繁忙` — 图像服务熔断器打开或容量已满
- `积分不足` — 检查余额，最少 `shotCount × 2` 积分

**积分**：READY/FAILED 分镜数 × 2

---

## 查询接口

### `GET /work/{workId}` — 查询单个作品状态

**路径参数**：`workId`

**响应 data**（`SkillWorkStatusResponse`）：
```json
{
  "workId":       "uuid",
  "status":       "generating",
  "coverImageUrl": null,
  "errorMessage": null,
  "markdownContent": null,
  "shots": [
    {
      "shotId":       12345,
      "shotIndex":    0,
      "status":       "completed",
      "imageUrl":     "https://...",
      "prompt":       "a cat in kitchen, anime style...",
      "caption":      "今天我要做饭！",
      "dialogue": [
        {"role":"猫","text":"喵","type":"speech","direction":"右"}
      ],
      "errorMessage": null
    }
  ]
}
```

| 字段 | 说明 |
|---|---|
| `status` | `generating` / `completed` / `failed` |
| `coverImageUrl` | `custom_image` 类型的结果在这里；`comic` / `article_illustration` 此字段为 null |
| `errorMessage` | 仅 `status=failed` 时有值，已脱敏 |
| `markdownContent` | **仅 `article_illustration`（文章配图）**：图已嵌入正文的成品 Markdown（最终交付物，可直接整篇复制/发布）。`comic`/`custom_image` 为 null；未完成时为 null，`completed` 后才有值 |
| `shots[].status` | `generating` / `ready` / `completed` / `failed` |
| `shots[].imageUrl` | `completed` 后才有值 |
| `shots[].prompt` | `ready` 后即有值（LLM 已写完图像 prompt） |
| `shots[].caption` | LLM 生成的字幕（可用精修接口覆盖） |
| `shots[].dialogue` | LLM 生成的气泡台词数组（可用精修接口覆盖） |
| `shots[].errorMessage` | 单格失败原因，仅 `status=failed` 时有值 |

**轮询建议**：每 4-6 秒一次，`completed` / `failed` 时停止。漫画/自定义生图通常 30s-2 分钟，
文章配图通常 1-5 分钟。

---

### `GET /works` — 分页查询作品列表

**查询参数**：

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `page` | | 1 | 页码，从 1 开始 |
| `pageSize` | | 10 | 每页 1-50 |
| `type` | | (全部) | `comic` / `article_illustration` / `custom_image` |

**响应 data**（`SkillWorkListResponse`）：
```json
{
  "total":    100,
  "current":  1,
  "pageSize": 10,
  "records": [
    {
      "workId":        "uuid",
      "title":         "猫咪厨神",
      "type":          "comic",
      "status":        "completed",
      "coverImageUrl": "https://...",
      "createdAt":     "2026-05-01T10:00:00"
    }
  ]
}
```

---

### `GET /workspaces` — 查询「我的空间」列表

**漫画创作的首选入口**。当前 API Key 所属用户的全部工作空间，按 `updated_at` 倒序。

无查询参数（按 API Key 自动定位用户）。

**响应 data**：`List<SkillWorkspaceVO>`。

```json
[
  {
    "id":              42,
    "name":            "治愈系小红书",
    "description":     "锁定治愈风 + 3:4 + 字幕",
    "scene":           "comic",
    "workType":        "COMIC",
    "typeId":          12,
    "aspectRatio":     "3:4",
    "outputMode":      "split",
    "shotCount":       4,
    "whitespaceRatio": 85,
    "updatedAt":       "2026-05-15T10:00:00"
  }
]
```

| 字段 | 说明 |
|---|---|
| `id` | 创作接口传 `workspaceId` 用这个数字 |
| `name` | 空间名称（用户自取），客户端可做 fuzzy 匹配 |
| `description` | 空间简介，可空 |
| `scene` | `comic` / `article` / `cover` / ... |
| `workType` | `COMIC` / `ARTICLE_ILLUSTRATION` / ... |
| `typeId` | 该空间绑定的风格类型 ID（对应 `workspace_types.id`）|
| `aspectRatio` | 默认画面比例 |
| `outputMode` | 默认输出模式（`split` / `merged` / `split_with_bubble` / `image_only`）|
| `shotCount` | 默认分镜数（漫画场景）|
| `whitespaceRatio` | 留白比例（50-95），可空 |
| `updatedAt` | 最后更新时间，列表按此倒序 |

**为什么推荐用空间创作**：空间锁定了一套完整创作参数（风格 / 比例 / 输出模式 / 分镜数 / 留白），
一次配好长期复用，比每次裸创作（传 `styleTypeId` + `outputMode` 等独立参数）稳定得多。

**空数组**意味着用户还没建过空间。建议引导用户去前端 <https://tutu.inkgai.com/workspace>
建一个，或临时走自定义创作。

---

### `GET /styles` — 查询可用风格列表

用于"风格发现"——拿到列表后客户端可让用户挑、或按 `slug` / `name` 做 fuzzy 匹配挑出 ID。

**查询参数**：

| 字段 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `category` | | `comic` | `comic` / `article_illustration` |

**响应 data**：`List<SkillStyleVO>`，按 `sort_order` 升序，只返回已上架且当前用户可见的风格。

```json
[
  {
    "id":                     12,
    "slug":                   "healing",
    "name":                   "治愈漫画风",
    "emoji":                  "🌿",
    "styleLabel":             "温柔系",
    "tagline":                "...",
    "recommendedAspectRatio": "1:1",
    "defaultLayout":          "caption"
  }
]
```

| 字段 | 说明 |
|---|---|
| `id` | 风格 ID，创作接口传 `styleTypeId` 用 |
| `slug` | 字符串别名（同 category 内唯一），客户端可做 fuzzy 匹配 |
| `name` | 中文风格名 |
| `emoji` | 风格 emoji（前端 chip 用） |
| `styleLabel` | 风格副标（如「反差金句型」） |
| `tagline` | 一句话描述 |
| `recommendedAspectRatio` | 推荐画面比例 |
| `defaultLayout` | 默认输出形态，映射到创作接口的 `outputMode`：`caption` → `split` / `bubble` → `merged` / `none` → `image_only` / `null` → 未设置（客户端自决） |

---

## 数据结构

### `SkillWorkStatusResponse`

工作状态响应。所有创作接口的初始响应 + `GET /work/{workId}` 都返回这个结构。

```typescript
{
  workId:        string;
  status:        "generating" | "completed" | "failed";
  coverImageUrl: string | null;     // 仅 custom_image 有
  errorMessage:  string | null;     // 仅 status=failed 时有值，已脱敏
  markdownContent: string | null;   // 仅 article_illustration：图已嵌入正文的成品 Markdown（completed 后才有）
  shots:         ShotResult[] | null;
}
```

### `ShotResult`

```typescript
{
  shotId:       number;
  shotIndex:    number;
  status:       "generating" | "ready" | "completed" | "failed";
  imageUrl:     string | null;
  prompt:       string | null;     // LLM 生成的图像 prompt
  caption:      string | null;     // 字幕文案
  dialogue:     DialogueItem[];    // 气泡台词数组
  errorMessage: string | null;     // 仅 status=failed 时有值，已脱敏
}
```

### `DialogueItem`

```typescript
{
  role:      string | null;        // 说话人
  text:      string;               // 台词文本，≤200 字
  type:      "speech" | "caption"; // speech=圆形气泡（默认）/ caption=旁白矩形框
  direction: "左" | "右" | "上" | "下" | null;  // 气泡尾巴方向
}
```

### `SkillStyleVO` / `SkillWorkListResponse`

见上文对应章节。

---

## 异步轮询模型

所有创作接口（`/comic` / `/article-illustration` / `/image` / `/prompt`）+ `/work/{workId}/render`
都是异步的：返回 `workId` 后任务进入队列，客户端需要轮询 `GET /work/{workId}` 直到完成。

```
1. POST /comic                       → workId
2. loop (interval 4-6s):
     GET /work/{workId}
     if status == "completed": done
     if status == "failed":    handle + show errorMessage
     else:                     continue
```

参考 `scripts/_client.py` 的 `poll_until_done()` 实现：
- 前 3 次 4s 间隔（赶快任务）
- 之后 6s 退避（多数任务 30s+，省一半请求）
- 连续 3 次查询异常自动停止
- 超时时**返回当前部分进度**而不是丢数据

---

## 并发与积分

### 并发限制

每个用户最多同时 **3 个 work 在生成中**。超过返回：

```json
{ "code": 50001, "message": "当前已有 3 个作品在生成中，请等待完成后再提交（上限 3 个）" }
```

### 积分扣费规则

| 动作 | 积分 |
|---|---|
| LLM 提示词生成（`/comic` / `/article-illustration` / `/prompt`） | **1** |
| 每张图像生成 | **2** |
| 自定义生图（`/image`） | **2**（失败自动退） |
| 上传参考图（`/upload-reference`） | **0**（免费） |
| 结构化图解（`/diagram`） | **1** |
| 修改 caption / dialogue / prompt | **0**（免费） |

漫画 4 格典型：1（LLM）+ 4 × 2（生图）= **9 积分**。

### 创作门槛

发起新作品（含 `/comic`、`/article-illustration`、`/image`、`/prompt`）需要账户余额
≥ **10 积分**。不足时返回：

```json
{ "code": 50003, "message": "积分不足，至少需要 10 积分才能创作。当前剩余 X 积分，请先充值。" }
```

`/work/{workId}/render` 续接生图**不受此门槛限制**（已是存量 work 的二次操作）。

---

## 失败 / 错误响应示例

```json
// API Key 缺失 / 无效
{ "code": 401, "message": "未授权", "errorMessage": "缺少必要的认证参数" }

// 校验失败
{ "code": 40001, "message": "请求参数错误", "errorMessage": "故事内容不能为空" }

// 资源不存在 / 越权
{ "code": 40404, "message": "资源不存在", "errorMessage": "作品不存在或无权访问" }

// 业务错误
{ "code": 50000, "message": "操作失败", "errorMessage": "图像服务暂时不可用，请稍后重试" }
```

错误消息已经过 `ErrorMessageSanitizer.stripBrandNames` 脱敏，剥除底层模型名 / 渠道域名等内部细节，
可直接透传给用户展示。

---

## 变更记录

| 日期 | 变更 |
|---|---|
| 2026-07-07 | `POST /image` 升级：新增 `referenceImageUrls`（≤3 张，仅图图 OSS URL）；`aspectRatio` 支持 `3:4` / `4:3` / `1:1` / `2:3` / `3:2` / `16:9` / `9:16`；计费 2 积分/次、失败自动退 |
| 2026-07-07 | 新增 `POST /upload-reference` 端点（multipart 字段 `image`，≤5MB 仅 image/*，返回 `{url, fileName, size}`） |
| 2026-06-30 | 新增 `POST /diagram` 端点（结构化图解：流程图 / 架构图，返回 nodes + edges 中间表示，本地布局成可在「画板(Beta)」打开的 `.tutu.json`） |
| 2026-05-17 | 新增 `GET /workspaces` 端点（"我的空间"查询，漫画创作首选） |
| 2026-05-17 | `POST /comic` / `POST /prompt` 接受 `workspaceId` 参数（空间创作，参数从空间锁定值读取） |
| 2026-05-17 | `POST /prompt` 接受 `outputMode` 参数（分步精修场景必备，否则 LLM 不生成 caption/dialogue） |
| 2026-05-17 | `GET /styles` 响应加 `defaultLayout` 字段（`caption` / `bubble` / `none` / null）|
| 2026-05-17 | 新增 `POST /work/{workId}/render` 续接生图端点 |
| 2026-05-17 | 新增 `PATCH /shot/{shotId}/caption` / `PATCH /shot/{shotId}/dialogue` / `PUT /shot/{shotId}/prompt` 分镜精修端点 |
| 2026-05-17 | `GET /work/{workId}` 响应加 `shotId` / `dialogue` / `errorMessage` 字段 |
| 2026-06-08 | `GET /work/{workId}` 响应加 `markdownContent` 字段（文章配图专属：图已嵌入正文的成品 Markdown，最终交付物） |
| 2026-06-08 | `POST /article-illustration` 接受 `workspaceId` 参数（空间创作：风格/比例/生图模式/角色从空间锁定值服务端解析，与 `/comic` 对齐） |
| 2026-05-17 | 新增 `GET /styles` 风格发现端点 |
| 2026-05-17 | `POST /comic` 接受 `outputMode` 参数 |
| 2026-05-03 | 初版 |

---

## 网页登录态功能（不属于 API Key OpenAPI）

下面这些页面功能需要浏览器登录态，当前不能用 `X-API-KEY` 直接调用：

- 灵感画报规划：`POST https://tutu.inkgai.com/v1/supertutu/inspiration-poster/plan`
- 画板/海报模板：`POST https://tutu.inkgai.com/v1/supertutu/feature-template/create-poster`
- 角色模板：`POST https://tutu.inkgai.com/v1/supertutu/feature-template/create`
- 参考图解析：`POST https://tutu.inkgai.com/v1/supertutu/feature-template/analyze-reference`

`poster_plan_request.py` 和 `template_request.py` 会校验字段并输出这些接口需要的 JSON 草稿；不要把它们改成向登录态接口发送 API Key。
