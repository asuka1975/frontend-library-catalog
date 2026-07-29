import { defaultCatalog } from './catalog.mjs'

/**
 * このファイルは、利用側が config dependency としてこのパッケージを入れると
 * pnpm が自動で読み込みます（パッケージ名が `@<scope>/pnpm-plugin-*` のため）。
 *
 * updateConfig で pnpm の設定オブジェクトにカタログを流し込むことで、
 * 利用側は `"react": "catalog:"` と書くだけでバージョンが揃います。
 */
export const hooks = {
  updateConfig(config) {
    config.catalogs ??= {}

    // 利用側の pnpm-workspace.yaml に同名の定義があればそちらを優先する。
    // カタログ全体を拒否せず、必要な 1 つだけ差し替えられるようにするため。
    config.catalogs.default = {
      ...defaultCatalog,
      ...(config.catalogs.default ?? {}),
    }

    return config
  },
}
