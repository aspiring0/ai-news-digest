# 部署文档（给部署者 / DSH）

> 本文面向"拿到这份代码、负责把它跑起来的人"。按下面步骤照抄即可，不需要懂 Python。

## 1. 这是什么

一个自托管的 AI 资讯聚合站。架构很简单，**只有一个进程**：

- `uvicorn` 跑 FastAPI 提供网页（热榜 / 时间线 / 日报 / 主题 / 收藏 / 设置）
- 定时抓取由 APScheduler **跑在同一个进程里**——进程活着，就会每 4 小时自动抓一次，不需要额外配 cron
- 数据是单个 SQLite 文件（`data/news.db`），备份就是拷走这个文件

## 2. 环境要求

| 项目 | 要求 |
|---|---|
| Python | 3.11 或更高（`python3 --version` 查看） |
| 磁盘 | 200MB 空闲（依赖约 150MB，数据库很小） |
| 网络 | 能访问公网（抓取信息源用） |
| 端口 | 默认 8000，可改 |

**不需要 Docker。** 一键脚本是唯一部署方式（v0.4.0 起已移除 Docker 相关文件）。

> **安全默认**：服务只监听 `127.0.0.1`（本机可访问）。要让局域网同事访问：把 `.env` 的 `HOST` 改为 `0.0.0.0` 后重启。**不要不加防护地暴露到公网**——本服务无内置登录鉴权，模型 key 存在服务机上；公网场景请自行加反向代理（nginx/caddy）+ 访问控制。

## 3. 三步启动

### Linux / macOS

```bash
# 第 1 步：拿到代码（两种方式任选一种）
git clone <仓库地址> ai-news-oss && cd ai-news-oss
# 或：解压 zip 包后 cd 进去

# 第 2 步：复制配置（可选，不改也行）
cp .env.example .env
# 用记事本/编辑器打开 .env，按需改 PORT 等（见第 4 节）

# 第 3 步：启动
chmod +x start.sh   # 只需做一次
./start.sh
```

看到打印出 `http://localhost:8000/hot` 就成功了。浏览器打开即用。
首次启动会自动抓一次全网（约几十秒到几分钟），页面一开始可能是空的，等一会儿刷新。

**验证服务正常**（任选一种）：

```bash
curl http://localhost:8000/api/health
# 期望返回：{"ok": true, "version": "0.3.0", "news_count": 164, "last_fetch": "..."}
# news_count 为 0 说明首次抓取还没完成，等一两分钟再查
```

### Windows

```
第 1 步：拿到代码
  git clone <仓库地址> ai-news-oss
  或解压 zip 包。建议放到全英文路径，如 D:\ai-news-oss
  （中文/带空格路径可能出奇怪问题）

第 2 步：复制配置（可选）
  copy .env.example .env
  用记事本打开 .env 按需修改（见第 4 节）

第 3 步：启动
  双击 start.bat（或在 cmd 里运行 start.bat）
```

脚本会自动：检查 Python 版本 → 创建虚拟环境 → 装依赖 → 启动服务。
**关闭窗口 = 停止服务。**

## 4. 配置说明（.env 每一项）

| 变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `8000` | 网页端口。被占用就换一个，如 `8080` |
| `HOST` | `127.0.0.1` | 监听地址。局域网共享改 `0.0.0.0`；公网请自行加反代与鉴权 |
| `TZ` | `Asia/Shanghai` | 时区。日报按此时区的自然天划分 |
| `FETCH_INTERVAL_HOURS` | `4` | 抓取间隔（小时）。**不要调太激进**（见下） |
| `DATA_DIR` | `./data` | 数据目录，`news.db` 放在里面 |
| `DB_PATH` | （空） | 高级项：直接指定数据库文件完整路径，设置后优先于 `DATA_DIR` |

**关于抓取间隔**：默认 4 小时是经验值。这些是别人的公开服务，1 小时以内一轮容易被限流甚至封 IP；4 小时对看资讯完全够用。改小之前请三思。

## 5. 运行说明

- **定时抓取**：不需要配 cron/计划任务。服务进程活着，APScheduler 就会每 `FETCH_INTERVAL_HOURS` 小时跑一轮；启动时还会先跑一次。
- **数据备份**：服务运行时直接复制 `data/news.db` 即可（SQLite 支持热拷贝）；恢复时拷回去重启服务。
- **日志**：直接看终端输出。每轮抓取会打印各源抓到的条数；单个源失败只记一行日志、不影响其他源，例如 `[量子位] 抓取失败: ...` 看到这种不用慌，下一轮会自动重试。
- **摘要功能**：需要自己在网页 `⚙️ 设置` 里填模型 key（DeepSeek/智谱/Kimi 等任选一家）。key 只存在本机 `data/news.db` 里，不会上传到任何地方。不填 key 不影响除摘要外的全部功能。

## 6. 开机自启

### Windows（任务计划程序）

1. `Win+R` → 输入 `taskschd.msc` 回车，打开"任务计划程序"
2. 右侧点 **"创建任务…"**（注意不是"创建基本任务"）
3. **常规**页：名称填 `AI资讯聚合`；下方"安全选项"按需勾选
4. **触发器**页：新建 → "开始任务"选 **"启动时"** → 确定
5. **操作**页：新建 → 操作选"启动程序"：
   - 程序或脚本：`D:\ai-news-oss\start.bat`（换成你的实际路径）
   - 起始于：`D:\ai-news-oss`（换成你的实际路径）
6. **条件**页：笔记本请取消勾选"只有在计算机使用交流电源时才启动此任务"
7. 确定保存（可能要求输入开机密码）

### Linux（systemd）

把下面存为 `/etc/systemd/system/ai-news.service`（路径换成实际的）：

```ini
[Unit]
Description=AI 新闻聚合
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=你的用户名
WorkingDirectory=/home/你的用户名/ai-news-oss
ExecStart=/home/你的用户名/ai-news-oss/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ai-news
# 看日志：journalctl -u ai-news -f
```

注意：先用 `./start.sh` 跑通一次（让 `.venv` 建好），再配 systemd。

## 7. 更新流程

```bash
cd ai-news-oss
git pull
./start.sh        # Windows: 双击 start.bat
```

脚本会自动检测 `requirements.txt` 变化并重装依赖。改了 `.env` 也要重启才生效。

## 8. 常见问题

**Q：端口被占用，启动报错 `Address already in use`？**
A：把 `.env` 里 `PORT` 换个数字（如 8080），重启。或查出占用者：
- Windows：`netstat -ano | findstr 8000`
- Linux/macOS：`ss -tlnp | grep 8000`

**Q：某个源抓不到，日志里有失败？**
A：正常。单个源失败只记日志、不影响整轮，下一轮自动重试。如果**所有**源都失败，检查本机能不能上网 / 是否需要代理。

**Q：摘要弹窗显示"摘要暂不可用"？**
A：两种可能：① 设置页没填 key（去 `⚙️ 设置` 填一家的 key 并设为默认）；② 原文网站有反爬/付费墙，正文抓不到——不扣费，换一篇试试。

**Q：key 会不会泄露？**
A：key 只存在本机 `data/news.db`。不要把 `data/` 目录或 `.env` 发给别人、传到网盘公开链接。

**Q：Windows 下双击 start.bat 一闪而过？**
A：在 start.bat 所在目录按住 Shift 点右键 → "在此处打开 PowerShell"，运行 `.\start.bat`，看报错信息。常见原因：Python 没装 / 没勾选 "Add python.exe to PATH" / 路径含中文。

**Q：页面一直是空的？**
A：首次启动要抓完全部源（几十秒到几分钟），等一会儿刷新。看终端有没有 `[xxx] 抓到 N 条` 的日志。

**Q：数据库越来越大？**
A：只保留 14 天数据，每次抓取后自动清理，不会无限膨胀。

## 9. 让你的 AI 帮你部署

如果你用的 AI 助手支持读代码、跑命令（如各类 AI 编程助手），三步就行：

1. 把仓库链接（或 zip 包）发给它
2. 让它**先读 `AGENTS.md`**（里面是给 AI 看的部署说明：技术栈、目录结构、启动和验证命令、常见坑）
3. 让它按本 `DEPLOY.md` 执行部署，最后 `curl /api/health` 验证

一句话指令模板（直接复制发给 AI）：

> 这是 ai-news-oss 仓库。请先读 AGENTS.md，然后按 DEPLOY.md 把它在我的机器上部署起来，最后用 curl http://localhost:8000/api/health 验证并告诉我结果。

## 11. 发布前检查（仓库主人看）

- [ ] `LICENSE` 里的 `YOUR_NAME` 换成你的名字/网名
- [ ] 确认 `.env`、`data/` 没进 git（`git status` 应该是干净的）
- [ ] 在一台干净机器上按第 3 节走一遍，确认能跑起来
