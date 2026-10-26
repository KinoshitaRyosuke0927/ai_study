// メインスレッドと Pyodide Worker の間でやり取りするメッセージの型

export interface RunResult {
  output: string // 標準出力 + 最後の式の値(採点対象)
  stderr: string // 警告など(採点対象外)
  error: string | null // 例外が発生した場合のメッセージ
  images: string[] // matplotlib のグラフ(PNG, base64)
  files: { name: string; size: number }[] // セルの実行で作成・更新された作業ディレクトリのファイル
  test_passed: boolean | null // テストコード採点の結果(テストなしは null)
  test_message: string | null
}

export type WorkerRequest =
  | { id: number; type: 'init'; baseUrl: string; matplotlibrc: string }
  | { id: number; type: 'files'; files: { name: string; data: ArrayBuffer }[] }
  | { id: number; type: 'read'; name: string }
  | { id: number; type: 'reset'; ctx: string }
  | { id: number; type: 'run'; ctx: string; code: string; test?: string }

export type WorkerResponse =
  | { id: number; type: 'done' }
  | { id: number; type: 'installing' }
  | { id: number; type: 'result'; result: RunResult }
  | { id: number; type: 'file'; data: ArrayBuffer }
  | { id: number; type: 'fatal'; message: string }
