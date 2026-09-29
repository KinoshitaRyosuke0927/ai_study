// Pyodide(ブラウザ内 Python)を動かす Web Worker(モジュール Worker)。
// 画面(メインスレッド)を固めずに Python を実行し、無限ループ時は Worker ごと停止できるようにする。
// Pyodide 314 系はクラシック Worker に対応していないため、pyodide.mjs を動的 import する。

/* eslint-disable @typescript-eslint/no-explicit-any */

import type { RunResult, WorkerRequest, WorkerResponse } from './protocol'

// セルの実行・後処理を行う Python 側の補助関数
const HELPER = String.raw`
import ast, base64, io, os, sys, traceback, warnings

# グラフは画像として取り出すため、画面を持たない描画方式にする
os.environ["MPLBACKEND"] = "Agg"
warnings.filterwarnings("ignore", message=".*non-interactive.*")

# 実行コンテキスト(単元)ごとの名前空間。同じ単元のセルは変数を共有する
_NS = {}


def _ns(ctx):
    ns = _NS.get(ctx)
    if ns is None:
        ns = {"__name__": "__main__"}
        _NS[ctx] = ns
    return ns


def _reset(ctx):
    _NS.pop(ctx, None)
    if "matplotlib.pyplot" in sys.modules:
        sys.modules["matplotlib.pyplot"].close("all")


def _format_error(e, filename):
    # 利用者のコード内で最後にエラーが起きた行番号を探す
    lineno = None
    tb = e.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == filename:
            lineno = tb.tb_lineno
        tb = tb.tb_next
    message = "".join(traceback.format_exception_only(type(e), e)).strip()
    if lineno is not None and not isinstance(e, SyntaxError):
        return f"{message}\n(セルの {lineno} 行目)"
    return message


def _exec(src, ns):
    # Jupyter と同じく、最後の行が式ならその値を表示する(末尾が ; なら表示しない)
    tree = ast.parse(src, "<cell>", "exec")
    last = None
    if tree.body and isinstance(tree.body[-1], ast.Expr) and not src.rstrip().endswith(";"):
        last = ast.Expression(tree.body.pop().value)
    exec(compile(tree, "<cell>", "exec"), ns)
    if last is not None:
        value = eval(compile(last, "<cell>", "eval"), ns)
        if value is not None:
            print(repr(value))


def _figures():
    # 描画されたグラフを PNG(base64)で取り出して閉じる
    if "matplotlib.pyplot" not in sys.modules:
        return []
    plt = sys.modules["matplotlib.pyplot"]
    images = []
    for num in plt.get_fignums():
        buf = io.BytesIO()
        # Pyodide 版 matplotlib が保存時に出す内部の非推奨警告は利用者に関係ないため抑止する
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            plt.figure(num).savefig(buf, format="png", bbox_inches="tight", dpi=100)
        images.append(base64.b64encode(buf.getvalue()).decode())
    plt.close("all")
    return images


def _run(ctx, src, test_src):
    ns = _ns(ctx)
    out, err = io.StringIO(), io.StringIO()
    saved = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out, err
    error = None
    test_passed = None
    test_message = None
    try:
        try:
            _exec(src, ns)
        except BaseException as e:
            error = _format_error(e, "<cell>")
        # テストコード採点の問題は、同じ名前空間でテストを実行する
        if error is None and test_src:
            try:
                exec(compile(test_src, "<test>", "exec"), ns)
                test_passed = True
            except AssertionError as e:
                test_passed = False
                test_message = str(e) or "テストの条件を満たしていません"
            except BaseException as e:
                test_passed = False
                test_message = _format_error(e, "<test>")
    finally:
        sys.stdout, sys.stderr = saved
    try:
        images = _figures()
    except Exception as e:
        images = []
        err.write(f"グラフの取り出しに失敗しました: {e}\n")
    return {
        "output": out.getvalue(),
        "stderr": err.getvalue(),
        "error": error,
        "images": images,
        "test_passed": test_passed,
        "test_message": test_message,
    }
`

let pyodide: any = null

function post(message: WorkerResponse) {
  ;(self as unknown as Worker).postMessage(message)
}

async function handle(req: WorkerRequest): Promise<void> {
  switch (req.type) {
    case 'init': {
      // Pyodide 本体を読み込み、補助関数を定義する(配信元は設定で差し替えられるため実行時に決める)
      const mod = await import(/* @vite-ignore */ `${req.baseUrl}pyodide.mjs`)
      pyodide = await mod.loadPyodide({ indexURL: req.baseUrl })
      pyodide.runPython(HELPER)
      post({ id: req.id, type: 'done' })
      return
    }
    case 'files': {
      // データファイルを作業ディレクトリに書き込む(pd.read_csv("scores.csv") で読めるようにする)
      for (const file of req.files) {
        pyodide.FS.writeFile(file.name, new Uint8Array(file.data))
      }
      post({ id: req.id, type: 'done' })
      return
    }
    case 'reset': {
      const reset = pyodide.globals.get('_reset')
      reset(req.ctx)
      reset.destroy()
      post({ id: req.id, type: 'done' })
      return
    }
    case 'run': {
      // import 文から必要なパッケージ(pandas など)を読み込む
      await pyodide.loadPackagesFromImports(`${req.code}\n${req.test ?? ''}`, {
        messageCallback: () => post({ id: req.id, type: 'installing' }),
        errorCallback: () => undefined,
      })
      const run = pyodide.globals.get('_run')
      const proxy = run(req.ctx, req.code, req.test ?? null)
      const result = proxy.toJs({ dict_converter: Object.fromEntries }) as RunResult
      proxy.destroy()
      run.destroy()
      post({ id: req.id, type: 'result', result })
      return
    }
  }
}

self.onmessage = (event: MessageEvent<WorkerRequest>) => {
  handle(event.data).catch((err: unknown) => {
    post({ id: event.data.id, type: 'fatal', message: err instanceof Error ? err.message : String(err) })
  })
}
