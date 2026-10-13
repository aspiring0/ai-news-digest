# 更新日志

## v0.3.9（2026-10-13）

兴趣画像 + 为我精选（自我进化闭环）

- 新增 app/profile.py：行为日志（interactions，v0.3.8 起 summary/
  bookmark/block 自动记录）→ LLM 蒸馏兴趣画像 {likes, dislikes,
  notes}（走默认引擎，提示词要求关键词具体化）；画像存本地 meta，
  可看/可手动编辑/可重置，不做黑箱
- API：GET/POST/DELETE /api/profile（读/存/重置）、
  POST /api/profile/distill（蒸馏；行为不足或无引擎返回 400 中文提示）
- 热榜个性化：/hot?personal=1 应用画像——命中 likes 关键词的故事
  +15%/词加成（上限 +60%），命中 dislikes 的直接不出现；
  热榜新增「★ 为我精选」开关（分页保留参数），无画像时给引导提示
- 设置抽屉新「兴趣画像」面板：学习按钮（蒸馏）/ 重置 / 关键词标签
  展示 / JSON 手动编辑保存
- 测试 +7（画像存取/加成过滤/空画像直通/get_hot_stories 集成/
  API 往返校验/行为不足 400/蒸馏写入与提示词行为日志入参）
- 实测：点 2 篇摘要补足行为后蒸馏出真实画像，「尹志尧/AI 泡沫」
  条目（命中 3 关键词）从普通榜第 7 名升至为我精选第 3 名

## v0.3.8（2026-10-13）

体验批次 A+B：GitHub 一键操作 / 收藏正文快照 / 自定义 RSS 源 / 屏蔽

- GitHub 条目一键操作：Trending/Releases 条目自动注入 Clone（复制
  git 命令）/ Fork（直达 fork 页）/ 部署（Vercel 一键部署链接）
- 收藏即存档：toggle_bookmark 收藏时抓正文存 bookmarks.snapshot
  （正文失败回退 RSS 摘要，存量库自动补列）；收藏页可展开"存档正文"，
  原文失效/14 天清理后仍可读
- 自定义 RSS 源：设置抽屉新面板，填名称+RSS 地址即加源（URL 去重/
  合法性校验），参与抓取轮与健康记录——看到任何社区/博客有 RSS
  就能零代码接入
- 屏蔽（不感兴趣）：条目 ✕ 按钮屏蔽（故事条目连带全部成员 URL）；
  后端 blocks 表（url/source/category 三类），热榜与时间线统一过滤，
  故事级分类屏蔽按代表条目话题判定；设置抽屉"屏蔽管理"可解除
- 行为日志底座（为下版兴趣画像）：interactions 表记录
  summary/bookmark/block 行为
- 测试 +6（快照两条/自定义源 CRUD+抓取轮+API/屏蔽过滤+解除恢复）

## v0.3.7（2026-10-13）

头条（top1）特殊处理：可读性优先

- 故事代表条目改为**中文标题优先**：多源故事里有中文成员时（如 AIHOT
  对英文新闻的中文报道），代表取中文标题中热度最高者；全英文故事回到
  最高分——解决"热榜头条是英文大字标题看不懂"的问题
- 头条内联真实摘要：top1 有摘要缓存时（点过一次 AI 解读即生成），
  lead 区直接显示"一句话核心（加粗）+ 为什么重要段落（≤160 字）"，
  按钮变为"展开完整 AI 解读"；无缓存时保持引导按钮不变
- 测试 +5：中文代表优先/全英文回退/中文内最高分/缓存内联/无缓存引导

## v0.3.6（2026-10-13）

使用体验组合：RSS 摘要兜底 / 已读未读 / 源健康 / 日报导出

- 修复摘要正文兜底缺失（真缺陷）：NewsItem 新增 summary 字段（RSS
  description 去标签/实体截 600 字）；news_items 加 summary 列（存量库
  自动 ALTER 补列，重抓同 URL 时回填）；/api/summary 把库内 RSS 摘要
  传入 summarizer——付费墙/反爬文章正文抓取失败时改用 RSS 摘要生成，
  不再直接 502
- 已读/未读（纯前端 localStorage）：未读条目标题前蓝点；点标题或
  「点开汇总」即记已读；热榜/时间线新增「只看未读」开关（与来源筛选
  可叠加）；回访时顶部「自上次到访新增 N 条」横幅
- 源健康：每轮抓取把各源 ok/fetched/error/at 写入 meta；新增
  GET /api/sources/health；utility bar 显示「源 19/19」，点击展开
  逐源状态面板（失败原因可见）
- 日报一键导出：/daily 「复制为 Markdown」（标题/链接/来源分组），
  clipboard API + execCommand 双兜底
- 测试 +5（RSS 摘要提取/入库回填/api 传参/源健康记录与健康接口）

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
