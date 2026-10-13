# 更新日志

## v0.3.5（2026-10-13）

故事合并：热榜按事件聚合，同一新闻多源刷屏归为一席

- 新增 app/stories.py：标题拉丁实体提取（≥3 字符、停用词/版本号过滤）
  + 48h 时间窗聚类（共享 ≥2 实体并入同一故事）；跨语言匹配依赖
  产品/公司名拉丁词，纯中文实体 v1 暂不支持（README 已注明）
- db.get_hot_stories：故事级排行/分页/每源配额（沿用 max_per_source=4，
  按代表条目来源计）；代表条目 = 故事内最高分成员，携带 _story 元数据
  （条数/来源列表/各源成员）
- 热榜热度加成：故事热度 = 成员最高 hot_score × (1 + 15%/额外来源)，
  上限 +100%；多源交叉验证的事件自然上浮
- UI：条目卡新增「⧉ N 源报道」描边徽标（悬停看来源），「各源报道(N)」
  可展开列表直达各源原文；分数 title 注明"故事热度（多源加成后）"
- 时间线/日报/分类保持条目级不变
- 测试：实体提取（中英混合/停用词/版本号）、真实 Muse 事件跨 3 源
  聚合、时间窗隔离、双实体阈值、加成公式、故事级分页与配额（9 个）

## v0.3.4（2026-10-13）

源池二批：再拆 3 个稳定上游为直接源（全部免 key），源总数 16 → 19

- 新增 fetcher：MarkTechPost / Tessl / GitHub Releases（GitHub 官方
  Atom，跟踪 openai/codex 与 anthropics/claude-code 版本发布，无需 key）
- 探测成功但稳定性不足未收录：Sierra / ARC Prize / Comfy Blog
  （探测一轮后对全部 UA 返回 404，疑似激进 IP 限流）
- 无公开 RSS 跳过：Vapi、Meshy、Artificial Analysis、Amazon Science、
  Anthropic、xAI、LangChain、Redwood、Epoch AI、Prime Intellect——
  这些内容继续经 AIHOT 兜底；按约定跳过需平台 API 的：X/Twitter
  个人号、微信公众号、YouTube、播客
- 测试：注册完整性门槛提升至 19 + 两批直接源名单断言

## v0.3.3（2026-10-13）

源池扩充：直接订阅 6 个原经 AIHOT 中转的上游源（先探 RSS 可用性再收录）

- 新增 fetcher：Ars Technica AI / Hacker News AI（hnrss >100 赞）/ OpenAI /
  Google DeepMind / IT之家（全站 feed + AI 关键词过滤，AI 分类 RSS 已 404）/
  VentureBeat AI；源总数 10 → 16
- The Decoder 探测被反爬挡（feed 路径返回 HTML），未收录，其内容仍经 AIHOT 兜底；
  Anthropic/xAI/Amazon Science 无公开 RSS，同样靠 AIHOT 中转
- 测试：fetcher 注册完整性（≥16 个、SOURCE_NAME/SCORE_CLASS/fetch 齐全且唯一）
  + IT之家 AI 关键词过滤单测

## v0.3.2（2026-10-13）

热榜打分修复（方案 D：多样性配额 + AIHOT 起步分修正）：

- 修复"新闻源进不了热榜"：原 AIHOT 静态分固定 50（RSS 不带上游分时的兜底），
  叠加时间衰减后最高只能排到第 48 名；现无上游分时按 rss 规则起步（66 起
  -2/位，下限 48），与其他新闻源同一起跑线；已有上游分时仍优先采用
- 热榜新增每源配额：get_hot(limit, max_per_source=4)，top20 每来源最多
  4 席，HuggingFace/GitHub 等高分源不再霸榜；仅影响榜单展示，不改动数据，
  时间线/日报/分类不受影响
- 测试：scorer AIHOT 规则、get_hot 配额（含 limit 放开时不丢数据）

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
