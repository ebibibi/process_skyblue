#!/usr/bin/env bash
# X (Twitter) API の資格情報を .env へ安全に書き込む。
#
# 手で .env を開いて編集すると、1行消す・改行を混ぜる・値に余計な空白が入る、が起きうる。
# このスクリプトは対話入力（エコーなし）で受け取り、一時ファイルへ書いてから
# mv で原子的に置き換える。値は一度も画面に出さず、シェル履歴にも残らない。
#
#   X_ENV_FILE=/path/to/.env bash scripts/set_x_credentials.sh
set -euo pipefail

ENV_FILE="${X_ENV_FILE:?X_ENV_FILE is not set}"
KEYS=(X_CONSUMER_KEY X_CONSUMER_SECRET X_CLIENT_ID X_CLIENT_SECRET X_ACCESS_TOKEN X_REFRESH_TOKEN)

[ -f "$ENV_FILE" ] || { echo "ERROR: $ENV_FILE が無い" >&2; exit 1; }

echo "X の資格情報を入力する。空Enterでその項目は今の値のまま。"
echo "（入力は画面に表示されない）"
echo

PAIRS="$(mktemp)"; TMP="$(mktemp)"
trap 'rm -f "$PAIRS" "$TMP"' EXIT
chmod 600 "$PAIRS" "$TMP"

count=0
for k in "${KEYS[@]}"; do
    IFS= read -rsp "  $k: " v; printf '\n'
    # 前後の空白・CR を落とす。コピペで混入すると 401 の原因になり、見た目では気づけない。
    v="$(printf '%s' "$v" | tr -d '\r' | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
    if [ -n "$v" ]; then printf '%s\t%s\n' "$k" "$v" >> "$PAIRS"; count=$((count+1)); fi
done

if [ "$count" -eq 0 ]; then echo "変更なし。終了。"; exit 0; fi

# 既存行を置換しつつ、無いキーは末尾へ足す。他の行は1バイトも触らない。
python3 "$(dirname "$0")/_apply_env_pairs.py" "$ENV_FILE" "$PAIRS" "$TMP"

mv "$TMP" "$ENV_FILE"; trap 'rm -f "$PAIRS"' EXIT
chmod 600 "$ENV_FILE"

echo
echo "書き込み完了: $ENV_FILE (perm $(stat -c %a "$ENV_FILE"))"
echo "--- 現在のキー（値は伏せる） ---"
sed -E 's/=.*/=<設定済み>/' "$ENV_FILE" | grep '^X_' || true
