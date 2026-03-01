# Process SkyBlue

BlueSkyに投稿したポストをXおよびDiscordへ自動クロスポストするサービスです。
Dockerコンテナとして常駐し、BlueSky APIをポーリングして新規投稿を検出・転送します。

## 特徴

- 🔁 **BlueSky → X 自動クロスポスト** — BlueSkyに投稿するだけで自動的にXにも投稿
- 🖼️ **画像対応** — BlueSkyの画像添付をXにそのまま転送（最大4枚）
- 🧵 **スレッド分割** — Xの文字数制限を超える長文を自動でスレッド分割
- ✨ **X Premium対応** — X Premiumなら25,000文字まで単一ポストで投稿
- 🔀 **スレッドマージ** — BlueSkyでスレッド投稿した内容をX側では1ポストにまとめる（X Premium時）
- 📢 **Discord連携** — Discord Webhookへのクロスポストも同時対応
- 🔄 **自動リトライ** — 投稿失敗時は最大3回まで自動リトライ
- 📡 **エラー通知** — ネットワークエラーや投稿失敗をDiscordへ通知

## 動作イメージ

```
BlueSkyに投稿
    ↓ （自動検出・60秒以内）
X に自動投稿  +  Discord に自動投稿
```

X Premiumでのスレッドマージ:
```
BlueSky: Part 1 → Part 2 → Part 3
    ↓
X:      「Part 1\n\nPart 2\n\nPart 3」（1ポスト）
```

## セットアップ

### 必要なもの

- Docker
- BlueSkyアカウント
- X（Twitter）の開発者アカウントとAPIキー（[X Developer Portal](https://developer.twitter.com/en/portal/dashboard)で取得）
- Discord Webhook URL（エラー通知用。[作成方法](https://support.discord.com/hc/en-us/articles/228383668)）

### 1. リポジトリをクローン

```bash
git clone https://github.com/ebibibi/process_skyblue.git
cd process_skyblue
```

### 2. 環境変数を設定

```bash
cp .env.example .env
```

`.env` を開いて各値を設定してください：

```env
# BlueSky
BLUESKY_IDENTIFIER=your-account.bsky.social
BLUESKY_PASSWORD=your-app-password   # App Passwordを推奨

# X (Twitter) API
X_API_KEY=your-api-key
X_API_SECRET=your-api-secret
X_ACCESS_TOKEN=your-access-token
X_ACCESS_TOKEN_SECRET=your-access-token-secret

# Discord（エラー通知用・必須）
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Discord えびログ（クロスポスト先・任意）
DISCORD_EBILOG_WEBHOOK_URL=https://discord.com/api/webhooks/...

# X Premium（25,000文字 + スレッドマージ。Freeプランは false）
X_PREMIUM=true
```

> **BlueSky App Password**: セキュリティのためアカウントパスワードではなく
> [App Password](https://bsky.app/settings/app-passwords) の使用を推奨します。

### 3. Dockerで起動

```bash
# イメージビルド
docker build -t process-skyblue .

# 起動
docker run -d \
  --name process-skyblue \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart=unless-stopped \
  process-skyblue
```

### 4. ログを確認

```bash
docker logs -f process-skyblue
```

正常に起動すると以下のようなログが表示されます：

```
🚀 Initializing Process SkyBlue...
X mode: Premium (25000 chars)
Connecting to Bluesky...
Connecting to X...
All services connected successfully!
Starting main polling loop...
```

## systemd でサービス化（Linux）

Dockerを使わずに直接サービスとして動かす場合：

```bash
# サービスファイルをコピーして編集
sudo cp process-skyblue.service /etc/systemd/system/
sudo nano /etc/systemd/system/process-skyblue.service  # パスを環境に合わせて修正

# サービスを有効化
sudo systemctl daemon-reload
sudo systemctl enable process-skyblue
sudo systemctl start process-skyblue
```

## 設定オプション

| 環境変数 | 必須 | デフォルト | 説明 |
|---------|------|-----------|------|
| `BLUESKY_IDENTIFIER` | ✅ | - | BlueSky ID（例: `user.bsky.social`） |
| `BLUESKY_PASSWORD` | ✅ | - | BlueSky パスワード（App Password推奨） |
| `X_API_KEY` | ✅ | - | X API Consumer Key |
| `X_API_SECRET` | ✅ | - | X API Consumer Secret |
| `X_ACCESS_TOKEN` | ✅ | - | X API Access Token |
| `X_ACCESS_TOKEN_SECRET` | ✅ | - | X API Access Token Secret |
| `DISCORD_WEBHOOK_URL` | ✅ | - | エラー通知用 Discord Webhook URL |
| `DISCORD_EBILOG_WEBHOOK_URL` | - | 無効 | クロスポスト先 Discord Webhook URL |
| `POLLING_INTERVAL` | - | `60` | ポーリング間隔（秒） |
| `X_PREMIUM` | - | `true` | X Premiumプランの有無（`true`/`false`） |
| `SKIP_POST_IDS` | - | - | スキップするポストID（カンマ区切り、デバッグ用） |

## X API のアクセスレベルについて

| API項目 | Free | Basic | Pro |
|---------|------|-------|-----|
| ツイート投稿（月） | 500 | 3,000 | 300,000 |
| 1日あたりのツイート投稿 | 17 | - | - |

FreeTierは1日17件制限があるため、高頻度の投稿には注意してください。

## 開発

### テストの実行

```bash
cd process_skyblue
PYTHONPATH=src pytest tests/ -v
```

### プロジェクト構成

```
src/process_skyblue/
├── core/
│   ├── config_manager.py    # 環境変数管理（Pydantic）
│   ├── state_manager.py     # 処理状態・リトライ管理
│   └── logger.py            # ログ（Discord通知連携）
├── services/
│   ├── bluesky_input_service.py   # BlueSky ATプロトコルAPI
│   ├── x_output_service.py        # X API v2
│   ├── discord_ebilog_service.py  # Discord Webhook
│   └── discord_notifier.py        # エラー通知
├── utils/
│   └── content_processor.py  # 文字数計算・スレッド分割
└── main.py                   # エントリポイント
```

詳細な設計ドキュメントは [design.md](./design.md) を参照してください。

## ライセンス

MIT License

## 作者

[@ebibibibibibi.bsky.social](https://bsky.app/profile/ebibibibibibi.bsky.social) / [@ebibibi](https://x.com/ebibibi)
