import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { devDependencies } = require('./package.json')

/**
 * デフォルトカタログ。
 *
 * バージョンの正本は package.json の devDependencies です。ここでは値を持たず、
 * そのまま公開します。Dependabot / Renovate は devDependencies をそのまま解釈できるため、
 * バージョン更新は通常の npm 更新 PR として届き、このファイルの編集は不要です。
 *
 * devDependencies にしているのは、config dependency が通常の dependencies を
 * 持てない制約に従いつつ、このリポジトリで `pnpm install` したときに
 * 全ライブラリの組み合わせが実際に解決できるかを検証するためです。
 * devDependencies は利用側にインストールされません。
 *
 * ここに手でバージョンを書かないでください（`pnpm test` で検査しています）。
 * 同じライブラリで 2 系統のバージョンを配る必要が出たときだけ、名前付きカタログ
 * （pnpm の catalogs）をこのファイルに追加し、pnpmfile.mjs から流し込みます。
 */
export const defaultCatalog = { ...devDependencies }
