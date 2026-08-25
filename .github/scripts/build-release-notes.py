#!/usr/bin/env python3
"""settle-prs.sh の結果からリリースコミットのメッセージを組み立てる。

このワークフローの成果物はコミットログである。カタログのバージョンだけを見ても、何が
どういう根拠で入ったのかは分からない。git log にレビュー内容が残っていれば、後から
「なぜこのバージョンなのか」を追える。Actions のログは 90 日で消える。

3 つの見出しは常に全部出す。該当が無ければ「なし」と書く。見出しごと省くと、後から
読んだ人には「該当が無かった」のか「調べていない」のか区別がつかない。

usage:
  build-release-notes.py --results results.jsonl --version 1.0.1 --out notes.txt
"""
import argparse
import json
import os
import sys

HELD_OUTCOME_SUFFIX = {
    "closed": "（クローズ済み）",
    "left_open": "（PR は open のまま）",
    "dry-run": "（dry-run のため未処理）",
}


def cell(text):
    """Markdown の表の 1 セルに収める。改行と | が入ると表が壊れる。"""
    return " ".join(str(text).split()).replace("|", "\\|") or "-"


def table(header, rows):
    if not rows:
        return "なし"
    out = ["| " + " | ".join(header) + " |",
           "| " + " | ".join("---" for _ in header) + " |"]
    out += ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", required=True)
    # どのモデルが判断したかは記録の一部。後からモデルを変えたとき、過去のコミットが
    # 何にレビューされたのか分からなくなるので、実際に使った名前をそのまま残す。
    ap.add_argument("--model", default=os.environ.get("FUGU_MODEL", "Fugu"))
    # git が pnpm-lock.yaml を自動マージした結果が package.json と食い違い、
    # lockfile を作り直した場合に立てる。何を触ったかは本文に残す。
    ap.add_argument("--lockfile-regenerated", action="store_true")
    args = ap.parse_args()

    with open(args.results, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    merged, held, unverified = [], [], []

    for r in sorted(records, key=lambda r: r["pr"]):
        pr = f"#{r['pr']}"
        updates = r.get("updates") or r.get("title") or ""

        if r.get("outcome") == "merged":
            # notes はセキュリティ以外の気づき（破壊的変更など）。マージの判断には
            # 使っていないが、利用側が知るべきことなので確認欄に併記する。
            checked = r.get("checked", "")
            notes = r.get("notes", "")
            merged.append([pr, updates, f"{checked} ／ 注意: {notes}" if notes else checked])
        else:
            reason = r.get("reason", "")
            suffix = HELD_OUTCOME_SUFFIX.get(r.get("outcome"), "")
            held.append([pr, updates, f"{reason}{suffix}"])

        for item in r.get("unverified") or []:
            unverified.append(f"- {pr}: {' '.join(str(item).split())}")

    if not merged:
        print("ERROR: マージした PR が 1 件も無い。バージョンを上げる理由が無いので"
              " リリースコミットは作らない。", file=sys.stderr)
        return 1

    lockfile_note = []
    if args.lockfile_regenerated:
        lockfile_note = [
            "",
            "pnpm-lock.yaml は `pnpm install --lockfile-only` で作り直しています。"
            " git が自動マージした lockfile がマージ後の package.json と食い違っていたためで、"
            " バージョン選択のやり直しではありません。",
        ]

    body = "\n".join([
        f"Bump version to {args.version}",
        "",
        "## マージした PR",
        "",
        table(["PR", "更新内容", "確認したこと"], merged),
        "",
        "## 保留した PR",
        "",
        table(["PR", "更新内容", "保留した理由"], held),
        "",
        "## 確認できなかったこと",
        "",
        "\n".join(unverified) if unverified else "なし",
        *lockfile_note,
        "",
        f"レビューは codex-fugu ({args.model}) が PR ごとに実行しました。",
        f"タグ {args.version} を push した実行が、同じ内容を npm に publish します。",
        "",
    ])

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(body)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
