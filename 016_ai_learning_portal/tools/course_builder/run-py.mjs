// Python スクリプトを Pyodide で実行する(原稿フォルダの data/ を作業ディレクトリに置く)。
// 問題に使う数値の確認や、データファイルの作成に使う。--save-csv を付けると、出力された CSV を原稿フォルダの data/ に保存する
// 使い方: node run-py.mjs <スクリプト> [--save-csv]
import fs from 'node:fs'
import path from 'node:path'
import { findDataDir, saveOutputs, setupPyodide } from './lib/pyodide.mjs'

const [script, flag] = process.argv.slice(2)
const save = flag === '--save-csv'
const py = await setupPyodide(['numpy', 'pandas', 'scipy', 'statsmodels', 'scikit-learn', 'lightgbm', 'matplotlib'], save ? null : findDataDir(script))
py.runPython(fs.readFileSync(script, 'utf8'))
// データファイルの作成スクリプト(原稿フォルダ直下にある)は、原稿フォルダの data/ に保存する
if (save) saveOutputs(py, '.csv', path.join(path.dirname(path.resolve(script)), 'data'))
