# frontend-library-catalog

複数の React プロジェクトで使うライブラリの**バージョンを統一する**ためのカタログです。
pnpm の catalog と config dependency を組み合わせ、1 つの npm パッケージとして発行します。

利用側は依存にバージョンを書かず、`catalog:` とだけ書きます。

```json
{
  "dependencies": {
    "react": "catalog:",
    "zustand": "catalog:",
    "@tanstack/react-query": "catalog:"
  }
}
```

```
frontend-library-catalog/
├── package.json          ← ここにバージョンを書く（devDependencies が正本）
├── catalog.mjs           ← devDependencies をカタログとして公開する
├── pnpmfile.mjs          ← pnpm が読み込むフック
├── pnpm-workspace.yaml   ← このリポジトリ自身の設定（公開物には含めない）
├── scripts/, test/
└── .github/
    ├── dependabot.yml
    ├── workflows/dependabot-review-release.yml   ← レビュー・マージ・リリース
    └── scripts/                                  ← ワークフローから呼ぶ部品
```

## kotlin-library-catalog との違い

| | kotlin-library-catalog | frontend-library-catalog |
| --- | --- | --- |
| 仕組み | `java-platform` の BOM | pnpm catalog + config dependency |
| 定義場所 | `build.gradle.kts` の `constraints` | `package.json` の `devDependencies` |
| 利用側の書き方 | `implementation("io.ktor:ktor-client-cio")` | `"react": "catalog:"` |
| 配布 | JitPack（git タグから） | npm レジストリ |
| 利用側と衝突したとき | 高い方が選ばれる | **利用側が優先** |

衝突時の挙動が逆である点に注意してください。BOM は Gradle が高い方を選びますが、
このカタログは利用側の `pnpm-workspace.yaml` に同名の定義があればそちらを優先します。
カタログ全体を捨てずに、必要な 1 つだけ差し替えられるようにするためです。

### JitPack に相当する配布方法はありません

config dependency は integrity（ハッシュ）の検証を必須にしているため、
ローカルの tgz や git 参照では入りません。次のように拒否されます。

```
[ERROR] Cannot resolve @asuka1975/pnpm-plugin-frontend-library-catalog@file:../catalog.tgz
        as a configuration dependency because it has no integrity
```

npm レジストリへの publish が必要です。

## 仕組み

pnpm の catalog はそのままでは 1 つのワークスペース内でしか共有できません。
リポジトリをまたいで配るために config dependency を使います。

```
利用側の pnpm-workspace.yaml
└── configDependencies
    └── @asuka1975/pnpm-plugin-frontend-library-catalog: 1.0.0
            │
            │ pnpm が通常の依存より先にインストールし、
            │ パッケージ名が @<scope>/pnpm-plugin-* なので
            │ pnpmfile.mjs を自動で読み込む
            ↓
        updateConfig フック
            └── config.catalogs.default にカタログを流し込む
                    ↓
            利用側の "react": "catalog:" が解決される
```

パッケージ名の `pnpm-plugin-` は必須です。pnpm が `pnpmfile.mjs` を自動で読み込むのは
`pnpm-plugin-*` / `@<scope>/pnpm-plugin-*` / `@pnpm/plugin-*` のいずれかに一致する名前だけです。
名前を変えるときはこの規則を外さないでください（`pnpm test` で検査しています）。

## ライブラリを追加・更新する

`package.json` の `devDependencies` を編集します。

```json
{
  "devDependencies": {
    "zustand": "^5.0.14"
  }
}
```

これだけです。`catalog.mjs` は `devDependencies` をそのまま公開しているので、
編集は不要です。

### なぜ devDependencies なのか

1. **Dependabot と Renovate がそのまま解釈できる。**
   バージョンを独自形式のファイルに書くと、更新は全部手作業になります。
2. **config dependency は通常の `dependencies` を持てない。**
   `devDependencies` は利用側にインストールされないので、この制約に抵触しません。
3. **`pnpm install` が組み合わせの検証になる。**
   カタログに載せた全ライブラリが実際に一緒に解決できるかを、このリポジトリで確認できます。

## Dependabot と自動リリース

更新 PR のレビューからリリースまでは
`.github/workflows/dependabot-review-release.yml` が毎週やります。手で回したいときは
`/dependabot-merge`（`.claude/skills/dependabot-merge/`）を使います。手順は同じで、
レビューするモデルだけが違います（CI は codex-fugu、手元は Opus）。

```
月曜 09:00 JST  Dependabot が package.json を走査して更新 PR を作る
      │ 15 時間
火曜 00:00 JST  ワークフローが起きる
      ↓
   collect   開いている Dependabot PR を列挙する
      ↓
   review    PR ごとに 1 ジョブ。codex-fugu が脆弱性・上流差分・npm 上の実物を
             調べ、MERGE / HOLD の評決を JSON で返す（トークンは読み取り専用）
      ↓
   apply     評決に従ってマージ / クローズ。マージ後の main で
             pnpm install --frozen-lockfile && pnpm test を通してから
             パッチを +1 してタグを push（レビュー内容はコミットメッセージに残る）
      ↓
   publish   タグの中身を npm に publish（trusted publishing）
```

ジョブを分けているのは権限のためです。レビューするモデルが読むのは上流のリリースノートや
npm レジストリの応答、つまり **攻撃者が書ける文章** です。それを読んだエージェント自身が
マージまでできてしまうと、このワークフローが防ごうとしている攻撃がそのまま通ります。
だから review ジョブのトークンは読み取り専用にし、マージとタグ push は評決 JSON だけを
受け取った apply ジョブが行い、publish ジョブには書き込み権限を持たせません。

判断するのはセキュリティだけです。破壊的変更・メジャーアップ・非推奨化は HOLD の理由に
しません（コミットログの「注意」欄に残します）。互換性の問題は利用側のビルドや型検査で
顕在化しますが、脆弱性は黙って通ります。見ているのは後者だけです。

### 用意するもの

- リポジトリの secret `SAKANA_API_KEY` — レビューに使う codex-fugu の API キー
- npm の trusted publisher 設定 — 下の「npm への publish」

### 試してから任せる

Actions のページから手で起動できます。`dry_run` は既定で on で、レビューと検証だけを行い、
マージ・クローズ・リリースはしません。評決は実行の成果物（`verdict-*`）に残ります。

`publish_tag` に既存のタグを入れると、PR を一切見ずにそのタグを publish するだけの
実行になります（下の「タグを指定して publish する」）。

### 自動では入らないもの

- **`package.json` / `pnpm-lock.yaml` / `.github/workflows/*.yml` 以外を触る PR。**
  評決が MERGE でも取り込みません。モデルの読み間違いに委ねてよい判断ではないので、
  ワークフローが機械的に見ています。author は Dependabot なので攻撃の兆候というより
  前提が変わった合図です。クローズせず open のまま残します。
- **公開直後（24 時間以内）のバージョンが必要になった回。** `pnpm-workspace.yaml` の
  `minimumReleaseAge` は供給網対策として置いている待ち時間なので、自動では緩めません。
  マージは済んでいるので、時間を置いて再実行すればリリースまで通ります。

GitHub Actions の更新だけがマージされた回は、バージョンを上げません。公開物
（`package.json` / `catalog.mjs` / `pnpmfile.mjs`）が変わっておらず、publish しても中身が
同じになるためです。

マージが何らかの理由で拒否された PR（ブランチ保護、必須チェックの未達など）は、
その 1 件だけ open のまま残り、他の PR とリリースは進みます。

### groups

`groups` でまとめてあるのは、揃えて更新しないと壊れるライブラリ群
（`react` と `react-dom`、`@tanstack/*` など同一バージョン系列のもの）だけです。
分野が近いだけのライブラリはまとめていません。個別に PR が来る方が、
壊れたときに原因を特定しやすいためです。

## ローカルで確認する

```bash
pnpm install   # 全ライブラリが一緒に解決できるか
pnpm test      # カタログとフックの整合性
pnpm catalog   # 現在のカタログを表として出力
```

`pnpm install` は依存のビルドスクリプトを実行しません（`pnpm-workspace.yaml` の `allowBuilds`）。
このリポジトリはバージョンの解決を確認するだけで、ビルドも実行もしないためです。

README にバージョンの一覧を転記していないのは、Dependabot の更新から取り残されて
嘘になるためです。一覧が必要なときは `pnpm catalog` を使ってください。

## npm への publish

バージョンは `package.json` の `version` です。利用側は exact version で参照するため、
カタログを更新したら version を上げて publish し直します。この上げ下ろしは上の
ワークフローがやるので、通常は手を出しません。

publish にトークンは使いません。npm の
[trusted publishing](https://docs.npmjs.com/trusted-publishers#configuring-trusted-publishing)
を使い、GitHub Actions が発行する OIDC トークンと引き換えに、その実行の間だけ有効な
資格情報を npm から受け取ります。**漏れて困る長期の資格情報がそもそも存在しません。**
CI に `NPM_TOKEN` を置く必要はなく、置いてもいけません。

### 1. 最初の 1 回だけ手で publish する

npm は **パッケージが存在しないと trusted publisher を設定できません**。
最初のバージョンだけは手元から上げてください。

```bash
git status --porcelain   # 空であること
git push                 # origin/main と同じところにいること
npm login
pnpm publish --access public
```

`pnpm publish` は publish 前に git を見ます。作業ツリーが汚れていると
`ERR_PNPM_GIT_UNCLEAN`、origin と揃っていないと `ERR_PNPM_BRANCH_IS_NOT_UP_TO_DATE` で
止まります。**`--no-git-checks` で黙らせないでください。** publish したものは
二度と差し替えられないので、「npm 上のこのバージョンは、この commit である」が
言えなくなると後から追えません。先にコミットして push します。

パッケージ名の scope（`@asuka1975`）は npm のアカウント名または organization 名と
一致している必要があります。scope を変える場合は `package.json` の `name` を変更します。
その際も `pnpm-plugin-` の部分は残してください（`pnpm test` で検査しています）。

### 2. trusted publisher を登録する

npmjs.com のパッケージ設定 → **Trusted Publisher** → **GitHub Actions** で次を入れます。

| 項目 | 値 |
| --- | --- |
| Organization or user | `asuka1975` |
| Repository | `frontend-library-catalog` |
| Workflow filename | `dependabot-review-release.yml` |
| Environment name | 空のまま |
| Allowed actions | `npm publish` |

**Workflow filename はパスではなくファイル名だけ**です。ここに登録した名前と実際に
publish するワークフローのファイル名が違うと 403 になります。
`.github/workflows/dependabot-review-release.yml` をリネームするときは、npm 側も直してください。

以降は、ワークフローがタグを push した回に publish まで自動で進みます。

### 前提

- publish ジョブに `id-token: write` が要ります（OIDC トークンの発行に必要）。
  そのジョブには書き込み権限を渡していないので、publish 以外のことはできません
- npm CLI 11.5.1 以上、Node 22.14 以上。ワークフローは Node 24 を使い、同梱の npm が
  古ければ上げてから publish します
- publish は `pnpm publish` ではなく **`npm publish`** です。npm のドキュメントが前提に
  しているのは npm CLI で、pnpm 側の OIDC 対応はバージョンによって挙動が変わってきた
  経緯があります（[pnpm#11513](https://github.com/pnpm/pnpm/issues/11513)）。
  このパッケージ自身の `package.json` は `catalog:` を使っていないため、`pnpm publish` の
  展開処理は要らず、公開物は同じものになります
- 公開リポジトリなので、provenance（どのワークフローのどのコミットから作られたか）が
  自動で付きます。`--provenance` は要りません
- **その provenance の検証が `package.json` の `repository` と突き合わせます。** 空だと
  `422 Unprocessable Entity ... "repository.url" is ""` で落ちます。認証が通った後、
  publish の瞬間に落ちるので気づきにくく、`pnpm test` で検査しています
- self-hosted ランナーからは使えません

### タグを指定して publish する

publish だけが失敗した回や、Dependabot PR に乗らない修正を出したいときは、タグを
指定してワークフローを起動します。レビューもマージもリリースも行わず、そのタグの
中身を npm に上げるだけです。provenance も付きます。

```bash
gh workflow run dependabot-review-release.yml -f publish_tag=1.0.2
```

Dependabot PR が 1 件も無くてもリリースできる経路が要るのは、publish 側の設定を
直したときに実際に困ったためです（タグは打てたが、直したものを運ぶ PR がどこにも
無い）。その場合は手でバージョンを上げてタグを打ってから、上のコマンドで publish
します。

```bash
node .claude/skills/dependabot-merge/scripts/next-version.mjs --apply
git commit -am "Bump version to <新バージョン>"
git tag <新バージョン>
git push origin main <新バージョン>
gh workflow run dependabot-review-release.yml -f publish_tag=<新バージョン>
```

**publish に失敗しても、push 済みのタグやコミットは巻き戻さないでください。**
npm に上がっていないのはその 1 バージョンだけです。npm は一度使ったバージョン番号を
再利用できませんが、**届かなかった番号は欠番にして次へ進めます。**

### 手元から publish するとき

trusted publishing は CI からしか効きません。手元から上げると provenance は付きません。
それでも構わない場合だけ、従来どおり `npm login` してから上げます。

```bash
git checkout <タグ>
npm publish --access public
```

## 利用側の設定

### 1. カタログを追加する

```bash
pnpm add --config @asuka1975/pnpm-plugin-frontend-library-catalog
```

`pnpm-workspace.yaml` に次が書き込まれます。integrity は `pnpm-lock.yaml` に入ります。

```yaml
configDependencies:
  '@asuka1975/pnpm-plugin-frontend-library-catalog': 1.0.0
```

### 2. バージョンを書かずに依存を宣言する

```json
{
  "dependencies": {
    "react": "catalog:",
    "react-dom": "catalog:",
    "@tanstack/react-query": "catalog:"
  },
  "devDependencies": {
    "vite": "catalog:",
    "vitest": "catalog:",
    "@testing-library/react": "catalog:",
    "msw": "catalog:"
  }
}
```

```bash
pnpm install
```

### 一部だけ違うバージョンを使う

利用側の `pnpm-workspace.yaml` に書いた定義が優先されます。

```yaml
catalog:
  react: 19.1.0     # これが勝つ。他はカタログの値のまま
```

## 使うときの注意

### `pnpm add <pkg>@catalog:` はカタログを複製する

このコマンドは、解決したバージョンを利用側の `pnpm-workspace.yaml` に**書き込みます**。

```yaml
# pnpm add zustand@catalog: の後
catalog:
  zustand: ^5.0.14   # カタログと同じ値がコピーされる
```

こうなると、カタログ側を更新しても利用側はコピーされた値を使い続けます。
`package.json` に `"catalog:"` と手で書いて `pnpm install` してください。
すでにコピーされている場合は、`pnpm-workspace.yaml` から該当行を消せば元に戻ります。

### publish 時に実際のバージョンへ展開される

ライブラリを npm に公開する場合、`pnpm publish` / `pnpm pack` が `catalog:` を
実際の範囲へ置き換えます。`peerDependencies` も同様です。

```json
// 手元
{ "peerDependencies": { "react": "catalog:" } }

// 公開されるもの
{ "peerDependencies": { "react": "^19.2.8" } }
```

利用側が pnpm でなくても問題ありません。

### 必要なバージョン

`updateConfig` フックは pnpm 10.8 以降です。動作確認は **pnpm 11.5.1** で行っています。

## 迷った場合の標準構成

カタログは「使ってよいバージョン」を決めるだけで、「何を使うか」は決めません。
React + Vite の業務 SPA なら、まずこれで始めます。

```json
{
  "dependencies": {
    "react": "catalog:",
    "react-dom": "catalog:",
    "react-router": "catalog:",
    "@tanstack/react-query": "catalog:"
  },
  "devDependencies": {
    "vite": "catalog:",
    "@vitejs/plugin-react": "catalog:",
    "typescript": "catalog:",
    "vitest": "catalog:",
    "@testing-library/react": "catalog:",
    "@testing-library/user-event": "catalog:",
    "msw": "catalog:",
    "@playwright/test": "catalog:"
  }
}
```

Zustand は必要になってから足します。Redux Toolkit は、プロジェクト開始時に儀式として
追加するものではありません。複雑な共有クライアント状態が実際に存在する場合に選びます。

## 管理しているライブラリ

バージョンは `pnpm catalog` で確認できます（正本は `package.json` の `devDependencies`）。

| 分野 | ライブラリ |
| --- | --- |
| React | `react` / `react-dom` / `@types/react` / `@types/react-dom` |
| ルーティング | `react-router` |
| 状態管理 | `zustand` / `@reduxjs/toolkit` / `react-redux` / `xstate` / `@xstate/react` / `immer` |
| API キャッシュ | `@tanstack/react-query` / `-devtools` / `-persist-client` / `@tanstack/query-sync-storage-persister` / `swr` |
| フォーム・検証 | `react-hook-form` / `@hookform/resolvers` / `zod` |
| スタイリング | `tailwindcss` / `@tailwindcss/vite` / `@vanilla-extract/css` / `-vite-plugin` / `-recipes` / `styled-components` / `clsx` |
| ビルド | `vite` / `@vitejs/plugin-react` / `typescript` |
| テスト | `vitest` / `@vitest/browser` / `-coverage-v8` / `-ui` / `@testing-library/react` / `-dom` / `-user-event` / `-jest-dom` / `msw` / `jsdom` / `happy-dom` |
| E2E・a11y | `@playwright/test` / `@axe-core/playwright` |
| 静的解析 | `eslint` / `typescript-eslint` / `eslint-plugin-react-hooks` / `globals` / `prettier` |
| その他 | `idb` / `date-fns` / `@types/node` |

用途の重なるライブラリ（TanStack Query と SWR、jsdom と happy-dom など）を両方載せているのは
意図的です。カタログは選択肢を並べてバージョンだけを固定するもので、使われない項目は
インストールされません。どれを選ぶかの指針はこのリポジトリの責務外です。

CSS Modules は Vite に組み込みのため、追加のライブラリはありません。
