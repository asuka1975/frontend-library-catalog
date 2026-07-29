#!/usr/bin/env node
// 次のパッチバージョンを決定する。
//
// package.json の version を読み、パッチを +1 した値と対応するタグ名を出す。
// --apply を付けると package.json を書き換える。
//
// 判断の余地はないので、この計算を手でやらないこと。npm は一度 publish した
// バージョンを二度と使えない(unpublish しても再利用不可)ため、重複の
// 取りこぼしは publish まで進んでから発覚して高くつく。
//
// usage:
//   next-version.mjs            現在値・次の値・タグ名を表示(何も書き換えない)
//   next-version.mjs --apply    package.json を書き換える
//
// exit code:
//   0  正常
//   1  version が X.Y.Z でない / タグが既に存在する / npm に publish 済み
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const apply = process.argv.includes('--apply')

function run(cmd, args, cwd) {
  try {
    return execFileSync(cmd, args, {
      encoding: 'utf8',
      cwd,
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
  } catch {
    return null
  }
}

function fail(msg) {
  console.error(`ERROR: ${msg}`)
  process.exit(1)
}

const root = run('git', ['rev-parse', '--show-toplevel'])
if (!root) fail('git リポジトリの中で実行してください')

const pkgPath = path.join(root, 'package.json')
const text = readFileSync(pkgPath, 'utf8')
const pkg = JSON.parse(text)
const current = pkg.version

if (!/^\d+\.\d+\.\d+$/.test(current)) {
  fail(
    `version=${current} は X.Y.Z 形式ではありません。` +
      ' 勝手に直さず報告してください。'
  )
}

const [major, minor, patch] = current.split('.').map(Number)
const next = `${major}.${minor}.${patch + 1}`
const tag = next // タグ名は version と同一(v は付けない)

const localTag = run('git', ['tag', '--list', tag], root)
const remoteTag = run('git', ['ls-remote', '--tags', 'origin', tag], root)
if (localTag || remoteTag) {
  fail(
    `タグ ${tag} は既に存在します(local=${!!localTag} remote=${!!remoteTag})。` +
      ' 公開済みタグは動かさず、止めて報告してください。'
  )
}

// npm 側の重複。存在しなければ npm view は非ゼロ終了するので null になる。
const published = run('npm', ['view', `${pkg.name}@${next}`, 'version'], root)
if (published) {
  fail(
    `${pkg.name}@${next} は npm に publish 済みです。` +
      ' version の巻き戻しを疑ってください。'
  )
}

if (apply) {
  // JSON.stringify で再整形せず、version の行だけ書き換える
  writeFileSync(pkgPath, text.replace(/("version":\s*")[^"]+(")/, `$1${next}$2`))
  console.log(`applied: ${pkgPath} version=${next}`)
}

console.log(`current=${current}`)
console.log(`next=${next}`)
console.log(`tag=${tag}`)
