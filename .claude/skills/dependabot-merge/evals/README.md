# dependabot-merge の評価ハーネス

GitHub に触らずにスキルを検証するための一式です。`origin` をローカルの bare
リポジトリにし、`gh` を差し替えることで、マージ・タグ・push まで本物の git
操作として実行しつつ、外部には一切影響しません。

`gh api` と `gh release` は本物の gh に委譲するので、脆弱性照会と上流差分は
ライブのデータを見ます。ここを模擬すると検証の意味が無くなるためです。
同様に、fixture の生成と `@dependabot rebase` の再現では本物の pnpm が
実レジストリを叩いて pnpm-lock.yaml を再生成します(Dependabot の PR は必ず
lockfile を書き換えるので、ここを省くと `--frozen-lockfile` 検証が嘘になります)。

## 使い方

```bash
# fixture を作る(scenario は clean / vulnerable / major_conflict)
python3 setup.py vulnerable /tmp/fx

# 差し替えた gh を使う
export FIXTURE_DIR=/tmp/fx
export PATH=$(pwd):$PATH      # この評価ディレクトリの gh を先に見せる

cd /tmp/fx/repo
# ここでスキルを実行させる

# 採点(レポートではなく git の実状態を見る)
python3 grade.py <config_dir>
```

## シナリオ

| scenario | 内容 | 期待 |
| --- | --- | --- |
| `clean` | @tanstack/* 5.100.0->5.101.4(グループ 4 件)、zustand 5.0.13->5.0.14 | 両方マージ、1.0.1 へ |
| `vulnerable` | prettier 3.9.5->3.9.6、minimist 1.2.0->1.2.5(GHSA-xvch-5gv4-984h の patched 1.2.6 未満に留まる) | minimist は保留 |
| `major_conflict` | zod 3.25.76->4.4.3(メジャー)、prettier と react が package.json の隣接行で競合 | メジャーは保留、競合は @dependabot rebase で解消 |

バージョンはすべて実在するものを使っています。捏造したバージョンにすると
上流差分の確認が実行されず、スキルの中核が検証されないまま通ってしまいます。

npm ならではの点が 2 つあります。

- **確実な競合源は package.json の隣接行です。** lockfile だけが絡むペア
  (react と @tanstack/* のような peer 依存)は、git が pnpm-lock.yaml を
  自動マージしてしまうことがあり、競合源として当てになりません(実測)。
  自動マージの結果が package.json と食い違うことがあるのはスキル側の論点で、
  `--frozen-lockfile` 検証で捕まえます。
- **publish は封じてあります。** fixture の package.json には到達不能なレジストリを
  指す `publishConfig` を入れ、pnpm-workspace.yaml の `fetchRetries` /
  `fetchTimeout` で即時失敗させています(0.3 秒で ECONNREFUSED)。エージェントが
  publish まで進んでも実 npm には絶対に届きません(npm ログイン済みのマシンでも
  安全)。publish が失敗した事実を正直に報告できるかは、eval-0 の採点対象です。

## 注意

スキルはセッション単位で登録されるため、fixture から `.claude/skills/` を
消しても「スキルなし」の比較対象にはなりません。A/B を取るには、そのスキルが
登録されていないプロジェクトでセッションを開始してください。
