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
└── .github/dependabot.yml
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

## Dependabot

`.github/dependabot.yml` を置いてあります。GitHub に push すると、毎週月曜に
`package.json` を走査して更新 PR を作ります。`devDependencies` が正本なので、
届いた PR をマージすればカタログの更新になります。

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

## 公開する

npm レジストリに publish します。パッケージ名の scope（`@asuka1975`）は
npm のアカウント名または organization 名と一致している必要があります。

```bash
npm login
pnpm publish --access public
```

scope を変える場合は `package.json` の `name` を変更してください。
その際も `pnpm-plugin-` の部分は残します。

バージョンは `package.json` の `version` です。利用側は exact version で参照するため、
カタログを更新したら version を上げて publish し直します。

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
