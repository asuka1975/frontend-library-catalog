---
name: dependabot-merge
description: Reviews this pnpm catalog repository's open Dependabot pull requests for security and upstream-change risk, merges the ones that are clean, then bumps the patch version, pushes a release tag whose commit message carries the full review record, and publishes the new version to npm. Use this whenever the user mentions Dependabot, dependency update PRs, "依存更新", bumping library versions, or asks to review/merge/release the pending version-bump PRs — including phrasings that never say "Dependabot", such as "溜まってる更新PRを見て問題なければ入れて" or "ライブラリ上げてリリースして".
---

# Dependabot PR のレビューとリリース

このリポジトリは `package.json` の `devDependencies` だけがバージョンの情報源です。
Dependabot の PR はほぼ全て、package.json の数行と pnpm-lock.yaml(自動生成)を
書き換えるだけです。つまり **差分を見ても数字しか分かりません。確認すべき実体は
上流リポジトリと npm レジストリにあります。**

役割分担がこのスキルの要点です。

- **あなた(このスキルを実行する側)** — 手順の進行、マージ、リリース。判断は
  サブエージェントの評決に従います。自分で脆弱性を調べようとしないでください。
- **Opus のサブエージェント** — PR ごとの脆弱性・上流差分レビュー。ここは
  「リリースノートに書かれていない変更を見抜く」作業で、能力差がそのまま
  見落としになるため、意図的に上位モデルへ回しています。

## 0. 前提を確認する

```bash
gh auth status
git status --porcelain            # 空であること
git rev-parse --abbrev-ref HEAD   # main であること
git fetch origin && git status -sb # origin/main と乖離していないこと
npm whoami                        # 最後の publish に必要(無くても進める)
```

作業ツリーが汚れている、main 以外にいる、origin より進んでいる —— どれか一つでも
当てはまるなら、片付けようとせずユーザーに伝えて止まってください。マージとタグ
push は取り消しが面倒なので、前提が崩れたまま進める価値はありません。

`npm whoami` だけは例外です。認証が無くても止まらず進めてください。マージと
バージョン上げは npm 認証と無関係で、最後の publish だけが残ります(手順 6 参照)。

## 1. 対象の PR を集める

```bash
gh pr list --author "app/dependabot" --state open \
  --json number,title,url,mergeable,headRefName
```

0 件なら「更新 PR はありません」と伝えて終了です。バージョンも上げません。

PR ごとに、更新されるパッケージと旧→新バージョンを確定させます。

```bash
gh pr view <番号> --json title,body
gh pr diff <番号>
```

`.github/dependabot.yml` で `groups` を設定しているので、**1 つの PR が複数の
パッケージを同時に上げます**(tanstack なら 4 件)。package.json の diff から
「パッケージ名 旧 -> 新」を全部列挙してください。この一覧をサブエージェントに渡します。

pnpm-lock.yaml の差分は読まないでください。自動生成物で巨大なうえ、人が読んで
分かる情報は package.json 側に全部あります。ただし **package.json と
pnpm-lock.yaml 以外のファイルを触っている PR は、それだけで HOLD** です。
Dependabot の PR がこの 2 ファイル以外を動かすことはありません。

## 2. 脆弱性レビューを Opus に投げる

**PR ごとに 1 エージェント。独立した作業なので、全 PR 分を同じメッセージ内で
まとめて起動してください**(逐次に投げると待ち時間が PR 数だけ積み上がります)。

Agent ツールで `model: "opus"`、`subagent_type: "general-purpose"` を指定し、
次のテンプレートの `<...>` を埋めて渡します。

```
あなたは Dependabot PR のセキュリティレビュー担当です。調査だけを行い、
リポジトリの状態を変更しないでください(merge / commit / push / ブランチ操作は禁止)。

対象 PR: #<番号> <タイトル>
更新されるパッケージ:
<パッケージ名 旧バージョン -> 新バージョン を1行ずつ>

次の 4 点を必ず確認してください。

1. 既知の脆弱性
   gh api -X GET /advisories -f ecosystem=npm -f affects="<パッケージ名>" \
     --jq '.[] | {ghsa: .ghsa_id, severity, summary,
                  ranges: [.vulnerabilities[] | select(.package.name == "<パッケージ名>")
                           | {vulnerable: .vulnerable_version_range, patched: .first_patched_version}]}'
   をパッケージごとに実行する。新バージョンが vulnerable_version_range に入っていれば
   「脆弱なバージョンへの更新」なので HOLD。旧バージョンだけが範囲内で新バージョンが
   外れているなら、それはセキュリティ修正の取り込みなので明記する。

2. 上流のリリースノート
   PR 本文に埋め込まれたリリースノートを読む。足りなければ
   npm view <パッケージ名> repository.url
   で上流を引き、gh release view <タグ> --repo <owner>/<repo> を見る。
   破壊的変更・非推奨化・新しい依存の追加・ライセンス変更を見る。

3. 上流のコード差分
   gh api repos/<owner>/<repo>/compare/<旧タグ>...<新タグ> --jq '.files[].filename'
   タグ名は v 付きのことが多く、monorepo では <パッケージ名>@<バージョン> 形式もある。
   見つかるまで試す。リリースノートに書かれていない変更を見つけるのが目的。
   差分が大きいときは package.json の scripts と dependencies、CI 設定
   (.github/workflows/)、新規のネットワークアクセスや child_process / eval、
   依存の追加・置換、見慣れないコミット作者、難読化やエンコードされた文字列を
   優先して見る。タグが存在せず差分が取れない場合は、その事実を必ず報告に
   含めること(「確認した」と書かないこと)。

4. npm レジストリ上の実物
   git の差分と npm に上がる tarball は別物で、公開時にだけ仕込まれる攻撃がある。
   npm view <パッケージ名>@<新バージョン> scripts
   npm view <パッケージ名>@<旧バージョン> scripts
   を比べ、preinstall / install / postinstall が「増えて」いたら最大級の警戒信号。
   同様に npm view ... dependencies を新旧で比べ、推移的依存の追加・置換を見る。

最後に、必ずこの形式で終えてください。

VERDICT: MERGE または HOLD
REASON: 1 行の理由
DETAIL:
(確認内容。表にできるならする。確認できなかったことも書く)

迷ったら HOLD。マージは後からできるが、入れたものを追うのは高くつく。
未修正の脆弱性 / 説明のつかない上流変更 / 破壊的変更 / メジャーアップ /
install scripts の追加 / リリースノートも差分も確認できない、のいずれかなら HOLD。
```

評決が出るまで待ちます。**あなたが評決を上書きしないでください。**
HOLD の PR はマージせず、理由をそのまま報告に載せます。

## 3. マージする

VERDICT が MERGE の PR について、まず CI を確認します。

```bash
gh pr checks <番号>
```

全て pass していればマージへ。fail していたら HOLD 扱いにして報告してください。
チェックが 1 つも報告されない場合(CI が動いていない環境)は、ローカルで
同じ検証をします。

```bash
git fetch origin <ブランチ名>
git checkout <ブランチ名>
pnpm install --frozen-lockfile && pnpm test
git checkout main
```

通ったらマージします。

```bash
gh pr merge <番号> --squash --delete-branch
```

**1 件ずつ処理してください。** 全ての PR が package.json と pnpm-lock.yaml を
書き換えるため、1 つマージすると残りが競合することがよくあります。package.json の
隣接行を触る PR 同士(prettier と react のように並びが近いもの)は確実に衝突します。
これは異常ではなく、npm リポジトリの通常運転です。

厄介なのは競合「しなかった」ケースです。git は pnpm-lock.yaml を自動マージ
できてしまうことがあり、その結果が package.json と食い違うことがあります。
競合が出なかったことは lockfile が正しいことを意味しません。だから手順 4 の
`--frozen-lockfile` 検証が省略できないのです。

マージ後、残りの PR の状態を確認します。

```bash
gh pr view <番号> --json mergeable --jq .mergeable
```

`CONFLICTING` なら Dependabot に作り直させます。

```bash
gh pr comment <番号> --body "@dependabot rebase"
```

rebase には数分かかります。ポーリングして待ち、**10 分待っても `MERGEABLE` に
ならなければ止めて報告してください。** 自分で競合を解決して force push しては
いけません。pnpm-lock.yaml を手で編集したり、`pnpm update` で PR の内容を再現
するのも禁止です(どちらもレビューを迂回して、レビューされていない解決結果を
main に入れることになります)。Dependabot の PR を書き換えると Dependabot 側の
追跡が壊れ、次回以降おかしな PR が出ます。`--admin` やブランチ保護の迂回も
使わないでください。

## 4. バージョンを上げる

1 件でもマージできた場合だけ実行します。0 件なら上げるものが無いので飛ばします。

```bash
git checkout main && git pull origin main
node .claude/skills/dependabot-merge/scripts/next-version.mjs --apply
```

パッチ +1、X.Y.Z 形式の検査、タグの重複チェック、npm に publish 済みでないことの
チェックはこのスクリプトが行います。**手で計算しないでください。** npm は一度
publish したバージョンを二度と使えません(unpublish しても再利用不可)。ここの
間違いは publish まで進んでから発覚して高くつきます。スクリプトが非ゼロで
終了したら、その内容をユーザーに伝えて止まってください。

マージ後の main で、カタログ全体が今も一緒に解決できることを確認します。
このリポジトリの生成物はカタログ(バージョンの組)そのものなので、これが検証の本体です。

```bash
pnpm install --frozen-lockfile && pnpm test
```

`--frozen-lockfile` が失敗した場合、原因はほぼ「git が lockfile を自動マージした
結果が package.json と食い違っている」です。その場合だけ、機械的に追従させます。

```bash
pnpm install --lockfile-only
```

これはバージョン選択のやり直しではなく、マージ済みの package.json に lockfile を
合わせるだけの操作です。再生成した pnpm-lock.yaml はリリースコミットに含め、
報告の「確認できなかったこと」ではなく本文にその旨を書いてください。

## 5. 報告をコミットログに残して push する

**このスキルの成果物はコミットログです。** カタログのバージョンだけを見ても、
何がどういう根拠で入ったのかは分かりません。`git log` にレビュー内容が残っていれば、
後から「なぜこのバージョンなのか」を追えます。ユーザーへのチャット出力は消えます。

報告を組み立ててファイルに書き、それをコミットメッセージにします。
**3 つの見出しは常に全部書いてください。** 該当が無ければ「なし」と書きます。
見出しごと省くと、後から読んだ人には「該当が無かった」のか「調べていない」のか
区別がつきません。それが分からない記録は、無いのとあまり変わりません。

```bash
cat > /tmp/release-notes.txt <<'EOF'
Bump version to <新バージョン>

## マージした PR

| PR | 更新内容 | 確認したこと |
| --- | --- | --- |
| #12 | @tanstack/* 5.100.0 -> 5.101.4 (4 件) | 脆弱性なし / 破壊的変更なし / install scripts 追加なし / 上流差分に不審な変更なし |

## 保留した PR

| PR | 更新内容 | 保留した理由 |
| --- | --- | --- |
| #15 | zod 3.25.76 -> 4.4.3 | メジャーアップ。スキーマ API が変わり利用側のコードが壊れる |

## 確認できなかったこと

- #12: 上流の一部タグが無く、タグ間差分は取得できていない
EOF

git add package.json   # lockfile を再生成した場合は pnpm-lock.yaml も
git commit -F /tmp/release-notes.txt
git tag <新バージョン>
git push origin main
git push origin <新バージョン>
```

各サブエージェントが返した DETAIL をそのまま貼るのではなく、表の 1 行に畳んでください。
畳んでよいのは根拠の細かさだけです。**HOLD の理由と、サブエージェントが「確認できなかった」
と報告した項目は、1 つ残らずコミットログに移してください。** ユーザーへのチャットにだけ
書いて済ませないこと。そこが後から効いてくる情報で、チャットは残りません。
セキュリティ修正を取り込んだ更新があれば目立つ位置に書きます。

## 6. npm へ publish する

タグを push しただけでは利用側に届きません。JitPack と違い、npm はレジストリへの
publish がリリースです。

```bash
pnpm publish --access public
```

出力に新しいバージョンが表示されれば完了です。

認証が無いなどの理由で publish できなかった場合は、失敗を握りつぶさず、
「タグ <新バージョン> まで完了、publish は未実施。`npm login` のうえ
`pnpm publish --access public` を実行すれば追いつける」と明確に報告してください。
`npm login` を代行しないでください(対話認証はユーザーの作業です)。publish の
失敗を理由に、push 済みのタグやコミットを巻き戻してもいけません。

## 7. ユーザーに伝える

コミットログに全部入っているので、チャットには要約だけで十分です。

- マージした PR の番号と更新内容
- 保留した PR と、その理由
- 新しいバージョンとタグ
- publish の結果(未実施ならその旨と追いつき方)
- 判断を仰ぎたいことがあればそれ
