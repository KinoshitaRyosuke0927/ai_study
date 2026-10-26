// 単元の原稿(#%% md / #%% code で区切ったテキスト)から .ipynb を作る。
// アプリと同じ Pyodide・同じ実行補助関数(worker.ts の HELPER)で、
// - 例題セル: 単元ごとの名前空間で順に実行(受講者と同じ)し、出力を保存
// - 解答セル: 新しい名前空間で単独実行(作成者の検証と同じ)し、出力を想定出力として保存
// - テストセル: 解答と同じ名前空間で実行し、すべての assert が通ることを確認
// 使い方: node build-course.mjs <原稿フォルダ(units/ を含む)> <講座フォルダ> [ファイル名の先頭(例: 01)]
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { WORKER_TS, setupPyodide, writeMatplotlibrc } from './lib/pyodide.mjs'

const [srcDir, courseDir, only] = process.argv.slice(2)
const unitsDir = path.join(srcDir, 'units')
const WORKER = fs.readFileSync(WORKER_TS, 'utf8').replace(/\r\n/g, '\n')
const HELPER = WORKER.split('String.raw`')[1].split('`\n\nlet pyodide')[0]

// 例題・解答のコードは、原稿フォルダの data/ と講座のデータファイル(講座フォルダの data/)を読める状態で実行する
const py = await setupPyodide(
  ['pandas', 'numpy', 'scipy', 'statsmodels', 'matplotlib', 'scikit-learn', 'lightgbm'],
  path.join(srcDir, 'data'),
)
const courseData = path.join(courseDir, 'data')
if (fs.existsSync(courseData)) {
  for (const name of fs.readdirSync(courseData)) py.FS.writeFile(name, fs.readFileSync(path.join(courseData, name)))
}
py.setStdout({ batched: () => {} }) // 実行結果は補助関数が集める
// グラフは受講画面と同じ共通スタイルで描く
writeMatplotlibrc(py)
py.runPython(HELPER)
const runFn = py.globals.get('_run')
const resetFn = py.globals.get('_reset')

function run(ctx, code, test = null) {
  const proxy = runFn(ctx, code, test)
  const r = proxy.toJs({ dict_converter: Object.fromEntries })
  proxy.destroy()
  return r
}

// 原稿をセルに分ける
function parseSource(text) {
  const cells = []
  let cur = null
  for (const line of text.replace(/\r\n/g, '\n').split('\n')) {
    const m = line.match(/^#%% (md|code)\s*$/)
    if (m) {
      if (cur) cells.push(cur)
      cur = { type: m[1], lines: [] }
    } else if (cur) {
      cur.lines.push(line)
    }
  }
  if (cur) cells.push(cur)
  return cells.map((c) => ({ type: c.type, source: c.lines.join('\n').replace(/^\n+|\s+$/g, '') })).filter((c) => c.source)
}

function toLines(s) {
  const parts = s.split('\n')
  return parts.map((p, i) => (i < parts.length - 1 ? p + '\n' : p))
}

function outputsOf(r) {
  const outs = []
  if (r.output) outs.push({ name: 'stdout', output_type: 'stream', text: toLines(r.output.replace(/\n$/, '') + '\n') })
  for (const img of r.images) outs.push({ output_type: 'display_data', data: { 'image/png': img, 'text/plain': ['<Figure>'] }, metadata: {} })
  return outs
}

// セル ID はファイル名と位置から決める(作り直しても差分が出ないようにする)
const cellId = (file, i) => crypto.createHash('sha1').update(`${file}:${i}`).digest('hex').slice(0, 8)
let failures = 0

function build(file) {
  const cells = parseSource(fs.readFileSync(path.join(unitsDir, file), 'utf8'))
  const ctx = `unit-${file}`
  resetFn(ctx)
  const nbCells = []
  let exec = 0
  for (let i = 0; i < cells.length; i++) {
    const c = cells[i]
    if (c.type === 'md') {
      nbCells.push({ cell_type: 'markdown', id: cellId(file, i), metadata: {}, source: toLines(c.source) })
      continue
    }
    const first = c.source.split('\n')[0].trim()
    const cell = { cell_type: 'code', execution_count: null, id: cellId(file, i), metadata: {}, outputs: [], source: toLines(c.source) }
    if (first === '# @starter' || first === '# @test') {
      // 初期コード(空欄を含む)・テストは単独では実行しない
    } else if (first === '# @solution') {
      // 解答: 新しい名前空間で実行(直後がテストセルならテストも実行)
      const next = cells[i + 1]
      const test = next && next.type === 'code' && next.source.startsWith('# @test') ? next.source : null
      const solCtx = `sol-${file}-${i}`
      const r = run(solCtx, c.source, test)
      resetFn(solCtx)
      const title = (c.source.match(/# @title: (.*)/) || [])[1]
      const grading = (c.source.match(/# @grading: (\w+)/) || [, 'output'])[1]
      if (r.error) {
        failures++
        console.log(`  NG ${file} 解答「${title}」: ${r.error}`)
      } else if (test && r.test_passed !== true) {
        failures++
        console.log(`  NG ${file} 解答「${title}」: テスト不合格 ${r.test_message}`)
      } else if (grading === 'output' && !r.output.trim()) {
        failures++
        console.log(`  NG ${file} 解答「${title}」: 出力がありません`)
      } else {
        console.log(`  ok ${file} 解答「${title}」(${grading}) 出力 ${r.output.trim().split('\n').length} 行`)
      }
      cell.execution_count = ++exec
      cell.outputs = outputsOf({ ...r, images: [] })
    } else {
      // 例題: 単元の名前空間で順に実行
      const r = run(ctx, c.source)
      if (r.error) {
        failures++
        console.log(`  NG ${file} 例題 #${i}: ${r.error}\n${c.source.slice(0, 200)}`)
      }
      cell.execution_count = ++exec
      cell.outputs = outputsOf(r)
    }
    nbCells.push(cell)
  }
  resetFn(ctx)
  const nb = {
    cells: nbCells,
    metadata: {
      kernelspec: { display_name: 'Python 3', language: 'python', name: 'python3' },
      language_info: { name: 'python' },
    },
    nbformat: 4,
    nbformat_minor: 5,
  }
  fs.writeFileSync(path.join(courseDir, file.replace(/\.txt$/, '.ipynb')), JSON.stringify(nb, null, 1) + '\n')
}

for (const file of fs.readdirSync(unitsDir).filter((f) => f.endsWith('.txt')).sort()) {
  if (only && !file.startsWith(only)) continue
  // 単元ごとに必要なパッケージを読み込む
  await py.loadPackagesFromImports(fs.readFileSync(path.join(unitsDir, file), 'utf8'), { messageCallback: () => {} })
  console.log(`build ${file}`)
  build(file)
}
console.log(failures ? `NG: ${failures} 件` : 'all ok')
process.exit(failures ? 1 : 0)
