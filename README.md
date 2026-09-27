# 图图创作 Skill

这个仓库把图图的图像创作能力封装为一个可被 agent 调用的 skill：先把中文想法整理成清晰的图像需求，再调用图图开放平台生成漫画、文章配图、单张图片或结构化图解。

## 安装

要求 Python 3.9+ 和 `requests`：

```bash
python3 -m pip install requests
export TUTU_API_KEY=ak_xxxx
```

API Key 从 [图图 API Key 页面](https://sso.inkgai.com/home/apikey) 获取。也可以给每个脚本传 `--api-key`。密钥不要写入仓库、脚本或日志。

## 常用示例

```bash
# 单张图片；比例支持 3:4、4:3、1:1、2:3、3:2、16:9、9:16
python3 scripts/create_image.py --prompt "春日窗边读书的女孩，柔和自然光，留出标题区" --ratio 3:4

# 文章配图（当前 OpenAPI 支持 1:1 / 2:3 / 3:4 / 4:3 / 3:2）
python3 scripts/create_article_illustration.py --content "这里放 300 字以上文章正文" --count 4 --ratio 4:3

# 漫画：先查空间，再生成分镜
python3 scripts/list_workspaces.py
python3 scripts/create_prompt.py --content "一只猫学会做饭的四格故事" --shot-count 4
python3 scripts/render_work.py --work-id WORK_ID

# 结构化灵感画板：输出 .tutu.json，可在图图画板导入编辑
python3 scripts/diagram.py --prompt "画一张从选题到发布的内容生产流程图"

# 查看开放能力与网页登录能力边界（不联网）
python3 scripts/capabilities.py

# 灵感画报/画板模板/角色模板：生成网页登录 payload，不会把 API Key 发给网页登录接口
python3 scripts/poster_plan_request.py --prompt "三页小红书健康科普海报，第一页提出问题，第二页解释原因，第三页给出行动建议" --page-count 3 --ratio 3:4
python3 scripts/template_request.py --type character --name "温柔的科普讲师" --category-id 12 --content "短发、圆框眼镜、浅色针织衫，亲和、可靠，半身正面立绘"
```

所有创作接口是异步的。脚本 stdout 输出 JSON，stderr 输出进度。查询作品时使用：

```bash
python3 scripts/check_work.py --work-id WORK_ID
python3 scripts/check_work.py --work-id WORK_ID --wait
```

## 功能边界

当前 API Key 开放平台地址为 `https://tutu.inkgai.com/api/v1/openapi`，已开放：

- 漫画 `/comic`
- 文章配图 `/article-illustration`
- 单张图片 `/image`
- 参考图上传 `/upload-reference`
- 分镜提示词和精修 `/prompt`、`/shot/*`、`/work/*/render`
- 结构化灵感画板 `/diagram`
- 空间、风格、作品查询

灵感画报多页策划、画板模板设计、角色模板设计目前是网页登录态接口。skill 已提供需求引导、参数校验和结构化 payload 草稿，并给出网页入口；它不会把 API Key 当作网页登录 Cookie，也不会伪造登录态。如果后端后续开放对应 API-key 路由，只需替换脚本的 transport，提示词规则和 payload 可直接复用。

## 参考文档

- [SKILL.md](SKILL.md)：agent 工作流、需求提问和调用决策
- [references/api.md](references/api.md)：OpenAPI 请求、响应、错误和计费
- [references/scripts.md](references/scripts.md)：脚本参数
- [references/comic-workflow.md](references/comic-workflow.md)：漫画分步精修
