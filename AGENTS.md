# AGENTS.md — 给 AI agent 看的部署说明

> 你是一个负责部署的 AI agent。读完本文件，按"启动"和"验证"两步执行即可。
> 人类部署文档见 [DEPLOY.md](DEPLOY.md)；配置项说明见 [.env.example](.env.example)。

## 项目一句话

自托管 AI 资讯聚合站：定时抓取 30 个 AI 信息源（10 个基础源 + 20 个直接上游：9 个从 AIHOT 拆出 + 拆上游续批 10 个——6 个平台 RSS + 4 个无 RSS 厂商 HTML 抓取），按"时间衰减热度"排热榜，点击新闻弹出 AI 摘要（用户自己填模型 key）。

## 技术栈

Python 3.11+ / FastAPI / SQLite（单文件 `data/news.db`）/ APScheduler（定时抓取跑在**同一进程**内，无需 cron）/ Jinja2 / trafilatura（正文提取）

## 目录结构

- `app/main.py` —— FastAPI 入口：页面路由 + API（含 `/api/health` 健康检查）
- `app/fetchers/` —— 信息源抓取器，每个源一个模块，统一 `fetch() -> list[NewsItem]`
- `app/fetch_all.py` —— 一轮抓取的编排（各源抓取→打分→入库→14 天清理）
- `app/db.py` —— SQLite 存取：按 URL 去重、热榜/时间线查询、摘要缓存、收藏、provider 设置
- `app/scorer.py` —— 静态分 + 时间衰减 `hot_score = score × 0.5^(age_hours/48)`
- `app/summarizer.py` —— 摘要链路：抓正文 → 调用户自配模型 → 按 URL 缓存
- `app/providers.py` —— 模型 provider 管理（内置 provider 接口地址强制官方域名白名单）
- `app/classifier.py` —— 主题分类关键词规则（集中一处，改分类只改这里）
- `app/scheduler.py` —— APScheduler 定时任务（默认每 4 小时）
- `templates/` —— Jinja2 页面模板
- `start.sh` / `start.bat` —— 一键启动脚本（主推部署方式）
- `DEPLOY.md` —— 人类部署文档；`CHANGELOG.md` —— 更新日志

## 启动

```bash
./start.sh
# Windows: 双击 start.bat
```

脚本会：检查 Python 3.11+ → 校验配置（非法直接中文报错退出）→ 创建/复用 `.venv` → 安装依赖 → 启动 `uvicorn`。
无 `.env` 时用默认配置（端口 8000）并打印提示。

## 验证

```bash
curl http://localhost:8000/api/health
```

期望返回类似：

```json
{"ok": true, "version": "0.4.0", "news_count": 164, "last_fetch": "2026-10-13T07:26:09+00:00"}
```

- `news_count` 为 0：首次抓取还没完成（约几十秒），等一两分钟再查
- `last_fetch` 为 null：抓取尚未成功跑完一轮，检查日志
- 页面：`/hot` 热榜、`/timeline` 时间线、`/github` GitHub 生态、`/settings` 设置页

## 常见坑

1. **端口被占用**：改 `.env` 的 `PORT` 后重启（启动脚本会校验 PORT 合法性）
2. **单个源抓取失败不影响整轮**：日志里 `[某某] 抓取失败` 是正常的，下一轮自动重试；只有**所有**源都失败才需要查网络/代理
3. **摘要功能需要用户在设置页自己填模型 key**；key 只存本机 SQLite，不要外发 `data/` 目录
4. **首次启动页面可能为空**：首抓在后台线程跑（服务立即可访问），等日志 `首次抓取完成`（或设置页源健康面板变绿）再刷新
5. **不要调小抓取间隔**：默认 4 小时；1 小时以内容易被源站限流
6. Windows 部署用全英文路径，避免中文/空格路径
