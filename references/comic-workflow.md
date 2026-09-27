# 漫画分步精修 · 风格 ID · outputMode 推导

漫画场景的深度机制。`SKILL.md` 给了路径决策的要点，做漫画分步精修、选风格、定输出形态时读本文件。

## 目录
- [分步精修完整流程](#分步精修完整流程)
- [分镜呈现模板](#分镜呈现模板)
- [用户回应解析表](#用户回应解析表)
- [关键约束](#关键约束)
- [积分账单](#积分账单)
- [风格 ID 查询](#风格-id-查询)
- [outputMode 默认推导规则](#outputmode-默认推导规则)

---

## 分步精修完整流程

这是漫画场景的**默认走法**（除非用户明确说"直接生图"）。让用户在花生图积分之前先把字幕 / 气泡看一遍，对中文创作者非常关键——LLM 经常把金句改得平淡，提前 review 能避免出图后才发现"文案不对"。

```
Step 0) （强烈推荐）先查「我的空间」
        python scripts/list_workspaces.py
        ↓ 按 name 匹配挑出 workspaceId；没空间走自定义模式

Step 1) 生成提示词（不生图，仅扣 1 积分）
        # 推荐：空间模式
        python scripts/create_prompt.py --workspace-id 42 --content "故事..." --shots 4

        # 自定义模式：默认 --output-mode split 带字幕条
        # 趣味/职场/对比/故事 风格请改 --output-mode merged
        python scripts/create_prompt.py --content "故事..." --shots 4 \
            [--style-id 12] [--output-mode split|merged]
        ↓ 拿到 workId + shots[] = [{shotId, prompt, caption, dialogue}, ...]

Step 2) 用下方「分镜呈现模板」把所有格列给用户看
        ↓

Step 3) ⏸️ 等用户回应（关键！绝不要自动 render）
        ↓

Step 4) 按用户回应分流：
        - 改单格 → update_shot.py → 回 Step 2 重新呈现该格
        - 重新生成全部 → create_prompt.py 重跑 → 回 Step 2
        - 确认满意 → Step 5
        - 终止 → 告诉用户当前 workId 可以稍后再继续
        ↓

Step 5) 生图（扣 shotCount × 2 积分）
        python scripts/render_work.py --work-id <workId>
        ↓ 默认自动轮询到完成，返回 imageUrls[]
```

## 分镜呈现模板

`create_prompt.py` 跑完后，**用以下 Markdown 格式**把所有格列给用户：

```markdown
我已经生成了 4 格分镜，请确认每格的文案：

📍 **第 1 格** （shotId: 8521）
- 字幕：今天我要做饭！
- 气泡：（无）
- 提示词：a chibi cat in a cozy kitchen, anime style, holding apron...

📍 **第 2 格** （shotId: 8522）
- 字幕：（无）
- 气泡：[猫] 怎么什么都没有！
- 提示词：cat opening fridge, surprised expression...

📍 **第 3 格** ...

---
**请告诉我**：哪几格要改？格式可以是：
- "第 2 格字幕改成 XXX"
- "第 3 格气泡换成 [猫] AAA、[狗] BBB"
- "第 1 格提示词加一句 'cinematic lighting'"
- 全部满意请说 **"开始生图"**（会扣 8 积分跑出 4 张图）
```

呈现规则：
- 字幕 / 气泡为空时显示"（无）"，不要省略整行
- 气泡多条时用 `[role] text` 格式逐条列出，role 为空就只写 text
- 提示词太长（>80 字）取前 80 字 + `...`，让用户能扫眼但不被淹没
- **每格务必带上 shotId**——下一步 update_shot 要用，用户也能引用

## 用户回应解析表

| 用户回应模式 | 解析行动 |
|---|---|
| "第 N 格字幕改成 XXX" | `update_shot.py --shot-id <N格的shotId> --caption "XXX"` |
| "第 N 格的气泡改成 [A]XXX [B]YYY" | 解析成 dialogue JSON：`[{"role":"A","text":"XXX"},{"role":"B","text":"YYY"}]`，调 `update_shot.py --dialogue '...'` |
| "第 N 格提示词加 / 改成 XXX" | 取原 prompt 拼接 / 替换后，`update_shot.py --prompt "..."` |
| "第 N 格不要字幕了 / 清空字幕" | `update_shot.py --caption ""` |
| "第 N 格清空气泡 / 不要对话" | `update_shot.py --dialogue '[]'` |
| "重新生成全部分镜 / 全部重来" | 同样参数再调 `create_prompt.py`，告诉用户 workId 变了 |
| "开始生图 / 确认 / 满意 / 没问题" | 调 `render_work.py --work-id <workId>` |
| "算了不要了 / 取消" | 终止，告诉用户当前 workId（可稍后用 `render_work` 继续）|

**多个修改可以并发**：用户同时说"第 1 格改字幕、第 3 格改气泡"时，**用一次 message 里并行执行**两个 `update_shot.py` 调用（独立 shotId 不冲突），改完后**重新呈现这两格**让用户复核。

## 关键约束

- **Step 3 必须等用户确认**——绝不要拿到 shots 后跳过 review 直接 render
- **改完后要重新呈现被改的格**——让用户看到改动生效（不需要重新列全部 4 格，只列改过的）
- **render 之前再次确认**——如果用户的"确认"措辞含糊（如"嗯"），明确反问"开始生图扣 N 积分吗？"
- **render 之后不再循环精修**——已经出图了，再改就是单格重生场景（暂未在 OpenAPI 暴露，告诉用户去前端）

## 积分账单

| 阶段 | 扣费 |
|---|---|
| Step 1 `create_prompt.py` | 1 积分 |
| Step 4 `update_shot.py` × N 次 | 0（免费） |
| Step 5 `render_work.py` | shotCount × 2 |
| **合计**（漫画 4 格） | **9 积分**，跟直接 `create_comic.py` 一样 |

精修是免费动作。分步精修对总积分**零增量**，纯赚 review 机会。

---

## 风格 ID 查询

漫画 / 配图（`--style-id`）传的是 `workspace_types.id`（自增数字 ID）。**用户说"治愈风"时，先调 `list_styles.py` 拿列表，按 `slug` 或 `name` 匹配**，再用对应 `id` 调创作脚本：

```bash
# Step 1：拿风格列表
python scripts/list_styles.py --category comic
# [{"id":12,"slug":"healing","name":"治愈漫画风",...}, ...]

# Step 2：用 id 创作
python scripts/create_comic.py --style-id 12 --content "..."
```

漫画当前已上架的风格（slug 一栏可作字符串别名匹配）：

| slug | 中文名 | `defaultLayout` | 推荐 `outputMode` | 适用场景 |
|---|---|---|---|---|
| `healing` | 治愈漫画风 | `caption` | `split` | 温柔系，情感故事，重文字共鸣 |
| `funny` | 趣味漫画风 | `bubble` | `merged` | 反差金句，搞笑段子，多人对话 |
| `workplace` | 职场漫画风 | `bubble` | `merged` | 职场对白，编辑卡通 |
| `romance` | 恋爱漫画风 | `caption` | `split` | 少女漫，温柔氛围，内心独白 |
| `contrast` | 对比漫画风 | `bubble` | `merged` | 二格对比，前后反差，吐槽 |
| `story` | 故事漫画风 | `bubble` | `merged` | 多格叙事，电影感，角色对话 |
| `parenting` | 育儿漫画风 | `bubble` | `merged` | 亲子日常，温暖治愈，对话感 |
| `webtoon` | 条漫风 | `caption` | `split` | 竖版长漫，画面+旁白 |
| `sketchy` | 手绘 Sketchy | `bubble` | `merged` | 手绘墨水+水彩，对白感 |

> 上表会随后端上下架变化，**以 `list_styles.py` 实际返回为准**。`defaultLayout` 字段直接从后端 `workspace_types.default_layout` 透出，是 v2 接口（`f9ba1eb` 之后）才有。

---

## outputMode 默认推导规则

**漫画场景下，用户没明确说想要什么形态时**（绝大多数情况），按以下优先级推 `outputMode`：

```
1. 用户明确说"纯画面/不要文字/no text"            → image_only
2. 用户明确说"图上字下/字幕/旁白"                 → split
3. 用户明确说"气泡/对话/对白"                     → merged
4. 用户明确说"字幕+气泡都要/又要旁白又要对话"     → split_with_bubble
5. 用户给了 styleTypeId 或风格名 → 按风格 defaultLayout 推：
     caption → split
     bubble  → merged
     none    → image_only
     null    → split（兜底，因为 95% 的风格都期望有文字 review）
6. 用户没给风格也没给输出形态                     → split（让 LLM 至少生成字幕给用户 review）
```

**为什么默认不是 image_only**：`image_only`（纯画面）下 LLM **不生成** caption / dialogue —— 分步精修阶段用户就**没东西可 review**。治愈类故事的金句、对比类的吐槽气泡才是漫画的灵魂，必须先让 LLM 产出来交给用户审稿。只有用户明确表达"我不要任何文字、就要画面"才走 `image_only`。

**实际操作**：调 `create_prompt.py` 时务必带上 `--output-mode`（脚本默认已是 `split`，但自定义风格时要按 defaultLayout 微调）：

```bash
# Step A：用户说要"治愈风" → 查列表确定 styleTypeId + defaultLayout
python scripts/list_styles.py --category comic
# [{"id":12, "slug":"healing", "name":"治愈漫画风", "defaultLayout":"caption", ...}, ...]

# Step B：按 defaultLayout 推 outputMode（caption→split）
python scripts/create_prompt.py --content "..." --shots 4 --style-id 12 --output-mode split
```

也可以让 Claude 自己用上面的风格 slug 表直接选 outputMode，跳过 list_styles 调用——但**线上风格定义可能变**，长期还是建议先 list 一次拿权威值。

**用户明确想要纯画面的情形**：
- "不要任何文字/字幕/气泡" → `--output-mode image_only`
- "纯画面就行/no text/不要文字" → `--output-mode image_only`
- "我不要 review 文案" → 跳过分步精修走 `create_comic.py` 一把梭（不要 review 时分步精修就没意义了）
