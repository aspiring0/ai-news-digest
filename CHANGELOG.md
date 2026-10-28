# 更新日志

## v0.4.4（2026-10-16）

体验补全版本：processing_status（条目/来源双态）、中文搜索修复、arXiv 论文流、源健康告警、文档全面校准。

功能：processing_status（清单 B 批，UI 五项最后一项）

- **为什么**：对照用户真实前端规格（App.tsx），条目与来源需要"整理中"
  中间态——英文条目入库后、中文翻译完成前，用户应看到明确的处理状态。
- **做了什么**：
  - **B1 条目级**：`_row_to_dict` 响应层实时计算（落点①，零 schema 变更）
    ——英文标题且未翻译的条目带 `processing_status: "pending"`，翻译完成
    自动消失；热榜/时间线等条目渲染「⏳ 整理中」徽标。arXiv 论文按设计
    保持英文，不构成 pending。
  - **B2 来源级**：`/api/sources/health` 升级 v2 结构——对象数组
    `{key, name, state, item_count, detail}`，state ∈ failed（本轮抓取
    失败）/ processing（已入库、中文整理中）/ connected；健康面板重写为
    三态（指示条：N 个失败 / M 个整理中 / 全部已响应；processing 行显示
    "· 整理中"）。meta 原始结构不变——agent 工具与连续异常告警直接读
    meta，不受改版影响。
- **测试**：+4（pending 判定四形态 / 热榜徽标渲染 / v2 三态与结构完整 /
  0 条 detail）；模板契约测试更新为 v2 锚点（转义契约保留）。

修复：中文搜索失效（C1）

- **为什么**：FTS5 默认 unicode61 分词器把整段连续中文当一个 token，子串
  查询（"翻译"匹配"…翻译功能…"）在 FTS 路径上本就基本搜不到；且 FTS 未
  索引 title_cn——翻译覆盖率上来后中文标题反而搜不到。
- **做了什么**：含 CJK 的查询改走 LIKE 子串路径（title/title_cn/summary
  三列，`%_\` 转义，ASCII 大小写不敏感），按热度排序；纯英文查询保持
  FTS 短语+前缀路径不变。零 schema 变更，当前万级行量级性能足够。

功能：源健康连续异常告警（B1）

- **为什么**：单源失败只记日志 + 健康面板显示，无人盯就发现不了持续劣化
  （HF 重置、VB 429、Anthropic 结构不稳都属此类）。
- **做了什么**：每轮抓取后统计各源连续异常轮数（ok=False 或 ok-但-0-条，
  即健康面板黄 ⚠ 那类），连续 **3 轮**触发**一次**告警（每个异常期只报
  一次，恢复自动清零）；计数持久化在 meta 表，重启不清零。出口：推送
  渠道已启用则推送（复用现有渠道配置），未启用降级 WARNING 日志
  （/api/logs 可见）。
- **测试**：+9（中文标题/翻译标题/摘要/特殊字符/英文 FTS 回归 ×5；
  阈值单次告警/零条计数/恢复清零/run_once 接线 ×4）。

功能：arXiv 论文流接入（源 30 → 31）

- **为什么**：学术一手动态此前缺失；arXiv RSS 曾整日返回空快照（接入时已恢复，
  2026-10-15 三分类实测 1353/301/486 条）。
- **做了什么**：`arxiv.py` 单 fetcher 拉 cs.AI/cs.CL/cs.LG 三分类各 15 条（crosslist
  按 URL 去重、剥标题 arXiv ID 后缀）；新增 `paper` 打分类 **(55, -2, 下限 45)**——
  论文是"新"但非"热榜事件"，刻意低于新闻源避免挤占新闻位；**翻译配额排除论文源**
  （60 条/轮的预算不被 ~45 条/日的论文标题吃掉，论文保持英文展示）；空快照按既有
  语义静默（源健康 ok+0 条标黄），连续两轮 0 条人工复查。
- **测试**：+5（三分类契约 / crosslist 去重+后缀剥离 / paper 打分 / 翻译排除 /
  注册表 31 源）。

## v0.4.3（2026-10-15）

安全与加固大版本：全面工程审计后修复 P0/P1/P2 全部事项，信息源 20→30，新增 GitHub 生态页。

### 安全修复

- **SSRF 防护（P0-1）**：`/api/summary` 任意 URL 抓取（含内网、读取回显）+ 任意缓存删除——双层修复：端点仅站内条目（资讯库 ∪ 收藏）+ 抓取层 urlguard（scheme 白名单、IP 字面量与 DNS 解析拒绝私网/保留段、IPv6 嵌入通道复判、重定向逐跳校验 ≤3 跳）；自定义 RSS 源添加同校验；`ALLOW_PRIVATE_FETCH=1` 内网源逃生门。
- **provider 存量 key 外发（P1-1）**：`/api/providers/models` 异址 + 空 key 曾会把已存 key 发往任意域名——回退收紧为同址才生效。
- **XSS**：源健康面板动态值转义（P1-2d）；Agent 聊天组件 safeHref 单点收口 URL scheme、session_id 服务端白名单、画像 likes 重构为 textContent+addEventListener（P1-2a-c，feature/agent 批）。
- 依赖安全：CI 加 pip-audit（宽松模式）；本地实测无已知漏洞。

### 稳定性（P0-2 / P2）

- Agent 流式端点改线程池桥接——LLM 调用（最坏 ~170s）不再阻塞整个事件循环（曾经全站停摆）。
- SQLite 三件套：WAL + busy_timeout=5000 + 连接确定性关闭（并发写不再 database is locked）。
- push 配置损坏回退默认（原返回 None 致 500/每轮异常）；首抓挪后台线程（服务就绪不等抓取）；确认流 10 分钟 TTL + 完整参数展示 + bookmark 切换语义明示。

### 功能

- **拆上游续批：信息源 20 → 30**：+6 平台 RSS（Google Research / Microsoft Research / Azure AI / Mistral / NVIDIA / MIT News AI）+ 4 无 RSS 厂商 HTML 抓取（Anthropic / Meta AI / xAI / Cohere，新增 parse_link_page 通用管线）；`lab` 打分类；聚合器保留并行（编辑信号 + 无 RSS 厂商兜底通道）。
- **GitHub 生态独立页**：`/github` + `/api/github`（Trending / Releases / Star 飙升三源热度混排）。
- P3 清理：入库失败日志、30 天摘要缓存过期清理、健康面板三态（ok 但 0 条标黄）、翻译回写按 URL 精确定位。

### 已知事项

- GitHub Actions 因账户计费锁暂停（非代码问题），CI 与 Release 自动构建待账户恢复；Windows exe 可本地 PyInstaller 构建。
- HuggingFace 源连接重置、VentureBeat 间歇 429（网络侧）；Anthropic 源页面结构不稳，观察期。
- 后期补源：arXiv（RSS 已恢复，接入方案设计中）、HuggingFace Daily Papers、Stanford HAI。

### 测试

- 97 → **209** 用例（+112）：urlguard 判定表全分支、逐跳重定向、端点允许列表、Agent 门槛、30 源注册表、启动后台化、P2/P3 全项。

## v0.4.3 前的开发批次记录（原"未发布"节，按时间序）

P3 清理（审计 P3 批）

- **为什么**：① insert_items 吞异常完全静默——坏行只留下 skipped+1，
  排错靠猜（此前测试排错已实际踩坑）；② summary_cache 只增不减，
  条目 14 天清理后缓存成孤儿永久留存；③ 健康面板对"ok 但 0 条"的源
  显示绿色 ✓，源失败被内部捕获后返回空列表的问题被掩盖；④ 批量翻译
  回写按 title 定位，同标题不同 URL 的多行会被误伤。
- **做了什么**：
  - db：insert_items 的 except 分支保留 skipped 计数，同时记
    `logger.warning("入库失败跳过 url=%s: %s")`（db.py 补同名 logger
    `ai-news-oss`，与其他模块统一日志出口）；新增
    `clear_stale_summaries(days=30)` 按 created_at 清理过期摘要缓存，
    run_once 在 14 天清理之后调用并记日志（30 天而非 14 天——书签页
    的过期条目仍可能命中旧缓存）。
  - 健康面板三态：`!ok` 红 ✗ / `ok 且 fetched>0` 绿 ✓ N 条 /
    `ok 且 0 条` 黄 ⚠ 0 条（复用现有 `--amber-text` 变量，深浅色主题
    都有定义）；动态值仍全部经 escH 转义。
  - 翻译回写按 url：SELECT 构建 title→url 映射，UPDATE 改
    `WHERE url=?`（title_cn 为空的守卫保留），映射缺失跳过；
    `_call_llm_translate` 协议不变，pending 顺带去重。
- **测试**：+5（入库失败日志 / 缓存旧删新留 / run_once 接线 / 健康面板
  ⚠ 契约 / 同标题仅映射行更新）。204 → 209 passed。
  备注：入库失败日志用"缺 score 键"的行触发 try 内 KeyError——
  INSERT OR IGNORE 会把 NOT NULL 违例也吞掉（走 rowcount=0 跳过路径，
  不进 except），缺 fetched_at 的行触发不了该分支。

功能：GitHub 生态独立页

- **为什么**：GitHub 类内容（Trending / Releases / Star 飙升）此前混排在
  热榜/时间线里，想专看仓库动态要靠来源筛选；独立入口 + API 更直接。
- **做了什么**：`GET /github` 页面（复用 `_item.html`，GitHub 条目的
  Clone/Fork 快捷操作自动生效）+ `GET /api/github`（与时间线同构的
  `{items, total, page, total_pages}`）；三源按 hot_score 倒序，屏蔽项
  过滤与收藏标记语义与其他页面一致；导航新增 GitHub 入口。零数据结构
  变更（纯查询层视图）。元数据扩展（star 数/语言等）明确不做——需要
  schema 改动，等真有需要再走完整流程。
- **测试**：+4（三源过滤+排序 / 屏蔽过滤 / 页面渲染 / 分页超界）。

加固（审计 P2 批）

- **为什么**：① push 配置损坏时 `get_config` 返回 None（`__defaults__` 误用，
  审计已动态验证：`/api/push` 500、每轮推送 AttributeError 被吞）；② SQLite
  无 busy_timeout/WAL、连接靠 GC 回收——调度线程与请求线程并发写有
  database is locked 风险；③ DEPLOY.md systemd 示例 `--host 0.0.0.0` 与同页
  安全警示自相矛盾；④ 依赖 CVE 无闭环（审计标注"未验证"）。
- **做了什么**：
  - push：损坏 JSON 回退 `DEFAULT_CONFIG` 副本（channel=off），端点与
    notify_round 均不再炸。
  - SQLite 三件套：`_connect` 改造为 contextmanager（busy_timeout=5000、
    with 退出确定性 close、异常 rollback），init_db 一次性 WAL（库级持久）；
    ~50 处调用点零改动。`.gitignore` 补 `*.db-wal`/`*.db-shm`。
  - DEPLOY.md：systemd 示例改 `127.0.0.1` + 注释说明何时才该 0.0.0.0。
  - CI：新增 pip-audit 步骤（宽松模式——不加 `--strict`，版本时间线较新，
    查不到的版本不阻断，只拦实锤漏洞）。
- **测试**：+7（损坏回退 ×3、busy_timeout/close/WAL/异常回滚 ×4）。

功能：拆上游续批——信息源 20 → 30

- **为什么**：延续"从聚合器拆直接上游"的既定方向（v0.3.3/v0.3.4 已从
  AIHOT 拆出 9 个）：实验室/厂商动态此前依赖 newsletter 转手，拆出一手源
  后零延迟入库；聚合器（TLDR/Rundown/TheBatch 等）保留并行——既保编辑
  信号，也是 Anthropic/Meta/xAI 这类无 RSS 厂商的兜底通道。
- **做了什么**：
  - +6 平台 RSS 直连：Google Research / Microsoft Research / Azure AI /
    Mistral / NVIDIA / MIT News AI（2026-10-15 全部探测通过，limit 15-25）。
  - +4 无 RSS 厂商 HTML 抓取：Anthropic / Meta AI / xAI / Cohere。新增
    `base.parse_link_page()` 通用管线，每条规则都来自实测踩坑：尾斜杠
    归一（Meta 绝对 URL）、aria-label 优先+剥 Read 前缀（Meta 标题）、
    同 URL 多锚点取最长可用标题（卡片/CTA 重复）、粘连清洗用词首断言
    而非 \b（"ProgramAnnouncements" 间无词边界）、CTA 词表+slug 兜底
    （Learn More）、页面 200 但 0 命中抛 RuntimeError 进健康面板
    （Anthropic 两次探测结构不一致，列观察期重点）。
  - scorer 新增 `lab` 类（68 起 -2/位，下限 50）：一手发布高于媒体 RSS、
    低于 HF 榜单。
  - 首抓挪后台线程：30 源顺序抓取最坏数分钟，不再阻塞服务就绪（审计
    P2 启动阻塞，增源后放大，顺手先修）。
- **后期补（既定方向，网络恢复后）**：arXiv（RSS 返回昨日空快照，48h
  后重试）、HuggingFace Daily Papers（连接重置）、Stanford HAI（锚点无
  条目）、Google blog 主站（与 Research 重叠暂缓）。
- **代价（明示）**：每轮 +150~250 条，翻译批次（60 条/轮）会常态积压；
  NVIDIA 混合内容靠分类器归桶。收录源跑两轮看源健康面板，不稳的一行
  摘除（Sierra 教训）。
- **测试**：+19（parse_link_page 全分支 ×6、RSS/HTML 源契约 ×10+parametrize、
  lab 打分、注册表 30 源完整性、启动就绪不等待首抓）。

安全修复：SSRF 防护（审计 P0-1）

- **为什么**：`GET /api/summary?url=<任意>` 会让服务端抓取任意 URL（含内网/环回/
  云元数据地址），正文经 LLM 摘要后回显给调用方，构成读取型 SSRF；
  `regenerate=1` 还能无条件删除任意 URL 的摘要缓存。无鉴权 + 局域网/公网
  暴露场景下可被直接利用；默认 127.0.0.1 部署下也可被恶意网页盲打。
- **做了什么**（双层防护，新增 `app/urlguard.py`）：
  - 端点层：`/api/summary` 仅接受站内条目（资讯库 ∪ 收藏），未知 URL 返回 400；
    `regenerate` 的缓存删除移到校验之后。明确不把 `summary_cache` 计入允许列表，
    防止升级前缓存的内网读取内容经旧缓存重新外泄。
  - 抓取层：正文抓取改走 `_safe_get`——scheme 白名单、IP 字面量与 DNS 解析
    结果拒绝私网/环回/链路本地/保留/组播网段（显式网段表，不随 stdlib 语义漂移），
    IPv6 嵌入式 v4 通道（mapped/NAT64/compatible）提取内层复判；重定向改为手动
    逐跳跟随（≤3 跳）每跳重新校验，封死"公网 302→内网"绕过。被拒走既有
    RSS 摘要兜底语义，不新增用户可见错误。
  - 自定义 RSS 源：添加时过同一校验（无鉴权下"加源→下轮即抓"是盲 SSRF 原语）；
    域名解析失败同样拒绝。内置 20 源为受信代码常量，不经此校验。
- **兼容性**：新增环境变量 `ALLOW_PRIVATE_FETCH`（默认 `0`）——内网 RSS 源用户的
  逃生门，仅放开地址类别判定，格式门永远生效；源码方式写在 `.env`，pip/exe
  安装设系统环境变量。行为变化面：对不在库内/收藏的 URL 求摘要、添加解析到
  内网的源，这两类请求从此被拒（前者此前无任何 UI 入口）。
- **测试**：+70 用例（urlguard 判定表全分支 / 逐跳重定向 / 端点允许列表 /
  custom-sources 校验），保持零网络原则（DNS 与 HTTP 全 mock）。

安全修复：provider 存量 key 外发（审计 P1-1）

- **为什么**：`POST /api/providers/models` 传 `custom-*` id + 任意 `base_url`
  + 空 `api_key`，后端会回退使用已保存的 key 并以 Bearer 发往该任意域名——
  绕过了 save_provider"修改接口地址必须重输 key"的既有防护；局域网/公网
  暴露场景下可直接窃取付费 API key（默认本机部署下浏览器恶意页面发不出
  JSON POST，受 CORS 预检阻拦）。
- **做了什么**：`list_models` 的存量 key 回退收紧为"接口地址与已保存值完全
  一致"才生效（与 save_provider 的比较语义对齐）；地址不一致且未传 key 时
  直接返回错误，不发起任何 HTTP 请求。`test_connection` 本就无回退逻辑，
  补一条防漂移回归测试锁住"不读存量 key"的语义。同址"一键获取模型"的
  既有 UX（含 custom provider）不受影响。
- **测试**：+4 用例（异址拒发且零请求 / custom 同址回退 / 自带 key 异址放行 /
  test_connection 不触存储）。

安全修复：Agent 门槛批（审计 P0-2 / P1-2a-c / P1-3，feature/agent 分支）

- **为什么**：① `/api/chat/stream` 在事件循环线程上跑同步 Agent 生成器，
  单次 LLM 调用最坏 ~170 秒，期间全站（页面/健康检查/其他会话）停摆；
  ② 聊天组件三处 XSS 残留——LLM 输出的 markdown 链接不过滤 URL scheme
  （`javascript:` 可执行）、客户端自报的 session_id 与画像 likes 关键词未
  转义直接进 innerHTML（无鉴权 API 均可写入，构成存储型 XSS）；
  ③ 确认流工程缺口——pending 确认无过期、确认条参数截断 50 字符与实际
  执行参数不一致、bookmark 切换语义不向用户明示。
- **做了什么**：
  - 流式端点改 `iterate_in_threadpool` 桥接，阻塞迭代挪到工作线程，
    SSE 输出格式不变（测试断言生成器线程 ≠ 事件循环线程）。
  - 两个 chat 端点对 session_id 校验 `^[A-Za-z0-9_-]{1,64}$`，不合法
    静默当新会话；前端 data-sid 兜底转义（兼容存量脏数据）。
  - 新增 `safeHref`（仅 http(s)/协议相对/站内相对可进 href，其余降级 #），
    单点收口 mdToHtml 链接、sources 两处、摘要弹窗原文链接；
    建议 chips 重构为 textContent + addEventListener（废除内联 onclick 拼接）。
  - `_pending_actions` 带 10 分钟 TTL；确认条完整展示执行参数；
    bookmark 确认文案按当前状态明示「收藏/取消收藏」，工具 schema 标注切换语义。
  - conftest clean_db 补清 bookmarks/chat_messages（toggle 语义对初始状态
    敏感，此前跨用例状态泄漏导致测试误报）。
- **边界声明**：确认流是 UX 机制而非安全边界（无鉴权模型下写 API 本就
  开放），代确认风险的真正解法是鉴权，属产品决策；prompt 注入面靠确认流
  拦截的现状不变。前端无 JS 测试设施，XSS 修复以静态契约测试锁定 +
  人工验收。

## v0.4.2（2026-10-13）

PWA / 推送通知 / 英文 README

- **PWA**：manifest + Service Worker + 自生成三尺寸图标，浏览器
  "安装到桌面/主屏"可用；离线时回退静态提示页（API 永远走网络，
  不会读到旧数据）
- **推送通知**（默认关闭）：每轮抓取后自动推送热榜 top N——支持
  Telegram Bot / 企业微信群机器人 / 飞书自定义机器人 / 通用 Webhook
  四种渠道；设置抽屉新面板（渠道切换 / 凭据打码显示 / 发送测试按钮）；
  API：GET/POST /api/push + POST /api/push/test；凭据存本机 meta 表
  与 provider key 同等保密
- **英文 README**（README_EN.md）+ 中文首行互链
- CI release.yml 补 static/ 目录入 PyInstaller 打包

## v0.4.1（2026-10-13）

多种安装方式 + 全文搜索 + 热榜缓存

- **三种安装方式**：① Releases 下载单文件可执行（PyInstaller 打包，
  Windows/macOS/Linux 由 CI 自动构建附到 Release，免 Python，双击即用，
  数据落在同目录 data/）② pip 安装（`pipx install git+…` 后 `ai-news`
  命令，pyproject [project.scripts]）③ 源码一键脚本（原有方式）
- 新增 app/launcher.py（启动即自动开浏览器；打包环境自动修正 DB_PATH
  到 exe 旁）与 run_app.py 打包入口；本地实测 Windows exe（33MB）独立
  运行通过（自动抓取、health 正常）
- CI 新增 release.yml：推 v* tag 自动三平台打包并附到 GitHub Release
- **全文搜索**：SQLite FTS5（标题/来源/RSS 摘要），触发器同步 + 存量
  库回填；顶栏搜索框 + /search 结果页（按热度排序）；输入自动转义
  防 FTS 语法炸
- **热榜缓存**：故事排行进程内缓存（画像/屏蔽/数据版本为键），入库/
  清理/屏蔽变化自动失效——14 天满载与并发下不再每次重算聚类
- 测试 +6（FTS 中英文/回填/转义/搜索页/缓存失效与命中）

## v0.4.0（2026-10-13）

开源发布收尾

- **移除 Docker 部署**（Dockerfile/docker-compose 删除）：一键脚本是
  唯一部署方式，文档同步清理
- **安全默认**：服务默认只监听 `127.0.0.1`；新增 `HOST` 环境变量
  （局域网共享改 `0.0.0.0`），README/DEPLOY 增加公网安全警示
  （无内置鉴权，公网需自行加反向代理与访问控制）
- 版本对齐：`__version__` / pyproject 0.3.0 → 0.4.0（此前 CHANGELOG
  到 0.3.9 而 health 仍报 0.3.0）
- README 重写：效果图（docs/screenshots 入仓）、功能一览
  （故事合并/为我精选/收藏存档/屏蔽/自定义源/一键操作等）、
  加源指南（零代码方式置顶）、配置表补 HOST
- 首访引导：空库时的热榜页显示三步上手（等抓取/配 key/加自定义源）
- DEPLOY 移除 Docker 节、补 HOST 与安全说明

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
