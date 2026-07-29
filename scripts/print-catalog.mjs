import { defaultCatalog } from '../catalog.mjs'

/**
 * 現在のカタログを Markdown の表として出力します。
 * README にバージョンを転記すると Dependabot の更新から取り残されるため、
 * 一覧が必要なときはこれを実行します。
 *
 *   pnpm catalog
 */

const entries = Object.entries(defaultCatalog).sort(([a], [b]) => a.localeCompare(b))

console.log(`## デフォルトカタログ（${entries.length} 件）\n`)
console.log('| ライブラリ | バージョン |')
console.log('| --- | --- |')
for (const [name, range] of entries) {
  console.log(`| \`${name}\` | \`${range}\` |`)
}
