import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { test } from 'node:test'

import { defaultCatalog } from '../catalog.mjs'
import { hooks } from '../pnpmfile.mjs'

const require = createRequire(import.meta.url)
const manifest = require('../package.json')

test('デフォルトカタログは devDependencies と一致する', () => {
  // catalog.mjs に手でバージョンを書いていないことの検査。
  // 正本は package.json の devDependencies だけにする。
  assert.deepEqual(defaultCatalog, manifest.devDependencies)
})

test('config dependency は通常の dependencies を持てない', () => {
  assert.equal(manifest.dependencies, undefined)
})

test('pnpm が pnpmfile を自動で読み込める名前になっている', () => {
  const autoLoaded =
    /^pnpm-plugin-/.test(manifest.name) ||
    /^@[^/]+\/pnpm-plugin-/.test(manifest.name) ||
    /^@pnpm\/plugin-/.test(manifest.name)
  assert.ok(autoLoaded, `${manifest.name} では pnpmfile.mjs が自動読み込みされない`)
})

test('公開物に pnpmfile.mjs と catalog.mjs が含まれる', () => {
  for (const file of ['pnpmfile.mjs', 'catalog.mjs']) {
    assert.ok(manifest.files.includes(file), `${file} が files に無い`)
  }
})

test('バージョンはすべて範囲指定として妥当な形をしている', () => {
  for (const [name, range] of Object.entries(defaultCatalog)) {
    assert.match(range, /^[\^~]?\d+\.\d+\.\d+/, `${name} のバージョン指定が不正: ${range}`)
  }
})

test('updateConfig がデフォルトカタログを流し込む', () => {
  const config = hooks.updateConfig({})

  assert.equal(config.catalogs.default.react, defaultCatalog.react)
  assert.equal(config.catalogs.default.zustand, defaultCatalog.zustand)
})

test('updateConfig は利用側の定義を優先する', () => {
  const config = hooks.updateConfig({
    catalogs: {
      default: { react: '19.1.0' },
    },
  })

  // 利用側が指定したものはそのまま残る
  assert.equal(config.catalogs.default.react, '19.1.0')

  // 指定していないものはカタログの値が入る
  assert.equal(config.catalogs.default.zustand, defaultCatalog.zustand)
})

test('updateConfig は既存の設定を壊さない', () => {
  const config = hooks.updateConfig({ minimumReleaseAge: 1440 })

  assert.equal(config.minimumReleaseAge, 1440)
})
