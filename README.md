# Process BlueSky

**Automatic mirroring service from BlueSky to a Discord channel.**

Runs as a single-shot process (one invocation = one check cycle). Call it every 60 seconds with cron, systemd timer, or your own scheduler to continuously mirror your BlueSky posts to Discord.

> **X (Twitter) output was removed in 2026-07.** This project used to cross-post to X as well, through the X API and later through a Web Intent link. Both paths are gone: there is no X code, no X credentials, and no X configuration left. If you need the old behaviour, use a tag before the removal commit.

[日本語](#japanese) | [中文](#chinese)

---

## Features

- 🦋 **BlueSky → Discord mirroring** — Post once on BlueSky, automatically mirrored to your Discord channel
- 🖼️ **Image support** — Transfers image attachments from BlueSky
- 🔄 **Auto-retry** — Failed posts are retried automatically (up to 3 times), then marked permanently failed so they are never retried forever
- 🛑 **Runaway protection** — A circuit breaker caps how many posts can be sent per run and per 30-minute window, and duplicate content is skipped outright
- 📡 **Error notifications** — Network errors and posting failures reported to a separate Discord webhook

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
| `DISCORD_WEBHOOK_URL` | ✅ | — | Discord Webhook for error/success notifications |
| `DISCORD_LOG_WEBHOOK_URL` | ✅ | — | Discord Webhook of the channel posts are mirrored to |
| `POLLING_INTERVAL` | — | `60` | Polling interval in seconds |
| `SKIP_POST_IDS` | — | — | Comma-separated BlueSky post IDs to skip (debug) |

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

**2026年7月にX（Twitter）への投稿機能を削除しました。** APIモードもWeb Intentモードも、コード・認証情報・設定ごと削除済みです。

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
