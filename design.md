# Process BlueSky 設計ドキュメント

## プロジェクト概要

BlueSkyへのポストをトリガーとしてDiscord（えびログ）へのミラーを自動化するシステム。
BlueSky APIをポーリングして新規投稿を検出・転送する。

> **2026-07-31: X（Twitter）出力を全廃した。** X APIモードもWeb Intentモードも、コード・
> 認証情報・設定ごと削除済み。宛先はDiscordえびログ1本だけになった。

---

## 機能仕様

### 1. BlueSky → Discord えびログ ミラー

#### 基本動作
- 設定したBlueSkyアカウントを1分間隔でポーリング監視
- 新規ポストを検出したらDiscordえびログに自動投稿
- 画像はDiscordに直接貼り付け
- 重複投稿防止: 処理済みポストIDをキャッシュ（最大1000件）
- 状態管理: `data/state.json` で処理済みIDと宛先の完了状態を管理
- `DISCORD_LOG_WEBHOOK_URL` 未設定なら出力先が無いので起動時に終了する

### 2. 暴走防止（サーキットブレーカー）

同じバッチを再送し続ける暴走が実際に起きたため、以下のガードを常時適用する。

| ガード | 上限 | 超過時 |
|--------|------|--------|
| 1実行あたりの投稿数 | 30件 | ブレーカー作動・実行中断 |
| 30分あたりの投稿数 | 40件 | ブレーカー作動・実行中断 |
| 直近100件との内容重複 | - | そのポストをスキップして完了扱い |

作動後は手動リセットが必要:

```bash
PYTHONPATH=src python3 -c "from process_bluesky.core.state_manager import StateManager; StateManager().reset_circuit_breaker()"
```

### 3. エラーハンドリング・リトライ

| エラー種別 | 動作 |
|-----------|------|
| BlueSky APIサーバーエラー（502/503/504） | ログ出力・スキップ・次サイクルで自動リトライ |
| BlueSky APIレートリミット | 同上 |
| BlueSky API認証エラー | ログ出力・プロセス終了 |
| ネットワークエラー | 5回連続でDiscord通知、回復時もDiscord通知 |
| Discord投稿失敗 | 最大3回リトライ後に永続失敗としてマーク（無限再送を防ぐ） |

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
     │                        （サーキットブレーカー・重複検出）
     └─→ [DiscordEbilogService] →  [Discord Webhook]

[DiscordNotifier]  →  [Discord Webhook（エラー通知用）]
```

### ディレクトリ構成

```
process_bluesky/
├── src/process_bluesky/
│   ├── core/
│   │   ├── config_manager.py    # 環境変数・バリデーション（Pydantic）
│   │   ├── state_manager.py     # 処理済み状態・リトライ・サーキットブレーカー
│   │   └── logger.py            # ログ出力（Discord通知連携）
│   ├── services/
│   │   ├── bluesky_input_service.py   # BlueSky ATプロトコルAPI
│   │   ├── discord_log_service.py  # Discord Webhook
│   │   ├── discord_notifier.py        # エラー通知用Discord
│   │   ├── base_input_service.py      # InputService 抽象基底
│   │   └── base_output_service.py     # OutputService 抽象基底
│   └── main.py                   # エントリポイント・メインループ
├── tests/                        # pytest テスト群
├── data/                         # state.json（実行時データ、gitignore済み）
├── Dockerfile
├── requirements.txt
├── .env.example                  # 環境変数テンプレート
└── process-bluesky.service       # systemd サービスファイル（例）
```

---

## 設定・環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `BLUESKY_IDENTIFIER` | ✅ | BlueSky ID（例: `user.bsky.social`） |
| `BLUESKY_PASSWORD` | ✅ | BlueSky パスワード（App Password推奨） |
| `DISCORD_WEBHOOK_URL` | ✅ | Discord Webhookエラー通知用 |
| `DISCORD_LOG_WEBHOOK_URL` | ✅ | ミラー先のDiscord Webhook（唯一の出力先） |
| `POLLING_INTERVAL` | - | ポーリング間隔（秒、デフォルト: 60） |
| `SKIP_POST_IDS` | - | スキップするBlueSkyポストID（カンマ区切り、デバッグ用） |

---

## デプロイ方法

### Docker（推奨）

```bash
# イメージビルド
docker build -t process-bluesky .

# 実行（.env を渡す）
docker run -d --name process-bluesky \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  --restart=unless-stopped \
  process-bluesky
```

### systemd（Linux）

`process-bluesky.service` を `/etc/systemd/system/` にコピーして利用。
`WorkingDirectory` と `--env-file` のパスを環境に合わせて編集すること。

---

## 技術仕様

- **言語**: Python 3.9
- **BlueSky API**: ATプロトコル（`atproto` ライブラリ）
- **設定管理**: Pydantic v2 + python-dotenv
- **テスト**: pytest + pytest-mock
- **コンテナ**: Docker（python:3.9-slim ベース）
- **ポーリング方式**（Webhookではなくポーリング。ATプロトコルのFirehoseは将来対応予定）
