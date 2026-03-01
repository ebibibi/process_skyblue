# Process SkyBlue 設計ドキュメント

## プロジェクト概要

BlueSkyへのポストをトリガーとしてX（Twitter）・Discordへのクロスポストを自動化するシステム。
Dockerコンテナとして常駐し、BlueSky APIをポーリングして新規投稿を検出・転送する。

---

## 機能仕様

### 1. BlueSky → X クロスポスト

#### 基本動作
- 設定したBlueSkyアカウントを1分間隔でポーリング監視
- 新規ポストを検出したらXに自動投稿
- 画像添付に対応（最大4枚）
- 重複投稿防止: 処理済みポストIDをキャッシュ（最大1000件）
- 状態管理: `data/state.json` で処理済みIDとX/Discord各宛先の完了状態を管理

#### 文字数制限対応

| モード | X最大文字数 | 動作 |
|--------|------------|------|
| X Free（`X_PREMIUM=false`） | 280文字 | 超過時にスレッド分割 |
| X Premium（`X_PREMIUM=true`） | 25,000文字 | 単一ポストに収める |

> **注意**: 日本語等のCJK文字はTwitterカウント上2文字として換算される。

#### X Premium スレッドマージ機能（`X_PREMIUM=true` 時）

BlueSkyでスレッド（連投）したポストを、X側では1つのポストにまとめる：

```
BlueSky: Part 1 → Part 2 → Part 3  （3件のリプライ連鎖）
    ↓ X Premium merge
X:      「Part 1\n\nPart 2\n\nPart 3」 （1件のポスト）
```

- **同一バッチ内のみマージ**: 同じポーリングサイクルで取得したポスト群の中でチェーンを検出
- `_group_thread_posts()` でリプライ連鎖（`reply_to` フィールド）をたどってグループ化
- プライマリ（最初の投稿）がXポストを実行、セカンダリはそのX IDに紐付けられる
- プライマリが失敗した場合、セカンダリは次サイクルで再グループ化して再試行

#### スレッド分割（X Free時 / 長文時）

X Freeモードで280文字を超える場合、または単一ポストに収まらない場合はXのスレッドとして分割投稿。

### 2. BlueSky → Discord えびログ クロスポスト

- Discord Webhook URLを設定することで有効化（`DISCORD_LOG_WEBHOOK_URL`）
- X投稿とは独立して宛先ごとにリトライ状態を管理
- 画像はDiscordに直接貼り付け

### 3. エラーハンドリング・リトライ

| エラー種別 | 動作 |
|-----------|------|
| BlueSky APIサーバーエラー（502/503/504） | ログ出力・スキップ・次サイクルで自動リトライ |
| BlueSky APIレートリミット | 同上 |
| BlueSky API認証エラー | ログ出力・プロセス終了 |
| ネットワークエラー | 5回連続でDiscord通知、回復時もDiscord通知 |
| X投稿失敗 | 最大3回リトライ後に永続失敗としてマーク |
| Discord投稿失敗 | 同上 |

---

## システム構成

### アーキテクチャ

```
[BlueSky API]
     │  ポーリング（60秒間隔）
     ▼
[BlueskyInputService]
     │  新規ポスト検出
     ▼
[Main Orchestrator]  ←→  [StateManager]  ←→  data/state.json
     │
     ├─→ [ContentProcessor]  （文字数チェック・URLエンコード・スレッド分割）
     │
     ├─→ [XOutputService]      →  [X API v2]
     │
     └─→ [DiscordEbilogService] →  [Discord Webhook]

[DiscordNotifier]  →  [Discord Webhook（エラー通知用）]
```

### ディレクトリ構成

```
process_skyblue/
├── src/process_skyblue/
│   ├── core/
│   │   ├── config_manager.py    # 環境変数・バリデーション（Pydantic）
│   │   ├── state_manager.py     # 処理済み状態・リトライ管理
│   │   └── logger.py            # ログ出力（Discord通知連携）
│   ├── services/
│   │   ├── bluesky_input_service.py   # BlueSky ATプロトコルAPI
│   │   ├── x_output_service.py        # X API v2（画像: v1.1）
│   │   ├── discord_log_service.py  # Discord Webhook
│   │   ├── discord_notifier.py        # エラー通知用Discord
│   │   ├── base_input_service.py      # InputService 抽象基底
│   │   └── base_output_service.py     # OutputService 抽象基底
│   ├── utils/
│   │   └── content_processor.py  # 文字数計算・URL処理・スレッド分割
│   └── main.py                   # エントリポイント・メインループ
├── tests/                        # pytest テスト群
├── data/                         # state.json（実行時データ、gitignore済み）
├── Dockerfile
├── requirements.txt
├── .env.example                  # 環境変数テンプレート
└── process-skyblue.service       # systemd サービスファイル（例）
```

---

## 設定・環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `BLUESKY_IDENTIFIER` | ✅ | BlueSky ID（例: `user.bsky.social`） |
| `BLUESKY_PASSWORD` | ✅ | BlueSky パスワード（App Password推奨） |
| `X_API_KEY` | ✅ | X API Consumer Key |
| `X_API_SECRET` | ✅ | X API Consumer Secret |
| `X_ACCESS_TOKEN` | ✅ | X API Access Token |
| `X_ACCESS_TOKEN_SECRET` | ✅ | X API Access Token Secret |
| `X_OAUTH2_CLIENT_ID` | - | X OAuth 2.0 Client ID（将来用） |
| `X_OAUTH2_CLIENT_SECRET` | - | X OAuth 2.0 Client Secret（将来用） |
| `DISCORD_WEBHOOK_URL` | ✅ | Discord Webhookエラー通知用 |
| `DISCORD_LOG_WEBHOOK_URL` | - | DiscordログWebhook（省略で無効） |
| `POLLING_INTERVAL` | - | ポーリング間隔（秒、デフォルト: 60） |
| `X_PREMIUM` | - | X Premium有無（`true`/`false`、デフォルト: `true`） |
| `SKIP_POST_IDS` | - | スキップするBlueSkyポストID（カンマ区切り、デバッグ用） |

---

## デプロイ方法

### Docker（推奨）

```bash
# イメージビルド
docker build -t process-skyblue .

# 実行（.env を渡す）
docker run -d --name process-skyblue \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart=unless-stopped \
  process-skyblue
```

### systemd（Linux）

`process-skyblue.service` を `/etc/systemd/system/` にコピーして利用。
`WorkingDirectory` と `--env-file` のパスを環境に合わせて編集すること。

---

## 技術仕様

- **言語**: Python 3.9
- **BlueSky API**: ATプロトコル（`atproto` ライブラリ）
- **X API**: v2 ツイート投稿、v1.1 メディアアップロード（`tweepy` ライブラリ）
- **設定管理**: Pydantic v2 + python-dotenv
- **テスト**: pytest + pytest-mock
- **コンテナ**: Docker（python:3.9-slim ベース）
- **ポーリング方式**（Webhookではなくポーリング。ATプロトコルのFirehoseは将来対応予定）
