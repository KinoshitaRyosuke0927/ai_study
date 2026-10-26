// 講座フォルダの .ipynb から、コードセルのテキスト出力を一覧表示する(内容確認用)
// 使い方: node dump-outputs.mjs <講座フォルダ> [ファイル名の先頭]
import fs from 'node:fs'
import path from 'node:path'

const [dir, only] = process.argv.slice(2)
for (const file of fs.readdirSync(dir).filter((f) => f.endsWith('.ipynb')).sort()) {
  if (only && !file.startsWith(only)) continue
  const nb = JSON.parse(fs.readFileSync(path.join(dir, file), 'utf8'))
  console.log(`===== ${file}`)
  for (const c of nb.cells) {
    if (c.cell_type !== 'code') continue
    const src = c.source.join('')
    const label = src.startsWith('# @solution') ? `[解答] ${(src.match(/# @title: (.*)/) || [])[1]}` : src.startsWith('# @') ? null : `[例題] ${src.split('\n')[0]}`
    if (!label) continue
    const text = c.outputs.filter((o) => o.output_type === 'stream').map((o) => o.text.join('')).join('')
    const imgs = c.outputs.filter((o) => o.output_type === 'display_data').length
    console.log(`--- ${label}${imgs ? ` (図 ${imgs})` : ''}`)
    if (text) console.log(text.trimEnd())
  }
}
