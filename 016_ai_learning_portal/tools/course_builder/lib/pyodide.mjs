// 講座ツール共通: アプリと同じ Pyodide(314 系)を Node で用意する
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { loadPyodide } from 'pyodide'

// 016_ai_learning_portal/ (このファイルは tools/course_builder/lib/ にある)
export const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..')
// ブラウザでセルを実行する補助関数(アプリの Web Worker と同じもの)
export const WORKER_TS = path.join(APP_ROOT, 'frontend', 'src', 'python', 'worker.ts')
// 図の共通スタイル
export const FIGURE_STYLE_PY = path.join(APP_ROOT, 'backend', 'app', 'ai', 'figure_style.py')

/**
 * スクリプトが属する原稿フォルダ(sources/<講座>/)の data/ を探す
 * (figures/・checks/ の中のスクリプトなら1つ上、原稿フォルダ直下のスクリプトならその場所)
 * @param {string} scriptPath スクリプトのパス
 * @returns {string | null} data/ のパス(無ければ null)
 */
export function findDataDir(scriptPath) {
  const dir = path.dirname(path.resolve(scriptPath))
  for (const candidate of [path.join(dir, 'data'), path.join(dir, '..', 'data')]) {
    if (fs.existsSync(candidate)) return candidate
  }
  return null
}

/**
 * Pyodide を読み込み、パッケージとデータファイルを用意する
 * @param {string[]} packages 読み込むパッケージ
 * @param {string | null} dataDir 作業ディレクトリに置くデータファイルのフォルダ
 */
export async function setupPyodide(packages, dataDir = null) {
  const py = await loadPyodide()
  await py.loadPackage(packages, { messageCallback: () => {} })
  if (dataDir && fs.existsSync(dataDir)) {
    for (const name of fs.readdirSync(dataDir)) py.FS.writeFile(name, fs.readFileSync(path.join(dataDir, name)))
  }
  py.setStdout({ batched: (s) => console.log(s) })
  return py
}

/**
 * 受講画面と同じく、グラフの共通スタイル(figure_style.py の MATPLOTLIBRC)を matplotlibrc として置く
 * (補助関数 HELPER が MPLCONFIGDIR=/tmp/mplconfig を指定する)
 */
export function writeMatplotlibrc(py) {
  const ns = py.toPy({})
  py.runPython(fs.readFileSync(FIGURE_STYLE_PY, 'utf8'), { globals: ns })
  py.FS.mkdirTree('/tmp/mplconfig')
  py.FS.writeFile('/tmp/mplconfig/matplotlibrc', ns.get('MATPLOTLIBRC'))
  ns.destroy()
}

/** 作業ディレクトリに出力された拡張子 ext のファイルを outDir に保存する */
export function saveOutputs(py, ext, outDir) {
  fs.mkdirSync(outDir, { recursive: true })
  for (const name of py.FS.readdir('.')) {
    if (name.endsWith(ext)) {
      const data = py.FS.readFile(name)
      fs.writeFileSync(path.join(outDir, name), data)
      console.log(`wrote ${path.join(outDir, name)} (${data.length} bytes)`)
    }
  }
}
