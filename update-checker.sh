#!/bin/bash
# Process SkyBlue 自動更新スクリプト
# git pull して変更があれば Docker イメージを再ビルドしサービスを再起動
#
# 注意: このスクリプトは root で実行される（systemctl restart のため）
# git/docker 操作は runuser でユーザーとして実行

set -e

REPO_DIR="/path/to/process_skyblue"  # 実際のパスに合わせて変更してください
LOG_TAG="process-skyblue-updater"
RUN_USER="your-username"  # 実際のユーザー名に合わせて変更してください

log() {
    logger -t "$LOG_TAG" "$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 指定ユーザーとしてコマンドを実行
run_as_user() {
    runuser -u "$RUN_USER" -- "$@"
}

cd "$REPO_DIR"

# 現在のコミットハッシュを取得
OLD_HASH=$(run_as_user git rev-parse HEAD)

# リモートの更新を取得
log "Fetching remote changes..."
run_as_user git fetch origin main

# リモートのハッシュを取得
REMOTE_HASH=$(run_as_user git rev-parse origin/main)

# 変更があるかチェック
if [ "$OLD_HASH" = "$REMOTE_HASH" ]; then
    log "No changes detected. Current: $OLD_HASH"
    exit 0
fi

log "Changes detected! Old: $OLD_HASH -> New: $REMOTE_HASH"

# 変更をプル
log "Pulling changes..."
run_as_user git pull origin main

# Docker イメージを再ビルド
log "Rebuilding Docker image..."
run_as_user docker build -t process-skyblue .

# サービスを再起動（root で実行されているので sudo 不要）
log "Restarting service..."
systemctl restart process-skyblue.service

log "Update complete! Service restarted with new code."
