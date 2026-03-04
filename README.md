# Process BlueSky

**Automatic cross-posting service from BlueSky to X (Twitter) and Discord.**

Runs as a single-shot process (one invocation = one check cycle). Call it every 60 seconds with cron, systemd timer, or your own scheduler to continuously mirror your BlueSky posts to X and Discord.

[日本語](#japanese) | [中文](#chinese)

---

## Features

- 🔁 **BlueSky → X cross-posting** — Post once on BlueSky, automatically published to X
- 🖼️ **Image support** — Transfers image attachments from BlueSky to X (up to 4 images)
- 🧵 **Thread splitting** — Long posts are automatically split into Twitter threads (Free plan)
- ✨ **X Premium support** — Up to 25,000 characters in a single post
- 🔀 **Thread merging** — Multiple BlueSky thread posts merged into one X post (X Premium)
- 📢 **Discord logging** — Optional cross-posting to your own Discord server via Webhook
- 🔄 **Auto-retry** — Failed posts are retried automatically (up to 3 times)
- 📡 **Error notifications** — Network errors and posting failures reported to Discord

## How it works

```
Post on BlueSky
    ↓ (auto-detected within 60 seconds)
X post  +  Discord message (optional)
```

X Premium thread merging:
```
BlueSky: Part 1 → Part 2 → Part 3
    ↓
X:      "Part 1\n\nPart 2\n\nPart 3" (single post)
```

## Setup

### Requirements

- Python 3.10+
- BlueSky account
- X (Twitter) developer account and API keys — [X Developer Portal](https://developer.twitter.com/en/portal/dashboard)
- Discord Webhook URL for error notifications — [How to create](https://support.discord.com/hc/en-us/articles/228383668)

### 1. Clone the repository

```bash
git clone https://github.com/ebibibi/process_bluesky.git
cd process_bluesky
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your credentials:

```env
# BlueSky
BLUESKY_IDENTIFIER=your-account.bsky.social
BLUESKY_PASSWORD=your-app-password   # App Password recommended

# X (Twitter) API
X_API_KEY=your-api-key
X_API_SECRET=your-api-secret
X_ACCESS_TOKEN=your-access-token
X_ACCESS_TOKEN_SECRET=your-access-token-secret

# Discord — error notifications (required)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Discord — log channel on your own server (optional)
DISCORD_LOG_WEBHOOK_URL=https://discord.com/api/webhooks/...

# X Premium: 25,000 char limit + thread merging. Set false for Free plan.
X_PREMIUM=true
```

> **BlueSky App Password**: For security, use an [App Password](https://bsky.app/settings/app-passwords) instead of your account password.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run once (single-shot mode)

```bash
source .env
PYTHONPATH=src python3 -m process_bluesky.main
```

Expected output:

```
🚀 Initializing Process BlueSky...
X mode: Premium (25000 chars)
Connecting to Bluesky...
All services connected successfully!
Starting single-run check...
...
Check completed
Disconnecting from services...
Process BlueSky stopped
```

### 5. Schedule repeated execution

The process exits after each check. Use your preferred scheduler to call it every 60 seconds:

**cron** (every minute):
```bash
* * * * * cd /path/to/process_bluesky && source .env && PYTHONPATH=src python3 -m process_bluesky.main >> /var/log/process_bluesky.log 2>&1
```

**systemd timer**: See `process-bluesky.service` and `process-bluesky-restart.timer` in the repo.

**Docker** (classic always-on container with internal loop — legacy mode):
```bash
docker build -t process-bluesky .
docker run -d --name process-bluesky --env-file .env \
  -v $(pwd)/data:/app/data --restart=unless-stopped process-bluesky
```

## Configuration reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BLUESKY_IDENTIFIER` | ✅ | — | BlueSky handle (e.g. `user.bsky.social`) |
| `BLUESKY_PASSWORD` | ✅ | — | BlueSky password (App Password recommended) |
| `X_API_KEY` | ✅ | — | X API Consumer Key |
| `X_API_SECRET` | ✅ | — | X API Consumer Secret |
| `X_ACCESS_TOKEN` | ✅ | — | X API Access Token |
| `X_ACCESS_TOKEN_SECRET` | ✅ | — | X API Access Token Secret |
| `DISCORD_WEBHOOK_URL` | ✅ | — | Discord Webhook for error/success notifications |
| `DISCORD_LOG_WEBHOOK_URL` | — | disabled | Discord Webhook to log all posts to your server |
| `POLLING_INTERVAL` | — | `60` | Polling interval in seconds |
| `X_PREMIUM` | — | `true` | X Premium mode (`true` / `false`) |
| `SKIP_POST_IDS` | — | — | Comma-separated BlueSky post IDs to skip (debug) |

## X API rate limits

| Tier | Posts/month | Posts/day |
|------|-------------|-----------|
| Free | 500 | 17 |
| Basic | 3,000 | — |
| Pro | 300,000 | — |

The Free tier has a 17 posts/day limit. Be mindful of your posting frequency.

## Development

### Running tests

```bash
PYTHONPATH=src pytest tests/ -v
```

### Project structure

```
src/process_bluesky/
├── core/
│   ├── config_manager.py    # Config loading and validation (Pydantic)
│   ├── state_manager.py     # State persistence and retry tracking
│   └── logger.py            # Logging with Discord notification integration
├── services/
│   ├── bluesky_input_service.py   # BlueSky AT Protocol API
│   ├── x_output_service.py        # X API v2 (media upload: v1.1)
│   ├── discord_log_service.py     # Discord Webhook (cross-posting)
│   └── discord_notifier.py        # Discord Webhook (error notifications)
├── utils/
│   └── content_processor.py  # Character counting, URL encoding, thread splitting
└── main.py                   # Entry point — single-shot check-and-exit
```

See [design.md](./design.md) for detailed architecture documentation.

## License

MIT License

## Author

[@ebibibibibibi.bsky.social](https://bsky.app/profile/ebibibibibibi.bsky.social) / [@ebibibi on X](https://x.com/ebibibi)

---

<a name="japanese"></a>
## 日本語

BlueSkyへの投稿をX（Twitter）とDiscordに自動クロスポストするサービスです。

### 特徴

- BlueSkyに投稿するだけでXにも自動投稿
- 画像添付対応（最大4枚）
- X Freeプランはスレッド分割、X Premiumは25,000文字まで単一ポスト
- BlueSkyのスレッド投稿をX側では1ポストにマージ（X Premium時）
- 自分のDiscordサーバーへのログ投稿（任意）

### セットアップ

1. リポジトリをクローン
2. `.env.example` を `.env` にコピーして認証情報を設定
3. `pip install -r requirements.txt` で依存パッケージをインストール
4. `source .env && PYTHONPATH=src python3 -m process_bluesky.main` で動作確認
5. cron または systemd timer で60秒ごとに実行するよう設定

詳細は上記の英語セクションを参照してください。

---

<a name="chinese"></a>
## 中文

将 BlueSky 帖子自动交叉发布到 X（Twitter）和 Discord 的服务。

### 功能特点

- 在 BlueSky 发帖后自动发布到 X
- 支持图片附件（最多4张）
- X Free 计划自动分割长帖，X Premium 支持最多 25,000 字符
- X Premium 模式下将 BlueSky 串联帖子合并为单条 X 帖子
- 可选将帖子记录到您自己的 Discord 服务器

### 快速开始

1. 克隆仓库
2. 将 `.env.example` 复制为 `.env` 并填写认证信息
3. 运行 `pip install -r requirements.txt` 安装依赖
4. 运行 `source .env && PYTHONPATH=src python3 -m process_bluesky.main` 验证运行
5. 使用 cron 或 systemd timer 每60秒定时执行

详细配置请参阅上方英文部分。
