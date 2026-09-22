# Process BlueSky 設計ドキュメント

## プロジェクト概要

BlueSkyへのポストをトリガーとしてDiscord（えびログ）へのミラーを自動化するシステム。
BlueSky APIをポーリングして新規投稿を検出・転送する。

> **X（Twitter）出力は全廃したまま。** 2026-09-21から本人のXポストをユーザー認証で読み取る入力経路を追加した。
> Xへの投稿・いいね・フォロー・削除は行わない。読み取ったポストはBlueSkyミラーと、コンテンツ制作向けの読み取り専用エクスポートにだけ使う。

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

### 2. X本人ポスト入力

- OAuth 2.0ユーザーコンテキストで `GET /2/users/{id}/tweets` のみを呼ぶ
- 開発者アプリ所有者本人のポストを読むことで、XのOwned Read料金を使う
- `x_mirror.py`: 新着をBlueSkyへスレッド構造付きでミラーする。初回はwatermarkだけを設定し、過去分を流さない
- `x_recent.py`: 直近N日・最大N件をJSONまたはMarkdownで標準出力し、note執筆やYouTube企画の入力にする
- OAuth refresh tokenは単回利用のため、更新成功時は新しいtoken pairをdotenvへ原子的に保存してから採用する
- Xへの書き込み操作は実装しない

### 3. 暴走防止（サーキットブレーカー）

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

### 4. エラーハンドリング・リトライ

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

[X API: 本人ポスト / Owned Read]
     │
     ├─→ [XMirror] → [BlueSkyOutputService] → BlueSky
     └─→ [XRecent CLI] → JSON / Markdown → note・YouTube企画
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
│   ├── main.py                   # BlueSky→Discord エントリポイント
│   ├── x_mirror.py               # X→BlueSky エントリポイント
│   └── x_recent.py               # X本人ポストの読み取り専用エクスポート
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
| `X_USER_ID` / `X_SCREEN_NAME` | X入力時 | 本人のXユーザーIDとscreen name |
| `X_CLIENT_ID` / `X_CLIENT_SECRET` | X入力時 | OAuth 2.0アプリ資格情報 |
| `X_ACCESS_TOKEN` / `X_REFRESH_TOKEN` | X入力時 | 本人のユーザーコンテキストtoken pair |
| `X_ENV_FILE` | Xミラー時 | token更新を書き戻すdotenvの絶対パス |

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
