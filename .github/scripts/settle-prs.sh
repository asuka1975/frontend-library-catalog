#!/usr/bin/env bash
#
# レビュージョブが出した評決に従って Dependabot PR を片付ける。
#
# 判断はしない。ここは評決を実行するだけの場所で、MERGE なら（検証が通れば）
# マージ、HOLD ならクローズ、評決が無ければ何もせず open のまま残す。
# 結果は 1 PR 1 行の JSON Lines として $RESULTS に書き出し、リリースコミットの
# メッセージ生成に渡す。
#
# 唯一の例外が「触っているファイル」の検査で、これだけはモデルの評決より前に、
# このスクリプトが機械的に見る。ここはモデルの読み間違いに委ねてよい種類の
# 判断ではないし、判定に解釈の余地も無い。
#
# 環境変数:
#   VERDICT_DIR  評決 JSON (<PR番号>.json) が置かれたディレクトリ   既定: artifacts
#   PRS_JSON     gh pr list の出力                                  既定: prs.json
#   RESULTS      結果の書き出し先 (JSON Lines)                      既定: results.jsonl
#   DRY_RUN      true ならマージもクローズもせず記録だけ            既定: false
#   FUGU_MODEL   クローズ理由のコメントに書くモデル名               既定: Fugu
#   GH_TOKEN     pull-requests:write / contents:write のトークン

set -euo pipefail

VERDICT_DIR=${VERDICT_DIR:-artifacts}
PRS_JSON=${PRS_JSON:-prs.json}
RESULTS=${RESULTS:-results.jsonl}
DRY_RUN=${DRY_RUN:-false}
MODEL=${FUGU_MODEL:-Fugu}

# Dependabot の rebase 待ち。SKILL.md と同じく 10 分で諦める。
POLL_INTERVAL=${POLL_INTERVAL:-30}
POLL_ATTEMPTS=${POLL_ATTEMPTS:-20}

: > "$RESULTS"

log() { printf '%s\n' "$*"; }

# クローズ理由のコメントを組み立てる。理由はモデルが書いた文字列なので、長すぎるときは
# 切る。読む人にとってこれは通知であって記録ではない。全文は評決アーティファクトと
# リリースコミットに残るので、実行へのリンクを添えて追えるようにしておく。
close_comment() {
  local reason=$1 body link=""
  reason=$(jq -rn --arg s "$reason" 'if ($s | length) > 500 then ($s[0:500] + "…") else $s end')
  if [ -n "${GITHUB_RUN_ID:-}" ]; then
    link=$(printf '\n\n[レビューの全文はこの実行の成果物にあります](%s/%s/actions/runs/%s)' \
      "${GITHUB_SERVER_URL:-https://github.com}" "${GITHUB_REPOSITORY:-}" "$GITHUB_RUN_ID")
  fi
  body=$(printf '%s によるレビューの結果、この更新は取り込まずクローズします。\n\n**理由**: %s\n\n判断が誤っている場合は PR を reopen してください。' \
    "$MODEL" "$reason")
  printf '%s%s' "$body" "$link"
}

# 触ってよいファイルかを見る。Dependabot の PR は npm 更新なら package.json と
# pnpm-lock.yaml、GitHub Actions 更新なら .github/workflows/*.yml しか動かさない。
# それ以外が混ざっていたら、評決が MERGE でも取り込まない。
#
# 許可されないパスを標準出力に出し、1 つでもあれば 1 を返す。
disallowed_files() {
  local pr=$1 files
  # gh の失敗を「許可されないファイルは無かった」と読み違えないよう、取得と
  # 絞り込みを分ける。取得に失敗したらここで set -e が実行ごと止める。
  files=$(gh pr view "$pr" --json files --jq '.files[].path')
  printf '%s\n' "$files" \
    | grep -Ev '^(package\.json|pnpm-lock\.yaml|\.github/workflows/[^/]+\.ya?ml)$' || true
}

# 評決を読む。ファイルが無い / 壊れている / verdict が MERGE|HOLD でない場合は
# ERROR を返す。ERROR は「調べていない」であって「問題なし」ではないので、
# その PR には一切手を触れない。
read_verdict() {
  local pr=$1 file="$VERDICT_DIR/$1.json"
  if [ ! -f "$file" ] || ! jq -e . "$file" >/dev/null 2>&1; then
    jq -n --argjson pr "$pr" '{
      pr: $pr, verdict: "ERROR",
      reason: "レビュー結果を取得できなかった",
      updates: "", checked: "", notes: "",
      unverified: ["レビュー自体が完了していないため、脆弱性・上流差分ともに未確認"]
    }'
    return
  fi
  jq --argjson pr "$pr" '{
    pr: $pr,
    verdict: (if (.verdict == "MERGE" or .verdict == "HOLD") then .verdict else "ERROR" end),
    reason: (.reason // ""), updates: (.updates // ""), checked: (.checked // ""),
    notes: (.notes // ""),
    unverified: (.unverified // [])
  }' "$file"
}

record() { # $1: 評決 JSON, $2: outcome
  local title
  title=$(jq -r --argjson pr "$(jq -r .pr <<<"$1")" \
    '.[] | select(.number == $pr) | .title' "$PRS_JSON")
  jq -c --arg outcome "$2" --arg title "$title" \
    '. + {outcome: $outcome, title: $title}' <<<"$1" >> "$RESULTS"
}

# マージ可能になるまで待つ。競合していたら Dependabot に作り直させる。
# 自分で競合を解決して force push しないこと。pnpm-lock.yaml を手で直したり
# pnpm update で PR の内容を再現するのも同じ理由で禁止で、どちらもレビューを
# 迂回して、レビューされていない解決結果を main に入れることになる。
wait_mergeable() {
  local pr=$1 rebased=0 state i
  for ((i = 1; i <= POLL_ATTEMPTS; i++)); do
    state=$(gh pr view "$pr" --json mergeable --jq .mergeable)
    case "$state" in
      MERGEABLE)
        return 0
        ;;
      CONFLICTING)
        if [ "$rebased" -eq 0 ]; then
          log "  #$pr は競合している。@dependabot rebase を依頼する"
          gh pr comment "$pr" --body "@dependabot rebase"
          rebased=1
        fi
        ;;
      *)
        # UNKNOWN。直前のマージを受けて GitHub が再計算している最中。
        ;;
    esac
    sleep "$POLL_INTERVAL"
  done
  log "  #$pr は ${POLL_ATTEMPTS}x${POLL_INTERVAL}s 待っても MERGEABLE にならなかった"
  return 1
}

# PR のブランチを検証する。このリポジトリの生成物はカタログ（バージョンの組）
# そのものなので、「全部が一緒に解決できること」が検証の本体になる。
#
# --frozen-lockfile なのは、Dependabot が作った pnpm-lock.yaml が package.json と
# 一致していることまで見たいため。ここを普通の install にすると、食い違いを
# その場で直してしまって気づけない。
#
# 途中で失敗しても main に戻って ci-verify を消す。&& で繋いでいるのは、fetch や
# checkout が失敗したまま pnpm まで進むと、別のブランチを検証して「通った」と
# 誤認するため。
verify_branch() {
  local branch=$1 rc=0
  git fetch --force origin "$branch:refs/heads/ci-verify" \
    && git checkout ci-verify \
    && verify_workflow_yaml \
    && pnpm install --frozen-lockfile \
    && pnpm test \
    || rc=$?
  git checkout main || true
  git branch -D ci-verify >/dev/null 2>&1 || true
  return "$rc"
}

# ワークフローの YAML が壊れていないか。GitHub Actions の更新 PR は
# .github/workflows/ を書き換えるので、構文が壊れたものを main に入れると
# この仕組み自体が次から動かなくなる。
verify_workflow_yaml() {
  local f
  # PyYAML が無い環境で全 PR のマージを止めるほどの検査ではない。飛ばしたことは残す。
  python3 -c 'import yaml' 2>/dev/null \
    || { log "  PyYAML が無いので workflow の YAML 検査は飛ばす"; return 0; }
  for f in .github/workflows/*.yml .github/workflows/*.yaml; do
    [ -f "$f" ] || continue
    python3 -c 'import sys, yaml; yaml.safe_load(open(sys.argv[1], encoding="utf-8"))' "$f" \
      || { log "  $f が YAML として読めない"; return 1; }
  done
}

# ---- 1. 評決を集める --------------------------------------------------------

mapfile -t numbers < <(jq -r '.[].number' "$PRS_JSON")
declare -a to_merge=()

for pr in "${numbers[@]}"; do
  verdict_json=$(read_verdict "$pr")
  verdict=$(jq -r .verdict <<<"$verdict_json")
  reason=$(jq -r .reason <<<"$verdict_json")
  log "#$pr: $verdict — $reason"

  # 評決より先に、触っているファイルを見る。MERGE でもここで落ちたら取り込まない。
  #
  # クローズはしない。author を app/dependabot に絞っている以上、ここに引っかかるのは
  # 「攻撃者が紛れ込んだ」ではなく「このリポジトリの前提が変わった」場合である
  # （pnpm が pnpm-workspace.yaml を書き足した、など）。人が見て決めることなので、
  # 取り込まないまま open で残し、実行サマリとリリースコミットに理由を書く。
  if [ "$verdict" = "MERGE" ]; then
    bad=$(disallowed_files "$pr" | paste -sd' ' -)
    if [ -n "$bad" ]; then
      log "  Dependabot が触らないはずのファイルを変更している: $bad"
      record "$(jq --arg bad "$bad" \
        '.verdict = "HOLD" |
         .reason = "Dependabot の PR が触らないはずのファイルを変更している: \($bad)（PR は open のまま）"' \
        <<<"$verdict_json")" "left_open"
      continue
    fi
  fi

  case "$verdict" in
    MERGE)
      to_merge+=("$pr")
      ;;
    HOLD)
      if [ "$DRY_RUN" = "true" ]; then
        log "  [dry-run] クローズしない"
        record "$verdict_json" "dry-run"
      else
        gh pr comment "$pr" --body "$(close_comment "$reason")"
        gh pr close "$pr"
        record "$verdict_json" "closed"
      fi
      ;;
    *)
      log "  評決が無いので触らない（open のまま残す）"
      record "$verdict_json" "left_open"
      ;;
  esac
done

# ---- 2. マージする ----------------------------------------------------------
#
# 1 件ずつ処理する。全ての PR が package.json と pnpm-lock.yaml を書き換えるため、
# 1 つマージすると残りが競合することがよくある。
#
# 厄介なのは競合「しなかった」ケースで、git は pnpm-lock.yaml を自動マージできて
# しまい、その結果が package.json と食い違うことがある。だから verify_branch の
# --frozen-lockfile と、マージ後の main での再検証（ワークフロー側）を省略しない。

for pr in "${to_merge[@]}"; do
  verdict_json=$(read_verdict "$pr")
  branch=$(jq -r --argjson pr "$pr" '.[] | select(.number == $pr) | .headRefName' "$PRS_JSON")

  if [ "$DRY_RUN" = "true" ]; then
    log "#$pr: [dry-run] $branch を検証するだけでマージしない"
    if verify_branch "$branch"; then
      record "$verdict_json" "dry-run"
    else
      record "$(jq '.verdict = "HOLD" | .reason = "検証（pnpm install --frozen-lockfile && pnpm test）が通らなかった" |
                    .unverified += ["検証失敗のため上流の妥当性以前に取り込めない"]' \
                 <<<"$verdict_json")" "dry-run"
    fi
    continue
  fi

  log "#$pr: マージ可能になるのを待つ"
  if ! wait_mergeable "$pr"; then
    record "$(jq '.verdict = "HOLD" |
                  .reason = "競合が解消されずマージできなかった（PR は open のまま）"' \
               <<<"$verdict_json")" "left_open"
    continue
  fi

  log "#$pr: $branch を検証する"
  if ! verify_branch "$branch"; then
    log "  検証が通らないので HOLD 扱いにする"
    record "$(jq '.verdict = "HOLD" | .reason = "検証（pnpm install --frozen-lockfile && pnpm test）が通らなかった（PR は open のまま）" |
                  .unverified += ["検証失敗のため取り込み後の挙動は未確認"]' \
               <<<"$verdict_json")" "left_open"
    continue
  fi

  log "#$pr: マージする"
  # マージ失敗で実行ごと止めない。ブランチ保護、必須チェックの未達、権限など、
  # 拒否の理由はこちらから制御できない。その 1 件を open のまま残して、他の PR と
  # リリースは進める。
  if ! gh pr merge "$pr" --squash --delete-branch; then
    log "  マージが拒否された。open のまま残す"
    record "$(jq '.verdict = "HOLD" |
                  .reason = "レビューは通ったがマージが拒否された（PR は open のまま。実行ログを参照）"' \
               <<<"$verdict_json")" "left_open"
    continue
  fi
  git checkout main
  git pull --ff-only origin main
  record "$verdict_json" "merged"
done

log ""
log "結果:"
jq -r '"  #\(.pr) \(.outcome) (\(.verdict))"' "$RESULTS"
