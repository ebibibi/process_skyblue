"""KEY<TAB>VALUE の組を .env へ反映する。set_x_credentials.sh から呼ばれる。

シェルのヒアドキュメントでスクリプトとデータの両方を渡そうとすると、
後ろのリダイレクトが stdin を奪ってスクリプト本体が届かない。
だからデータはファイル経由で渡し、この処理は独立したファイルに置く。
"""
import re
import sys


def main(src: str, pairs_path: str, dst: str) -> None:
    new: dict[str, str] = {}
    with open(pairs_path, encoding="utf-8") as f:
        for line in f.read().splitlines():
            if not line:
                continue
            key, _, value = line.partition("\t")
            new[key] = value

    out: list[str] = []
    seen: set[str] = set()
    with open(src, encoding="utf-8") as f:
        for line in f.read().splitlines():
            match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)=", line)
            if match and match.group(1) in new:
                key = match.group(1)
                out.append(f"{key}={new[key]}")
                seen.add(key)
            else:
                out.append(line)

    for key, value in new.items():
        if key not in seen:
            out.append(f"{key}={value}")

    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
