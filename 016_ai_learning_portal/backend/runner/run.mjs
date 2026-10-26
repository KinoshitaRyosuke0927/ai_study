// AI が作ったコードを、受講画面と同じ Pyodide(と同じ実行補助関数)で実行する。
// バックエンド(app/ai/executor.py)から 1 回ごとに起動し、標準入力の JSON を受け取って、結果の JSON を標準出力に返す。
//
// 入力: {
//   "matplotlibrc": "グラフの共通スタイル",
//   "files": [{"name": "train.csv", "data": "base64"}],      作業ディレクトリに置くデータファイル
//   "tasks": [{"id": "...", "ctx": "unit", "code": "...", "test": "..."}]
// }
//   - 同じ ctx のタスクは変数を共有する(受講画面の単元と同じ)。単独で実行したいタスクには別の ctx を付ける
// 出力: {"results": [{"id", "output", "stderr", "error", "images", "test_passed", "test_message"}]}
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadPyodide } from 'pyodide'

const here = path.dirname(fileURLToPath(import.meta.url))

/** 受講画面の Web Worker(worker.ts)から、セルの実行補助関数(Python)を取り出す */
function loadHelper() {
  // コンテナでは runner/worker.ts にコピーされる。開発環境ではフロントエンドのソースを読む
  const candidates = [path.join(here, 'worker.ts'), path.join(here, '..', '..', 'frontend', 'src', 'python', 'worker.ts')]
  const file = candidates.find((p) => fs.existsSync(p))
  if (!file) throw new Error('worker.ts が見つかりません')
  const source = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n')
  return source.split('String.raw`')[1].split('`\n\nlet pyodide')[0]
}

const input = JSON.parse(fs.readFileSync(0, 'utf8'))
// Pyodide の読み込み中のメッセージは標準エラーに出す(標準出力は結果の JSON だけにする)
const py = await loadPyodide({ stdout: (s) => process.stderr.write(s + '\n'), stderr: (s) => process.stderr.write(s + '\n') })

// グラフの共通スタイルとデータファイルを置き、実行補助関数を定義する
py.FS.mkdirTree('/tmp/mplconfig')
py.FS.writeFile('/tmp/mplconfig/matplotlibrc', input.matplotlibrc ?? '')
for (const f of input.files ?? []) py.FS.writeFile(f.name, Buffer.from(f.data, 'base64'))
py.runPython(loadHelper())
const run = py.globals.get('_run')

const results = []
for (const task of input.tasks ?? []) {
  try {
    // import 文から必要なパッケージ(pandas など)を読み込んでから実行する
    await py.loadPackagesFromImports(`${task.code}\n${task.test ?? ''}`, { messageCallback: () => {} })
    const proxy = run(task.ctx ?? 'default', task.code, task.test ?? null)
    const r = proxy.toJs({ dict_converter: Object.fromEntries })
    proxy.destroy()
    results.push({ id: task.id, ...r })
  } catch (e) {
    // パッケージの読み込みの失敗など、実行補助関数の外で起きた失敗
    results.push({ id: task.id, output: '', stderr: '', error: String(e?.message ?? e), images: [], test_passed: null, test_message: null })
  }
}
process.stdout.write(JSON.stringify({ results }))
