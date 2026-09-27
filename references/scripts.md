# 脚本参数详解

每个脚本的完整命令行参数。`SKILL.md` 的「脚本清单」给了一行速览，需要具体参数时读本文件对应小节。

所有脚本都支持 `--api-key ak_xxx`（或 `TUTU_API_KEY` 环境变量，参数优先）。

## 目录
- [list_workspaces.py — 查询「我的空间」](#list_workspacespy)
- [create_comic.py — 漫画生成](#create_comicpy)
- [create_article_illustration.py — 文章配图](#create_article_illustrationpy)
- [create_image.py — 自定义生图](#create_imagepy)
- [diagram.py — 生成画板 / 流程图](#diagrampy)
- [create_prompt.py — 仅生成提示词](#create_promptpy)
- [list_works.py — 查询作品](#list_workspy)
- [list_styles.py — 查询风格](#list_stylespy)
- [update_shot.py — 精修单格分镜](#update_shotpy)
- [render_work.py — 续接生图](#render_workpy)

---

## list_workspaces.py
查询「我的空间」（漫画首选）

```
--api-key       API Key
```
无其他参数。返回当前 API Key 所属用户的全部工作空间，按更新时间倒序。**漫画创作的第一步永远是这个**，按 name 匹配挑空间。

## create_comic.py
漫画生成（一把梭，跳过分步精修）

```
--content       故事文案（必填，≤5000 字）
--workspace-id  工作空间 ID（强烈推荐！锁定所有参数，长期复用更稳定）；指定后下面 4 项被忽略
--title         标题（可选，留空 AI 自动生成）
--shots         格数 1-8，默认 4
--ratio         画面比例，默认 1:1（仅自定义模式生效）
--style-id      风格 ID（用 list_styles.py 查询；仅自定义模式生效）
--output-mode   输出模式（默认 split 带字幕条；仅自定义模式生效）：
                  image_only         纯画面，无文字（不推荐——分步精修无内容可 review）
                  split              画面 + 字幕条（默认）
                  merged             气泡对话（角色头顶气泡）
                  split_with_bubble  字幕 + 气泡同时出（长漫场景）
--api-key       API Key
```

## create_article_illustration.py
文章配图

```
--content       文章正文（必填，≥300 字，≤5000 字）
--count         生成张数 1-10，默认 4
--workspace-id  工作空间 ID（空间创作；传了之后 风格/比例/生图模式/角色 由空间锁定，
                覆盖下面 --style/--ratio/--mode；先用 list_workspaces.py 查 scene=article 的空间）
--style         风格 key（默认 warm_illustration；用 --workspace-id 时由空间决定）
                workplace / warm_illustration / rednote / infographic /
                humor / narrative / literary / cute
--style-id      风格 ID（指定后覆盖 --style）
--ratio         画面比例 1:1 / 3:4 / 4:3 / 2:3 / 3:2，默认 2:3 竖图（用 --workspace-id 时由空间决定）
--mode          pure_image（默认）/ text_blend（用 --workspace-id 时由空间决定）
--character-id  角色模板 ID（可选，跨张保持角色一致）
--ref-image     风格参考图 URL，可重复，最多 3 张
--api-key       API Key
```

**空间创作**：跟漫画一样推荐——先 `list_workspaces.py` 查 `scene=article` 的空间，按 name 模糊匹配挑出 id，再 `create_article_illustration.py --workspace-id <id> --content "..."`。风格 / 比例 / 生图模式 / 角色一次配好长期复用，比每次裸传 `--style` 稳。

**输出**：`{workId, title, imageUrls[], markdownContent, status}`。`markdownContent` 是图已按位置嵌入正文的成品文章（图文交付物），`completed` 后有值——**优先把它整篇给用户**（可直接发公众号/小红书），散图 URL 作为补充。

**风格 key 映射**（用户中文 → `--style` 值）：

| 用户说 | --style |
|---|---|
| 职场 / 商务 / 工作 | `workplace` |
| 温暖 / 治愈 / 插画 | `warm_illustration` |
| 小红书 / 红薯 | `rednote` |
| 知识 / 信息图 / 图解 | `infographic` |
| 幽默 / 搞笑 | `humor` |
| 故事 / 叙事 | `narrative` |
| 文艺 / 文学 | `literary` |
| 可爱 / Q 版 | `cute` |

## create_image.py
自定义生图（支持参考图）

```
--prompt    图像描述（必填，≤2000 字符，英文效果更佳）
--title     标题（可选，≤100 字）
--ratio     画面比例：3:4 竖图 / 1:1 方图 / 4:3 横图 / 2:3 竖图 / 3:2 横图（默认 1:1）
--ref       参考图，可重复，最多 3 张：
              本地文件路径 → 自动先调 /upload-reference 上传到图图 OSS（≤5MB，
                            仅 jpg/jpeg/png/gif/webp，上传前本地先校验）
              http(s) URL  → 直接透传；必须是图图 OSS 域名（s.inkgai.com）的 URL，
                            外部 URL 会被后端 400 拒绝
--seed      随机种子（可选，复现同画面用）
--api-key   API Key
```

示例：
```bash
# 用本地草图当参考
python create_image.py --prompt "把这张草图变成水彩插画" --ref ./sketch.png
# 混用本地文件 + 已上传的 OSS URL（最多 3 张）
python create_image.py --prompt "融合两图风格" --ref ./a.jpg --ref https://s.inkgai.com/uploads/b.png
```

**计费**：2 积分/次，失败自动退；上传参考图免费。
**⚠️ 注意**：结果在 `imageUrl`（单张），不在 `imageUrls[]`。

## diagram.py
生成画板 / 流程图 / 架构图 / 图解

```
--prompt    要画的内容描述（必填，≤5000 字），如「用户注册登录流程」「微服务架构」
--out       输出文件路径（可选，默认当前目录 <title>.tutu.json）
--api-key   API Key
```

一句话生成一张可在图图「画板(Beta)」里继续编辑的流程图。脚本：① 调 `POST /diagram` 拿结构化图解 `spec`（title + nodes + edges，不含坐标）→ ② **本地**自动布局（分层自顶向下）→ ③ **本地**转成白板元素（黑色手绘描边 + 居中文字 + 绑定箭头）→ ④ 写出 `.tutu.json` 文件。

**交付**：产物是一个 `.tutu.json` 文件（路径在输出 `file` 字段），用户在「画板(Beta)」点「打开」导入即可手绘 / 调整 / 导出。脚本同时把结构化 `spec` 打到 stdout，供其它 AI 直接复用结构。

shape 支持 `rectangle`（流程步骤）/ `ellipse`（开始/结束节点）/ `diamond`（判断分支）；边可带 label（如「是」「否」「正确」）。**积分：1**（生成结构化图解，本地布局/转换不另收费）。

## create_prompt.py
仅生成提示词（分步精修入口）

```
--content       故事文案（必填，≤5000 字）
--workspace-id  工作空间 ID（强烈推荐！锁定所有参数，长期复用更稳定）；指定后下面 3 项被忽略
--title         标题（可选）
--shots         格数 1-8，默认 4
--style-id      风格 ID（仅自定义模式生效）
--output-mode   输出模式（默认 split 带字幕条；仅自定义模式生效）
--api-key       API Key
```

适合：拿提示词去别处生图 / 先看分镜再决定要不要生图。所有 shots 到 `ready` 状态即终止，比走完整生图省时省积分。

**默认 `--output-mode=split`** 让 LLM 必生成 caption 供 review。自定义模式下，按风格 defaultLayout 微调：caption 类保持 split，bubble 类（趣味 / 职场等）改 `merged`。详见 [comic-workflow.md](./comic-workflow.md) 的 outputMode 推导规则。

## list_works.py
查询作品

```
--page        页码（默认 1）
--page-size   每页 1-50，默认 10
--type        comic / article_illustration / custom_image（可选过滤）
--api-key     API Key
```

## list_styles.py
查询可用风格

```
--category    comic（默认）/ article_illustration
--api-key     API Key
```

## update_shot.py
精修单格分镜（分步精修流程中用；免费）

```
--shot-id    分镜 ID（必填；从 work.shots[].shotId 拿）
--caption    新字幕文案（≤500 字，空串=清空）；split / split_with_bubble 模式生效
--dialogue   气泡对话 JSON 数组字符串；空数组 []=清空台词
--prompt     新图像提示词（覆盖 LLM 生成版本，不消耗积分）
--api-key    API Key
```

至少传 `--caption` / `--dialogue` / `--prompt` 中的一个；可同时传多个。**任一字段失败不影响其他字段** —— 脚本是「逐字段独立提交」，最后输出 `updates` 数组告诉你哪些字段成功了。

`dialogue` JSON 结构（每条最多 200 字，最多 20 条）：
```json
[
  { "role": "猫咪", "text": "我饿了！", "type": "speech", "direction": "右" }
]
```
- `role`（选填）：说话人；独白 / 旁白可省略
- `text`（必填）：台词文本
- `type`（选填）：`speech`（默认，圆形气泡）/ `caption`（旁白矩形框）
- `direction`（选填）：`左` / `右` / `上` / `下` —— 气泡尾巴指向

## render_work.py
续接生图（精修完成后触发图像）

```
--work-id    作品 ID（必填；从 create_prompt.py 输出拿）
--seed       随机种子（可选，多格画风一致用）
--no-wait    只触发不轮询，立即返回
--api-key    API Key
```

把当前 work 下所有 READY/FAILED 分镜批量送进图像生成队列。**不重新走 LLM、不丢精修**。内部走标准生图链路（积分预扣 + 熔断 / 容量校验 + 新队列入队）。默认轮询到 completed/failed/timeout，加 `--no-wait` 时只触发不等。

## `capabilities.py` — 能力边界

```bash
python3 scripts/capabilities.py
python3 scripts/capabilities.py --check-live
```

默认离线输出开放平台和网页登录态能力；`--check-live` 只读取 `/styles`、`/workspaces`，不会创建作品。

## `poster_plan_request.py` — 灵感画报规划 payload

```bash
python3 scripts/poster_plan_request.py --prompt "主题、受众、页间关系、视觉方向" --page-count 3 --ratio 3:4
```

只生成网页登录接口的请求草稿，不发送请求。

## `template_request.py` — 画板/角色模板 payload

```bash
python3 scripts/template_request.py --type poster --name "健康科普卡片" --content "顶部标题，中央主视觉，底部行动建议" --aspect-ratio 3:4
python3 scripts/template_request.py --type character --name "讲师" --category-id 12 --content "短发、圆框眼镜、浅色针织衫，半身正面"
```

只生成网页登录接口的请求草稿；角色模板需要 `--category-id`。
