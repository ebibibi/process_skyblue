# Process BlueSky

**Mirroring service for BlueSky, Discord, and owned X posts.**

Runs as single-shot processes (one invocation = one check cycle). The main entry point mirrors BlueSky to Discord. A separate X input path mirrors the authenticated owner's X posts to BlueSky and exposes those posts to downstream content workflows.

> **X output remains removed.** This project does not post to X. It only reads the authenticated owner's posts through X's user-context API.

[日本語](#japanese) | [中文](#chinese)

---

## Features

- 🦋 **BlueSky → Discord mirroring** — Post once on BlueSky, automatically mirrored to your Discord channel
- 🖼️ **Image support** — Transfers image attachments from BlueSky
- 🔄 **Auto-retry** — Failed posts are retried automatically (up to 3 times), then marked permanently failed so they are never retried forever
- 🛑 **Runaway protection** — A circuit breaker caps how many posts can be sent per run and per 30-minute window, and duplicate content is skipped outright
- 📡 **Error notifications** — Network errors and posting failures reported to a separate Discord webhook
- ✍️ **Read-only X export** — Emits recent owned X posts as JSON or Markdown for writing and video-planning workflows

## How it works

```
Post on BlueSky
    ↓ (auto-detected within 60 seconds)
Discord message
```

## Setup

### Requirements

- Python 3.10+
- BlueSky account
- Discord Webhook URL for error notifications — [How to create](https://support.discord.com/hc/en-us/articles/228383668)
- Discord Webhook URL for the mirror channel

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

# Discord — error notifications (required)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Discord — mirror channel (required; without it there is nothing to do)
DISCORD_LOG_WEBHOOK_URL=https://discord.com/api/webhooks/...
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
Output: Discord えびログ only (X output removed)
Connecting to Bluesky...
All services connected successfully!
Starting single-run check...
...
Check completed
Disconnecting from services...
Process BlueSky stopped
```

### 5. Export recent owned X posts

After adding the optional `X_*` OAuth 2.0 values shown in `.env.example`, run:

```bash
PYTHONPATH=src python3 -m process_bluesky.x_recent \
  --env-file /absolute/path/to/.env --days 30 --limit 50 --format markdown
```

The command only calls `GET /2/users/{id}/tweets`; it never posts, likes, follows, or deletes. Use OAuth user-context tokens for the developer app owner so X classifies the requests as lower-cost Owned Reads. JSON is the default format for machine consumers.

### 6. Schedule repeated execution

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
| `DISCORD_WEBHOOK_URL` | ✅ | — | Discord Webhook for error/success notifications |
| `DISCORD_LOG_WEBHOOK_URL` | ✅ | — | Discord Webhook of the channel posts are mirrored to |
| `POLLING_INTERVAL` | — | `60` | Polling interval in seconds |
| `SKIP_POST_IDS` | — | — | Comma-separated BlueSky post IDs to skip (debug) |
| `X_USER_ID` / `X_SCREEN_NAME` | X input only | — | Authenticated owner's numeric ID and screen name |
| `X_CLIENT_ID` / `X_CLIENT_SECRET` | X input only | — | OAuth 2.0 application credentials |
| `X_ACCESS_TOKEN` / `X_REFRESH_TOKEN` | X input only | — | OAuth 2.0 user-context tokens; refreshed tokens are persisted to the env file |
| `X_ENV_FILE` | X mirror only | — | Absolute dotenv path used for safe token persistence |

## Runaway protection

Mirroring the same batch over and over is the failure mode this project has actually hit, so the circuit breaker guards against it:

| Guard | Limit | Behaviour on breach |
|-------|-------|---------------------|
| Posts per run | 30 | Breaker trips, run aborts |
| Posts per 30-minute window | 40 | Breaker trips, run aborts |
| Duplicate content (last 100 posts) | — | That post is skipped and marked done |

A tripped breaker must be reset manually:

```bash
PYTHONPATH=src python3 -c "from process_bluesky.core.state_manager import StateManager; StateManager().reset_circuit_breaker()"
```

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
│   ├── state_manager.py     # State persistence, retry tracking, circuit breaker
│   └── logger.py            # Logging with Discord notification integration
├── services/
│   ├── bluesky_input_service.py   # BlueSky AT Protocol API
│   ├── discord_log_service.py     # Discord Webhook (mirror channel)
│   └── discord_notifier.py        # Discord Webhook (error notifications)
└── main.py                   # Entry point — single-shot check-and-exit
```

See [design.md](./design.md) for detailed architecture documentation.

## License

MIT License

## Author

[@ebibibibibibi.bsky.social](https://bsky.app/profile/ebibibibibibi.bsky.social)

---

<a name="japanese"></a>
## 日本語

BlueSkyへの投稿をDiscordチャンネルに自動ミラーするサービスです。

**X（Twitter）への投稿機能は削除済みです。** 現在は本人アカウントのポストをユーザー認証APIで読み取り、BlueSkyへのミラーとコンテンツ制作向けの読み取り専用エクスポートに利用します。Xへの投稿・いいね・フォロー・削除は行いません。

### 特徴

- BlueSkyに投稿するだけでDiscordにも自動ミラー
- 画像添付対応
- 失敗時の自動リトライ（最大3回）と恒久失敗マーク
- 暴走防止のサーキットブレーカー（実行あたり30件 / 30分あたり40件 / 重複内容はスキップ）

### セットアップ

1. リポジトリをクローン
2. `.env.example` を `.env` にコピーして認証情報を設定
3. `pip install -r requirements.txt` で依存パッケージをインストール
4. `source .env && PYTHONPATH=src python3 -m process_bluesky.main` で動作確認
5. cron または systemd timer で60秒ごとに実行するよう設定
6. コンテンツ素材として使う場合は `PYTHONPATH=src python3 -m process_bluesky.x_recent --env-file /absolute/path/to/.env --days 30 --format markdown` で直近の本人ポストを取得

詳細は上記の英語セクションを参照してください。

---

<a name="chinese"></a>
## 中文

将 BlueSky 帖子自动镜像到 Discord 频道的服务。

**2026年7月已移除对 X（Twitter）的发布功能**，包括 API 模式和 Web Intent 模式的代码、凭据与配置。

### 功能特点

- 在 BlueSky 发帖后自动镜像到 Discord
- 支持图片附件
- 失败自动重试（最多3次），超过后标记为永久失败
- 熔断保护（每次运行30条 / 每30分钟40条 / 重复内容跳过）

### 快速开始

1. 克隆仓库
2. 将 `.env.example` 复制为 `.env` 并填写认证信息
3. 运行 `pip install -r requirements.txt` 安装依赖
4. 运行 `source .env && PYTHONPATH=src python3 -m process_bluesky.main` 验证运行
5. 使用 cron 或 systemd timer 每60秒定时执行

详细配置请参阅上方英文部分。
