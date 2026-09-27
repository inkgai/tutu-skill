---
name: tutu-creator
description: >
  Use this skill when a user wants to create or refine images with 图图（漫画、文章配图、
  自定义图片、灵感画板图解），or asks to inspect spaces, styles, works, or generation status.
  It also guides prompt optimization and prepares poster-template and character-template
  requests for the 图图 web app. Ask only for missing decisions that materially change the
  result, preserve the user's intent, and use the current 图图 OpenAPI for API-key calls.
---

# 图图创作 Skill

图图是面向中文创作者的图像创作平台。本 skill 用 `scripts/` 里的小脚本调用
`https://tutu.inkgai.com/api/v1/openapi`，并把模糊想法整理成可执行的图像需求。
底层模型由平台路由管理；本 skill 按 GPT Image 2 兼容的提示词习惯优化请求，但不在
请求体里虚构 `model` 字段，也不声称当前生产路由一定使用某个模型。

## 先做需求整理，再调用接口

对小白先支持自然语言：用户不需要按字段填写，直接说“做什么、画什么、给谁用”即可。skill 负责抽取主体、场景、构图和限制，补默认值后用一句话回显方案，再进入扣费接口。

不要把用户一句含糊的话直接送去扣费。先判断作品类型，然后补齐会明显影响结果的字段：

1. **主体**：画什么、人物/物体数量、年龄或外观、是否需要保持角色一致。
2. **目的与受众**：公众号配图、小红书封面、漫画分镜、流程图、教学图等。
3. **场景和动作**：地点、时间、动作、情绪、前后关系。
4. **构图和尺寸**：主体位置、景别、留白、比例。常用 `3:4` 竖图、`4:3` 横图、
   `1:1` 方图，也支持 `2:3`、`3:2`、`16:9` 宽屏和 `9:16` 长屏。
5. **视觉语言**：写实/插画/水彩/国风/漫画、光线、色彩、材质、镜头感。
6. **文字**：图中是否真的要出现文字；文字必须逐字准确时，先确认短文案、位置和
   字体气质。长段文字、表格和密集小字优先放到后期排版，避免让模型生成不可读文字。
7. **参考图和限制**：最多 3 张参考图；说明每张图参考什么（角色、构图、色调），
   以及不想出现的元素。不要凭空补品牌名、日期、人物身份或版权角色细节。

### 什么时候问，什么时候直接做

- 已经给出主体、用途、画面方向和比例时，直接整理提示词并提交；不为非必填项反复追问。
- 缺少**类型**或**核心主体**时必须问：`想做漫画、文章配图、自定义图片，还是画板图解？主体是什么？`
- 缺少**用途/比例**但图片构图会受影响时只问一个合并问题：
  `这张图主要发公众号、小红书还是屏幕展示？要竖图 3:4、横图 4:3，还是方图 1:1？不确定我也可以帮你选。`
- 必须准确生成文字时问文案原文；文字不是重点时默认建议后期排版。
- 用户说“随便来一个/帮我整一个”时先澄清类型和主题，不要擅自扣积分。
- 小白没有填写比例、风格、构图时，按用途给默认值并说明；不要要求用户补齐整张表。
- 用户只说一句自然语言时，先回显“类型 / 主体 / 用途 / 比例 / 文字处理”五项，让用户一句“开始”即可继续。

整理完成后，在提交前用一句话展示关键取舍：
`我会做：4 格治愈漫画，比例 1:1，先看分镜；图中文字用字幕条。`

用户回复“开始/确认”后再提交；用户只说自然语言时，不要求先填写模板。

## 入口决策

| 用户意图 | 调用方式 |
|---|---|
| 漫画、条漫、多格分镜 | 先 `list_workspaces.py`；默认 `create_prompt.py` 生成分镜，展示给用户确认后再 `render_work.py` |
| 明确说“直接出图/不用看分镜” | `create_comic.py` 一次提交并轮询 |
| 给文章/公众号/小红书配图 | `create_article_illustration.py`；文章正文建议 300 字以上 |
| 单张海报、插画、封面、角色立绘 | `create_image.py`；需要参考图时用 `--ref` |
| 流程图、架构图、知识图、结构化图解 | `diagram.py`，生成 `.tutu.json` 后在图图画板打开编辑 |
| 查询我的空间、风格、作品、任务 | 分别用 `list_workspaces.py`、`list_styles.py`、`list_works.py`、`check_work.py` |
| 画板模板设计/海报规划/角色模板设计 | 用 `capabilities.py` 查看能力，再用 `poster_plan_request.py` 或 `template_request.py` 生成网页流程所需的结构化草稿；当前这些是登录态网页接口，API Key 不能直接调用。文章配图、单张图片和漫画都支持 1:1 / 2:3 / 3:4 / 4:3 / 3:2 / 16:9 / 9:16 |

## 漫画工作流

漫画默认走“先分镜、后生图”：

1. `list_workspaces.py` 列出空间。按用户指定名称或风格匹配；没有明确空间时列出让用户选，不要默认第一个。
2. `create_prompt.py` 只生成分镜。输出后检查每格的主体、动作、字幕/气泡、画面提示词。
3. 用户修改时，用 `update_shot.py` 改字幕、气泡或提示词，不要重新创建作品。
4. 用户确认后才 `render_work.py`。生成中用 `check_work.py` 看完整进度；不能只看到第一张就说全部完成。

默认输出：治愈/叙事类用 `split` 字幕条，趣味/对话类可用 `merged` 气泡；用户说纯画面才用
`image_only`。用户明确“直接出图”时才跳过 review。

## 灵感画板、画板模板、角色模板

### 灵感画板

“灵感画板”分两类：

- **结构化图解**（流程、节点、箭头、架构）：使用 `diagram.py`，这是当前 API Key 开放接口。
- **灵感画报/多页海报策划**：网页端会先规划页面，再生成每页作品；规划接口属于登录态
  `/v1/supertutu/inspiration-poster/plan`，当前不在 `/v1/openapi`。使用
  `poster_plan_request.py` 生成校验过的请求草稿，并把返回的网页入口给用户，不要用 API Key
  硬调不存在的开放接口。

### 画板模板设计和角色模板设计

`template_request.py` 支持 `poster` 与 `character` 两种模板，负责把名称、用途、规则、
参考图和分类整理成网页登录接口需要的 JSON，并明确下一步：

- 画板/海报模板：网页接口 `POST /v1/supertutu/feature-template/create-poster`。
- 角色模板：网页接口 `POST /v1/supertutu/feature-template/create`，需要 `categoryId`。
- 参考图解析：网页接口 `POST /v1/supertutu/feature-template/analyze-reference`。

这些接口需要浏览器登录态；脚本不会伪造 Cookie，也不会把 API Key 发送到网页接口。等后端
提供 API-key OpenAPI 版本时，只需把目标路径接入同一份 payload，skill 的需求整理规则无需改动。

## 生成后必须正确交付

- 所有异步任务都要报 `N/M` 进度，并列出**所有**已完成图片 URL。
- 文章配图完成后优先返回 `markdownContent` 成品文章，再补散图 URL。
- 部分失败：说明成功与失败数量，保留 workId，建议 `render_work.py` 重试。
- 超时：保留已有进度，不重复扣费；让用户稍后用 `check_work.py --wait` 查询。
- 参考图必须是图图 OSS（`s.inkgai.com`）地址；本地图片直接传 `--ref`，脚本会先上传。
- 不要把 API Key、Cookie 或内部响应中的敏感字段写入文件、日志或最终回复。

## API Key 和脚本约定

```bash
export TUTU_API_KEY=ak_xxxx
python scripts/create_image.py --prompt "..." --ratio 3:4
```

也可以临时传 `--api-key`；参数优先于 `TUTU_API_KEY`，脚本仍兼容旧环境变量名
`SUPERTUTU_API_KEY`。所有脚本 stdout 输出 JSON，stderr 输出进度；API Key 不会被打印。

用户问“怎么用/帮助/示例”时直接运行 `python scripts/help.py` 并转发结果。
用户想要可复制的详细指令模板时运行 `python scripts/guide.py`，或按需阅读 [`references/creation-commands.md`](references/creation-commands.md)。
需要完整参数、响应信封和计费说明时按需阅读：

- [`references/api.md`](references/api.md)
- [`references/scripts.md`](references/scripts.md)
- [`references/comic-workflow.md`](references/comic-workflow.md)
- [`README.md`](README.md)
