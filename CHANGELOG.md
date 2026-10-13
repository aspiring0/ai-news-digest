# 更新日志

## v0.3.1（2026-10-13）

安全修复与名实对齐（外部代码审查驱动）：

- 修复设置页存储型 XSS：provider id 后端强校验 `^[A-Za-z0-9_-]{1,64}$`；模板 onclick 改用 `|tojson` 渲染 id/name，消除内联 JS 字符串逃逸（此前含引号的 id/name 经浏览器实体解码后可逃逸 `saveProvider(...)` 的 JS 字符串）
- Gemini 内置 provider 改走官方 OpenAI 兼容端点 `/v1beta/openai/chat/completions`（此前拼 `/chat/completions` 恒 404，裸域名 base_url 自动补全前缀）；Anthropic 官方无 OpenAI 兼容端点，从内置列表移除（请走「自定义」填中转地址）
- 补上 v0.3.0 承诺的 CI 与测试：GitHub Actions（Python 3.11/3.12 矩阵）+ pytest（健康检查/六页面/收藏链路/scorer/classifier/provider 安全规则，零网络）
- 修复 docker-compose 在 `.env` 改 PORT 后端口映射错位的问题（容器内固定监听 8000）

## v0.3.0（2026-10-13）

工程化收尾，目标是"开箱即用、别人也能装起来"：

- 一键启动脚本：`start.sh`（Linux/macOS）、`start.bat`（Windows），自动检查 Python 3.11+、创建虚拟环境、安装依赖、启动服务
- 启动时配置校验：PORT 非数字、数据目录不可写等非法配置直接中文报错退出，不静默带病运行
- 健康检查端点 `GET /api/health`（版本/库内条数/上次抓取时间），部署验证用
- `pyproject.toml`（PEP 621），`requirements.txt` 保留兼容
- GitHub Actions CI：Python 3.11/3.12 冒烟测试
- `DEPLOY.md` 部署文档（含开机自启、常见问题）、`AGENTS.md`（给 AI agent 看的部署说明）
- 部署主推 Python 直连；Dockerfile/docker-compose 保留为可选方案

## v0.2.0（2026-10-13）

- 摘要弹窗：点击新闻弹出四段式中文摘要（核心一句/说人话/关键细节），trafilatura→readability 抓正文，按 URL 缓存，有"重新生成"
- 收藏：⭐ 开关 + 收藏页（按收藏时间倒序）
- 日报视图：今日 top 20 按主题分组；主题分类视图（6 类关键词规则）
- 设置页：7 家内置模型 + 自定义 provider，一键测试连接，设默认解读引擎
- 安全加固：内置 provider 接口地址强制官方域名白名单；改已保存的接口地址必须重输 key
- 修复：Starlette 1.x `TemplateResponse` 签名变更导致全站 500；GitHub Trending 链接解析漏抓

## v0.1.0（2026-10-13）

- 首个可用版本：10 个信息源抓取入库（AIHOT/TLDR AI/Superhuman/Rundown/量子位/TechCrunch AI/The Batch/HuggingFace/ProductHunt/GitHub Trending），按 URL 去重，保留 14 天
- 热榜：静态分 + 时间衰减 `hot_score = score × 0.5^(age_hours/48)`（48 小时半衰）
- 热榜 / 时间线两个页面；APScheduler 每 4 小时自动抓取；SQLite 单文件
- 机器之心（RSS 下线）、智东西（无公开 RSS）暂跳过
