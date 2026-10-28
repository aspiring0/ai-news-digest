# AI News Digest (Open Source · v0.4.5)

[中文文档](README.md) | **English**

A self-hosted AI news aggregator: fetches 31 AI sources on schedule, ranks stories by time-decayed hotness (with multi-source story merging and per-source diversity quota), and offers AI-powered summaries using your own model key. English titles are auto-translated to Chinese. Full-text search (CJK substring + English FTS prefix), a dedicated GitHub ecosystem page, optional push notifications, and PWA support are included. Single-file SQLite, all data stays on your machine.

## Screenshots

| Hot List (story merge + editorial style) | Summary Modal (4 sections) |
|---|---|
| ![Hot](docs/screenshots/hot.png) | ![Summary](docs/screenshots/modal.png) |

| Dark Mode | Model Platform (drawer) |
|---|---|
| ![Dark](docs/screenshots/dark.png) | ![Settings](docs/screenshots/settings.png) |

## Installation (3 ways)

### Option 1: Download executable (no Python required, recommended)

Download the single-file executable for your platform from [Releases](../../releases) (`ai-news.exe` / `ai-news`), place it in any directory and **double-click** — it auto-creates the database, fetches, and opens your browser.
> Releases are **pending** (CI builds temporarily unavailable); use Option 2/3 until then.

### Option 2: pip install

```bash
pipx install git+https://github.com/aspiring0/ai-news-digest.git
ai-news            # starts and opens browser
```

### Option 3: From source

```bash
cp .env.example .env
./start.sh         # Linux / macOS
# start.bat        # Windows
```

All three are functionally identical. First launch fetches all 31 sources in the background (~1 minute measured), then auto-refreshes every 4 hours.

> **Security note**: The service listens on `127.0.0.1` by default. For LAN sharing, set `HOST=0.0.0.0` in `.env`. **Do not expose directly to the public internet** (no built-in auth; model keys stored locally). Use a reverse proxy with access control for public deployments.

## Features

- **Hot List**: Time-decayed scoring (48h half-life) + per-source quota (max 4 slots) + **story merging** (same event from multiple sources → one slot, cross-language matching via Latin entity extraction, multi-source bonus) + pagination
- **For You (self-evolving)**: Logs your behavior (summary clicks / bookmarks / blocks) → one-click AI distillation into an interest profile → topics you like float up, topics you dislike disappear. Profile stored locally, editable and resettable
- **AI Summary**: 4-section Chinese analysis (What is this / Key facts / In plain language / Source link), cached by URL; RSS description fallback when article scraping fails
- **19 Sources**: 10 base sources + 9 direct upstream sources extracted from AIHOT (OpenAI / DeepMind / Hacker News / Ars Technica etc.); **add any RSS feed from the settings UI** — zero code
- **Bookmark = Archive**: Bookmarks save a full-text snapshot; content readable even after source link rots or 14-day cleanup
- **Block / Not Interested**: Per-item ✕ button (URL / source / category); hot list and timeline respect blocks instantly
- **Search**: Chinese/CJK substring search across titles, translated titles, and summaries (LIKE path — the FTS tokenizer can't segment CJK); English full-text via SQLite FTS5 prefix matching, ranked by hotness
- **Chinese Translation**: English titles/descriptions auto-translated in batches each cycle (Chinese shown as primary, original as subtitle); arXiv papers stay in English without consuming translation quota
- **31 Sources**: 10 base sources + 21 direct upstreams — 9 extracted from AIHOT in v0.3.3/v0.3.4 (OpenAI / DeepMind / Hacker News / Ars Technica / IT之家 / VentureBeat / Tessl / GitHub Releases / MarkTechPost), the GitHub Star-rising source, 10 more added in the upstream-split batch (official RSS of Google Research / Microsoft Research / Azure AI / Mistral / NVIDIA / MIT + HTML scraping of Anthropic / Meta AI / xAI / Cohere), and the arXiv paper feed (cs.AI/CL/LG); **add any RSS feed from the settings UI** (intranet addresses blocked by default, SSRF-safe)
- **GitHub Page** (/github): Trending / Releases / Star-rising sources in one view, with one-click Clone/Fork
- **Push Notifications** (optional, off by default): Telegram Bot / WeCom group bot / Feishu custom bot / Generic Webhook — pushes hot list top N after each fetch cycle
- **PWA**: Installable as a standalone app from your browser (with offline fallback)
- **UX details**: Unread dots / unread-only filter / new-content banner / source filter chips / GitHub one-click Clone/Fork/Deploy / source health panel / dark mode / mobile responsive

## How the Hot List Works

1. **Static score**: Written once per fetch by in-feed position — RSS starts at 66 (-2/rank, floor 48); HuggingFace starts at 72; ProductHunt/GitHub starts at 70; AIHOT uses upstream score (falls back to RSS rules if absent).
2. **Hot score** (computed at read time, original untouched): `hot_score = score × 0.5^(age_hours / 48)`.
3. **Diversity quota** (v0.3.2): Max 4 slots per source in top 20.
4. **Story merging** (v0.3.5): Items sharing ≥2 title entities within 48h merge into one story. `story_score = max_member × (1 + 15%/extra_source)`.

## Adding a New Source

**Option 1 (zero code)**: Settings → "Custom RSS Sources" — paste a name and RSS URL.

**Option 2 (for sites without RSS)**: Create a module in `app/fetchers/` (see `qbitai.py` for a ~10-line RSS example), register in `FETCHERS`.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Web port |
| `HOST` | `127.0.0.1` | Listen address. Set `0.0.0.0` for LAN; **use reverse proxy for public** |
| `TZ` | `Asia/Shanghai` | Timezone (daily report day boundary) |
| `FETCH_INTERVAL_HOURS` | `4` | Fetch interval. **Don't set below 1h** (rate limiting risk) |
| `DATA_DIR` | `./data` | Data directory for `news.db` |
| `DB_PATH` | (empty) | Advanced: direct database file path (overrides `DATA_DIR`) |

## License

MIT (see [LICENSE](LICENSE)).
