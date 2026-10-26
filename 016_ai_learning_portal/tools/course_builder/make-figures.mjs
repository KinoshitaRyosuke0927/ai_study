// 図を作るスクリプトを、共通スタイル(backend/app/ai/figure_style.py の FIGURE_STYLE_CODE)を適用した Pyodide で実行し、
// 出力された PNG を講座フォルダの images/ に保存する(データは原稿フォルダの data/ から読める)
// 使い方: node make-figures.mjs <図のスクリプト> <講座フォルダ>
import fs from 'node:fs'
import path from 'node:path'
import { FIGURE_STYLE_PY, findDataDir, saveOutputs, setupPyodide } from './lib/pyodide.mjs'

const [script, courseDir] = process.argv.slice(2)
const py = await setupPyodide(['numpy', 'pandas', 'scipy', 'matplotlib'], findDataDir(script))
// 共通スタイルを適用してから、図のスクリプトを同じ名前空間で実行する
const ns = py.toPy({})
py.runPython(fs.readFileSync(FIGURE_STYLE_PY, 'utf8'), { globals: ns })
py.runPython(ns.get('FIGURE_STYLE_CODE'), { globals: ns })
py.runPython(fs.readFileSync(script, 'utf8'), { globals: ns })
saveOutputs(py, '.png', path.join(courseDir, 'images'))
